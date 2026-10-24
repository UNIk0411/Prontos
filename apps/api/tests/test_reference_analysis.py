import pytest

from app.services.reference_analysis import analyze_race_reference


def test_reference_analysis_reports_stints_and_marks_comparison_unvalidated() -> None:
    rows = [
        {'lap_number': '1', 'lap_time_seconds': '90', 'stint_number': '1', 'tire_compound': 'SOFT', 'pit_out_lap': 'False'},
        {'lap_number': '2', 'lap_time_seconds': '92', 'stint_number': '1', 'tire_compound': 'SOFT', 'pit_out_lap': 'False'},
        {'lap_number': '3', 'lap_time_seconds': '110', 'stint_number': '2', 'tire_compound': 'HARD', 'pit_out_lap': 'True'},
        {'lap_number': '4', 'lap_time_seconds': '91', 'stint_number': '2', 'tire_compound': 'HARD', 'pit_out_lap': 'False'},
    ]

    report = analyze_race_reference(
        rows,
        pit_loss_scenarios=[22],
        tire_wear_scenarios=[0.06],
        max_stint_laps=3,
    )

    assert report['analysis_status'] == 'EXPLORATORY_NOT_VALIDATION'
    assert report['reference']['observed_pit_after_laps'] == [2]
    assert report['reference']['stints'][1]['median_lap_time_seconds_excluding_pit_out'] == 91
    assert len(report['strategy_scenarios']) == 1
    assert 'not evidence of predictive accuracy' in report['interpretation']


def test_reference_analysis_rejects_duplicate_laps() -> None:
    duplicate_rows = [
        {'lap_number': '1', 'lap_time_seconds': '90', 'stint_number': '1'},
        {'lap_number': '1', 'lap_time_seconds': '91', 'stint_number': '1'},
    ]

    with pytest.raises(ValueError, match='duplicate lap numbers'):
        analyze_race_reference(duplicate_rows, [22], [0.06])
