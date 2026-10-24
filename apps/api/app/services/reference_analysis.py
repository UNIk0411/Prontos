from collections import defaultdict
from statistics import median
from typing import Any

from app.core.schemas import RaceStrategyConfig
from app.services.race_strategy import MODEL_VERSION, simulate_race_strategy


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {'true', '1', 'yes'}


def analyze_race_reference(
    rows: list[dict[str, Any]],
    pit_loss_scenarios: list[float],
    tire_wear_scenarios: list[float],
    max_stint_laps: int = 35,
) -> dict[str, Any]:
    if not rows:
        raise ValueError('Reference data contains no lap rows')
    if not pit_loss_scenarios or not tire_wear_scenarios:
        raise ValueError('At least one pit-loss and tire-wear scenario is required')

    laps: list[dict[str, Any]] = []
    for row in rows:
        try:
            lap_number = int(row['lap_number'])
            lap_time = float(row['lap_time_seconds'])
            stint_number = int(row['stint_number'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('Reference rows must contain valid lap, lap-time, and stint values') from exc
        if lap_number < 1 or lap_time <= 0:
            raise ValueError('Lap numbers and lap times must be positive')
        laps.append({
            'lap_number': lap_number,
            'lap_time_seconds': lap_time,
            'stint_number': stint_number,
            'compound': row.get('tire_compound') or 'unknown',
            'pit_out_lap': _as_bool(row.get('pit_out_lap', False)),
        })

    laps.sort(key=lambda lap: lap['lap_number'])
    if len({lap['lap_number'] for lap in laps}) != len(laps):
        raise ValueError('Reference data contains duplicate lap numbers')

    grouped_stints: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for lap in laps:
        grouped_stints[lap['stint_number']].append(lap)
    stint_summaries = []
    for stint_number, stint_laps in sorted(grouped_stints.items()):
        clean_lap_times = [
            lap['lap_time_seconds'] for lap in stint_laps
            if not lap['pit_out_lap']
        ]
        stint_summaries.append({
            'stint_number': stint_number,
            'lap_start': stint_laps[0]['lap_number'],
            'lap_end': stint_laps[-1]['lap_number'],
            'lap_count': len(stint_laps),
            'tire_compound': stint_laps[0]['compound'],
            'median_lap_time_seconds_excluding_pit_out': (
                round(median(clean_lap_times), 3) if clean_lap_times else None
            ),
        })

    observed_pit_laps = [
        stint['lap_start'] - 1
        for stint in stint_summaries[1:]
    ]
    clean_lap_times = [
        lap['lap_time_seconds'] for lap in laps
        if not lap['pit_out_lap']
    ]
    if not clean_lap_times:
        raise ValueError('Reference data contains no non-pit-out lap times')

    baseline = median(clean_lap_times)
    strategy_scenarios = []
    for pit_loss in pit_loss_scenarios:
        for tire_wear in tire_wear_scenarios:
            config = RaceStrategyConfig(
                race_laps=laps[-1]['lap_number'],
                base_lap_time_seconds=max(30.001, baseline),
                starting_fuel_kg=1000,
                fuel_burn_per_lap_kg=0.1,
                fuel_time_penalty_seconds_per_kg=0,
                pit_loss_seconds=pit_loss,
                tire_wear_seconds_per_lap=tire_wear,
                max_stint_laps=max_stint_laps,
            )
            result = simulate_race_strategy(config)
            strategy_scenarios.append({
                'pit_loss_seconds_assumed': pit_loss,
                'tire_wear_seconds_per_lap_of_age_assumed': tire_wear,
                'suggested_pit_laps': result['pit_laps'],
                'suggested_stop_count': result['pit_stops'],
                'matches_observed_pit_laps': result['pit_laps'] == observed_pit_laps,
                'matches_observed_stop_count': result['pit_stops'] == len(observed_pit_laps),
            })

    return {
        'analysis_status': 'EXPLORATORY_NOT_VALIDATION',
        'model': MODEL_VERSION,
        'reference': {
            'lap_count': len(laps),
            'first_lap': laps[0]['lap_number'],
            'last_lap': laps[-1]['lap_number'],
            'median_lap_time_seconds_excluding_pit_out': round(baseline, 3),
            'observed_pit_after_laps': observed_pit_laps,
            'observed_stop_count': len(observed_pit_laps),
            'stints': stint_summaries,
        },
        'model_setup': {
            'base_lap_time_seconds_assumed': round(baseline, 3),
            'max_stint_laps_assumed': max_stint_laps,
            'fuel_inputs': 'Artificial feasibility placeholders; fuel is not calibrated from the CSV.',
            'tire_and_pit_inputs': 'Sensitivity values supplied by the caller; not measured from this race.',
        },
        'strategy_scenarios': strategy_scenarios,
        'interpretation': (
            'A matching stop count or pit-lap plan is only a sensitivity observation. It is not evidence '
            'of predictive accuracy because the model assumptions are not calibrated, observed race '
            'strategy is not necessarily time-optimal, and race context is absent.'
        ),
    }
