"""Apply the two reviewed M1 pavement corrections without changing survey sources.

Contract: refine_pavement_alignment(points, source_chainage, crossfall, width_m,
project_root=None, write_evidence=True) returns new points, crossfall, widths, report.
Call after the existing centre smoothing and before final normals are computed.
Run this module directly for the numerical source review only; it runs no app.
"""
from pathlib import Path
import hashlib
import json
import math

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.ndimage import median_filter
from scipy.signal import savgol_filter
from scipy.spatial import cKDTree
import shapely
from shapely.geometry import LineString, Point, Polygon

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "data/derived/m1-pavement-alignment-baseline.npz"
DRAFT = "manifests/m1-pavement-correction-draft.json"
OUT = "evidence/m1-pavement-alignment"


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2)+"\n", encoding="utf8")


def _normals(points):
    tangent = np.gradient(points[:, :2], axis=0)
    tangent[0] = tangent[-1] = points[1, :2]-points[-2, :2]
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    return np.column_stack((-tangent[:, 1], tangent[:, 0]))


def prepare_baseline(project_root=ROOT):
    """Freeze the reviewed input once. Never overwrite an existing baseline."""
    root = Path(project_root)
    draft = json.loads((root/DRAFT).read_text())
    runtime_path = root/"data/derived/paved-circuit-runtime.json"
    if (root/BASELINE).exists():
        return
    if _sha(runtime_path) != draft["route_sha256"]:
        raise ValueError("Current route is not the reviewed baseline; do not reconstruct it from a changed route.")
    runtime = json.loads(runtime_path.read_text())
    proposal_path = root/"data/derived/paved-circuit-proposal.npz"
    with np.load(proposal_path) as source:
        np.savez_compressed(root/BASELINE,
                            xyz=np.asarray(runtime["points_local_m"]),
                            chainage_source=source["chainage_source"],
                            crossfall=source["crossfall"], width_m=source["width_m"])
    _json(root/"manifests/m1-pavement-alignment-baseline.json", {
        "source_runtime_sha256": draft["route_sha256"],
        "source_proposal_sha256": _sha(proposal_path),
        "draft_sha256": _sha(root/DRAFT), "baseline_sha256": _sha(root/BASELINE),
        "purpose": "Immutable pre-correction authoring input; not a new survey",
        "source_geometry_unchanged": True})


def _load_ground(root, corrected, window):
    xy = corrected[window, :2]
    lower, upper = xy.min(0)-3, xy.max(0)+3
    tiles = set()
    for x in [lower[0], upper[0]]:
        for y in [lower[1], upper[1]]:
            tiles.add((math.floor((x+489600)/1000)*1000,
                       math.floor((y+5461100)/1000)*1000))
    pieces, sources = [], []
    for east, north in sorted(tiles):
        path = root/f"data/derived/lidar2022_{east}_{north}.npz"
        with np.load(path) as package:
            ground = package["ground"]
            take = ((ground[:, :2] >= lower) & (ground[:, :2] <= upper)).all(axis=1)
            pieces.append(ground[take, :3].astype(float))
            count = int(take.sum())
            del ground
        sources.append({"path": path.relative_to(root).as_posix(), "sha256": _sha(path),
                        "cropped_classified_ground_points": count})
    points = np.concatenate(pieces)
    return points, cKDTree(points[:, :2]), sources


def _plane_fit(points, tree, xy, normal):
    indices = tree.query_ball_point(xy, .8)
    if len(indices) < 8:
        return None
    near = points[indices]
    offset = near[:, :2]-xy
    matrix = np.column_stack((offset, np.ones(len(near))))
    base_weight = np.exp(-np.square(np.linalg.norm(offset, axis=1)/.45))
    weight = base_weight.copy()
    fit = None
    for _ in range(3):
        fit, _, rank, _ = np.linalg.lstsq(matrix*np.sqrt(weight[:, None]),
                                         near[:, 2]*np.sqrt(weight), rcond=None)
        if rank < 3:
            return None
        residual = matrix@fit-near[:, 2]
        scale = max(.008, float(np.median(abs(residual)))*1.4826)
        weight = base_weight*np.minimum(1., 2.5*scale/np.maximum(abs(residual), 1e-9))
    rms = float(np.sqrt(np.average(np.square(residual), weights=weight)))
    if rms > .05 or np.linalg.norm(fit[:2]) > .18:
        return None
    return float(fit[2]), float(fit[:2]@normal), rms, len(indices)


