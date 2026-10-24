from app.core.schemas import RaceStrategyConfig


MODEL_VERSION = 'race-strategy-v1'


def _tire_cost(start_lap: int, end_lap: int, wear_seconds_per_lap: float) -> float:
    stint_length = end_lap - start_lap
    return wear_seconds_per_lap * stint_length * (stint_length - 1) / 2


def _optimize_pit_laps(config: RaceStrategyConfig) -> list[int]:
    laps = config.race_laps
    max_stints = (laps + config.max_stint_laps - 1) // config.max_stint_laps
    costs = [[float('inf')] * (laps + 1) for _ in range(max_stints + 1)]
    previous = [[-1] * (laps + 1) for _ in range(max_stints + 1)]
    costs[0][0] = 0.0

    for stint_count in range(1, max_stints + 1):
        for end_lap in range(stint_count, laps + 1):
            first_start = max(stint_count - 1, end_lap - config.max_stint_laps)
            for start_lap in range(first_start, end_lap):
                if costs[stint_count - 1][start_lap] == float('inf'):
                    continue
                pit_cost = config.pit_loss_seconds if stint_count > 1 else 0.0
                candidate = (
                    costs[stint_count - 1][start_lap]
                    + _tire_cost(start_lap, end_lap, config.tire_wear_seconds_per_lap)
                    + pit_cost
                )
                if candidate < costs[stint_count][end_lap]:
                    costs[stint_count][end_lap] = candidate
                    previous[stint_count][end_lap] = start_lap

    best_stint_count = min(
        range(1, max_stints + 1),
        key=lambda count: (costs[count][laps], count),
    )
    pit_laps: list[int] = []
    end_lap = laps
    for stint_count in range(best_stint_count, 0, -1):
        start_lap = previous[stint_count][end_lap]
        if start_lap < 0:
            raise RuntimeError('Unable to reconstruct a feasible race strategy')
        if start_lap:
            pit_laps.append(start_lap)
        end_lap = start_lap
    return sorted(pit_laps)


def simulate_race_strategy(config: RaceStrategyConfig) -> dict:
    pit_laps = (
        _optimize_pit_laps(config)
        if config.strategy_mode == 'optimize'
        else config.pit_laps
    )
    pit_lap_set = set(pit_laps)
    lap_results = []
    tire_age = 0
    total_race_time = 0.0

    for lap in range(1, config.race_laps + 1):
        fuel_before_lap = config.starting_fuel_kg - config.fuel_burn_per_lap_kg * (lap - 1)
        fuel_penalty = fuel_before_lap * config.fuel_time_penalty_seconds_per_kg
        tire_penalty = tire_age * config.tire_wear_seconds_per_lap
        pit_loss = config.pit_loss_seconds if lap in pit_lap_set else 0.0
        lap_time = (
            config.base_lap_time_seconds
            + fuel_penalty
            + tire_penalty
            + pit_loss
        )
        lap_results.append({
            'lap': lap,
            'lap_time_seconds': round(lap_time, 3),
            'fuel_before_lap_kg': round(fuel_before_lap, 3),
            'tire_age_laps': tire_age,
            'pit_stop': lap in pit_lap_set,
            'pit_loss_seconds': pit_loss,
        })
        total_race_time += lap_time
        if lap in pit_lap_set:
            tire_age = 0
        else:
            tire_age += 1

    fuel_used = config.fuel_burn_per_lap_kg * config.race_laps
    return {
        'model': MODEL_VERSION,
        'validation_status': 'UNVALIDATED',
        'strategy_mode': config.strategy_mode,
        'race_laps': config.race_laps,
        'total_race_time_seconds': round(total_race_time, 3),
        'average_lap_time_seconds': round(total_race_time / config.race_laps, 3),
        'pit_laps': pit_laps,
        'pit_stops': len(pit_laps),
        'fuel_used_kg': round(fuel_used, 3),
        'fuel_remaining_kg': round(config.starting_fuel_kg - fuel_used, 3),
        'assumptions': [
            'Constant baseline lap time; no traffic, overtaking, incidents, or track evolution.',
            'Fuel burn and fuel-time sensitivity are constant for every lap.',
            'Tire degradation is linear with tire age; all stints use an equivalent tire.',
            'Pit loss is fixed and applied to the lap ending at each planned pit stop.',
            'No weather, safety-car, reliability, setup, or regulatory model is included.',
        ],
        'laps': lap_results,
    }
