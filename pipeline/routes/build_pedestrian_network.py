"""Build an attributed candidate walking graph and explicit City branch junctions.

OSM nodes provide topology, not measured control. The City route database remains
the bicycle permission source. No 2-D crossing is silently made a junction.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from pyproj import Transformer
from scipy.interpolate import RegularGridInterpolator
from shapely.geometry import LineString, Point, shape
import shapely

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/routes/derived"
CONFIG = ROOT / "manifests/pedestrian-dimensions.json"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_dimensions():
    if not CONFIG.exists():
        save(CONFIG, {
            "schema_version": 1,
            "units": "metres",
            "status": "editable_blockout_estimates_not_measured_widths",
            "defaults": {"paved_walk": 2.4, "forest_walk": 2.4, "unknown_walk": 2.4, "steps": 1.8, "shared": 3.0},
            "width_uncertainty_m": 1.0,
            "use_osm_width_tags": True,
            "way_overrides": {},
            "note": "OSM width tags are contributor estimates unless a measurement source is supplied. A width tag does not pass the 0.10m target. Each way override can replace width_m and add source_ids and a note."
        })
    value = json.loads(CONFIG.read_text(encoding="utf8"))
    if "unknown_walk" not in value["defaults"]:
        value["defaults"]["unknown_walk"] = 2.4
        save(CONFIG, value)
    return value


def main():
    raw = ROOT / "data/routes/raw/osm/park-map-20260927.osm"
    origin_path = ROOT / "manifests/world-origin.json"
    origin = json.loads(origin_path.read_text(encoding="utf8"))
    project = Transformer.from_crs(4326, origin["horizontal_crs"], always_xy=True)
    park = shape(json.loads((ROOT / "data/derived/park_boundary.geojson").read_text(encoding="utf8"))["features"][0]["geometry"])
    # Keep a small shore/entrance margin. This is an explicit coverage boundary,
    # not an access boundary. City border vertices are themselves generalized.
    coverage = park.buffer(12)
    lake_data = json.loads((ROOT / "data/derived/lake-surfaces.geojson").read_text(encoding="utf8"))
    lake_mask = shapely.union_all([shape(f["geometry"]) for f in lake_data["features"]])
    dimensions = load_dimensions()
    root = ET.parse(raw).getroot()
    node_xy, node_tags = {}, {}
    for node in root.findall("node"):
        e, n = project.transform(float(node.attrib["lon"]), float(node.attrib["lat"]))
        nid = int(node.attrib["id"])
        node_xy[nid] = [e - origin["easting"], n - origin["northing"]]
        node_tags[nid] = {t.attrib["k"]: t.attrib["v"] for t in node.findall("tag")}

    grid_path = ROOT / "data/derived/terrain_2022_park.npz"
    with np.load(grid_path) as grid:
        height = RegularGridInterpolator((grid["y"], grid["x"]), grid["z"], bounds_error=False, fill_value=np.nan)

    ways, excluded = [], []
    for way in root.findall("way"):
        tags = {t.attrib["k"]: t.attrib["v"] for t in way.findall("tag")}
        kind = tags.get("highway")
        if kind not in {"footway", "path", "steps", "pedestrian", "cycleway", "bridleway", "track"}:
            continue
        refs = [int(n.attrib["ref"]) for n in way.findall("nd")]
        if any(n not in node_xy for n in refs) or len(refs) < 2:
            continue
        line = LineString([node_xy[n] for n in refs])
        if not line.intersects(coverage):
            continue
        reason = None
        if tags.get("access") in {"private", "no", "customers"} or tags.get("foot") in {"private", "no"}:
            reason = "non_public_or_walking_prohibited_source_tag"
        elif tags.get("area") == "yes":
            reason = "area_polygon_not_a_path_centreline"
        elif kind == "cycleway" and tags.get("foot") not in {"yes", "designated", "permissive"}:
            reason = "cycleway_without_explicit_walking_tag"
        if reason:
            excluded.append({"way_id": int(way.attrib["id"]), "reason": reason, "name": tags.get("name"), "tags": tags})
            continue
        ways.append({"way_id": int(way.attrib["id"]), "refs": refs, "tags": tags,
                     "source_timestamp": way.attrib.get("timestamp"), "source_version": int(way.attrib["version"])})

    incidence = Counter(n for w in ways for n in set(w["refs"]))
    edges, nodes = [], {}
    for w in ways:
        tags, refs = w["tags"], w["refs"]
        source_kind = tags["highway"]
        surface = tags.get("surface", "unknown")
        walking_type = "steps" if source_kind == "steps" else (
            "shared" if source_kind == "cycleway" else (
                "paved_walk" if surface in {"asphalt", "paved", "concrete", "paving_stones", "concrete:plates"}
                or "Seawall" in tags.get("name", "") else (
                    "forest_walk" if surface in {"compacted", "gravel", "fine_gravel", "ground", "dirt", "woodchips", "unpaved", "earth", "grass", "sand"} else "unknown_walk")))
        width = float(dimensions["defaults"][walking_type])
        width_source = "development_default"
        if dimensions["use_osm_width_tags"]:
            try:
                candidate = float(tags.get("width", "").replace(" m", ""))
                if .5 <= candidate <= 12:
                    width, width_source = candidate, "unverified_osm_width_tag"
            except ValueError:
                pass
        override = dimensions["way_overrides"].get(str(w["way_id"]), {})
        if "width_m" in override:
            width, width_source = float(override["width_m"]), "authored_dimension_override"
        cut_indices = [0] + [i for i in range(1, len(refs) - 1) if incidence[refs[i]] > 1 or node_tags[refs[i]].get("barrier")] + [len(refs) - 1]
        for part, (a, b) in enumerate(zip(cut_indices, cut_indices[1:])):
            ids = refs[a:b + 1]
            original = LineString([node_xy[n] for n in ids])
            # Clipping creates boundary nodes only. It does not join close paths.
            for fragment_no, fragment in enumerate(shapely.get_parts(original.intersection(coverage))):
                if not isinstance(fragment, LineString) or fragment.length < .05:
                    continue
                xy = np.asarray(fragment.coords)
                d = np.linspace(0, fragment.length, max(2, int(np.ceil(fragment.length / 2)) + 1))
                samples = shapely.get_coordinates(shapely.line_interpolate_point(fragment, d))
                z = height(samples[:, ::-1])
                xyz = [[float(p[0]), float(p[1]), float(v) if np.isfinite(v) else None] for p, v in zip(samples, z)]
                grades = np.abs(np.diff(z) / np.maximum(np.diff(d), .001))
                maximum_grade = float(np.nanmax(grades)) if np.any(np.isfinite(grades)) else None
                edge_id = f"osm_way_{w['way_id']}_{part:02d}_{fragment_no}"
                endpoints = []
                for end, ref in [(0, ids[0]), (-1, ids[-1])]:
                    node_id = f"osm_node_{ref}" if np.linalg.norm(xy[end] - node_xy[ref]) < .001 else f"boundary_{edge_id}_{end}"
                    endpoints.append(node_id)
                    nodes.setdefault(node_id, {"node_id": node_id, "xy_local_m": xy[end].tolist(), "source_node_id": ref if node_id.startswith("osm_node") else None,
                                               "source_tags": node_tags[ref] if node_id.startswith("osm_node") else {}, "edges": []})["edges"].append(edge_id)
                water_crossing = float(fragment.intersection(lake_mask).length)
                special = source_kind == "steps" or tags.get("bridge", "no") != "no" or tags.get("tunnel", "no") != "no" or tags.get("layer", "0") != "0" or water_crossing > .1
                edges.append({"edge_id": edge_id, "source_way_id": w["way_id"], "source_timestamp": w["source_timestamp"],
                              "source_version": w["source_version"], "source_tags": tags, "name": tags.get("name", "Unnamed mapped path"),
                              "start_node": endpoints[0], "end_node": endpoints[1], "coordinates_local_xy_m": xy.tolist(), "xyz_local_m": xyz,
                              "length_m": float(fragment.length), "width_m": width, "width_source": width_source, "width_uncertainty_m": dimensions["width_uncertainty_m"],
                              "width_override": override, "surface": surface, "walking_type": walking_type,
                              "permitted_modes": ["walk"], "cycling_permission": "not_granted_by_this_layer; City bikeways and official current map control",
                              "horizontal_accuracy": "unsurveyed_OSM_candidate_requires_reference_review",
                              "height_source": "terrain_2022_park_bilinear; historic_fallback_and_surface_mismatch_possible",
                              "maximum_terrain_grade": maximum_grade, "missing_height_samples": int(np.count_nonzero(~np.isfinite(z))),
                              "structure_flags": {"bridge": tags.get("bridge", "no"), "tunnel": tags.get("tunnel", "no"), "layer": tags.get("layer", "0"), "stairs": source_kind == "steps", "centreline_lake_overlap_m": water_crossing},
                              "special_surface_review": special, "render_candidate": not special and bool(np.all(np.isfinite(z))),
                              "traversability": "blocked_pending_structure_surface" if special else "candidate_terrain_contact_not_accepted",
                              "release_accepted": False})

    # Explicit source endpoint topology for branches; no grade-separated 2D join.
    city = json.loads((ROOT / "data/routes/derived/park_routes.json").read_text(encoding="utf8"))
    circuit_ids = {s["edge_id"] for s in city["main_circuit"]["ordered_edges"]}
    branches, city_nodes = [], defaultdict(list)
    for e in city["edges"]:
        for endpoint, point in [("start", e["coordinates_local_xy_m"][0]), ("end", e["coordinates_local_xy_m"][-1])]:
            city_nodes[tuple(round(float(v), 3) for v in point)].append({"edge_id": e["edge_id"], "endpoint": endpoint, "main_circuit": e["edge_id"] in circuit_ids})
        if e["edge_id"] not in circuit_ids:
            branches.append({k: e[k] for k in ("edge_id", "name", "source_object_id", "source_properties", "coordinates_local_xy_m", "length_m", "surface", "permitted_direction", "direction_resolved", "restrictions")})
    junctions = [{"junction_id": f"city_junction_{i:03d}", "xy_local_m": list(xy), "incident_edges": entries,
                  "type": "main_circuit_branch" if any(e["main_circuit"] for e in entries) and any(not e["main_circuit"] for e in entries) else "source_endpoint",
                  "connection_status": "source_endpoint_connection; fitted_runtime_transition_requires_check"}
                 for i, (xy, entries) in enumerate(sorted(city_nodes.items())) if len(entries) > 1]
    # Connected components use source identity, never proximity or 2-D crossing.
    parent = {n: n for n in nodes}
    def leader(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n
    for edge in edges:
        a, b = leader(edge["start_node"]), leader(edge["end_node"])
        parent[b] = a
    components = defaultdict(list)
    for edge in edges:
        components[leader(edge["start_node"])].append(edge["edge_id"])
    barriers = [{"node_id": n["node_id"], "xy_local_m": n["xy_local_m"], "tags": n["source_tags"], "opening_width_m": None,
                 "status": "mapped_barrier_requires_current_reference_and_runtime_model"}
                for n in nodes.values() if "barrier" in n["source_tags"]]
    gaps = [{"node_id": n["node_id"], "xy_local_m": n["xy_local_m"], "incident_edges": n["edges"],
             "type": "coverage_boundary" if n["node_id"].startswith("boundary") else "mapped_terminal_or_unconnected_crossing_requires_review"}
            for n in nodes.values() if len(n["edges"]) == 1]
    graph = {"schema_version": 1, "licence": "ODbL-1.0", "attribution": "© OpenStreetMap contributors", "licence_url": "https://opendatacommons.org/licenses/odbl/1-0/",
             "origin_path": origin_path.relative_to(ROOT).as_posix(), "origin_sha256": digest(origin_path), "units": "metres", "axes": "east,north,up",
             "source_path": raw.relative_to(ROOT).as_posix(), "source_sha256": digest(raw), "dimensions_path": CONFIG.relative_to(ROOT).as_posix(),
             "terrain_sha256": digest(grid_path), "coverage": "City park polygon plus 12m; source edges clipped at coverage boundary",
             "status": "candidate_graph_no_survey_or_access_acceptance", "edges": edges, "nodes": list(nodes.values()), "excluded": excluded,
             "topology_components": list(components.values()), "terminal_review": gaps, "barriers": barriers}
    save(OUT / "pedestrian-network.json", graph)
    save(OUT / "pedestrian-network-local.geojson", {"type": "FeatureCollection", "coordinate_reference": "local_metres", "licence": "ODbL-1.0", "features": [
        {"type": "Feature", "geometry": {"type": "LineString", "coordinates": e["coordinates_local_xy_m"]}, "properties": {k: e[k] for k in ("edge_id", "name", "walking_type", "width_m", "render_candidate", "release_accepted")}} for e in edges]})
    save(OUT / "city-branch-junctions.json", {"schema_version": 1, "licence": "Open Government Licence - Vancouver", "source": "data/routes/derived/park_routes.json", "source_sha256": digest(ROOT / "data/routes/derived/park_routes.json"), "branches": branches, "junctions": junctions,
         "note": "Separate City source product. No OSM points are used to infer a City bike permission or force connectivity."})
    result = {"kind": "numerical_data_checks_not_application_test", "osm_source_way_count": len(ways), "edge_count": len(edges), "walking_length_m": sum(e["length_m"] for e in edges),
              "node_count": len(nodes), "junction_count": sum(len(n["edges"]) > 2 for n in nodes.values()), "render_candidate_edges": sum(e["render_candidate"] for e in edges),
              "topology_components": len(components), "terminal_review_nodes": len(gaps), "mapped_barriers": len(barriers),
              "special_surface_review_edges": sum(e["special_surface_review"] for e in edges), "missing_height_samples": sum(e["missing_height_samples"] for e in edges),
              "city_branch_count": len(branches), "city_junction_count": len(junctions), "city_main_branch_junction_count": sum(j["type"] == "main_circuit_branch" for j in junctions),
              "city_unresolved_direction_branches": [e["edge_id"] for e in branches if not e["direction_resolved"]], "accepted_survey_edges": 0, "release_route_pass": False}
    save(ROOT / "evidence/pedestrian-network-checks.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
