import csv
import hashlib
import io
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

from app.core.auth import authenticate_user, create_token, get_current_user, hash_password, require_roles, seed_users
from app.core.config import settings
from app.core.schemas import ExperimentCreate, OrganizationCreate, OrganizationUpdate, SchedulerRun, UserCreate, UserUpdate
from app.db.base import Base
from app.db.models import Experiment, Job, Organization, User, Worker
from app.db.session import SessionLocal, engine
from app.services.runner import run_workload
from app.services.reference_analysis import analyze_race_reference
from app.services.scheduler import base_workers, build_demo_experiments, choose_jobs, make_config_hash, resource_pressure_summary, schedule_policy_comparison


def ensure_database() -> None:
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    with engine.begin() as connection:
        legacy_columns = {
            'users': {'organization_id': 'VARCHAR'},
            'experiments': {'organization_id': 'VARCHAR'},
            'workers': {'organization_id': 'VARCHAR'},
            'jobs': {'worker_id': 'VARCHAR'},
        }
        for table, columns in legacy_columns.items():
            if table not in inspector.get_table_names():
                continue
            existing = {column['name'] for column in inspector.get_columns(table)}
            for column_name, column_type in columns.items():
                if column_name not in existing:
                    connection.execute(text(f'ALTER TABLE {table} ADD COLUMN {column_name} {column_type}'))

    db = SessionLocal()
    try:
        if db.get(Organization, 'prontos-demo') is None:
            db.add(Organization(
                id='prontos-demo',
                name='PRONTOS Demo',
                cpu_quota=16,
                memory_quota=12,
                budget_quota=1000,
                created_at=datetime.utcnow(),
            ))
            db.flush()
        for model in (User, Experiment, Worker):
            db.query(model).filter(model.organization_id.is_(None)).update(
                {model.organization_id: 'prontos-demo'},
                synchronize_session=False,
            )
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        seed_users(db)
        seed_demo_data(db, 'prontos-demo')
        for worker in db.query(Worker).all():
            supported = list(worker.supported_workloads or [])
            if (
                'Synthetic vehicle or engineering simulation' in supported
                and 'Race strategy simulation' not in supported
            ):
                worker.supported_workloads = [*supported, 'Race strategy simulation']
        db.commit()
    finally:
        db.close()


app = FastAPI(title='PRONTOS API', version='0.1.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_methods=['*'],
    allow_headers=['*'],
)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_demo_data(db: Session, organization_id: str) -> None:
    if db.query(Experiment).filter(Experiment.organization_id == organization_id).count() > 0:
        return

    worker_id_map = {
        worker['id']: f'{organization_id}-{worker["id"]}' if organization_id != 'prontos-demo' else worker['id']
        for worker in base_workers()
    }
    for worker in base_workers():
        db.merge(Worker(**{
            **worker,
            'id': worker_id_map[worker['id']],
            'organization_id': organization_id,
        }))

    demo_experiments = build_demo_experiments()
    experiment_id_map = {
        exp['id']: f'{organization_id}-{exp["id"]}' if organization_id != 'prontos-demo' else exp['id']
        for exp in demo_experiments
    }
    for exp in demo_experiments:
        db.merge(Experiment(**{
            'id': experiment_id_map[exp['id']],
            'organization_id': organization_id,
            'name': exp['name'],
            'description': exp['description'],
            'category': exp['category'],
            'parameters': exp['parameters'],
            'estimated_runtime': float(exp['estimated_runtime']),
            'cpu': float(exp['cpu']),
            'memory': float(exp['memory']),
            'priority': int(exp['priority']),
            'deadline': exp.get('deadline'),
            'budget': float(exp['budget']),
            'dependencies': [experiment_id_map[dependency] for dependency in exp.get('dependencies', [])],
            'dataset_ref': exp.get('dataset_ref', 'demo-v1'),
            'config_hash': exp.get('config_hash', ''),
            'status': exp.get('status', 'ready'),
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
        }))
    db.commit()


ensure_database()


