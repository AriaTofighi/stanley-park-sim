"""Read retained normalized Get-Counter rows. Does not sample or run the app."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

PID = re.compile(r"(?:^|[(_])pid_(\d+)(?=_|[)\\]|$)", re.IGNORECASE)
COUNTER = re.compile(r"\\gpu process memory\(([^)]+)\)\\dedicated usage$", re.IGNORECASE)
STATUS_SOURCE = "https://learn.microsoft.com/en-us/windows/win32/perfctrs/pdh-error-codes"


def utc(value):
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset")
    return result.astimezone(timezone.utc)


def iso(value):
    return value.isoformat().replace("+00:00", "Z") if value else None


def summarize(path, pid, start=None, end=None):
    raw = path.read_bytes()
    if path.suffix.lower() == ".csv":
        rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    else:
        rows = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(rows, list):
        raise ValueError("input must be a JSON array or normalized CSV rows")
    groups, rejected, excluded = {}, [], []
    for index, row in enumerate(rows):
        try:
            if not isinstance(row, dict):
                raise ValueError("row is not an object")
            pids = {int(value) for key in ("path", "instance")
                    for value in PID.findall(str(row.get(key, "")))}
            if len(pids) != 1:
                raise ValueError("path/instance PID is absent or inconsistent")
            if pid not in pids:
                excluded.append(index)
                continue
            stamp = utc(row["timestamp_utc"])
            group = groups.setdefault(stamp, {"rows": [], "instances": {}, "errors": []})
            group["rows"].append(index)
            match = COUNTER.search(str(row["path"]).strip())
            if not match:
                raise ValueError("path is not GPU Process Memory / Dedicated Usage")
            instance = match[1].lower()
            if instance != str(row["instance"]).strip().lower():
                raise ValueError("counter path and instance do not agree")
            if instance in group["instances"]:
                raise ValueError("duplicate instance at one sample timestamp")
            status_text = str(row["status"]).strip()
            status = int(status_text, 16 if status_text.lower().startswith("0x") else 10)
            if status not in (0, 1):
                raise ValueError(f"invalid PDH CStatus: {status}")
            value = float(row["value_bytes"])
            if isinstance(row["value_bytes"], bool) or not math.isfinite(value) or value < 0:
                raise ValueError("value_bytes must be a finite nonnegative byte count")
            group["instances"][instance] = value
        except (ValueError, TypeError, KeyError) as exc:
            rejected.append({"row_index": index, "reason": str(exc)})
            # Keep invalid target rows attached to their timestamp when known.
            for group in groups.values():
                if index in group["rows"]:
                    group["errors"].append(str(exc))
                    break
    selected = {stamp: group for stamp, group in groups.items()
                if (start is None or stamp >= start) and (end is None or stamp <= end)}
    expected = set().union(*(set(group["instances"]) for group in selected.values())) if selected else set()
    samples = []
    for stamp, group in sorted(selected.items()):
        missing = sorted(expected - group["instances"].keys())
        valid = bool(expected) and not missing and not group["errors"]
        samples.append({"timestamp_utc": iso(stamp), "raw_row_indices": group["rows"],
                        "instances_bytes": group["instances"], "missing_instances": missing,
                        "errors": group["errors"], "complete_valid_sample": valid,
                        "total_bytes": sum(group["instances"].values()) if valid else None})
    totals = [sample["total_bytes"] for sample in samples if sample["complete_valid_sample"]]
    all_times = sorted(groups)
    times = sorted(selected)
    bracketed = bool(all_times) and (start is None or all_times[0] <= start) and (end is None or all_times[-1] >= end)
    all_valid = bool(samples) and all(sample["complete_valid_sample"] for sample in samples) and not rejected
    peak = max(totals) if totals else None
    return {
        "scope": "Offline Windows GPU Process Memory / Dedicated Usage samples for one exact PID; not adapter-wide memory, GPU budget, continuous peak, or proof of no paging.",
        "input": str(path), "input_sha256": hashlib.sha256(raw).hexdigest(), "pid": pid,
        "measured_start_utc": iso(start), "measured_end_utc": iso(end),
        "all_input_first_sample_utc": iso(all_times[0]) if all_times else None,
        "all_input_last_sample_utc": iso(all_times[-1]) if all_times else None,
        "measurement_bracketed_by_samples": bracketed,
        "available": bool(totals), "all_selected_samples_valid": all_valid,
        "usable_for_requested_window": bool(totals) and all_valid and bracketed,
        "selected_sample_count": len(samples), "complete_valid_sample_count": len(totals),
        "maximum_selected_sample_gap_seconds": max(((b-a).total_seconds() for a, b in zip(times, times[1:])), default=None),
        "sampled_peak_dedicated_bytes": peak,
        "sampled_peak_dedicated_gib": peak / 1024**3 if peak is not None else None,
        "expected_distinct_instances": sorted(expected), "excluded_other_pid_row_indices": excluded,
        "rejected_rows": rejected, "samples": samples, "raw_rows": rows,
        "status_source": STATUS_SOURCE, "valid_pdh_status_values": [0, 1],
        "limits": "Empty or invalid data is unavailable, never zero. Instances are summed only within the same exact sample timestamp. Missing or duplicate instances invalidate that sample. The observed in-window instance union is a conservative consistency check, not proof that Windows reported every adapter. One-second sampling can miss peaks. PID identity must be linked separately to the packaged process and launch; PID reuse is not detectable in these rows. No automatic budget acceptance."
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--start", help="Inclusive measured UTC timestamp (ISO 8601).")
    parser.add_argument("--end", help="Inclusive measured UTC timestamp (ISO 8601).")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        start, end = utc(args.start) if args.start else None, utc(args.end) if args.end else None
        if args.pid <= 0 or (start and end and end < start):
            raise ValueError("PID must be positive and end must not precede start")
        if args.output.resolve() == args.input.resolve():
            raise ValueError("output must not overwrite the source rows")
        result = summarize(args.input.resolve(), args.pid, start, end)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("available", "usable_for_requested_window",
          "selected_sample_count", "sampled_peak_dedicated_gib")}))


if __name__ == "__main__":
    main()
