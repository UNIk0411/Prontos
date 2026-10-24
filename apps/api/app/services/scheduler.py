import hashlib
import json
from datetime import datetime
from typing import Any


def make_config_hash(experiment: dict[str, Any]) -> str:
    payload = {
        'name': experiment.get('name'),
        'category': experiment.get('category'),
        'parameters': experiment.get('parameters', {}),
        'estimated_runtime': float(experiment.get('estimated_runtime', 0)),
        'cpu': float(experiment.get('cpu', 0)),
        'memory': float(experiment.get('memory', 0)),
        'dataset_ref': experiment.get('dataset_ref', 'demo'),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()


def compute_dependency_depth(experiments: list[dict[str, Any]], exp_id: str, cache: dict[str, int] | None = None) -> int:
    cache = cache or {}
    if exp_id in cache:
        return cache[exp_id]

    experiment = next((exp for exp in experiments if exp['id'] == exp_id), None)
    if experiment is None:
        return 0
    if not experiment.get('dependencies'):
        cache[exp_id] = 0
        return 0

    deps = [compute_dependency_depth(experiments, dep, cache) for dep in experiment['dependencies']]
    depth = 1 + max(deps, default=0)
    cache[exp_id] = depth
    return depth


def score_adaptive(experiment: dict[str, Any], now: datetime, experiments: list[dict[str, Any]] | None = None) -> tuple[float, dict[str, Any]]:
    deadline = experiment.get('deadline')
    deadline_factor = 0.0
    if deadline:
        try:
            deadline_dt = datetime.strptime(deadline, '%Y-%m-%d')
            deadline_factor = max(0.0, 1.0 - (deadline_dt - now).days / 30)
        except ValueError:
            deadline_factor = 0.0

    depth = compute_dependency_depth(experiments or [experiment], experiment['id']) if experiments else 0
    resource_pressure = float(experiment.get('cpu', 0)) + float(experiment.get('memory', 0))
    workload_balance = max(0.0, 12.0 - resource_pressure)

    base_score = (
        (float(experiment.get('priority', 0)) * 18)
        + (max(0.0, 20.0 - float(experiment.get('estimated_runtime', 0))) * 0.6)
        + (deadline_factor * 30.0)
        + (depth * 6.0)
        + (float(experiment.get('budget', 0)) * 0.7)
        + (workload_balance * 1.4)
    )
    return base_score, {'deadline_factor': round(deadline_factor, 3), 'depth': depth, 'resource_pressure': round(resource_pressure, 2), 'workload_balance': round(workload_balance, 2)}


def build_demo_experiments() -> list[dict[str, Any]]:
    experiments = [
        {
            'id': 'exp-101',
            'name': 'mesh-prep',
            'description': 'Generate baseline mesh and boundaries',
            'category': 'CPU-bound numerical workload',
            'parameters': {'cells': 120000, 'mesh_quality': 'medium'},
            'estimated_runtime': 8,
            'cpu': 6,
            'memory': 4,
            'priority': 5,
            'deadline': '2026-10-20',
            'budget': 20,
            'dependencies': [],
            'dataset_ref': 'demo-v1',
            'status': 'ready',
        },
        {
            'id': 'exp-102',
            'name': 'flow-sweep',
            'description': 'Run a CFD parameter sweep',
            'category': 'Parameter sweep',
            'parameters': {'variables': ['angle_of_attack', 'spoiler_position']},
            'estimated_runtime': 11,
            'cpu': 5,
            'memory': 3,
            'priority': 4,
            'deadline': '2026-10-19',
            'budget': 18,
            'dependencies': ['exp-101'],
            'dataset_ref': 'demo-v1',
            'status': 'ready',
        },
        {
            'id': 'exp-103',
            'name': 'thermal-risk',
            'description': 'Monte Carlo thermal reliability pass',
            'category': 'Monte Carlo experiment',
            'parameters': {'trials': 10000},
            'estimated_runtime': 9,
            'cpu': 4,
            'memory': 2,
            'priority': 3,
            'deadline': '2026-10-18',
            'budget': 14,
            'dependencies': ['exp-101'],
            'dataset_ref': 'demo-v1',
            'status': 'ready',
        },
        {
            'id': 'exp-104',
            'name': 'aero-simulation',
            'description': 'Synthetic vehicle aero evaluation',
            'category': 'Synthetic vehicle or engineering simulation',
            'parameters': {'drag_coefficient': 0.29, 'downforce_proxy': 0.76},
            'estimated_runtime': 12,
            'cpu': 6,
            'memory': 5,
            'priority': 5,
            'deadline': '2026-10-21',
            'budget': 22,
            'dependencies': ['exp-102'],
            'dataset_ref': 'demo-v1',
            'status': 'ready',
        },
        {
            'id': 'exp-105',
            'name': 'resilience-check',
            'description': 'Purposefully failing workload to validate recovery',
            'category': 'Deliberately failing workload for testing recovery',
            'parameters': {'fault_mode': 'drift'},
            'estimated_runtime': 5,
            'cpu': 2,
            'memory': 1,
            'priority': 2,
            'deadline': '2026-10-17',
            'budget': 8,
            'dependencies': [],
            'dataset_ref': 'demo-v1',
            'status': 'ready',
        },
        {
            'id': 'exp-106',
            'name': 'performance-forecast',
            'description': 'Evaluate the forecast model for the next cycle',
            'category': 'CPU-bound numerical workload',
            'parameters': {'model': 'baseline'},
            'estimated_runtime': 7,
            'cpu': 3,
            'memory': 2,
            'priority': 4,
            'deadline': '2026-10-22',
            'budget': 11,
            'dependencies': ['exp-103', 'exp-104'],
            'dataset_ref': 'demo-v1',
            'status': 'ready',
        },
    ]

    for exp in experiments:
        exp['config_hash'] = make_config_hash(exp)
    return experiments


def base_workers() -> list[dict[str, Any]]:
    return [
        {
            'id': 'worker-01',
            'name': 'solver-a',
            'cpu_capacity': 8.0,
            'memory_capacity': 8.0,
            'supported_workloads': [
                'CPU-bound numerical workload',
                'Parameter sweep',
                'Synthetic vehicle or engineering simulation',
                'Race strategy simulation',
            ],
            'status': 'online',
            'current_allocations': {'cpu': 0.0, 'memory': 0.0},
            'health': {'healthy': True},
        },
        {
            'id': 'worker-02',
            'name': 'risk-b',
            'cpu_capacity': 6.0,
            'memory_capacity': 4.0,
            'supported_workloads': ['Monte Carlo experiment', 'Deliberately failing workload for testing recovery'],
            'status': 'online',
            'current_allocations': {'cpu': 0.0, 'memory': 0.0},
            'health': {'healthy': True},
        },
    ]


def eligible_experiments(experiments: list[dict[str, Any]], state: dict[str, str] | None = None) -> list[dict[str, Any]]:
    if state is None:
        state = {exp['id']: exp.get('status', 'ready') for exp in experiments}
    ready = []
    for experiment in experiments:
        if state.get(experiment['id'], experiment.get('status', 'ready')) not in {'ready', 'pending'}:
            continue
        deps = experiment.get('dependencies', [])
        if deps and any(state.get(dep) != 'completed' for dep in deps):
            continue
        ready.append(experiment)
    return ready


def choose_jobs(experiments: list[dict[str, Any]], policy: str = 'adaptive', state: dict[str, str] | None = None) -> list[dict[str, Any]]:
    now = datetime.utcnow()
    candidates = eligible_experiments(experiments, state)
    if not candidates:
        return []

    if policy == 'fifo':
        candidates = sorted(candidates, key=lambda x: (x.get('deadline') or '9999-12-31', x['id']))
    elif policy == 'priority':
        candidates = sorted(candidates, key=lambda x: (-int(x.get('priority', 0)), x['id']))
    elif policy == 'shortest':
        candidates = sorted(candidates, key=lambda x: (float(x.get('estimated_runtime', 0)), -int(x.get('priority', 0)), x['id']))
    elif policy == 'deadline':
        candidates = sorted(candidates, key=lambda x: (x.get('deadline') or '9999-12-31', -int(x.get('priority', 0)), x['id']))
    elif policy == 'adaptive':
        candidates = sorted(candidates, key=lambda x: (-score_adaptive(x, now, experiments)[0], x['id']))
    else:
        raise ValueError(f'Unsupported scheduler policy: {policy}')

    output = []
    for experiment in candidates:
        score, details = score_adaptive(experiment, now, experiments)
        output.append({
            'id': experiment['id'],
            'name': experiment['name'],
            'score': round(score, 2),
            'policy': policy,
            'status': 'selected',
            'details': details,
        })
    return output


def explain_policy_selection(policy: str, chosen: list[dict[str, Any]], experiments: list[dict[str, Any]]) -> str:
    if not chosen:
        return f'No eligible experiments were available for the {policy} policy.'

    selected_names = ', '.join(item['name'] for item in chosen)
    top_item = max(chosen, key=lambda item: item['score'])
    top_exp = next((exp for exp in experiments if exp['id'] == top_item['id']), None)
    if top_exp and top_exp.get('deadline'):
        return (
            f'{policy.upper()} selected {selected_names} because it prioritised high-value, deadline-sensitive work. '
            f'{top_item["name"]} was the strongest candidate with a score of {top_item["score"]} and a deadline of {top_exp["deadline"]}.'
        )
    return (
        f'{policy.upper()} selected {selected_names} because it prioritised the strongest eligible workload mix in the current queue.'
    )


def resource_pressure_summary(
    experiments: list[dict[str, Any]],
    state: dict[str, str] | None = None,
    workers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    eligible = eligible_experiments(experiments, state)
    total_cpu = sum(float(exp.get('cpu', 0)) for exp in experiments)
    total_memory = sum(float(exp.get('memory', 0)) for exp in experiments)
    eligible_cpu = sum(float(exp.get('cpu', 0)) for exp in eligible)
    eligible_memory = sum(float(exp.get('memory', 0)) for exp in eligible)
    worker_cpu = sum(float(worker.get('cpu_capacity', 0)) for worker in workers or [])
    worker_memory = sum(float(worker.get('memory_capacity', 0)) for worker in workers or [])
    pressure_denominator = worker_cpu if workers is not None else total_cpu
    active_pressure = round((eligible_cpu / pressure_denominator) * 100, 1) if pressure_denominator else 0.0
    return {
        'total_cpu': round(total_cpu, 2),
        'total_memory': round(total_memory, 2),
        'eligible_cpu': round(eligible_cpu, 2),
        'eligible_memory': round(eligible_memory, 2),
        'eligible_percentage': active_pressure,
        'worker_cpu_capacity': round(worker_cpu, 2) if workers is not None else None,
        'worker_memory_capacity': round(worker_memory, 2) if workers is not None else None,
        'ready_count': len(eligible),
    }


def schedule_policy_comparison(
    experiments: list[dict[str, Any]] | None = None,
    states: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    experiments = experiments if experiments is not None else build_demo_experiments()
    states = states if states is not None else {exp['id']: exp.get('status', 'ready') for exp in experiments}
    results = []
    for policy in ['fifo', 'priority', 'shortest', 'deadline', 'adaptive']:
        chosen = choose_jobs(experiments, policy, states)
        total_budget = sum(float(exp.get('budget', 0)) for exp in experiments)
        total_runtime = sum(float(exp.get('estimated_runtime', 0)) for exp in chosen)
        deadline_hits = sum(1 for item in chosen if item['id'] in {exp['id'] for exp in experiments if exp.get('deadline')})
        selected_names = [item['name'] for item in chosen]
        results.append({
            'policy': policy,
            'completed_jobs': len(chosen),
            'makespan': round(total_runtime, 2),
            'deadline_success_rate': round(min(1.0, deadline_hits / max(1, len(chosen))), 2),
            'budget_used': round(sum(float(next(exp['budget'] for exp in experiments if exp['id'] == item['id'])) for item in chosen) / total_budget, 2) if total_budget else 0.0,
            'score': round(sum(item['score'] for item in chosen), 2),
            'selected_ids': [item['id'] for item in chosen],
            'selected_names': selected_names,
            'explanation': explain_policy_selection(policy, chosen, experiments),
            'resource_load': round(sum(float(next(exp['cpu'] for exp in experiments if exp['id'] == item['id'])) for item in chosen), 2),
        })
    return results