def serialise_experiment(exp: Experiment) -> dict[str, Any]:
    return {
        'id': exp.id,
        'name': exp.name,
        'description': exp.description,
        'category': exp.category,
        'parameters': exp.parameters,
        'cpu': exp.cpu,
        'memory': exp.memory,
        'priority': exp.priority,
        'estimated_runtime': exp.estimated_runtime,
        'budget': exp.budget,
        'status': exp.status,
        'dependencies': exp.dependencies,
        'deadline': exp.deadline,
        'created_at': exp.created_at.isoformat(),
        'config_hash': exp.config_hash,
        'dataset_ref': exp.dataset_ref,
    }


def build_state_map(db: Session, organization_id: str) -> dict[str, str]:
    state: dict[str, str] = {}
    experiments = db.query(Experiment).filter(Experiment.organization_id == organization_id).all()
    for exp in experiments:
        state[exp.id] = exp.status
    experiment_ids = [exp.id for exp in experiments]
    for job in db.query(Job).filter(Job.experiment_id.in_(experiment_ids)).all():
        if job.status in {'queued', 'running'}:
            state[job.experiment_id] = job.status
        elif job.status == 'completed':
            state[job.experiment_id] = 'completed'
        elif job.status == 'failed':
            state[job.experiment_id] = 'failed'
    return state


def fit_jobs_to_workers(
    selected: list[dict[str, Any]],
    experiments: list[Experiment],
    workers: list[Worker],
    active_jobs: list[Job],
) -> tuple[list[dict[str, Any]], list[str]]:
    experiment_map = {experiment.id: experiment for experiment in experiments}
    active_allocations: dict[str, dict[str, float]] = {}
    for job in active_jobs:
        if job.worker_id:
            allocated = active_allocations.setdefault(job.worker_id, {'cpu': 0.0, 'memory': 0.0})
            allocated['cpu'] += job.cpu
            allocated['memory'] += job.memory
    available = {
        worker.id: {
            'cpu': max(
                0.0,
                worker.cpu_capacity - max(
                    float((worker.current_allocations or {}).get('cpu', 0)),
                    active_allocations.get(worker.id, {}).get('cpu', 0.0),
                ),
            ),
            'memory': max(
                0.0,
                worker.memory_capacity - max(
                    float((worker.current_allocations or {}).get('memory', 0)),
                    active_allocations.get(worker.id, {}).get('memory', 0.0),
                ),
            ),
        }
        for worker in workers
        if worker.status == 'online'
    }
    workers_by_id = {worker.id: worker for worker in workers}

    scheduled: list[dict[str, Any]] = []
    deferred: list[str] = []
    for item in selected:
        experiment = experiment_map[item['id']]
        candidates = []
        for worker_id, capacity in available.items():
            worker = workers_by_id[worker_id]
            supported = worker.supported_workloads or []
            if experiment.category not in supported:
                continue
            if experiment.cpu > capacity['cpu'] or experiment.memory > capacity['memory']:
                continue
            remaining_cpu = capacity['cpu'] - experiment.cpu
            remaining_memory = capacity['memory'] - experiment.memory
            waste = remaining_cpu / max(worker.cpu_capacity, 1.0) + remaining_memory / max(worker.memory_capacity, 1.0)
            candidates.append((waste, worker_id))

        if not candidates:
            deferred.append(item['id'])
            continue

        _, worker_id = min(candidates)
        available[worker_id]['cpu'] -= experiment.cpu
        available[worker_id]['memory'] -= experiment.memory
        scheduled.append({**item, 'worker_id': worker_id})

    return scheduled, deferred


def summarize_worker_capacity(workers: list[Worker], jobs: list[Job]) -> dict[str, Any]:
    active_allocations: dict[str, dict[str, float]] = {}
    for job in jobs:
        if job.status not in {'queued', 'running'} or not job.worker_id:
            continue
        allocated = active_allocations.setdefault(job.worker_id, {'cpu': 0.0, 'memory': 0.0})
        allocated['cpu'] += job.cpu
        allocated['memory'] += job.memory

    cpu_allocated = 0.0
    memory_allocated = 0.0
    for worker in workers:
        stored = worker.current_allocations or {}
        active = active_allocations.get(worker.id, {})
        cpu_allocated += max(float(stored.get('cpu', 0)), active.get('cpu', 0.0))
        memory_allocated += max(float(stored.get('memory', 0)), active.get('memory', 0.0))

    return {
        'cpu_total': round(sum(worker.cpu_capacity for worker in workers), 2),
        'memory_total': round(sum(worker.memory_capacity for worker in workers), 2),
        'cpu_allocated': round(cpu_allocated, 2),
        'memory_allocated': round(memory_allocated, 2),
        'worker_count': len(workers),
        'online_workers': sum(1 for worker in workers if worker.status == 'online'),
    }


