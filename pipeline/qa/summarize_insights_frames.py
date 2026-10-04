"""Summarize exported Unreal frame intervals and explicit thread-idle scopes.

This is offline analysis. It neither starts nor controls the game. Input comes
from scripts/export-insights-timing.ps1 using UE 5.8's supported export command.
"""
import argparse
import bisect
import csv
import fnmatch
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

IDLE_TIMER = "FThreadIdleStats::FScopeIdle"
FRAME_THREADS = {"Game Frames": "GameThread", "Rendering Frames": "RenderThread*"}


def merge_intervals(intervals):
    """Return a union: nested scopes and overlapping idle markers count once."""
    merged = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return merged


class Intervals:
    def __init__(self, intervals):
        self.values = merge_intervals(intervals)
        self.ends = [end for _, end in self.values]

    def overlap(self, start, end):
        total = 0.0
        index = bisect.bisect_right(self.ends, start)
        while index < len(self.values) and self.values[index][0] < end:
            left, right = self.values[index]
            total += max(0.0, min(right, end) - max(left, start))
            index += 1
        return total


def percentiles(values):
    ordered = sorted(value for value in values if value is not None)
    if not ordered:
        return None

    def quantile(fraction):
        rank = fraction * (len(ordered) - 1)
        low = int(rank)
        return ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (rank - low)

    streak = longest = 0
    for value in values:
        streak = streak + 1 if value is not None and value > 25 else 0
        longest = max(longest, streak)
    return {"count": len(ordered), "p50_ms": quantile(.5), "p95_ms": quantile(.95),
            "p99_ms": quantile(.99), "max_ms": ordered[-1],
            "frames_above_50_ms": sum(value > 50 for value in ordered),
            "longest_streak_above_25_ms": longest}


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        yield from csv.DictReader(source)