def _smoothstep(t):
    t = np.clip(t, 0., 1.)
    return t*t*t*(10+t*(-15+6*t))


def _height_refit(root, before, after, station, old_crossfall, row):
    lo, hi = row["correction_source_window_m"]
    window = np.flatnonzero((station >= lo) & (station <= hi))
    normals = _normals(after)
    ground, tree, sources = _load_ground(root, after, window)
    fits = [_plane_fit(ground, tree, after[i, :2], normals[i]) for i in window]
    good = np.array([p is not None for p in fits])
    gaps = np.split(np.flatnonzero(~good), np.flatnonzero(np.diff(np.flatnonzero(~good)) > 1)+1)
    longest_gap = max([len(g) for g in gaps], default=0)
    if good.mean() < .9 or longest_gap > 3:
        raise ValueError(f"{row['id']}: insufficient ground fits ({good.mean():.3f}, gap {longest_gap})")
    measured_z = np.array([p[0] if p else np.nan for p in fits])
    measured_crossfall = np.array([p[1] if p else np.nan for p in fits])
    s = station[window]
    filled_z = np.interp(s, s[good], measured_z[good])
    filled_crossfall = np.interp(s, s[good], measured_crossfall[good])
    filtered_z = savgol_filter(median_filter(filled_z, size=5, mode="nearest"), 11, 2, mode="interp")
    filtered_crossfall = savgol_filter(median_filter(filled_crossfall, size=5, mode="nearest"), 11, 2, mode="interp")
    blend = _smoothstep((s-lo)/8)*_smoothstep((hi-s)/8)
    after[window, 2] = before[window, 2]+blend*(filtered_z-before[window, 2])
    new_crossfall = old_crossfall.copy()
    new_crossfall[window] += blend*(np.clip(filtered_crossfall, -.08, .08)-old_crossfall[window])
    grades = np.diff(after[window, 2])/np.linalg.norm(np.diff(after[window, :2], axis=0), axis=1)
    report = {"ground_sources": sources, "query_radius_m": .8, "minimum_points": 8,
              "robust_plane_maximum_rms_m": .05, "height_filter": "5-station median then 11-station quadratic Savitzky-Golay; 8 m quintic endpoint blend",
              "valid_fits": int(good.sum()), "samples": len(window), "longest_interpolated_gap_samples": longest_gap,
              "maximum_plane_rms_m": max(p[2] for p in fits if p),
              "maximum_final_minus_measured_z_m": float(np.nanmax(abs(after[window, 2]-measured_z))),
              "maximum_z_change_m": float(np.max(abs(after[window, 2]-before[window, 2]))),
              "maximum_absolute_grade_percent": float(abs(grades).max()*100),
              "crossfall_clip_count": int((abs(filtered_crossfall) > .08).sum()),
              "source_station_m": s.tolist(), "raw_fitted_height_m": [float(x) if np.isfinite(x) else None for x in measured_z],
              "raw_fitted_crossfall": [float(x) if np.isfinite(x) else None for x in measured_crossfall],
              "final_height_m": after[window, 2].tolist(), "final_crossfall": new_crossfall[window].tolist(),
              "absolute_accuracy_accepted": False}
    if report["maximum_absolute_grade_percent"] > 12:
        raise ValueError(f"{row['id']}: grade over 12%; retain and review the source fit")
    return new_crossfall, report