def deterministic_seed(identifier: str) -> int:
    return int.from_bytes(hashlib.sha256(identifier.encode('utf-8')).digest()[:4], 'big')


def serialize_user(user: User) -> dict[str, Any]:
    return {
        'id': user.id,
        'organization_id': user.organization_id,
        'email': user.email,
        'username': user.username,
        'role': user.role,
        'is_active': user.is_active,
        'created_at': user.created_at.isoformat(),
    }


@app.get('/api/health')
def health() -> dict:
    return {'status': 'ok', 'service': 'prontos-api'}


@app.get('/api/reference/bahrain-2024')
def get_bahrain_reference(
    current_user: dict[str, str] = Depends(require_roles('viewer', 'operator', 'admin', 'platform_admin')),
) -> dict[str, Any]:
    reference_path = Path(__file__).resolve().parents[1] / 'data' / 'reference' / '2024_Bahrain_VER_laps.csv'
    if not reference_path.is_file():
        raise HTTPException(status_code=503, detail='Bundled Bahrain reference sample is unavailable')
    try:
        with reference_path.open(newline='', encoding='utf-8-sig') as input_file:
            rows = list(csv.DictReader(input_file))
        report = analyze_race_reference(
            rows,
            pit_loss_scenarios=[18, 22, 26],
            tire_wear_scenarios=[0.03, 0.06, 0.09, 0.12],
        )
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=f'Unable to analyze bundled Bahrain reference data: {exc}') from exc
    report['reference']['event_name'] = '2024 Bahrain Grand Prix'
    report['reference']['driver_name'] = 'Max Verstappen'
    report['reference']['data_source'] = 'OpenF1 historical API sample'
    return report


@app.post('/api/auth/login')
def login(payload: dict, db: Session = Depends(get_db)) -> dict:
    email = str(payload.get('email') or '').strip().lower()
    password = str(payload.get('password') or '')
    if not email or not password:
        raise HTTPException(status_code=400, detail='Email and password are required')
    user = authenticate_user(db, email, password)
    token = create_token(user)
    return {
        'token': token,
        'user': {
            'email': user.email,
            'username': user.username,
            'role': user.role,
            'organization_id': user.organization_id,
        },
    }


@app.get('/api/auth/me')
def me(current_user: dict[str, str] = Depends(get_current_user)) -> dict:
    return current_user


@app.get('/api/organization')
def get_organization(
    db: Session = Depends(get_db),
    current_user: dict[str, str] = Depends(require_roles('viewer', 'operator', 'admin', 'platform_admin')),
) -> dict:
    organization = db.query(Organization).filter(
        Organization.id == current_user['organization_id']
    ).one()
    return {
        'id': organization.id,
        'name': organization.name,
        'cpu_quota': organization.cpu_quota,
        'memory_quota': organization.memory_quota,
        'budget_quota': organization.budget_quota,
    }


@app.post('/api/admin/organizations', status_code=201)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    current_user: dict[str, str] = Depends(require_roles('platform_admin')),
) -> dict:
    owner_email = payload.owner_email.strip().lower()
    owner_username = payload.owner_username.strip()
    if db.query(User).filter(
        (User.email == owner_email) | (User.username == owner_username)
    ).first():
        raise HTTPException(status_code=409, detail='Owner email or username is already registered')

    organization_id = f'org-{uuid4().hex}'
    organization = Organization(
        id=organization_id,
        name=payload.name.strip(),
        cpu_quota=payload.cpu_quota,
        memory_quota=payload.memory_quota,
        budget_quota=payload.budget_quota,
    )
    db.add(organization)

    default_workers = base_workers()
    cpu_scale = min(1.0, payload.cpu_quota / sum(worker['cpu_capacity'] for worker in default_workers))
    memory_scale = min(
        1.0,
        payload.memory_quota / sum(worker['memory_capacity'] for worker in default_workers),
    )
    for worker in default_workers:
        db.add(Worker(
            **{
                **worker,
                'id': f'{organization_id}-{worker["id"]}',
                'organization_id': organization_id,
                'cpu_capacity': worker['cpu_capacity'] * cpu_scale,
                'memory_capacity': worker['memory_capacity'] * memory_scale,
            }
        ))

    owner = User(
        id=f'user-{uuid4().hex}',
        organization_id=organization_id,
        email=owner_email,
        username=owner_username,
        password_hash=hash_password(payload.owner_password),
        role='admin',
        is_active=True,
    )
    db.add(owner)
    db.commit()
    return {
        'organization': {
            'id': organization.id,
            'name': organization.name,
            'cpu_quota': organization.cpu_quota,
            'memory_quota': organization.memory_quota,
            'budget_quota': organization.budget_quota,
        },
        'owner': {'email': owner.email, 'username': owner.username, 'role': owner.role},
    }


