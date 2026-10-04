# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.4.3", "pyproj==3.7.2", "shapely==2.1.2"]
# ///
"""Build source-preserving park route lines and an ordered City seawall circuit.

Coordinates are City geometry, not a hand-drawn approximation. Heights are
provisional nearest-cell terrain samples, not a path survey or collision approval.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely.geometry import box, shape

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/routes/derived"
# Each sign gives traversal relative to the immutable City feature coordinates.
# Southwest return follows the City's route lines south of Lost Lagoon.
LOOP = [2986, 1748, 1459, 2120, 3550, 2909, 131, -1307, -42, -1207, 2814, 278, 138, 723]
SEAWALL = {2986, 1748, 1459, 2120, 3550, 2909, 131}
CLIFF = {3550, 2909, 131}
WALK_RESTRICTIONS = {
    1459: ["Lumbermans_Arch_walk_bikes_exact_limits_unresolved"],
    3550: ["Prospect_Point_walk_bikes_exact_limits_unresolved"],
    2909: ["Prospect_Point_walk_bikes_exact_limits_unresolved"],
    131: ["Third_Beach_walk_bikes_exact_limits_unresolved"],
}


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def densify(xy: list[list[float]], spacing: float = 5.0) -> list[list[float]]:
    result = [xy[0]]
    for a, b in zip(xy, xy[1:]):
        count = max(1, math.ceil(math.dist(a, b) / spacing))
        result.extend([[a[k] + (b[k] - a[k]) * i / count for k in (0, 1)] for i in range(1, count + 1)])
    return result


def main() -> None:
    origin_path = ROOT / "manifests/world-origin.json"
    origin = json.loads(origin_path.read_text(encoding="utf-8"))
    project = Transformer.from_crs("EPSG:4326", origin["horizontal_crs"], always_xy=True)
    unproject = Transformer.from_crs(origin["horizontal_crs"], "EPSG:4326", always_xy=True)
    raw_path = ROOT / "data/routes/raw/city_bikeways.geojson"
    source = json.loads(raw_path.read_text(encoding="utf-8"))
    terrain_path = ROOT / "data/derived/terrain_park.npz"
    terrain = np.load(terrain_path)
    tx, ty, tz = terrain["x"], terrain["y"], terrain["z"]

    def height(x: float, y: float) -> float | None:
        if not (tx[0] <= x <= tx[-1] and ty[0] <= y <= ty[-1]):
            return None
        ix = int(np.clip(np.searchsorted(tx, x), 1, len(tx) - 1))
        iy = int(np.clip(np.searchsorted(ty, y), 1, len(ty) - 1))
        ix -= int(abs(tx[ix - 1] - x) < abs(tx[ix] - x))
        iy -= int(abs(ty[iy - 1] - y) < abs(ty[iy] - y))
        value = float(tz[iy, ix])
        return round(value - origin["height"], 4) if math.isfinite(value) else None

    study_box = box(-123.165, 49.289, -123.116, 49.318)
    edges = []
    for feature in source["features"]:
        properties = feature["properties"]
        route = properties.get("bike_route_name") or ""
        if not (route.startswith("Stanley Park") or route == "Seaside"):
            continue
        if not shape(feature["geometry"]).intersects(study_box):
            continue
        if properties.get("status") != "Active":
            continue
        sid = int(properties["object_id"])
        geographic = feature["geometry"]["coordinates"]
        projected = [list(project.transform(*p[:2])) for p in geographic]
        local = [[p[0] - origin["easting"], p[1] - origin["northing"]] for p in projected]
        samples = densify(local)
        xyz = [[round(p[0], 5), round(p[1], 5), height(*p)] for p in samples]
        length = sum(math.dist(a, b) for a, b in zip(local, local[1:]))
        slopes = [abs((b[2] - a[2]) / math.dist(a[:2], b[:2])) for a, b in zip(xyz, xyz[1:])
                  if a[2] is not None and b[2] is not None and math.dist(a[:2], b[:2]) > 0.01]
        direction = properties.get("bikeway_direction")
        # OW states one-way but does not document whether storage order is travel order.
        # Main seawall order is independently resolved from City map CCW arrows.
        direction_resolved = sid in SEAWALL or direction in ("2W", "Bidirectional")
        edges.append({
            "edge_id": f"city_bikeways_{sid}", "source_object_id": sid,
            "source_id": "city_bikeways", "name": route,
            "source_properties": properties,
            "coordinates_wgs84": geographic,
            "coordinates_projected_m": projected,
            "coordinates_local_xy_m": local,
            "xyz_local_m": xyz,
            "length_m": round(length, 3), "sample_spacing_max_m": 5.0,
            "surface": properties.get("surface_type"),
            "surveyed_width_m": None,
            "mode": "ride_or_push" if sid in WALK_RESTRICTIONS else "ride",
            "permitted_direction": "forward_ccw" if sid in SEAWALL else ("both" if direction in ("2W", "Bidirectional") else "oneway_orientation_unresolved"),
            "direction_resolved": direction_resolved,
            "source_access_status": "Active bikeway in City 2026-09-21 extract",
            "access_confidence": "official_catalog_and_map_circuit" if sid in set(map(abs, LOOP)) else "official_catalog_not_individually_map_checked",
            "exact_restriction_chainage_verified": sid not in WALK_RESTRICTIONS,
            "restrictions": WALK_RESTRICTIONS.get(sid, []),
            "height_source": "data/derived/terrain_park.npz; historical 2013 ground surface in CGVD2013",
            "height_method": "nearest_2m_cell; no smoothing, clamp or invented elevation",
            "height_is_path_survey": False,
            "unresolved_cliff_height": sid in CLIFF,
            "missing_height_samples": sum(p[2] is None for p in xyz),
            "maximum_raw_sample_grade": round(max(slopes, default=0.0), 4),
            "height_review_required": True,
            "source_accuracy_note": "City manually maintained approximate bikeway centreline; sub-metre accuracy is not established.",
            "source_ids": ["city_bikeways", "city_park_map_2026"] if sid in set(map(abs, LOOP)) else ["city_bikeways"],
        })
    edges.sort(key=lambda e: e["source_object_id"])
    by_id = {e["source_object_id"]: e for e in edges}
    loop_xyz, loop_xy, steps, gaps = [], [], [], []
    for signed_id in LOOP:
        e = by_id[abs(signed_id)]
        forward = signed_id > 0
        points = e["xyz_local_m"] if forward else e["xyz_local_m"][::-1]
        xy = e["coordinates_local_xy_m"] if forward else e["coordinates_local_xy_m"][::-1]
        if loop_xy:
            gaps.append({"before_edge": e["edge_id"], "gap_m": math.dist(loop_xy[-1], xy[0])})
        loop_xyz.extend(points if not loop_xyz else points[1:])
        loop_xy.extend(xy if not loop_xy else xy[1:])
        steps.append({"edge_id": e["edge_id"], "reverse_source_geometry": not forward,
                      "length_m": e["length_m"], "restrictions": e["restrictions"]})
    gaps.append({"before_edge": steps[0]["edge_id"], "gap_m": math.dist(loop_xy[-1], loop_xy[0])})
    document = {
        "schema_version": 1, "origin_path": "manifests/world-origin.json",
        "origin_sha256": hashlib.sha256(origin_path.read_bytes()).hexdigest(),
        "horizontal_crs": origin["horizontal_crs"], "vertical_datum": "CGVD2013",
        "axes": {"x": "east", "y": "north", "z": "up"}, "units": "metres",
        "source_data_modified": "2026-09-21T13:30:24+00:00",
        "source_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "terrain_sha256": hashlib.sha256(terrain_path.read_bytes()).hexdigest(),
        "status": "source_backed_blockout_route_height_and_walk_zone_review_required",
        "edges": edges,
        "main_circuit": {
            "id": "stanley_park_ccw_city_circuit", "ordered_edges": steps,
            "length_m": round(sum(by_id[abs(i)]["length_m"] for i in LOOP), 3),
            "xyz_local_m": loop_xyz,
            "geometry_closed": max(g["gap_m"] for g in gaps) <= 0.01,
            "max_source_join_gap_m": max(g["gap_m"] for g in gaps),
            "permitted_cycling_direction": "counter_clockwise",
            "return_connector": "City lines 1307,42,1207,2814,278,138,723; inland via south Lost Lagoon, not pedestrian shoreline.",
            "continuous_journey_requires_push_zones": True,
            "exact_push_zone_limits_resolved": False,
            "collision_ready": False,
            "navigation_evidence": "2026-05-19 City map page 2 visually inspected in Chrome on 2026-09-26. South lagoon line and CCW arrows checked; map is diagrammatic.",
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write(OUT / "park_routes.json", document)
    for filename, key in [("park_routes_local.geojson", "coordinates_local_xy_m"),
                          ("park_routes_wgs84.geojson", "coordinates_wgs84")]:
        write(OUT / filename, {"type": "FeatureCollection", "coordinate_reference": "local_metres" if "local" in filename else "EPSG:4326",
              "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": e[key]},
                            "properties": {k: e[k] for k in ("edge_id", "name", "length_m", "surface", "mode", "permitted_direction", "height_review_required")}} for e in edges]})
    roundtrip = max(math.dist(p, unproject.transform(*q)) for e in edges for p, q in zip(e["coordinates_wgs84"], e["coordinates_projected_m"]))
    checks = {"validation_kind": "numerical_route_data_check_not_application_test",
              "edge_count": len(edges), "circuit_edge_count": len(LOOP),
              "circuit_length_m": document["main_circuit"]["length_m"],
              "joins": gaps, "maximum_coordinate_roundtrip_degrees": roundtrip,
              "missing_height_samples": sum(e["missing_height_samples"] for e in edges),
              "main_circuit_missing_height_samples": sum(p[2] is None for p in loop_xyz),
              "unresolved": ["Precise walk-bike boundaries at three sites", "Path-specific heights, bank, width and 2026 repair changes", "One-way orientation of non-circuit roads", "Grade-separated intersections need explicit nodes; do not node every 2D line crossing"],
              "geometry_pass": max(g["gap_m"] for g in gaps) <= 0.01,
              "release_route_pass": False}
    write(ROOT / "manifests/routes-validation.json", checks)
    print(json.dumps({k: v for k, v in checks.items() if k != "joins"}, indent=2))


if __name__ == "__main__":
    main()