def summarize(events_path, timers_path, metadata, start, end):
    all_events = defaultdict(list)
    idle_events = defaultdict(list)
    frames = defaultdict(list)
    thread_names = {}
    invalid_rows = []
    clipped_frame_rows = 0
    idle_timer_defined = any(row.get("Name") == IDLE_TIMER for row in read_csv(timers_path))
    event_count = 0
    for index, row in enumerate(read_csv(events_path), 2):
        event_count += 1
        try:
            begin, finish = float(row["StartTime"]), float(row["EndTime"])
            if not math.isfinite(begin) or not math.isfinite(finish) or finish < begin:
                raise ValueError("non-finite or reversed event interval")
            thread_id = int(row["ThreadId"])
            name = row["ThreadName"]
            if name in FRAME_THREADS:
                # A boundary frame is excluded, never truncated into a short
                # frame. Frame index comes from the pseudo-thread TimerId.
                if begin >= start and finish <= end:
                    frames[name].append((int(row["TimerId"]), begin, finish))
                else:
                    clipped_frame_rows += 1
            else:
                if thread_id in thread_names and thread_names[thread_id] != name:
                    raise ValueError("one thread id has inconsistent names")
                thread_names[thread_id] = name
                if finish > start and begin < end:
                    all_events[thread_id].append((begin, finish))
                    if row["TimerName"] == IDLE_TIMER:
                        idle_events[thread_id].append((begin, finish))
        except (KeyError, ValueError, TypeError) as error:
            invalid_rows.append({"csv_line": index, "reason": str(error)})

    per_frame = []
    groups = {}
    for frame_track, pattern in FRAME_THREADS.items():
        frame_rows = sorted(frames[frame_track], key=lambda frame: frame[1])
        matched = [thread_id for thread_id, name in thread_names.items() if fnmatch.fnmatchcase(name, pattern)]
        # Separate actual threads. Never sum multiple thread timelines and call
        # that elapsed rendering time; parallel workers are outside this scope.
        group = {"frame_track": frame_track, "complete_frame_count": len(frame_rows),
                 "thread_ids": matched, "threads": {}, "frame_index_gaps": [],
                 "overlapping_frames": 0,
                 "frame_envelope": percentiles([(finish - begin) * 1000 for _, begin, finish in frame_rows])}
        for previous, current in zip(frame_rows, frame_rows[1:]):
            if current[0] != previous[0] + 1:
                group["frame_index_gaps"].append([previous[0], current[0]])
            if current[1] < previous[2] - .000001:
                group["overlapping_frames"] += 1
        for thread_id in matched:
            covered = Intervals(all_events[thread_id])
            idle = Intervals(idle_events[thread_id])
            rows = []
            for frame_id, begin, finish in frame_rows:
                duration = finish - begin
                coverage = covered.overlap(begin, finish)
                idle_time = idle.overlap(begin, finish) if idle_timer_defined else None
                value = {
                    "frame_track": frame_track, "frame_id": frame_id,
                    "thread_id": thread_id, "thread_name": thread_names[thread_id],
                    "start_trace_seconds": begin, "end_trace_seconds": finish,
                    "frame_envelope_ms": duration * 1000,
                    "instrumented_scope_union_ms": coverage * 1000,
                    "explicit_idle_ms": idle_time * 1000 if idle_time is not None else None,
                    "frame_minus_explicit_idle_ms": max(0.0, duration - idle_time) * 1000 if idle_time is not None else None,
                    "instrumented_scope_minus_idle_ms": max(0.0, coverage - idle_time) * 1000 if idle_time is not None else None,
                    "uncovered_frame_ms": max(0.0, duration - coverage) * 1000,
                }
                rows.append(value)
            per_frame.extend(rows)
            group["threads"][str(thread_id)] = {
                "name": thread_names[thread_id],
                "exported_scope_count": len(all_events[thread_id]),
                "explicit_idle_scope_count": len(idle_events[thread_id]),
                **{metric: percentiles([row[metric] for row in rows]) for metric in (
                    "frame_minus_explicit_idle_ms", "explicit_idle_ms",
                    "instrumented_scope_union_ms", "instrumented_scope_minus_idle_ms", "uncovered_frame_ms")},
            }
        groups[frame_track] = group

    return {
        "scope": "Offline Unreal Insights frame envelopes and same-thread explicit-idle subtraction. The exact selected interval is trace-relative.",
        "start_trace_seconds": start, "end_trace_seconds": end,
        "export_metadata": metadata,
        "events_csv": str(events_path), "events_sha256": hashlib.sha256(events_path.read_bytes()).hexdigest(),
        "timers_csv": str(timers_path), "timers_sha256": hashlib.sha256(timers_path.read_bytes()).hexdigest(),
        "exported_event_rows": event_count, "excluded_boundary_frames": clipped_frame_rows,
        "invalid_event_rows": invalid_rows,
        "idle_timer": IDLE_TIMER, "idle_timer_observed_in_trace": idle_timer_defined,
        "percentile_method": "Linear interpolation at rank (n-1)*p; milliseconds.",
        "groups": groups,
        "frame_data_available": all(group["complete_frame_count"] and group["thread_ids"] for group in groups.values()),
        "performance_budget_pass": None,
        "limits": [
            "Frame envelope is elapsed time between Unreal frame markers, including waits. It is not display presentation time.",
            "Frame-minus-explicit-idle removes the union of FThreadIdleStats::FScopeIdle intervals on the corresponding CPU thread. It still includes scheduling delays, unknown waits and uninstrumented work; it is not OS CPU execution time.",
            "Instrumented-scope-minus-idle counts the interval union of exported scopes, not a sum of nested durations. Uninstrumented gaps are reported separately.",
            "Idle subtraction is unavailable when the idle timer is absent from the trace. Enable threadidlescope with cpu and frame channels. Missing data is never zero work.",
            "Game and render frames have different boundaries and can overlap. Their times must not be added. Parallel rendering workers and GPU queues are not part of these CPU-thread measures.",
            "The explicit interval must be checked against map loading and the desired scenario. No automatic warm-up inference or performance-budget acceptance is made.",
            "Trace capture adds overhead. A stationary sample does not establish full-route performance or an external frame-presentation result.",
        ],
    }, per_frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--timers", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--end", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not (math.isfinite(args.start) and math.isfinite(args.end) and 0 <= args.start < args.end):
        parser.error("use finite trace-relative bounds with 0 <= start < end")
    if args.end - args.start > 60:
        parser.error("use an interval of at most 60 seconds")
    frame_path = args.output.with_suffix(".frames.csv")
    if args.output.exists() or frame_path.exists():
        parser.error("choose a new output name to preserve earlier evidence")
    metadata = json.loads(args.metadata.read_text(encoding="utf-8-sig"))
    if args.start < metadata["trace_start_seconds"] or args.end > metadata["trace_end_seconds"]:
        parser.error("summary bounds must be within the exported trace interval")
    summary, rows = summarize(args.events.resolve(), args.timers.resolve(), metadata, args.start, args.end)
    summary["per_frame_csv"] = str(frame_path.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        with frame_path.open("w", encoding="utf-8", newline="") as destination:
            writer = csv.DictWriter(destination, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    args.output.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"summary": str(args.output), "frame_data_available": summary["frame_data_available"],
                      "idle_timer_observed_in_trace": summary["idle_timer_observed_in_trace"]}))


if __name__ == "__main__":
    main()
