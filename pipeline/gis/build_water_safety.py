"""Export water recovery footprints from existing water/coast sources.

No Blender/Unreal process is started. The ocean display mesh is a global plane;
the existing FWA ocean mask excludes land, islands and dry underpasses. Lake
footprints are the same polygons used by build_blockout.py. No shoreline is
buffered or simplified for the runtime file.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

from shapely.geometry import Point, Polygon, box, shape
from shapely.ops import nearest_points

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ["data/derived/ocean_mask.geojson", "data/derived/lake-surfaces.geojson",
           "manifests/water-levels.json", "manifests/blender-export.json", "manifests/world-origin.json"]


def read(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8-sig"))


def digest(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def polygons(geometry):
    if isinstance(geometry, Polygon):
        return [geometry]
    if geometry.geom_type == "MultiPolygon":
        return list(geometry.geoms)
    raise ValueError(f"Unexpected water geometry: {geometry.geom_type}")


def check_edge_bands(regions):
    """Compare the native parity/band algorithm with Shapely, without the app."""
    rng = random.Random(581004)
    samples = 0
    for region in regions:
        rings = region["rings"]
        polygon = Polygon(rings[0], rings[1:])
        minimum_x, minimum_y, maximum_x, maximum_y = polygon.bounds
        bands = {}
        for ring in rings:
            for a, b in zip(ring, ring[1:] + ring[:1]):
                if math.dist(a, b) <= .0001:
                    continue
                for band in range(math.floor(min(a[1], b[1]) / 12800), math.floor(max(a[1], b[1]) / 12800) + 1):
                    bands.setdefault(band, []).append((a, b))

        def contains(point):
            x, y = point
            if x < minimum_x or x > maximum_x or y < minimum_y or y > maximum_y:
                return False
            inside = False
            for a, b in bands.get(math.floor(y / 12800), []):
                dx, dy = b[0] - a[0], b[1] - a[1]
                alpha = max(0., min(1., ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy)))
                if (x - a[0] - dx * alpha) ** 2 + (y - a[1] - dy * alpha) ** 2 <= .0001:
                    return True
                if (a[1] > y) != (b[1] > y) and a[0] + (y - a[1]) * dx / dy > x:
                    inside = not inside
            return inside

        probes = [(rng.uniform(minimum_x - 100, maximum_x + 100), rng.uniform(minimum_y - 100, maximum_y + 100)) for _ in range(2000)]
        # Include every stored vertex, ring interior controls and band boundaries.
        probes.extend(tuple(point) for ring in rings for point in ring)
        probes.extend((rng.uniform(minimum_x, maximum_x), band * 12800) for band in bands)
        for point in probes:
            expected = polygon.covers(Point(point))
            actual = contains(point)
            if expected != actual and polygon.boundary.distance(Point(point)) > .011:
                raise AssertionError(f"Water edge-band classification differs: {region['name']} {point}")
            samples += 1
    return {"samples": samples, "mismatches_beyond_0_011_cm_boundary_tolerance": 0}


def build():
    levels = read("manifests/water-levels.json")
    assets = {a["name"]: a for a in read("manifests/blender-export.json")["assets"]}
    ocean_asset = assets["SM_Water_OceanMean"]
    # Export bounds use Unreal north/east centimetres. Limit the existing mask
    # to the actual visible plane, without extending water over unclassified land.
    lo = [a + b for a, b in zip(ocean_asset["position_cm"], ocean_asset["bounds_min_cm"])]
    hi = [a + b for a, b in zip(ocean_asset["position_cm"], ocean_asset["bounds_max_cm"])]
    plane = box(lo[1] / 100, lo[0] / 100, hi[1] / 100, hi[0] / 100)
    shapes = [("Ocean", shape(feature["geometry"]).intersection(plane), levels["ocean"]["height_m"], "SM_Water_OceanMean")
              for feature in read("data/derived/ocean_mask.geojson")["features"]]
    for feature in read("data/derived/lake-surfaces.geojson")["features"]:
        prop = feature["properties"]
        geometry = shape(feature["geometry"])
        # The original Blender authoring uses the exterior ring for these two
        # lakes. Stop if a later source adds holes that need an authoring update.
        if any(p.interiors for p in polygons(geometry)):
            raise ValueError("Lake holes differ from current Blender authoring")
        shapes.append((prop["name"], geometry, prop["height_m"], "SM_Water_" + prop["name"].replace(" ", "")))

    regions, bounds, bands = [], [], []
    for name, geometry, height, asset_name in shapes:
        if not geometry.is_valid or geometry.is_empty:
            raise ValueError(f"Invalid water source: {name}")
        asset = assets[asset_name]
        asset_z = asset["position_cm"][2] + asset["bounds_min_cm"][2]
        if abs(asset_z - height * 100) > .01 or abs(asset["bounds_max_cm"][2] - asset["bounds_min_cm"][2]) > .01:
            raise ValueError(f"Source water level differs from exported mesh: {name}")
        if name != "Ocean":
            east_min, north_min, east_max, north_max = geometry.bounds
            expected_bounds = [north_min * 100, east_min * 100, north_max * 100, east_max * 100]
            export_bounds = [asset["position_cm"][i] + asset[key][i] for key in ("bounds_min_cm", "bounds_max_cm") for i in (0, 1)]
            if max(abs(a - b) for a, b in zip(expected_bounds, export_bounds)) > .05:
                raise ValueError(f"Source lake footprint bounds differ from exported mesh: {name}")
        for number, polygon in enumerate(polygons(geometry)):
            rings = [[[round(north * 100, 5), round(east * 100, 5)] for east, north in list(ring.coords)[:-1]]
                     for ring in [polygon.exterior, *polygon.interiors]]
            regions.append({"name": name if number == 0 else f"{name} {number + 1}",
                            "surface_z_cm": height * 100, "rings": rings})
            band_counts = {}
            for ring in rings:
                for a, b in zip(ring, ring[1:] + ring[:1]):
                    for band in range(math.floor(min(a[1], b[1]) / 12800), math.floor(max(a[1], b[1]) / 12800) + 1):
                        band_counts[band] = band_counts.get(band, 0) + 1
            bounds.append({"name": name, "source_asset": asset_name, "local_east_north_bounds_m": list(polygon.bounds),
                           "surface_z_cm": height * 100, "rings": len(rings), "points": sum(map(len, rings))})
            bands.append({"name": name, "band_count": len(band_counts), "maximum_edges_in_one_band": max(band_counts.values())})

    comparison = check_edge_bands(regions)
    result = {"schema_version": 1, "coordinate_contract": "unreal_north_east_up_cm", "band_height_cm": 12800,
              "source_hashes": {relative: digest(relative) for relative in SOURCES},
              "limits": "Ocean: existing generalized BC FWA coastline mask clipped to display plane. Lakes: existing display polygons and fixed source levels. No new survey, tide, swimming or collision geometry.",
              "regions": regions}
    output = ROOT / "unreal/Content/WorldData/water-safety.json"
    output.write_text(json.dumps(result, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")

    world = read("unreal/Content/WorldData/world.json")
    spawn = world["spawn"]
    # The inward buffer is only used to select a test point; runtime geometry is
    # unchanged. Root must place a pawn for the short recovery regression.
    ocean = shapes[0][1]
    fixture = nearest_points(Point(spawn[1] / 100, spawn[0] / 100), ocean.buffer(-3))[1]
    route_conflicts = []
    main = next(r for r in world["routes"] if r["id"] == "main_circuit")
    remaining = 3360.0
    near_point = main["points"][0]
    for a, b in zip(main["points"], main["points"][1:]):
        distance = math.dist(a, b)
        if remaining <= distance:
            near_point = [a[i] + (b[i] - a[i]) * remaining / distance for i in range(3)]
            break
        remaining -= distance
    near_fixture = nearest_points(Point(near_point[1] / 100, near_point[0] / 100), ocean.buffer(-3))[1]
    for i, (north, east, z) in enumerate(main["points"]):
        for name, geometry, height, _ in shapes:
            if z < height * 100 + 5 and geometry.covers(Point(east / 100, north / 100)):
                route_conflicts.append({"point": i, "region": name, "position_cm": [north, east, z], "water_z_cm": height * 100})
    audit = {"method": "Source geometry, export level, spatial-index and route-point checks only; no application run.",
             "runtime_sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "source_hashes": result["source_hashes"],
             "regions": bounds, "edge_bands": bands, "main_route_points": len(main["points"]),
             "edge_band_source_comparison": comparison,
             "route_points_not_dry": route_conflicts,
             "ocean_recovery_fixture": {"world_xy_cm": [fixture.y * 100, fixture.x * 100],
                                        "surface_z_cm": levels["ocean"]["height_m"] * 100,
                                        "foot_z_for_test_cm": levels["ocean"]["height_m"] * 100 - 50,
                                        "source_shore_distance_m": fixture.distance(ocean.boundary)},
             "ocean_recovery_fixture_at_route_33_6m": {"world_xy_cm": [near_fixture.y * 100, near_fixture.x * 100],
                                        "surface_z_cm": levels["ocean"]["height_m"] * 100,
                                        "foot_z_for_test_cm": levels["ocean"]["height_m"] * 100 - 50,
                                        "source_shore_distance_m": near_fixture.distance(ocean.boundary)},
             "land_control": {"world_position_cm": [0, 0, -100], "covered_by_water_xy": any(g.covers(Point(0, 0)) for _, g, _, _ in shapes)}}
    (ROOT / "evidence/water-safety-source-check.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"regions": len(regions), "bytes": output.stat().st_size, "route_conflicts": len(route_conflicts),
                      "fixture": audit["ocean_recovery_fixture"], "bands": bands}, indent=2))


if __name__ == "__main__":
    build()
