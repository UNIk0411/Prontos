import hashlib
import json
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.schemas import RaceStrategyConfig
from app.services.race_strategy import MODEL_VERSION, simulate_race_strategy


@dataclass
class JobResult:
    job_id: str
    status: str
    duration: float
    progress: float
    exit_code: int | None
    output: dict[str, Any]
    error: str | None = None


def run_workload(experiment: dict[str, Any], seed: int = 42) -> JobResult:
    rng = random.Random(seed)
    workload = experiment.get('category', 'CPU-bound numerical workload')
    base = float(experiment.get('estimated_runtime', 6))
    if workload == 'Race strategy simulation':
        config = RaceStrategyConfig.model_validate(experiment.get('parameters', {}))
        summary = simulate_race_strategy(config)
        duration = base
    elif workload.startswith('Monte Carlo'):
        duration = base * (1.2 + rng.random() * 0.8)
        summary = {'samples': 5000 + int(rng.random() * 3000), 'mean': round(rng.random() * 12, 3)}
    elif workload.startswith('Parameter sweep'):
        duration = base * (1.1 + rng.random() * 0.7)
        summary = {'sweep_points': 14 + int(rng.random() * 10), 'coverage': 'full'}
    elif workload.startswith('Synthetic vehicle'):
        duration = base * (1.3 + rng.random() * 0.9)
        summary = {'drag_coefficient': round(0.3 + rng.random() * 0.2, 4), 'temperature_c': round(74 + rng.random() * 18, 2)}
    elif workload.startswith('Deliberately failing'):
        duration = base * 0.8
        summary = {'failure_mode': 'deterministic injection'}
        return JobResult(
            job_id='simulated-job',
            status='failed',
            duration=duration,
            progress=1.0,
            exit_code=17,
            output=summary,
            error='Simulated workload failure for testing recovery.'
        )
    else:
        duration = base * (0.9 + rng.random() * 0.4)
        summary = {'iterations': 1000 + int(rng.random() * 4000), 'score': round(rng.random() * 100, 2)}

    success = duration < base * 1.8
    if not success and workload.startswith('CPU-bound'):
        return JobResult(
            job_id='simulated-job',
            status='failed',
            duration=duration,
            progress=1.0,
            exit_code=1,
            output=summary,
            error='Resource pressure exceeded the allowed simulation envelope.'
        )

    return JobResult(
        job_id='simulated-job',
        status='completed',
        duration=round(duration, 2),
        progress=1.0,
        exit_code=0,
        output={
            **summary,
            'seed': seed,
            'executed_at': datetime.utcnow().isoformat(),
            'job_type': workload,
            **({'model_version': MODEL_VERSION} if workload == 'Race strategy simulation' else {}),
        },
    )
