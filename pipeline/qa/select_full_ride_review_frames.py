"""Select real recorded frames for offline review; never launch or test the app.

Use only after the complete full-circuit trace and capture.json exist. This
creates a selection ledger, not a visual review or an acceptance result.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ref(path):
    path = path.resolve()
    try:
        name = path.relative_to(ROOT).as_posix()
    except ValueError:
        name = str(path)
    return dict(path=name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def select(trace_path, capture_path, output, m3_sections=False):
    if output.exists():
        raise FileExistsError(f"Preserve existing evidence: {output}")
    trace, capture = read(trace_path), read(capture_path)
    if not trace["scenario"].startswith("full-circuit-") or not trace["completed"]:
        raise ValueError("A completed full-circuit trace is required; no partial-run inference")
    if not capture["capture_complete"] or not trace["video_capture_complete"]:
        raise ValueError("Capture is incomplete; preserve its failure before selecting a repeat")
    if any(capture[k] for k in ("missing_frames", "failed_writes", "skipped_slots")):
        raise ValueError("Capture has missing frames, failed writes or skipped slots")
    if Path(trace["video_capture_directory"]).name != capture_path.parent.name:
        raise ValueError("Trace and capture directory identities differ")
    if abs(trace["seconds"] - capture["duration_seconds"]) > 1e-6:
        raise ValueError("Trace and capture duration differ")
    frames, samples = capture["frames"], trace["samples"]
    if len(frames) != capture["requested_frames"] or not all(f["saved"] for f in frames):
        raise ValueError("All requested actual frames must exist and be saved")
    if [f["index"] for f in frames] != list(range(len(frames))):
        raise ValueError("Frame indices are not complete and ordered")
    times = np.asarray([s["seconds"] for s in samples], float)
    frame_times = np.asarray([f["seconds"] for f in frames], float)
    xy = np.asarray([[s["east_cm"] / 100, s["north_cm"] / 100] for s in samples])
    chain = np.asarray([s["chainage_m"] for s in samples], float)
    if not all(np.isfinite(a).all() for a in (times, frame_times, xy, chain)):
        raise ValueError("Nonfinite recorded array")
    if np.any(np.diff(times) <= 0) or np.any(np.diff(frame_times) <= 0):
        raise ValueError("Recorded times must increase")
    paths = {
        "world": ROOT / "unreal/Content/WorldData/world.json",
        "runtime": ROOT / "data/derived/paved-circuit-runtime.json",
        "gates": ROOT / "manifests/maze-gate-blockouts.json",
        "underpasses": ROOT / "data/derived/underpass-openings.geojson",
        "junctions": ROOT / "data/routes/derived/city-branch-connections-reviewed.json",
    }
    world, runtime, gates = (read(paths[k]) for k in ("world", "runtime", "gates"))
    main = next(r for r in world["routes"] if r["id"] == "main_circuit")
    length = float(np.linalg.norm(np.diff(np.asarray(main["points"]), axis=0), axis=1).sum() / 100)
    source_s = np.asarray(runtime["chainage_source_m"])
    runtime_s = np.asarray(runtime["chainage_runtime_m"])
    if abs(runtime_s[-1] - length) > .001:
        raise ValueError("Runtime/source chainage map does not match current world")
    unwrapped = chain.copy()
    offset = 0.
    for i in range(1, len(chain)):
        if chain[i] - chain[i - 1] < -length / 2:
            offset += length
        elif chain[i] - chain[i - 1] > length / 2:
            offset -= length
        unwrapped[i] += offset
    # The full run stores samples once per second. Its final progress/time
    # aggregate is also a real observation and can occur after the last sample.
    # Use it for time interpolation only; never fabricate a position/sample row.
    chain_times, chain_values = times.copy(), unwrapped.copy()
    final_progress = float(trace["circuit_progress_m"])
    if not np.isfinite(final_progress):
        raise ValueError("Nonfinite final recorded progress")
    final_aggregate_used = bool(trace["seconds"] > times[-1] + 1e-9)
    if final_aggregate_used:
        if final_progress < unwrapped[-1] - .25:
            raise ValueError("Final progress is inconsistent with last recorded sample")
        chain_times = np.r_[chain_times, trace["seconds"]]
        chain_values = np.r_[chain_values, final_progress]
    if chain_values[-1] < length - .1:
        raise ValueError("Trace does not reach the closing seam")
    targets = []

    def add(group, label, seconds, method, source=None):
        if seconds < 0 or seconds > capture["duration_seconds"]:
            raise ValueError(f"Requested time outside capture: {group}/{label}")
        targets.append(dict(group=group, label=label, target_seconds=float(seconds),
                            selection_method=method, source=source))

    def chain_time(value):
        matches = []
        for i in np.flatnonzero((chain_values[:-1] <= value) & (chain_values[1:] >= value)):
            if chain_values[i + 1] <= chain_values[i]:
                continue
            fraction = (value - chain_values[i]) / (chain_values[i + 1] - chain_values[i])
            matches.append(float(chain_times[i] + fraction * (chain_times[i + 1] - chain_times[i])))
        if not matches or max(matches) - min(matches) > 2:
            raise ValueError(f"Missing/ambiguous runtime chainage crossing: {value}; {matches}")
        return matches[0]

    def source_target(group, label, station):
        distance = float(np.interp(station, source_s, runtime_s))
        add(group, label, chain_time(distance),
            "Source chainage mapped to saved runtime chainage; time interpolated from real trace samples and final recorded progress aggregate when needed.",
            dict(source_chainage_m=station, runtime_chainage_m=distance))

    for label, t in (("begin", frame_times[0]), ("middle", trace["seconds"] / 2), ("end", frame_times[-1])):
        add("whole_run_context", label, t, "First, elapsed-time midpoint, or last existing recorded frame.")
    if m3_sections:
        paths['m3_sections'] = ROOT / 'manifests/seawall-m3-sections.json'
        registry = read(paths['m3_sections'])
        if registry['route_sha256'] != ref(paths['runtime'])['sha256']:
            raise ValueError('M3 registry route source differs')
        if abs(registry['route_length_m'] - length) > .001:
            raise ValueError('M3 runtime section length differs')
        for section in registry['sections']:
            for label, station in [('midpoint', section['view_station_m']),
                                   ('boundary', section['boundary_station_m'])]:
                # M3 stations are accumulated runtime polyline lengths, not
                # source chainages. No second mapping is applicable.
                moment = chain_time(station) if station > 0 else float(frame_times[0])
                for phase, delta in [('before', -1.), ('at', 0.), ('after', 1.)]:
                    add('m3_'+section['id'], label+'_'+phase,
                        min(float(frame_times[-1]), max(float(frame_times[0]), moment+delta)),
                        'M3 runtime station crossing interpolated from the real trace; select actual recorded frames around it.',
                        dict(runtime_chainage_m=station, section_start_m=section['start_m'],
                             section_end_m=section['end_m'], offset_seconds=delta))
    for site in gates["sites"]:
        centre = float(np.interp(site["source_station_m"], source_s, runtime_s))
        eligible = np.asarray([
            s["physical_gate_guide"] and s["route_distance_reference"] == site["id"]
            for s in samples
        ]) & (np.abs(unwrapped - centre) < 60)
        if eligible.sum() < 2:
            raise ValueError(f"Missing actual gate-guide samples: {site['id']}")
        posts = np.asarray([p["xy"] for p in site["grounded_posts"]], float)
        if site["kind"] == "double":
            planes = []
            for row, a, b in (("row_A", posts[0], posts[1]), ("row_B", posts[2], posts[3])):
                axis = b - a
                planes.append((row, a, np.array([-axis[1], axis[0]]) / np.linalg.norm(axis)))
            form = "Actual two transverse rows; plane through each pair of authored post centres."
        elif site["kind"] == "divider":
            a, b = np.asarray(site["source_divider_xy_m"], float)
            axis = (b - a) / np.linalg.norm(b - a)
            planes = [("divider_end_0_with_return", a, axis), ("divider_end_1", b, axis)]
            form = "Long divider with short return, not two maze rows. Planes transverse to divider at its ends."
        else:
            raise ValueError(f"Unsupported actual gate form: {site['kind']}")
        for label, anchor, normal in planes:
            distances = (xy - anchor) @ normal
            crossings = []
            for i in np.flatnonzero(eligible[:-1] & eligible[1:] & (distances[:-1] * distances[1:] <= 0)):
                if abs(distances[i + 1] - distances[i]) < 1e-9:
                    continue
                alpha = -distances[i] / (distances[i + 1] - distances[i])
                point = xy[i] + alpha * (xy[i + 1] - xy[i])
                if np.linalg.norm(point - anchor) > 6:
                    continue
                crossings.append(dict(seconds=float(times[i] + alpha * (times[i + 1] - times[i])),
                                      xy_m=point.tolist(), trace_sample_indices=[int(i), int(i + 1)]))
            if len(crossings) != 1:
                raise ValueError(f"Gate plane requires explicit review: {site['id']}/{label}: {crossings}")
            crossing = crossings[0]
            for phase, dt in (("before", -2.), ("at", 0.), ("after", 2.)):
                add(f"gate_{site['id']}", f"{label}_{phase}", crossing["seconds"] + dt,
                    "Actual trace actor-centre crossing of source-derived plane; select real frame before/at/after.",
                    dict(form=form, plane_anchor_xy_m=anchor.tolist(), plane_normal_xy=normal.tolist(),
                         **crossing, offset_seconds=dt))
        idx = np.flatnonzero(eligible)
        add(f"gate_{site['id']}", "guide_entry", times[idx[0]], "First actual trace sample on this physical guide.")
        add(f"gate_{site['id']}", "guide_exit", times[idx[-1]], "Last actual trace sample on this physical guide.")
    for feature in read(paths["underpasses"])["features"]:
        p = feature["properties"]
        stations = (("approach", p["source_start_m"] - 6), ("roof_entry", p["roof_source_start_m"]),
                    ("inside", (p["roof_source_start_m"] + p["roof_source_end_m"]) / 2),
                    ("roof_exit", p["roof_source_end_m"]), ("depart", p["source_end_m"] + 6))
        for label, station in stations:
            source_target(f"underpass_{p['id']}", label, station)
    junction = next(j for j in read(paths["junctions"])["main_circuit_junction_reviews"]
                    if j["junction_id"] == "city_junction_041")
    if junction["connection_status"] != "grade_separated_no_transfer":
        raise ValueError("041 source status changed; review source binding")
    source_target("underpass_Chilco", "junction_041_below_road", junction["source_circuit_station_m"])
    seam_time = chain_time(length)
    for label, t in (("before", max(0., seam_time - 2)), ("at", seam_time),
                     ("after_or_last_available", min(seam_time + 2, frame_times[-1]))):
        add("closing_seam", label, t, "Unwrapped real trace reaches full runtime length; after view limited by actual last capture.",
            dict(runtime_length_m=length, seam_seconds=seam_time,
                 last_frame_minus_seam_seconds=float(frame_times[-1] - seam_time)))
    selected = {}
    for target in targets:
        index = int(np.argmin(np.abs(frame_times - target["target_seconds"])))
        frame = frames[index]
        if index not in selected:
            path = capture_path.parent / frame["file"]
            if not path.is_file():
                raise FileNotFoundError(path)
            sample_index = int(np.argmin(np.abs(times - frame["seconds"])))
            selected[index] = dict(**ref(path), index=frame["index"], seconds=frame["seconds"],
                                   nearest_trace_sample_index=sample_index,
                                   nearest_trace_sample=samples[sample_index],
                                   visual_review_status="Not yet opened by this selector", targets=[])
        selected[index]["targets"].append(dict(**target,
            actual_frame_minus_target_seconds=float(frame["seconds"] - target["target_seconds"])))
    result = dict(schema_version=1, scope="Real-frame selection only. No visual review or acceptance is inferred.",
        inputs=dict(trace=ref(trace_path), capture=ref(capture_path), **{k: ref(v) for k, v in paths.items()}),
        source_binding_limit="Current source hashes are retained. Full v27 traces do not embed a world-file hash; bind the packaged run to its build record separately.",
        runtime_length_m=length, trace_full_circuit_check_pass=trace.get("full_circuit_check_pass"),
        trace_endpoint_aggregate=dict(seconds=trace["seconds"], progress_m=final_progress,
            used_for_chainage_time_interpolation=final_aggregate_used,
            last_position_sample_seconds=float(times[-1]),
            limit="Actual final aggregate only; no position or speed sample is fabricated."),
        source_gate_count=len(gates["sites"]), target_count=len(targets), selected_frame_count=len(selected),
        frames=[selected[k] for k in sorted(selected)],
        limits=["Interpolated actor-centre times are not complete bicycle swept-volume measurements.",
                "Gate dimensions remain recorded source estimates.",
                "Closing-seam after view may precede exact stop or provide less than2s follow-through.",
                "Open and assess each selected full image before recording a visual result."])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return dict(output=str(output), sha256=ref(output)["sha256"], selected_frame_count=len(selected), target_count=len(targets))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("capture", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--m3-sections", action="store_true",
                        help="Also select real before/at/after frames for every M3 midpoint and boundary")
    args = parser.parse_args()
    print(json.dumps(select(args.trace.resolve(), args.capture.resolve(), args.output.resolve(), args.m3_sections), indent=2))
