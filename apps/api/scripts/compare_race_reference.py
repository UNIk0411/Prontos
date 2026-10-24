import argparse
import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.reference_analysis import analyze_race_reference


def parse_scenario_values(value: str) -> list[float]:
    try:
        parsed = [float(item.strip()) for item in value.split(',')]
    except ValueError as exc:
        raise argparse.ArgumentTypeError('Scenario values must be comma-separated numbers') from exc
    if not parsed or any(number < 0 for number in parsed):
        raise argparse.ArgumentTypeError('Scenario values must be non-negative numbers')
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Compare an exploratory strategy model sweep with observed historical pit laps.'
    )
    parser.add_argument(
        '--input',
        type=Path,
        default=Path('data/reference/2024_Bahrain_VER_laps.csv'),
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('data/reference/2024_Bahrain_VER_comparison.json'),
    )
    parser.add_argument('--pit-loss-seconds', type=parse_scenario_values, default=[18, 22, 26])
    parser.add_argument('--tire-wear-seconds-per-lap', type=parse_scenario_values, default=[0.03, 0.06, 0.09, 0.12])
    parser.add_argument('--max-stint-laps', type=int, default=35)
    args = parser.parse_args()

    if args.max_stint_laps < 1:
        parser.error('--max-stint-laps must be at least 1')
    if not args.input.is_file():
        parser.error(f'Input CSV does not exist: {args.input}')

    with args.input.open(newline='', encoding='utf-8-sig') as input_file:
        rows = list(csv.DictReader(input_file))
    report = analyze_race_reference(
        rows,
        pit_loss_scenarios=args.pit_loss_seconds,
        tire_wear_scenarios=args.tire_wear_seconds_per_lap,
        max_stint_laps=args.max_stint_laps,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    print(f'\nReport saved to {args.output}')


if __name__ == '__main__':
    main()