@app.get('/api/admin/organizations')
def list_organizations(
    db: Session = Depends(get_db),
    current_user: dict[str, str] = Depends(require_roles('platform_admin')),
) -> list[dict[str, Any]]:
    organizations = db.query(Organization).order_by(Organization.name).all()
    return [{
        'id': organization.id,
        'name': organization.name,
        'cpu_quota': organization.cpu_quota,
        'memory_quota': organization.memory_quota,
        'budget_quota': organization.budget_quota,
        'user_count': db.query(User).filter(User.organization_id == organization.id).count(),
        'experiment_count': db.query(Experiment).filter(Experiment.organization_id == organization.id).count(),
    } for organization in organizations]


@app.patch('/api/admin/organization')
def update_organization_quotas(
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
    current_user: dict[str, str] = Depends(require_roles('admin', 'platform_admin')),
) -> dict:
    organization = db.query(Organization).filter(
        Organization.id == current_user['organization_id']
    ).one()
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(organization, field, value)

    workers = db.query(Worker).filter(
        Worker.organization_id == organization.id,
        Worker.status == 'online',
    ).all()
    if sum(worker.cpu_capacity for worker in workers) > organization.cpu_quota:
        raise HTTPException(status_code=409, detail='CPU quota cannot be below online worker capacity')
    if sum(worker.memory_capacity for worker in workers) > organization.memory_quota:
        raise HTTPException(status_code=409, detail='Memory quota cannot be below online worker capacity')
    reserved_budget = sum(
        float(row[0])
        for row in db.query(Experiment.budget).filter(
            Experiment.organization_id == organization.id
        ).all()
    )
    if reserved_budget > organization.budget_quota:
        raise HTTPException(status_code=409, detail='Budget quota cannot be below committed experiment budgets')

    db.commit()
    return {
        'id': organization.id,
        'name': organization.name,
        'cpu_quota': organization.cpu_quota,
        'memory_quota': organization.memory_quota,
        'budget_quota': organization.budget_quota,
    }


@app.get('/api/admin/users')
def list_users(
    db: Session = Depends(get_db),
    current_user: dict[str, str] = Depends(require_roles('admin', 'platform_admin')),
) -> list[dict[str, Any]]:
    users = db.query(User).filter(
        User.organization_id == current_user['organization_id']
    ).order_by(User.username).all()
    return [serialize_user(user) for user in users]