def _strip_check(points, station, width, row, tolerance):
    lo, hi = row["correction_source_window_m"]
    normal = _normals(points)
    left, right = points[:, :2]+normal*width[:, None]/2, points[:, :2]-normal*width[:, None]/2
    indices = np.flatnonzero((station >= lo-3) & (station <= hi+3))
    footprint = shapely.union_all([Polygon([right[i], right[i+1], left[i+1], left[i]]) for i in indices[:-1]])
    bands = row["bands"]
    lane = Polygon([b["edges_local_m"][0] for b in bands]+[b["edges_local_m"][1] for b in reversed(bands)])
    if not lane.is_valid:
        raise ValueError(f"{row['id']}: invalid fixed source lane polygon")
    samples = np.arange(lo+2, hi-2, .25)
    # The actual 1 m ruled mesh edges are interpolated, not a prettier render spline.
    edge_samples = np.concatenate([np.column_stack([np.interp(samples, station, edge[:, axis]) for axis in [0,1]]) for edge in [left,right]])
    outside = shapely.distance(shapely.points(edge_samples), lane)
    sample_station = np.tile(samples,2)
    failures = [{"source_station_m":float(sample_station[i]),"side":"left" if i<len(samples) else "right",
                 "outside_m":float(outside[i]),"xy_local_m":edge_samples[i].tolist()}
                for i in np.flatnonzero(outside > tolerance)]
    fixed = []
    for band in bands:
        a,b = np.array(band["edges_local_m"])
        mid, direction = (a+b)/2, (b-a)/np.linalg.norm(b-a)
        cut = footprint.intersection(LineString([mid-direction*40, mid+direction*40]))
        parts = [cut] if cut.geom_type == "LineString" else [g for g in getattr(cut,"geoms",[]) if g.geom_type == "LineString"]
        if not parts:
            fixed.append({"source_station_m": band["source_station_m"], "pass": False, "reason": "No strip intersection"})
            continue
        part = min(parts, key=lambda p:p.distance(Point(mid)))
        p = np.asarray(part.coords)
        low, high = sorted([(p[0]-a)@direction, (p[-1]-a)@direction])
        excess = max(0., -low, high-np.linalg.norm(b-a))
        i = int(np.argmin(abs(station-band["source_station_m"])))
        excess_normal = float(excess*abs(direction@normal[i]))
        fixed.append({"source_station_m": band["source_station_m"], "excess_along_transect_m":float(excess),
                      "excess_perpendicular_m":excess_normal, "pass":excess_normal <= tolerance})
    return {"source_station_window_m":[lo,hi], "edge_sample_spacing_m": .25,
            "endpoint_polygon_exclusion_m":2., "endpoint_check":"All fixed end transects are checked separately against the complete strip",
            "edge_pick_uncertainty_m":tolerance, "edge_samples":len(edge_samples),
            "maximum_between_knots_edge_outside_m":float(outside.max(initial=0)),
            "between_knots_failed_samples":int((outside > tolerance).sum()),
            "between_knots_failures":failures,
            "fixed_bands":fixed, "pass": bool((outside <= tolerance).all() and all(b["pass"] for b in fixed))}


