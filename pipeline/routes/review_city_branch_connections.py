"""Resolve supported branch directions and expose grade-separated source joins.

City geometry and Active/OW attributes are retained. OSM way order is a second
orientation reference, not a replacement legal authority. Conflicts are explicit.
"""
from collections import Counter
import json
import xml.etree.ElementTree as ET

import numpy as np
from pyproj import Transformer
from scipy.interpolate import RegularGridInterpolator
from shapely.geometry import LineString, Point

from build_pedestrian_network import ROOT, save, digest


def main():
    source_path = ROOT / "data/routes/derived/city-branch-junctions.json"
    city = json.loads(source_path.read_text(encoding="utf8"))
    xml_path = ROOT / "data/routes/raw/osm/park-map-20260927.osm"
    xml = ET.parse(xml_path).getroot()
    origin = json.loads((ROOT / "manifests/world-origin.json").read_text(encoding="utf8"))
    project = Transformer.from_crs(4326, origin["horizontal_crs"], always_xy=True)
    nodes = {}
    for n in xml.findall("node"):
        e, north = project.transform(float(n.attrib["lon"]), float(n.attrib["lat"]))
        nodes[int(n.attrib["id"])] = [e - origin["easting"], north - origin["northing"]]
    ways = []
    for way in xml.findall("way"):
        tags = {x.attrib["k"]: x.attrib["v"] for x in way.findall("tag")}
        refs = [int(n.attrib["ref"]) for n in way.findall("nd")]
        if "highway" not in tags or len(refs) < 2 or any(n not in nodes for n in refs):
            continue
        line = LineString([nodes[n] for n in refs])
        ways.append({"way_id": int(way.attrib["id"]), "tags": tags, "line": line, "timestamp": way.attrib.get("timestamp"), "version": int(way.attrib["version"])})

    overrides = json.loads((ROOT / "manifests/branch-direction-overrides.json").read_text(encoding="utf8"))["overrides"]
    reviews = []
    for edge in city["branches"]:
        if edge["direction_resolved"]:
            continue
        line = LineString(edge["coordinates_local_xy_m"])
        shared_road = edge["source_properties"]["bikeway_type"] == "Shared Lanes"
        candidates = [w for w in ways if w["tags"]["highway"] in ({"tertiary", "residential", "unclassified", "service", "trunk_link", "secondary"} if shared_road else {"cycleway", "path", "footway"}) and w["line"].distance(line) < 12]
        samples = []
        used = {}
        for station in np.linspace(line.length * .1, line.length * .9, 17):
            point = line.interpolate(station)
            tangent = np.array(line.interpolate(min(line.length, station + 2)).coords[0]) - line.interpolate(max(0, station - 2)).coords[0]
            tangent /= np.linalg.norm(tangent)
            matches = []
            for w in candidates:
                tags, ref = w["tags"], w["line"]
                if not shared_road and tags.get("bicycle") not in {"yes", "designated", "permissive"} and tags["highway"] != "cycleway":
                    continue
                distance = ref.distance(point)
                if distance > 12:
                    continue
                rs = ref.project(point)
                direction = np.array(ref.interpolate(min(ref.length, rs + 2)).coords[0]) - ref.interpolate(max(0, rs - 2)).coords[0]
                if np.linalg.norm(direction) < .01:
                    continue
                dot = float(np.dot(tangent, direction / np.linalg.norm(direction)))
                if abs(dot) < .85:
                    continue
                matches.append((distance, w, dot))
            if not matches:
                samples.append({"station_m": float(station), "status": "no_parallel_reference"})
                continue
            distance, w, dot = min(matches, key=lambda x: x[0])
            tags = w["tags"]
            oneway = tags.get("oneway:bicycle", tags.get("oneway", "unspecified"))
            if oneway in {"yes", "1", "true", "-1"}:
                sign = (1 if dot > 0 else -1) * (-1 if oneway == "-1" else 1)
                status = "forward" if sign > 0 else "reverse"
            else:
                status = "two_way_conflict" if oneway in {"no", "0", "false"} else "orientation_unspecified"
            samples.append({"station_m": float(station), "way_id": w["way_id"], "distance_m": float(distance), "parallel_dot": dot, "oneway_tag": oneway, "status": status})
            used[w["way_id"]] = {"way_id": w["way_id"], "timestamp": w["timestamp"], "version": w["version"], "tags": tags,
                                   "url": f"https://www.openstreetmap.org/way/{w['way_id']}"}
        count = Counter(s["status"] for s in samples)
        winner, votes = max([(key, count[key]) for key in ("forward", "reverse")], key=lambda row: row[1])
        supported = votes >= 13 and count["reverse" if winner == "forward" else "forward"] == 0 and count["two_way_conflict"] <= 3
        reviews.append({"edge_id": edge["edge_id"], "source_object_id": edge["source_object_id"], "city_oneway_flag": edge["source_properties"].get("bikeway_direction"),
                        "permitted_direction": winner + "_relative_to_city_geometry" if supported else "oneway_orientation_unresolved",
                        "direction_resolved": supported, "resolution_class": "City_OW_plus_consistent_OSM_orientation" if supported else "conflicting_or_insufficient_orientation_evidence",
                        "resolution_limits": "Official current sign orientation is not independently surveyed; the City Active/OW flag controls access type. Do not turn a conflicting OSM no tag into permission for two-way travel.",
                        "route_graph_action": "use_source_direction_with_recorded_evidence" if supported else "exclude_from_automatic_cycling_routing_until_review",
                        "sample_status_counts": dict(count), "samples": samples, "osm_references": list(used.values()),
                        "official_references": ["https://vancouver.ca/files/cov/stanley-park-map-and-guide.pdf", "https://opendata.vancouver.ca/explore/dataset/bikeways/"]})
        if edge["edge_id"] in overrides:
            manual = overrides[edge["edge_id"]]
            reviews[-1].update(direction_resolved=True, permitted_direction=manual["permitted_direction"], resolution_class=manual["resolution_class"],
                               route_graph_action="use_source_direction_with_recorded_manual_evidence", manual_review=manual)

    route = json.loads((ROOT / "data/routes/derived/park_routes.json").read_text(encoding="utf8"))
    original_circuit = LineString([v[:2] for v in route["main_circuit"]["xyz_local_m"]])
    paved_path = ROOT / "data/derived/paved-circuit-runtime.json"
    paved = json.loads(paved_path.read_text(encoding="utf8"))
    stations = np.asarray(paved["chainage_source_m"])
    xyz = np.asarray(paved["points_local_m"])
    widths = np.asarray(paved["width_m"])
    terrain_path = ROOT / "data/derived/terrain_2022_park.npz"
    with np.load(terrain_path) as grid:
        sample_height = RegularGridInterpolator((grid["y"], grid["x"]), grid["z"], bounds_error=False, fill_value=np.nan)
    junctions = []
    for junction in city["junctions"]:
        if junction["type"] != "main_circuit_branch":
            continue
        xy = junction["xy_local_m"]
        s = float(original_circuit.project(Point(xy)))
        p = np.array([np.interp(s, stations, xyz[:, k]) for k in range(3)])
        terrain_z = float(sample_height([xy[::-1]])[0])
        xy_gap = float(np.linalg.norm(p[:2] - xy))
        z_difference = terrain_z - float(p[2])
        width = float(np.interp(s, stations, widths)) if widths.ndim else float(widths)
        separated = abs(z_difference) > .3
        junctions.append({**junction, "source_circuit_station_m": s, "fitted_circuit_xyz_local_m": p.tolist(), "terrain_at_source_endpoint_m": terrain_z,
                          "fitted_xy_shift_m": xy_gap, "terrain_minus_paved_m": z_difference, "within_development_pavement_width": xy_gap <= width / 2,
                          "connection_status": "grade_separated_no_transfer" if separated else "at_grade_candidate_runtime_junction_check_pending",
                          "navigation_transfer_enabled": False,
                          "required_action": "Keep road-top branches separate from underpass route; confirm the real entrance/exit connector independently." if separated else "Inspect lane join, priority, signs and contact. Source endpoint lies within the development pavement width.",
                          "measurement_note": "This checks current model layers, not independent as-built geometry."})
    output = {"schema_version": 1, "city_branch_source_sha256": digest(source_path), "osm_source_sha256": digest(xml_path), "paved_source_sha256": digest(paved_path), "terrain_source_sha256": digest(terrain_path),
              "attribution": ["© OpenStreetMap contributors", "Contains information licensed under the Open Government Licence - Vancouver."],
              "licence": "ODbL-1.0 for review database with OSM-derived orientation; immutable City geometry stays in separate City product",
              "direction_reviews": reviews, "main_circuit_junction_reviews": junctions,
              "direction_supported_count": sum(r["direction_resolved"] for r in reviews), "direction_unresolved_count": sum(not r["direction_resolved"] for r in reviews),
              "grade_separated_source_junctions": [j["junction_id"] for j in junctions if j["connection_status"] == "grade_separated_no_transfer"]}
    save(ROOT / "data/routes/derived/city-branch-connections-reviewed.json", output)
    print(json.dumps({"supported": [(r["source_object_id"], r["permitted_direction"], r["sample_status_counts"]) for r in reviews if r["direction_resolved"]],
                      "unresolved": [(r["source_object_id"], r["sample_status_counts"]) for r in reviews if not r["direction_resolved"]], "junctions": [(j["junction_id"], j["connection_status"], j["terrain_minus_paved_m"]) for j in junctions]}, indent=2))


if __name__ == "__main__":
    main()