@app.post('/api/admin/users', status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: dict[str, str] = Depends(require_roles('admin', 'platform_admin')),
) -> dict:
    email = payload.email.strip().lower()
    username = payload.username.strip()
    if db.query(User).filter((User.email == email) | (User.username == username)).first():
        raise HTTPException(status_code=409, detail='Email or username is already registered')
    user = User(
        id=f'user-{uuid4().hex}',
        organization_id=current_user['organization_id'],
        email=email,
        username=username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return serialize_user(user)


@app.patch('/api/admin/users/{user_id}')
def update_user(
    user_id: str,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: dict[str, str] = Depends(require_roles('admin', 'platform_admin')),
) -> dict:
    user = db.query(User).filter(
        User.id == user_id,
        User.organization_id == current_user['organization_id'],
    ).first()
    if user is None:
        raise HTTPException(status_code=404, detail='User not found')
    updates = payload.model_dump(exclude_unset=True)
    if user.role == 'platform_admin' and current_user['role'] != 'platform_admin':
        raise HTTPException(status_code=403, detail='Only a platform administrator can manage this account')
    if user.email == current_user['email'] and updates.get('is_active') is False:
        raise HTTPException(status_code=400, detail='You cannot deactivate your own account')
    if user.email == current_user['email'] and updates.get('role') not in (None, 'admin'):
        raise HTTPException(status_code=400, detail='You cannot remove your own administrator role')
    if user.email == current_user['email'] and user.role == 'platform_admin' and 'role' in updates:
        raise HTTPException(status_code=400, detail='You cannot change your platform administrator role')
    if user.role == 'admin' and user.is_active and (
        updates.get('role') not in (None, 'admin') or updates.get('is_active') is False
    ):
        other_admins = db.query(User).filter(
            User.organization_id == user.organization_id,
            User.role == 'admin',
            User.is_active.is_(True),
            User.id != user.id,
        ).count()
        if other_admins == 0:
            raise HTTPException(status_code=409, detail='The organization must retain an active administrator')

    if 'password' in updates:
        user.password_hash = hash_password(updates.pop('password'))
    for field, value in updates.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return serialize_user(user)


@app.get('/api/dashboard')
def dashboard(
    db: Session = Depends(get_db),
    current_user: dict[str, str] = Depends(require_roles('viewer', 'operator', 'admin', 'platform_admin')),
) -> dict:
    organization_id = current_user['organization_id']
    experiments = db.query(Experiment).filter(
        Experiment.organization_id == organization_id
    ).order_by(Experiment.name).all()
    experiment_ids = [exp.id for exp in experiments]
    jobs = db.query(Job).filter(Job.experiment_id.in_(experiment_ids)).all()
    workers = db.query(Worker).filter(Worker.organization_id == organization_id).all()
    organization = db.query(Organization).filter(Organization.id == organization_id).one()
    state = build_state_map(db, organization_id)
    experiment_rows = [serialise_experiment(exp) for exp in experiments]

    summary = {
        'completed_jobs': sum(1 for job in jobs if job.status == 'completed'),
        'active_jobs': sum(1 for job in jobs if job.status in {'queued', 'running'}),
        'failed_jobs': sum(1 for job in jobs if job.status == 'failed'),
        'avg_runtime': round(sum((job.duration or 0.0) for job in jobs) / max(1, len(jobs)), 2),
        'budget_usage': round(
            min(100.0, sum(exp.budget for exp in experiments) / organization.budget_quota * 100),
            2,
        ) if organization.budget_quota else 0.0,
    }

    comparison = schedule_policy_comparison(experiment_rows, state)
    analytics = resource_pressure_summary(
        experiment_rows,
        state,
        [
            {
                'cpu_capacity': worker.cpu_capacity,
                'memory_capacity': worker.memory_capacity,
            }
            for worker in workers
            if worker.status == 'online'
        ],
    )
    worker_capacity = summarize_worker_capacity(workers, jobs)
    experiment_names = {experiment.id: experiment.name for experiment in experiments}
    timeline = []
    recent_jobs = sorted(
        jobs,
        key=lambda job: job.completed_at or job.started_at or job.queued_at or datetime.min,
        reverse=True,
    )[:10]
    for job in recent_jobs:
        metadata = job.scheduler_metadata or {}
        policy = metadata.get('policy', 'manual')
        experiment_name = experiment_names.get(job.experiment_id, job.experiment_id)
        worker_name = next(
            (worker.name for worker in workers if worker.id == job.worker_id),
            'unassigned worker',
        )
        if job.status == 'failed':
            reason = f'{experiment_name} failed on {worker_name}. {job.error or "No error details available."}'
        elif job.status == 'completed':
            reason = f'{experiment_name} completed on {worker_name} in {job.duration or 0:.2f}h.'
        else:
            reason = f'{experiment_name} is {job.status} on {worker_name} ({job.progress:.0f}% complete).'
        timeline.append({
            'id': job.id,
            'policy': policy,
            'status': job.status,
            'reason': reason,
            'result': (
                job.output_artifacts
                if job.output_artifacts and job.output_artifacts.get('model') == 'race-strategy-v1'
                else None
            ),
        })

    return {
        'summary': summary,
        'experiments': [serialise_experiment(exp) for exp in experiments],
        'jobs': [{
            'id': job.id,
            'experiment_id': job.experiment_id,
            'worker_id': job.worker_id,
            'status': job.status,
            'duration': job.duration,
            'progress': job.progress,
            'attempt': job.attempt,
        } for job in jobs],
        'comparison': comparison,
        'analytics': analytics,
        'worker_capacity': worker_capacity,
        'organization': {
            'id': organization.id,
            'name': organization.name,
            'cpu_quota': organization.cpu_quota,
            'memory_quota': organization.memory_quota,
            'budget_quota': organization.budget_quota,
        },
        'workers': [{
            'id': worker.id,
            'name': worker.name,
            'cpu_capacity': worker.cpu_capacity,
            'memory_capacity': worker.memory_capacity,
            'status': worker.status,
            'supported_workloads': worker.supported_workloads,
        } for worker in workers],
        'timeline': timeline,
    }


@app.get('/api/export/benchmark', response_model=None)
def export_benchmark(
    export_format: str = Query(default='json', alias='format', pattern='^(json|csv)$'),
    status_filter: str | None = Query(default=None, alias='status'),
    category: str | None = None,
    policy: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: dict[str, str] = Depends(require_roles('viewer', 'operator', 'admin', 'platform_admin')),
) -> dict | Response:
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=400, detail='from_date must be on or before to_date')
    if status_filter and status_filter not in {'ready', 'queued', 'running', 'completed', 'failed'}:
        raise HTTPException(status_code=400, detail='Unknown experiment status')
    payload = dashboard(db=db, current_user=current_user)
    experiments = payload['experiments']
    if status_filter:
        experiments = [exp for exp in experiments if exp['status'] == status_filter]
    if category:
        experiments = [exp for exp in experiments if exp['category'].casefold() == category.casefold()]

    query = db.query(Experiment).filter(
        Experiment.organization_id == current_user['organization_id']
    )
    if status_filter:
        query = query.filter(Experiment.status == status_filter)
    if category:
        query = query.filter(func.lower(Experiment.category) == category.casefold())
    if from_date:
        query = query.filter(Experiment.created_at >= datetime.combine(from_date, datetime.min.time()))
    if to_date:
        query = query.filter(Experiment.created_at < datetime.combine(to_date, datetime.max.time()))
    filtered_rows = query.order_by(Experiment.created_at, Experiment.id).all()
    filtered_ids = {row.id for row in filtered_rows}
    experiments = [exp for exp in experiments if exp['id'] in filtered_ids]

    strategies = payload['comparison']
    normalized_policy = policy.strip().lower() if policy else None
    if normalized_policy:
        strategies = [item for item in strategies if item['policy'] == normalized_policy]
        if not strategies:
            raise HTTPException(status_code=400, detail='Unknown scheduling policy')

    report = {
        'exported_at': datetime.utcnow().isoformat(),
        'generated_by': current_user.get('email'),
        'summary': payload['summary'],
        'filtered_experiment_count': len(experiments),
        'filters': {
            'status': status_filter,
            'category': category,
            'policy': normalized_policy,
            'from_date': from_date.isoformat() if from_date else None,
            'to_date': to_date.isoformat() if to_date else None,
        },
        'strategies': strategies,
        'experiments': experiments,
    }
    if export_format == 'json':
        return report

    stream = io.StringIO()
    fieldnames = [
        'id', 'name', 'status', 'category', 'priority', 'estimated_runtime',
        'cpu', 'memory', 'budget', 'deadline', 'dependencies', 'created_at', 'policy',
        'policy_score', 'policy_explanation',
    ]
    writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    policy_scores = {
        item['policy']: item['score']
        for item in strategies
    }
    chosen_policy = (normalized_policy or (strategies[0]['policy'] if strategies else ''))
    score = policy_scores.get(chosen_policy, '')
    explanation = next(
        (item['explanation'] for item in strategies if item['policy'] == chosen_policy),
        '',
    )
    def protect_csv_formula(value: Any) -> Any:
        if isinstance(value, str) and value.startswith(('=', '+', '-', '@', '\t', '\r')):
            return f"'{value}"
        return value

    for experiment in experiments:
        writer.writerow({
            **{key: protect_csv_formula(value) for key, value in experiment.items()},
            'dependencies': protect_csv_formula(','.join(experiment['dependencies'])),
            'policy': chosen_policy,
            'policy_score': score,
            'policy_explanation': explanation,
        })
    return Response(
        content=stream.getvalue(),
        media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="prontos-benchmark.csv"'},
    )


