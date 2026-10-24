from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models import Experiment, Job, Organization, User, Worker
from app.db.session import SessionLocal
from app.main import app


def test_health_check() -> None:
    client = TestClient(app)
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'
    assert client.get('/api/dashboard').status_code == 401


def test_bahrain_reference_sample_requires_auth_and_returns_exploratory_report() -> None:
    client = TestClient(app)
    assert client.get('/api/reference/bahrain-2024').status_code == 401

    login = client.post(
        '/api/auth/login',
        json={'email': 'admin@prontos.local', 'password': 'admin123'},
    )
    token = login.json()['token']
    response = client.get(
        '/api/reference/bahrain-2024',
        headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 200
    report = response.json()
    assert report['analysis_status'] == 'EXPLORATORY_NOT_VALIDATION'
    assert report['reference']['event_name'] == '2024 Bahrain Grand Prix'
    assert report['reference']['lap_count'] == 57
    assert report['reference']['observed_pit_after_laps'] == [17, 37]
    assert len(report['strategy_scenarios']) == 12


def test_login_and_dashboard_protected() -> None:
    client = TestClient(app)
    login = client.post('/api/auth/login', json={'email': 'admin@prontos.local', 'password': 'admin123'})
    assert login.status_code == 200
    token = login.json()['token']

    response = client.get('/api/dashboard', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 200
    payload = response.json()
    assert 'experiments' in payload
    assert 'comparison' in payload


def test_organization_isolation_admin_management_exports_and_quotas() -> None:
    client = TestClient(app)
    platform_login = client.post(
        '/api/auth/login',
        json={'email': 'admin@prontos.local', 'password': 'admin123'},
    )
    platform_token = platform_login.json()['token']
    suffix = uuid4().hex[:10]
    owner_email = f'owner-{suffix}@example.test'
    owner_password = 'secure-owner-password'

    creation = client.post(
        '/api/admin/organizations',
        headers={'Authorization': f'Bearer {platform_token}'},
        json={
            'name': f'Test Organization {suffix}',
            'owner_email': owner_email,
            'owner_username': f'owner-{suffix}',
            'owner_password': owner_password,
            'cpu_quota': 3,
            'memory_quota': 2,
            'budget_quota': 50,
        },
    )
    assert creation.status_code == 201
    organization_id = creation.json()['organization']['id']
    organizations = client.get(
        '/api/admin/organizations',
        headers={'Authorization': f'Bearer {platform_token}'},
    )
    assert organizations.status_code == 200
    assert any(item['id'] == organization_id for item in organizations.json())
    owner_login = client.post(
        '/api/auth/login',
        json={'email': owner_email, 'password': owner_password},
    )
    owner_token = owner_login.json()['token']
    owner_headers = {'Authorization': f'Bearer {owner_token}'}

    try:
        assert owner_login.json()['user']['organization_id'] == organization_id
        tenant_dashboard = client.get('/api/dashboard', headers=owner_headers).json()
        assert tenant_dashboard['experiments'] == []
        assert tenant_dashboard['organization']['cpu_quota'] == 3
        assert client.patch(
            '/api/admin/organization',
            headers=owner_headers,
            json={'cpu_quota': 2},
        ).status_code == 409

        default_dashboard = client.get(
            '/api/dashboard',
            headers={'Authorization': f'Bearer {platform_token}'},
        ).json()
        assert all(
            experiment['id'] not in {row['id'] for row in tenant_dashboard['experiments']}
            for experiment in default_dashboard['experiments']
        )

        created = []
        for name in ('tenant-workload-a', 'tenant-workload-b'):
            response = client.post(
                '/api/experiments',
                headers=owner_headers,
                json={
                    'name': name,
                    'cpu': 1,
                    'memory': 0.5,
                    'budget': 5,
                    'priority': 3,
                    'estimated_runtime': 8,
                    'category': 'CPU-bound numerical workload',
                },
            )
            assert response.status_code == 200
            created.append(response.json()['id'])

        oversized = client.post(
            '/api/experiments',
            headers=owner_headers,
            json={
                'name': 'oversized',
                'cpu': 4,
                'memory': 1,
                'budget': 5,
                'priority': 3,
                'estimated_runtime': 8,
            },
        )
        assert oversized.status_code == 422

        schedule = client.post(
            '/api/scheduler/run',
            headers=owner_headers,
            json={'policy': 'priority'},
        )
        assert schedule.status_code == 200
        assert len(schedule.json()['selected_jobs']) == 1
        assert len(schedule.json()['deferred_experiment_ids']) == 1
        assert schedule.json()['selected_jobs'][0]['worker_id']

        foreign_experiment = client.get(
            f"/api/experiments/{default_dashboard['experiments'][0]['id']}",
            headers=owner_headers,
        )
        assert foreign_experiment.status_code == 404

        member = client.post(
            '/api/admin/users',
            headers=owner_headers,
            json={
                'email': f'operator-{suffix}@example.test',
                'username': f'operator-{suffix}',
                'password': 'secure-operator-password',
                'role': 'operator',
            },
        )
        assert member.status_code == 201
        assert member.json()['organization_id'] == organization_id
        assert client.get('/api/admin/users', headers=owner_headers).status_code == 200
        assert client.post(
            '/api/admin/organizations',
            headers=owner_headers,
            json={
                'name': 'Should Not Create',
                'owner_email': f'blocked-{suffix}@example.test',
                'owner_username': f'blocked-{suffix}',
                'owner_password': 'secure-blocked-password',
            },
        ).status_code == 403

        csv_export = client.get(
            '/api/export/benchmark?format=csv&status=ready&policy=priority',
            headers=owner_headers,
        )
        assert csv_export.status_code == 200
        assert csv_export.headers['content-type'].startswith('text/csv')
        remaining_name = next(
            item['name']
            for item in client.get('/api/dashboard', headers=owner_headers).json()['experiments']
            if item['status'] == 'ready'
        )
        assert remaining_name in csv_export.text

        json_export = client.get(
            '/api/export/benchmark?format=json&status=completed',
            headers=owner_headers,
        )
        assert json_export.status_code == 200
        assert all(item['status'] == 'completed' for item in json_export.json()['experiments'])
    finally:
        db = SessionLocal()
        experiment_ids = [
            row[0] for row in db.query(Experiment.id).filter(Experiment.organization_id == organization_id).all()
        ]
        db.query(Job).filter(Job.experiment_id.in_(experiment_ids)).delete(synchronize_session=False)
        db.query(Experiment).filter(Experiment.organization_id == organization_id).delete(synchronize_session=False)
        db.query(Worker).filter(Worker.organization_id == organization_id).delete(synchronize_session=False)
        db.query(User).filter(User.organization_id == organization_id).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id == organization_id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_failed_job_retry_increments_attempt_and_stays_tenant_scoped() -> None:
    client = TestClient(app)
    platform_login = client.post(
        '/api/auth/login',
        json={'email': 'admin@prontos.local', 'password': 'admin123'},
    )
    platform_token = platform_login.json()['token']
    suffix = uuid4().hex[:10]
    owner_email = f'retry-owner-{suffix}@example.test'
    owner_password = 'secure-retry-password'
    created_org = client.post(
        '/api/admin/organizations',
        headers={'Authorization': f'Bearer {platform_token}'},
        json={
            'name': f'Retry Test {suffix}',
            'owner_email': owner_email,
            'owner_username': f'retry-owner-{suffix}',
            'owner_password': owner_password,
        },
    )
    assert created_org.status_code == 201
    organization_id = created_org.json()['organization']['id']
    owner_token = client.post(
        '/api/auth/login',
        json={'email': owner_email, 'password': owner_password},
    ).json()['token']
    headers = {'Authorization': f'Bearer {owner_token}'}

    try:
        experiment = client.post(
            '/api/experiments',
            headers=headers,
            json={
                'name': 'retryable-failure',
                'category': 'Deliberately failing workload for testing recovery',
                'cpu': 2,
                'memory': 1,
                'budget': 5,
                'priority': 3,
                'estimated_runtime': 4,
            },
        )
        assert experiment.status_code == 200
        experiment_id = experiment.json()['id']
        first_run = client.post(
            '/api/scheduler/run',
            headers=headers,
            json={'policy': 'priority'},
        )
        assert first_run.status_code == 200
        job_id = f'job-{experiment_id}'
        assert client.get('/api/dashboard', headers=headers).json()['jobs'][0]['attempt'] == 1

        retry = client.post(f'/api/jobs/{job_id}/run', headers=headers)
        assert retry.status_code == 200
        dashboard = client.get('/api/dashboard', headers=headers).json()
        assert dashboard['jobs'][0]['attempt'] == 2
        assert dashboard['jobs'][0]['status'] == 'failed'
    finally:
        db = SessionLocal()
        experiment_ids = [
            row[0] for row in db.query(Experiment.id).filter(Experiment.organization_id == organization_id).all()
        ]
        db.query(Job).filter(Job.experiment_id.in_(experiment_ids)).delete(synchronize_session=False)
        db.query(Experiment).filter(Experiment.organization_id == organization_id).delete(synchronize_session=False)
        db.query(Worker).filter(Worker.organization_id == organization_id).delete(synchronize_session=False)
        db.query(User).filter(User.organization_id == organization_id).delete(synchronize_session=False)
        db.query(Organization).filter(Organization.id == organization_id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_race_strategy_experiment_runs_and_exposes_lap_results() -> None:
    client = TestClient(app)
    token = client.post(
        '/api/auth/login',
        json={'email': 'admin@prontos.local', 'password': 'admin123'},
    ).json()['token']
    headers = {'Authorization': f'Bearer {token}'}
    experiment_id = None

    try:
        invalid_config = client.post(
            '/api/experiments',
            headers=headers,
            json={
                'name': f'invalid-race-{uuid4().hex[:8]}',
                'category': 'Race strategy simulation',
                'race_strategy': {
                    'race_laps': 10,
                    'starting_fuel_kg': 5,
                    'fuel_burn_per_lap_kg': 1,
                },
            },
        )
        assert invalid_config.status_code == 422

        created = client.post(
            '/api/experiments',
            headers=headers,
            json={
                'name': f'race-strategy-{uuid4().hex[:8]}',
                'category': 'Race strategy simulation',
                'cpu': 1,
                'memory': 1,
                'budget': 1,
                'priority': 5,
                'estimated_runtime': 1,
                'race_strategy': {
                    'race_laps': 12,
                    'starting_fuel_kg': 24,
                    'fuel_burn_per_lap_kg': 2,
                    'max_stint_laps': 6,
                },
            },
        )
        assert created.status_code == 200
        experiment_id = created.json()['id']

        scheduled = client.post(
            '/api/scheduler/run',
            headers=headers,
            json={'policy': 'priority'},
        )
        assert scheduled.status_code == 200
        assert any(row['id'] == experiment_id for row in scheduled.json()['selected_jobs'])

        dashboard = client.get('/api/dashboard', headers=headers).json()
        race_job = next(job for job in dashboard['jobs'] if job['experiment_id'] == experiment_id)
        assert race_job['status'] == 'completed'
        race_event = next(step for step in dashboard['timeline'] if step['id'] == race_job['id'])
        assert race_event['result']['model'] == 'race-strategy-v1'
        assert race_event['result']['validation_status'] == 'UNVALIDATED'
        assert len(race_event['result']['laps']) == 12
        assert race_event['result']['pit_stops'] == 1
    finally:
        if experiment_id is not None:
            db = SessionLocal()
            db.query(Job).filter(Job.experiment_id == experiment_id).delete(synchronize_session=False)
            db.query(Experiment).filter(Experiment.id == experiment_id).delete(synchronize_session=False)
            db.commit()
            db.close()
