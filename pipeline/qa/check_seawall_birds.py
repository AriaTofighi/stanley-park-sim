"""Bounded offline checks for the authored bird envelope, not live acceptance.

Run with pipeline/gis/.venv/Scripts/python.exe. Writes one bird-only evidence
file. Does not open Blender or Unreal, change geometry, or move the player.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
INPUTS = {
    "config": ROOT / "manifests/seawall-birds.json",
    "world": ROOT / "unreal/Content/WorldData/world.json",
    "shoreline": ROOT / "data/derived/shoreline.geojson",
    "park_boundary": ROOT / "data/derived/park_boundary.geojson",
    "bird_source": ROOT / "unreal/Source/StanleyParkSim/SPSeawallBirds.cpp",
}


def geometries(path):
    return unary_union([shape(feature["geometry"]) for feature in
                        json.loads(path.read_text(encoding="utf-8"))["features"]])


config = json.loads(INPUTS["config"].read_text(encoding="utf-8"))
route = next(row for row in json.loads(INPUTS["world"].read_text(encoding="utf-8"))["routes"]
             if row["id"] == "main_circuit")
route_points = [(p[1] / 100, p[0] / 100, p[2] / 100) for p in route["points"]]
line = LineString([p[:2] for p in route_points])
shore = geometries(INPUTS["shoreline"])
park = geometries(INPUTS["park_boundary"])
records = []
for zone in config["zones"]:
    east, north, up = zone["centre_local_east_north_up_m"]
    assert zone["centre_unreal_cm"] == [north * 100, east * 100, up * 100]
    a, b = zone["radius_east_cm"] / 100, zone["radius_north_cm"] / 100
    boundary = [(east + a * math.cos(step * math.tau / 1440),
                 north + b * math.sin(step * math.tau / 1440)) for step in range(1440)]
    # Test the filled footprint as well as the perimeter. All seeded 0.9–1.0
    # ellipse scales are inside this envelope; no inner-loop crossing is hidden.
    envelope = Polygon(boundary)
    observer = route_points[zone["review_route_point_index"]]
    horizontal = [Point(observer[:2]).distance(Point(p)) for p in boundary]
    minimum_shore = envelope.distance(shore)
    minimum_park = envelope.distance(park)
    minimum_route = envelope.distance(line)
    nearest = math.sqrt(min(horizontal) ** 2 + (up - observer[2] - 1.53) ** 2)
    farthest = math.sqrt(max(horizontal) ** 2 + (up + 2.4 - observer[2] - 1.53) ** 2)
    # A broadside upper estimate, not a promised silhouette width. Bank, yaw,
    # lighting, antialiasing, output size and occlusion affect the actual image.
    focal = 1920 / (2 * math.tan(math.radians(85 / 2)))
    row = dict(zone=zone["id"], samples=1440, centre_local_m=[east, north, up],
        radius_east_north_m=[a, b], source_shore_gap_m=minimum_shore,
        source_park_gap_m=minimum_park, route_gap_m=minimum_route,
        review_route_point_index=zone["review_route_point_index"],
        review_route_point_local_m=observer,
        horizontal_near_far_m=[min(horizontal), max(horizontal)],
        approximate_broadside_pixels_at_1920_85deg=[focal * 1.44 / farthest, focal * 1.44 / nearest],
        minimum_authored_height_m=up - 0.45,
        source_footprint_pass=minimum_shore > 10 and minimum_park > 3 and minimum_route > 20)
    records.append(row)

# Exercise the same arc-length inversion used by the C++ motion, with fixed
# representative radii/speeds. This checks the math only, not engine execution.
radius_x, radius_y = 2800.0, 1800.0
table = [0.0]
previous = (radius_x, 0.0)
for step in range(1, 129):
    angle = step * math.tau / 128
    point = (radius_x * math.cos(angle), radius_y * math.sin(angle))
    table.append(table[-1] + math.dist(point, previous))
    previous = point


def sample(t):
    distance = (t * 740.0) % table[-1]
    low, high = 1, 128
    while low < high:
        middle = (low + high) // 2
        if table[middle] < distance:
            low = middle + 1
        else:
            high = middle
    alpha = (distance - table[low - 1]) / (table[low] - table[low - 1])
    angle = (low - 1 + alpha) * math.tau / 128
    return radius_x * math.cos(angle), radius_y * math.sin(angle)


speeds = [math.dist(sample(i / 120), sample((i + 1) / 120)) * 120 / 100 for i in range(3600)]
flaps = []
for i in range(1080):
    t = i / 120
    cycle = t % 9
    envelope = math.sin(math.pi * cycle / 3.6) ** 2 if cycle < 3.6 else 0
    flaps.append(6 + 38 * envelope * math.sin(t * math.tau * 1.8))
record = dict(schema_version=1, created_utc=datetime.now(timezone.utc).isoformat(),
    scope="Offline source envelope and math checks only; no live clearance, visibility, or performance acceptance.",
    hashes={name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in INPUTS.items()},
    zones=records, analytical_motion=dict(sample_count=3600, time_step_seconds=1/120,
        target_speed_m_s=7.4, sampled_speed_min_max_m_s=[min(speeds), max(speeds)],
        flap_min_max_degrees=[min(flaps), max(flaps)],
        glide_pose_degrees=6, cycle_seconds=9, flap_window_seconds=3.6,
        note="Python transcription of the motion formula; actual C++ poses must be captured separately."),
    offline_pass=all(row["source_footprint_pass"] for row in records)
        and min(speeds) > 7.2 and max(speeds) < 7.6 and min(flaps) < -25 and max(flaps) > 35,
    runtime_acceptance=False)
out = ROOT / "evidence/seawall-bird-placement-v2.json"
out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps(record, indent=2))
if not record["offline_pass"]:
    raise SystemExit("Bird source or analytical motion check failed")