def refine_pavement_alignment(points, source_chainage, crossfall, width_m, *, project_root=None, write_evidence=True):
    root = Path(project_root) if project_root else ROOT
    prepare_baseline(root)
    metadata = json.loads((root/"manifests/m1-pavement-alignment-baseline.json").read_text())
    if _sha(root/BASELINE) != metadata["baseline_sha256"] or _sha(root/DRAFT) != metadata["draft_sha256"]:
        raise ValueError("Alignment baseline or reviewed draft changed; review the sources before regeneration")
    with np.load(root/BASELINE) as baseline:
        before = np.array(points, dtype=float, copy=True)
        station = np.asarray(source_chainage, dtype=float)
        width = np.asarray(width_m, dtype=float)
        original_crossfall = np.asarray(crossfall, dtype=float)
        for value,key in [(before,"xyz"),(station,"chainage_source"),(width,"width_m"),(original_crossfall,"crossfall")]:
            if value.shape != baseline[key].shape or not np.allclose(value,baseline[key],rtol=0,atol=1e-7):
                raise ValueError(f"Input {key} differs from the reviewed baseline")
    draft = json.loads((root/DRAFT).read_text())
    after, new_crossfall = before.copy(), original_crossfall.copy()
    width_path = root/"manifests/m1-pavement-width-corrections.json"
    width_record = json.loads(width_path.read_text())
    new_width = width.copy()
    for adjustment in width_record["records"]:
        lo, full_lo = adjustment["start_source_m"], adjustment["full_width_start_source_m"]
        full_hi, hi = adjustment["full_width_end_source_m"], adjustment["end_source_m"]
        blend = _smoothstep((station-lo)/(full_lo-lo))*_smoothstep((hi-station)/(hi-full_hi))
        new_width += blend*(adjustment["width_m"]-width)
    records = []
    for row in draft["records"]:
        knots = np.array(row["correction_source_knots_m"])
        target = np.array(row["correction_centre_knots_local_m"])
        old_knots = np.column_stack([np.interp(knots,station,before[:,axis]) for axis in [0,1]])
        delta = target-old_knots
        delta[0] = delta[-1] = 0.
        curve = CubicSpline(knots, delta, bc_type=((1,np.zeros(2)),(1,np.zeros(2))))
        window = (station >= knots[0]) & (station <= knots[-1])
        after[window,:2] += curve(station[window])
        baseline_check = _strip_check(before,station,width,row,draft["pixel_pick_uncertainty_m"])
        corrected_check = _strip_check(after,station,new_width,row,draft["pixel_pick_uncertainty_m"])
        new_crossfall, heights = _height_refit(root,before,after,station,new_crossfall,row)
        records.append({"id":row["id"],"baseline_failure":baseline_check,
                        "corrected_repeat":corrected_check,"height_refit":heights,
                        "maximum_xy_change_m":float(np.linalg.norm(after[window,:2]-before[window,:2],axis=1).max()),
                        "endpoint_correction_m":[delta[0].tolist(),delta[-1].tolist()],
                        "endpoint_correction_derivative":[curve(knots[0],1).tolist(),curve(knots[-1],1).tolist()]})
    report = {"kind":"Numerical authoring check; no application test", "algorithm":"Clamped cubic correction with zero endpoint displacement and derivative; original survey retained; documented local width tapers",
              "inputs":metadata, "helper_sha256":_sha(Path(__file__)), "draft_path":DRAFT,
              "width_adjustments": {"path":width_path.relative_to(root).as_posix(),"sha256":_sha(width_path),"records":width_record["records"]},
              "records":records,"pass":all(r["corrected_repeat"]["pass"] for r in records),
              "source_geometry_unchanged":True,"absolute_accuracy_accepted":False}
    if write_evidence:
        folder=root/OUT;folder.mkdir(parents=True,exist_ok=True)
        _json(folder/"alignment-review.json",report)
        np.savez_compressed(folder/"alignment-preview.npz",before=before,after=after,
                            chainage_source=station,crossfall_before=original_crossfall,crossfall_after=new_crossfall,width_before_m=width,width_m=new_width)
    if not report["pass"]:
        raise ValueError("Pavement alignment failed fixed source edge checks; inspect evidence/m1-pavement-alignment/alignment-review.json")
    return after, new_crossfall, new_width, report


if __name__ == "__main__":
    prepare_baseline()
    with np.load(ROOT/BASELINE) as package:
        _,_,_,result=refine_pavement_alignment(package["xyz"],package["chainage_source"],package["crossfall"],package["width_m"])
    print(json.dumps({"pass":result["pass"],"areas":[{"id":r["id"],"repeat":r["corrected_repeat"]["pass"],"max_xy_m":r["maximum_xy_change_m"],"max_z_m":r["height_refit"]["maximum_z_change_m"]} for r in result["records"]]}))
