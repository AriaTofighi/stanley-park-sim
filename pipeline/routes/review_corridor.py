"""Locate source-route risks. No path correction or access boundary is inferred.

Compare the same City centreline against two resolutions of one historic DTM.
The samples are correlated references, not two independent surveys. The 3 m
cross section is a diagnostic footprint, not a measured usable path width.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "tmp/matplotlib"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import RegularGridInterpolator
from shapely.geometry import LineString

OUT = ROOT / "evidence/corridor"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sampler(path):
    grid = np.load(path)
    sample = RegularGridInterpolator((grid["y"], grid["x"]), grid["z"],
                                     bounds_error=False, fill_value=np.nan)
    return lambda xy: sample(xy[:, ::-1])


def camera(target, tangent):
    # The outer/right side of the counter-clockwise circuit is a useful view.
    side = np.array([tangent[1], -tangent[0]])
    eye = np.array(target) + np.r_[35 * side - 20 * tangent, 20]
    direction = np.array(target) - eye
    yaw = math.degrees(math.atan2(direction[0], direction[1]))
    pitch = math.degrees(math.atan2(direction[2], np.linalg.norm(direction[:2])))
    args = {"toolset_name": "EditorToolset.EditorAppToolset", "tool_name": "SetCameraTransform",
            "arguments": {"transform": {
                "location": {"x": float(eye[1]*100), "y": float(eye[0]*100), "z": float(eye[2]*100)},
                "rotation": {"pitch": pitch, "yaw": yaw, "roll": 0},
                "scale": {"x": 1, "y": 1, "z": 1}}}}
    return dict(target_local_m=target, eye_local_m=eye.tolist(), unreal_mcp=args)


def plot_profiles(s, h1, h2, grade1, grade2, cross, issues):
    fig, axes = plt.subplots(3, 1, figsize=(15, 10), sharex=True, constrained_layout=True)
    axes[0].plot(s, h2, label="2 m blockout grid", linewidth=.8, color="#98642a")
    axes[0].plot(s, h1, label="1 m review grid", linewidth=.8, color="#21597b")
    axes[0].set_ylabel("CGVD2013 height (m)")
    axes[0].legend(loc="upper right")
    axes[1].plot(s, 100*grade2, linewidth=.7, label="2 m grid", color="#98642a")
    axes[1].plot(s, 100*grade1, linewidth=.7, label="1 m grid", color="#21597b")
    axes[1].axhline(18, color="#b33232", linestyle="--", label="Review threshold")
    axes[1].set_ylabel("Absolute centreline grade (%)")
    axes[2].plot(s, 100*cross, linewidth=.7, color="#21597b")
    axes[2].axhline(12, color="#b33232", linestyle="--")
    axes[2].set_ylabel("Cross-slope in 3 m probe (%)")
    axes[2].set_xlabel("Distance from declared entrance along source circuit (m)")
    for ax in axes:
        ax.grid(alpha=.2)
        ax.set_xlim(0, s[-1])
    for issue in sorted(issues, key=lambda v: v["priority_score"], reverse=True)[:8]:
        axes[0].annotate(issue["issue_id"],
            (issue["peak_chainage_m"], issue["target_local_m"][2]), xytext=(0, 16),
            textcoords="offset points", fontsize=7, rotation=35)
    fig.suptitle("Whole-circuit source review — no corrections applied\n"
                 "Both grids use the 2013 DTM. Thresholds identify risks; they are not survey acceptance limits.")
    fig.savefig(OUT / "route-source-profiles.png", dpi=140)
    plt.close(fig)


def main():
    paths = {"routes": ROOT / "data/routes/derived/park_routes.json",
             "reference_1m": ROOT / "data/derived/terrain_corridor_reference.npz",
             "blockout_2m": ROOT / "data/derived/terrain_park.npz"}
    routes = json.loads(paths["routes"].read_text())
    line = LineString(np.asarray(routes["main_circuit"]["xyz_local_m"])[:, :2])
    s = np.linspace(0, line.length, math.ceil(line.length) + 1)
    xy = np.array([line.interpolate(v).coords[0] for v in s])
    tangent = np.gradient(xy, s, axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    left = np.column_stack((-tangent[:, 1], tangent[:, 0]))
    sample1, sample2 = sampler(paths["reference_1m"]), sampler(paths["blockout_2m"])
    h1, h2 = sample1(xy), sample2(xy)
    sides = np.column_stack([sample1(xy + offset * left) for offset in (-1.5, 1.5)])
    if not np.isfinite(np.column_stack((h1, h2, sides))).all():
        raise RuntimeError("Missing DTM samples on the circuit/probe: review coverage before risk scoring")
    grade1, grade2 = np.abs(np.gradient(h1, s)), np.abs(np.gradient(h2, s))
    cross = np.abs(sides[:, 1] - sides[:, 0]) / 3
    score = np.maximum(grade1 / .18, cross / .12)
    flagged = np.flatnonzero(score > 1)
    groups = np.split(flagged, np.flatnonzero(np.diff(s[flagged]) > 30) + 1) if len(flagged) else []
    edge_by_id = {e["edge_id"]: e for e in routes["edges"]}
    edge_ends = np.cumsum([LineString(edge_by_id[e["edge_id"]]["coordinates_local_xy_m"]).length
                          for e in routes["main_circuit"]["ordered_edges"]])
    issues = []
    for group in groups:
        first, last = max(0, int(group[0])-10), min(len(s)-1, int(group[-1])+10)
        peak = int(group[np.argmax(score[group])])
        edge_index = min(int(np.searchsorted(edge_ends, s[peak])), len(edge_ends)-1)
        edge_id = routes["main_circuit"]["ordered_edges"][edge_index]["edge_id"]
        target = [float(xy[peak, 0]), float(xy[peak, 1]), float(h2[peak])]
        issue_id = f"CR_{round(s[peak]):05d}"
        issue = dict(issue_id=issue_id, status="open_source_review", source_edge_id=edge_id,
            chainage_from_m=round(float(s[first]), 3), chainage_to_m=round(float(s[last]), 3),
            peak_chainage_m=round(float(s[peak]), 3), target_local_m=target,
            priority_score=round(float(score[peak]), 3), flagged_samples=int(len(group)),
            maximum_grade_1m=round(float(grade1[first:last+1].max()), 5),
            maximum_grade_2m=round(float(grade2[first:last+1].max()), 5),
            maximum_probe_cross_slope=round(float(cross[first:last+1].max()), 5),
            maximum_grid_height_difference_m=round(float(np.abs(h1[first:last+1]-h2[first:last+1]).max()), 5),
            source_ids=["city_bikeways", "NRCan_VILLE_VANCOUVER_2013_DTM"],
            required_action="Inspect georeferenced imagery and current ground references; measure pavement "
                            "edges and grade separation before authoring a reviewed path correction.")
        issue.update(camera(target, tangent[peak]))
        issues.append(issue)
        save(OUT / "viewpoints" / f"{issue_id}.json", issue["unreal_mcp"])
    record = dict(schema_version=1, created_utc=datetime.now(timezone.utc).isoformat(),
        scope="Main circuit only. Source comparison, not application or survey acceptance.",
        runtime_modified=False, release_route_pass=False,
        origin_path="manifests/world-origin.json", origin_sha256=routes["origin_sha256"],
        inputs={k: {"path": str(p.relative_to(ROOT)), "sha256": digest(p)} for k, p in paths.items()},
        grid_correlation="Both grids derive from the same 2013 LiDAR DTM; not independent controls.",
        thresholds=dict(absolute_grade=.18, probe_cross_slope=.12, diagnostic_width_m=3,
                        merge_gap_m=30, padding_m=10, width_surveyed=False),
        summary=dict(circuit_length_m=line.length, sample_count=len(s),
                     spacing_max_m=float(np.diff(s).max()), missing_samples=0,
                     flagged_samples=len(flagged), issue_count=len(issues),
                     maximum_grade_1m=float(grade1.max()), maximum_grade_2m=float(grade2.max()),
                     maximum_probe_cross_slope=float(cross.max()),
                     maximum_grid_height_difference_m=float(np.abs(h1-h2).max())),
        restrictions_pending=[dict(name=name, edges=edges, exact_limits_resolved=False)
            for name, edges in [("Lumberman's Arch", [1459]), ("Prospect Point", [3550,2909]),
                                ("Third Beach", [131])]],
        issues=issues)
    save(ROOT / "manifests/corridor-review.json", record)
    plot_profiles(s, h1, h2, grade1, grade2, cross, issues)
    fig, ax = plt.subplots(figsize=(11, 10), constrained_layout=True)
    ax.plot(xy[:, 0], xy[:, 1], color="#526374", linewidth=1)
    ax.scatter(xy[flagged, 0], xy[flagged, 1], s=3, color="#c34033", label="Source review flag")
    for issue in sorted(issues, key=lambda v: v["priority_score"], reverse=True)[:12]:
        ax.annotate(issue["issue_id"], issue["target_local_m"][:2], fontsize=8,
                    xytext=(8, 8), textcoords="offset points", arrowprops=dict(arrowstyle="-", lw=.5))
    ax.set_aspect("equal"); ax.grid(alpha=.2)
    ax.set_xlabel("East from project origin (m)"); ax.set_ylabel("North from project origin (m)")
    ax.set_title("Stanley Park main circuit: path source review\nRed marks need inspection, not automatic smoothing")
    ax.legend(loc="lower right")
    fig.savefig(OUT / "route-source-review-map.png", dpi=140); plt.close(fig)
    rows = ["# Corridor review queue", "", record["scope"], "",
        "The 1 m reference is complete over the park. It is historic resampled data, not a new survey.", "",
        "Run `scripts/focus-corridor.ps1 -Issue CR_...` to inspect the same issue in Blender and Unreal.", "",
        "| Issue | Source edge | Circuit interval (m) | 1 m grade max | Probe cross slope max | Status |",
        "|---|---|---:|---:|---:|---|"]
    for issue in sorted(issues, key=lambda v: v["priority_score"], reverse=True):
        rows.append(f"| {issue['issue_id']} | {issue['source_edge_id']} | "
                    f"{issue['chainage_from_m']:.0f}–{issue['chainage_to_m']:.0f} | "
                    f"{issue['maximum_grade_1m']:.0%} | {issue['maximum_probe_cross_slope']:.0%} | Open |")
    rows += ["", "The 3 m probe width is a development value. These percentages describe the sampled "
             "source surface; they do not describe verified real path grades. More resolution alone "
             "does not fix approximate route alignment, a cliff overhang, or an underpass.", "",
             "Walk-bike boundaries at Lumberman's Arch, Prospect Point, and Third Beach remain separate "
             "source tasks. This queue does not assign legal boundaries or permit cycling there.", ""]
    (OUT / "REVIEW-QUEUE.md").write_text("\n".join(rows), encoding="utf-8")
    print(json.dumps(record["summary"], indent=2))


if __name__ == "__main__":
    main()
