import argparse
import csv
import json
import re
from statistics import median
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_BASE = 'https://api.openf1.org/v1'


def fetch_json(endpoint: str, parameters: dict[str, str | int]) -> list[dict]:
    url = f'{API_BASE}/{endpoint}?{urlencode(parameters)}'
    request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'PRONTOS-race-reference-demo/1.0'})
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        raise RuntimeError(f'OpenF1 request failed with HTTP {exc.code}: {endpoint}') from exc
    except URLError as exc:
        raise RuntimeError(f'Could not reach OpenF1 for {endpoint}: {exc.reason}') from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'OpenF1 returned invalid JSON for {endpoint}') from exc

    if not isinstance(payload, list):
        raise RuntimeError(f'OpenF1 returned an unexpected response for {endpoint}')
    return payload


def safe_filename_part(value: str) -> str:
    normalized = re.sub(r'[^A-Za-z0-9_-]+', '_', value.strip()).strip('_')
    if not normalized:
        raise ValueError('Event and driver names must contain letters or numbers')
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Download and summarize one historical race driver’s lap timing and tire stints.'
    )
    parser.add_argument('--year', type=int, default=2024)
    parser.add_argument('--event', default='Bahrain', help='OpenF1 country_name, for example Bahrain')
    parser.add_argument('--session', default='Race')
    parser.add_argument('--driver', default='VER', help='Driver acronym or number, for example VER or 1')
    parser.add_argument(
        '--output',
        type=Path,
        help='CSV destination (defaults to data/reference/<year>_<event>_<driver>_laps.csv)',
    )
    args = parser.parse_args()

    sessions = fetch_json('sessions', {
        'year': args.year,
        'country_name': args.event,
        'session_name': args.session,
    })
    if len(sessions) != 1:
        raise RuntimeError(
            f'Expected one session for {args.year} {args.event} {args.session}; found {len(sessions)}'
        )
    session = sessions[0]
    session_key = session['session_key']

    drivers = fetch_json('drivers', {'session_key': session_key})
    driver = next((
        row for row in drivers
        if str(row.get('driver_number')) == args.driver
        or str(row.get('name_acronym', '')).upper() == args.driver.upper()
    ), None)
    if driver is None:
        available = ', '.join(sorted(
            str(row.get('name_acronym'))
            for row in drivers
            if row.get('name_acronym')
        ))
        raise RuntimeError(f'Driver {args.driver} not found. Available acronyms: {available}')

    parameters = {
        'session_key': session_key,
        'driver_number': driver['driver_number'],
    }
    laps = fetch_json('laps', parameters)
    stints = fetch_json('stints', parameters)
    timed_laps = [
        lap for lap in laps
        if lap.get('lap_number') is not None
        and isinstance(lap.get('lap_duration'), (int, float))
        and lap['lap_duration'] > 0
    ]
    if not timed_laps:
        raise RuntimeError(
            f'No timed laps found for {driver["name_acronym"]} in {args.year} {args.event} {args.session}'
        )

    timed_laps.sort(key=lambda lap: lap['lap_number'])
    output_rows = []
    for lap in timed_laps:
        stint = next((
            row for row in stints
            if row.get('lap_start') is not None
            and row.get('lap_end') is not None
            and row['lap_start'] <= lap['lap_number'] <= row['lap_end']
        ), {})
        output_rows.append({
            'lap_number': lap['lap_number'],
            'lap_time_seconds': lap['lap_duration'],
            'sector_1_seconds': lap.get('duration_sector_1'),
            'sector_2_seconds': lap.get('duration_sector_2'),
            'sector_3_seconds': lap.get('duration_sector_3'),
            'pit_out_lap': lap.get('is_pit_out_lap'),
            'stint_number': stint.get('stint_number'),
            'tire_compound': stint.get('compound'),
            'tire_age_at_start_laps': stint.get('tyre_age_at_start'),
        })

    output_path = args.output or Path(
        'data/reference/'
        f'{args.year}_{safe_filename_part(args.event)}_{safe_filename_part(driver["name_acronym"])}_laps.csv'
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', newline='', encoding='utf-8') as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)

    lap_times = [row['lap_time_seconds'] for row in output_rows]
    print(json.dumps({
        'source': 'OpenF1 historical API',
        'session': {
            'year': args.year,
            'event': session.get('meeting_key'),
            'country': session.get('country_name'),
            'circuit': session.get('circuit_short_name'),
            'session_name': session.get('session_name'),
            'session_key': session_key,
        },
        'driver': {
            'name': driver.get('full_name'),
            'acronym': driver.get('name_acronym'),
            'number': driver.get('driver_number'),
            'team': driver.get('team_name'),
        },
        'timed_lap_count': len(lap_times),
        'fastest_lap_seconds': round(min(lap_times), 3),
        'median_lap_seconds': round(median(lap_times), 3),
        'lap_data_csv': str(output_path),
        'strategy_model_comparison': {
            'status': 'NOT_PERFORMED',
            'reason': (
                'Historical timing alone does not provide calibrated strategy inputs or account for '
                'traffic, fuel, weather, incidents, and race context; comparing it directly to this '
                'prototype would not validate the model.'
            ),
        },
        'data_notice': (
            'OpenF1 is an unofficial community API. Its free historical data is intended for '
            'educational and research use; check its current terms before other use or redistribution.'
        ),
    }, indent=2))


if __name__ == '__main__':
    main()