@app.post('/api/experiments')
def create_experiment(
    payload: ExperimentCreate,
    db: Session = Depends(get_db),
    current_user: dict[str, str] = Depends(require_roles('operator', 'admin', 'platform_admin')),
) -> dict:
    organization_id = current_user['organization_id']
    organization = db.query(Organization).filter(Organization.id == organization_id).one()
    name = payload.name.strip()
    dependencies = list(dict.fromkeys(payload.dependencies))

    for dep in dependencies:
        if db.query(Experiment).filter(
            Experiment.id == dep,
            Experiment.organization_id == organization_id,
        ).count() == 0:
            raise HTTPException(status_code=400, detail=f'Dependency {dep} not found')

    if payload.cpu > organization.cpu_quota or payload.memory > organization.memory_quota:
        raise HTTPException(status_code=422, detail='Experiment resource request exceeds organization quota')
    if payload.budget > organization.budget_quota:
        raise HTTPException(status_code=422, detail='Experiment budget exceeds organization quota')
    reserved_budget = db.query(Experiment).filter(
        Experiment.organization_id == organization_id
    ).with_entities(Experiment.budget).all()
    if sum(float(row[0]) for row in reserved_budget) + payload.budget > organization.budget_quota:
        raise HTTPException(status_code=409, detail='Adding this experiment would exceed the organization budget quota')

    experiment_id = f'exp-{uuid4().hex[:16]}'
    parameters = (
        payload.race_strategy.model_dump()
        if payload.race_strategy is not None
        else {'scenario': name, 'custom': True}
    )
    experiment = Experiment(
        id=experiment_id,
        organization_id=organization_id,
        name=name,
        description=payload.description,
        category=payload.category,
        parameters=parameters,
        estimated_runtime=payload.estimated_runtime,
        cpu=payload.cpu,
        memory=payload.memory,
        priority=payload.priority,
        deadline=payload.deadline,
        budget=payload.budget,
        dependencies=dependencies,
        dataset_ref='manual',
        config_hash=make_config_hash({
            'name': name,
            'category': payload.category,
            'parameters': parameters,
            'estimated_runtime': payload.estimated_runtime,
            'cpu': payload.cpu,
            'memory': payload.memory,
            'dataset_ref': 'manual',
        }),
        status='ready',
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(experiment)
    db.commit()
    db.refresh(experiment)
    return {'id': experiment.id, 'status': 'created'}


@app.post('/api/scheduler/run')
def run_scheduler(
    payload: SchedulerRun,
    db: Session = Depends(get_db),
    current_user: dict[str, str] = Depends(require_roles('operator', 'admin', 'platform_admin')),
) -> dict:
    organization_id = current_user['organization_id']
    policy = payload.policy
    experiments = db.query(Experiment).filter(Experiment.organization_id == organization_id).all()
    rows = [serialise_experiment(exp) for exp in experiments]
    if not rows:
        return {'policy': policy, 'selected_jobs': [], 'message': 'No experiments available'}

    selected = choose_jobs(rows, policy, build_state_map(db, organization_id))
    if not selected:
        return {'policy': policy, 'selected_jobs': [], 'message': 'No eligible jobs available'}

    workers = db.query(Worker).filter(Worker.organization_id == organization_id).all()
    active_jobs = db.query(Job).join(Experiment).filter(
        Experiment.organization_id == organization_id,
        Job.status.in_({'queued', 'running'}),
    ).all()
    selected, deferred = fit_jobs_to_workers(selected, experiments, workers, active_jobs)
    if not selected:
        return {
            'policy': policy,
            'selected_jobs': [],
            'deferred_experiment_ids': deferred,
            'message': 'No eligible experiments fit an online worker capacity.',
        }

    experiment_map = {exp.id: exp for exp in experiments}
    for item in selected:
        experiment = experiment_map[item['id']]
        runnable = run_workload({
            'category': experiment.category,
            'estimated_runtime': experiment.estimated_runtime,
            'parameters': experiment.parameters,
        }, seed=deterministic_seed(experiment.id))
        existing_job = db.query(Job).filter(Job.experiment_id == experiment.id).first()
        if existing_job is not None:
            continue

        db.add(Job(
            id=f"job-{experiment.id}",
            experiment_id=experiment.id,
            worker_id=item['worker_id'],
            attempt=1,
            duration=float(runnable.duration),
            cpu=float(experiment.cpu),
            memory=float(experiment.memory),
            status=runnable.status,
            progress=runnable.progress,
            exit_code=runnable.exit_code,
            error=runnable.error,
            output_artifacts=runnable.output,
            cache_status='warm',
            scheduler_metadata={'policy': policy, 'score': item['score'], 'details': item['details']},
            queued_at=datetime.utcnow(),
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        ))
        experiment.status = runnable.status
    db.commit()

    return {
        'policy': policy,
        'selected_jobs': selected,
        'deferred_experiment_ids': deferred,
        'message': f'{len(selected)} jobs dispatched with policy {policy}.',
    }


@app.post('/api/demo/reset')
def reset_demo(
    db: Session = Depends(get_db),
    current_user: dict[str, str] = Depends(require_roles('admin', 'platform_admin')),
) -> dict:
    organization_id = current_user['organization_id']
    experiment_ids = [
        row[0] for row in db.query(Experiment.id).filter(Experiment.organization_id == organization_id).all()
    ]
    db.query(Job).filter(Job.experiment_id.in_(experiment_ids)).delete(synchronize_session=False)
    db.query(Experiment).filter(Experiment.organization_id == organization_id).delete(synchronize_session=False)
    db.query(Worker).filter(Worker.organization_id == organization_id).delete(synchronize_session=False)
    seed_demo_data(db, organization_id)
    return {'status': 'reset'}


@app.get('/api/experiments/{experiment_id}')
def get_experiment(
    experiment_id: str,
    db: Session = Depends(get_db),
    current_user: dict[str, str] = Depends(require_roles('viewer', 'operator', 'admin', 'platform_admin')),
) -> dict:
    exp = db.query(Experiment).filter(
        Experiment.id == experiment_id,
        Experiment.organization_id == current_user['organization_id'],
    ).first()
    if not exp:
        raise HTTPException(status_code=404, detail='Experiment not found')
    return serialise_experiment(exp)


@app.post('/api/jobs/{job_id}/run')
def run_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: dict[str, str] = Depends(require_roles('operator', 'admin', 'platform_admin')),
) -> dict:
    job = db.query(Job).join(Experiment).filter(
        Job.id == job_id,
        Experiment.organization_id == current_user['organization_id'],
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail='Job not found')
    if job.status in {'queued', 'running', 'completed'}:
        raise HTTPException(status_code=409, detail=f'Job in {job.status} state cannot be retried')
    experiment = db.query(Experiment).filter(Experiment.id == job.experiment_id).first()
    if experiment is None:
        raise HTTPException(status_code=404, detail='Experiment not found')

    organization_id = current_user['organization_id']
    workers = db.query(Worker).filter(Worker.organization_id == organization_id).all()
    active_jobs = db.query(Job).join(Experiment).filter(
        Experiment.organization_id == organization_id,
        Job.status.in_({'queued', 'running'}),
        Job.id != job.id,
    ).all()
    assignments, deferred = fit_jobs_to_workers(
        [{'id': experiment.id}],
        [experiment],
        workers,
        active_jobs,
    )
    if not assignments:
        raise HTTPException(
            status_code=409,
            detail=f'No online worker with available capacity can retry this job: {", ".join(deferred)}',
        )
    now = datetime.utcnow()
    job.worker_id = assignments[0]['worker_id']
    job.attempt += 1
    job.queued_at = now
    job.started_at = now
    job.completed_at = now
    result = run_workload({
        'category': experiment.category,
        'estimated_runtime': experiment.estimated_runtime,
        'parameters': experiment.parameters,
    }, seed=deterministic_seed(f'{experiment.id}:{job.attempt}'))

    job.duration = result.duration
    job.status = result.status
    job.progress = result.progress
    job.exit_code = result.exit_code
    job.output_artifacts = result.output
    job.error = result.error
    experiment.status = result.status
    db.commit()

    return {'job_id': job_id, 'status': result.status, 'duration': result.duration, 'output': result.output}
