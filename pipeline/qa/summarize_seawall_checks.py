"""Summarize saved short-ride evidence. Does not start or control the application."""
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def distribution(values):
    ordered = sorted(values)
    def percentile(p):
        position = (len(ordered) - 1) * p
        lo = math.floor(position)
        hi = math.ceil(position)
        return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)
    longest = current = 0
    for value in values:
        current = current + 1 if value > 50 else 0
        longest = max(longest, current)
    return dict(count=len(values), p50=percentile(.5), p95=percentile(.95),
                p99=percentile(.99), maximum=max(values), above_50_ms=sum(v > 50 for v in values),
                longest_consecutive_above_50_ms=longest)


def summarize(path):
    record = json.loads(path.read_text())
    timings = record['engine_timings_ms']
    keys = ('scenario', 'scenario_start_chainage_m', 'seconds', 'distance_m',
            'maximum_speed_kmh', 'maximum_route_distance_m', 'frames_without_surface',
            'surface_misses', 'brake_end_speed_kmh', 'blocking_contacts',
            'dropped_simulation_seconds', 'short_controller_check_pass',
            'video_capture_requested', 'video_capture_complete', 'video_capture_directory',
            'render_settings', 'ride_settings', 'timing_method', 'scenario_setup_ms')
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                **{key: record.get(key) for key in keys},
                process_working_set_gib=record['process_working_set_bytes'] / 2**30,
                process_peak_working_set_gib=record['process_peak_working_set_bytes'] / 2**30,
                frame_ms=distribution(record['observed_frame_ms']),
                engine_ms={key: distribution([row[key] for row in timings]) for key in timings[0]})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('records', nargs='+')
    args = parser.parse_args()
    result = dict(scope='Bounded PIE section checks. Engine counters are not display timing. '
                        'Recording runs include readback overhead. No full-route or release acceptance.',
                  checks=[summarize(ROOT / path) for path in args.records])
    (ROOT / args.output).write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result, indent=2))
