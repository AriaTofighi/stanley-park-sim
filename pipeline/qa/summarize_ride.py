"""Summarize retained ride traces. This script does not run the application."""
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def percentiles(values):
    values = sorted(float(v) for v in values if v is not None and math.isfinite(v))
    if not values:
        return None
    def quantile(q):
        p = q * (len(values) - 1)
        lo = int(p)
        return values[lo] + (values[min(lo + 1, len(values) - 1)] - values[lo]) * (p - lo)
    return dict(count=len(values), p50=quantile(.5), p95=quantile(.95),
                p99=quantile(.99), maximum=values[-1])


def summarize(path):
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    frames = data["observed_frame_ms"]
    streak = longest = 0
    for value in frames:
        streak = streak + 1 if value > 25 else 0
        longest = max(streak, longest)
    result = {k: v for k, v in data.items()
              if k not in ("observed_frame_ms", "engine_timings_ms", "samples")}
    result.update(trace=str(path.relative_to(ROOT)),
                  trace_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  tick_intervals_ms=percentiles(frames),
                  frames_above_50_ms=sum(v > 50 for v in frames),
                  longest_streak_above_25_ms=longest,
                  timing_limit="Tick intervals are not external presentation measurements. Blockout runs do not replace the representative scene benchmark. Video capture and concurrent editor work must be reported separately.")
    timing = data.get("engine_timings_ms", [])
    result["engine_counters_ms"] = {
        key: percentiles(row.get(key) for row in timing)
        for key in ("game_ms", "render_ms", "rhi_ms", "gpu_ms")}
    result["whole_route_accepted"] = False
    result["representative_performance_accepted"] = False
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = summarize(args.trace.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
