import pytest
from pydantic import ValidationError

from app.core.schemas import RaceStrategyConfig
from app.services.race_strategy import simulate_race_strategy


def test_optimized_strategy_is_deterministic_and_respects_stint_limit() -> None:
    config = RaceStrategyConfig(
        race_laps=24,
        starting_fuel_kg=48,
        fuel_burn_per_lap_kg=2,
        max_stint_laps=10,
    )

    first = simulate_race_strategy(config)
    second = simulate_race_strategy(config)

    assert first == second
    assert len(first['laps']) == 24
    assert first['validation_status'] == 'UNVALIDATED'
    assert all(lap['lap_time_seconds'] > 0 for lap in first['laps'])
    assert first['pit_laps'] == [8, 16]
    assert first['fuel_used_kg'] == 48
    assert first['fuel_remaining_kg'] == 0


def test_manual_strategy_records_pit_loss_on_selected_laps() -> None:
    config = RaceStrategyConfig(
        strategy_mode='manual',
        race_laps=12,
        starting_fuel_kg=24,
        fuel_burn_per_lap_kg=2,
        max_stint_laps=6,
        pit_laps=[6],
    )

    result = simulate_race_strategy(config)

    assert result['pit_laps'] == [6]
    assert result['laps'][5]['pit_stop'] is True
    assert result['laps'][5]['pit_loss_seconds'] == config.pit_loss_seconds
    assert result['laps'][6]['tire_age_laps'] == 0


@pytest.mark.parametrize(
    'values',
    [
        {'race_laps': 10, 'starting_fuel_kg': 5, 'fuel_burn_per_lap_kg': 1},
        {'strategy_mode': 'manual', 'race_laps': 10, 'starting_fuel_kg': 10, 'fuel_burn_per_lap_kg': 1, 'max_stint_laps': 5},
        {'strategy_mode': 'manual', 'race_laps': 10, 'starting_fuel_kg': 10, 'fuel_burn_per_lap_kg': 1, 'max_stint_laps': 10, 'pit_laps': [5, 4]},
        {'strategy_mode': 'manual', 'race_laps': 10, 'starting_fuel_kg': 10, 'fuel_burn_per_lap_kg': 1, 'max_stint_laps': 5, 'pit_laps': [4]},
    ],
)
def test_invalid_race_configurations_are_rejected(values: dict) -> None:
    with pytest.raises(ValidationError):
        RaceStrategyConfig(**values)
