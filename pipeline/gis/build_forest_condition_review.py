"""Build dated forest review references without inventing canopy removals.

The lines locate named trails. They are not treatment-area boundaries, cleared
polygons, tree locations, or runtime deletion masks. Geometry remains unchanged
until an individual override has a source, location and visual review.
"""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import shape
from shapely.ops import unary_union
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "manifests/forest-condition-overrides.json"
NETWORK = ROOT / "data/routes/derived/pedestrian-network-local.geojson"
OSM = ROOT / "data/routes/raw/osm/park-map-20260927.osm"
OUTPUT = ROOT / "data/derived/forest-condition-review.geojson"
PLOT = ROOT / "evidence/forest-condition-review-map.png"


def main():
    config = json.loads(CONFIG.read_text(encoding="utf8"))
    network = json.loads(NETWORK.read_text(encoding="utf8"))
    osm_root = ET.parse(OSM).getroot()
    to_local = Transformer.from_crs(4326, 3157, always_xy=True)
    nodes = {node.attrib["id"]: node for node in osm_root.findall("node")}

    def local_node(node):
        x, y = to_local.transform(float(node.attrib["lon"]), float(node.attrib["lat"]))
        return [x - 489600, y - 5461100]

    def named_osm_features(name):
        found = []
        for item in osm_root:
            if item.tag not in ("node", "way"):
                continue
            tags = {tag.attrib["k"]: tag.attrib["v"] for tag in item.findall("tag")}
            if tags.get("name") != name:
                continue
            geometry = ({"type": "Point", "coordinates": local_node(item)} if item.tag == "node"
                        else {"type": "LineString", "coordinates": [local_node(nodes[n.attrib["ref"]])
                                                                      for n in item.findall("nd")]})
            found.append({"geometry": geometry, "properties": {"name": name,
                          "edge_id": f"osm_{item.tag}_{item.attrib['id']}"}})
        return found

    selected = []
    for zone in config["review_areas"]:
        matches = (named_osm_features(zone["osm_name"]) if "osm_name" in zone else
                   [f for f in network["features"] if f["properties"]["name"] in zone["trail_names"]])
        if not matches:
            raise ValueError(f"No mapped trail for {zone['id']}")
        geometries = [shape(f["geometry"]) for f in matches]
        extent = unary_union(geometries)
        zone["reference_extent_local_m"] = list(extent.bounds)
        zone["source_edge_ids"] = [f["properties"]["edge_id"] for f in matches]
        zone["reference_length_m"] = extent.length
        for f in matches:
            selected.append({"type": "Feature", "geometry": f["geometry"],
                             "properties": {
                                 "zone_id": zone["id"], "phase": zone["phase"],
                                 "trail_name": f["properties"]["name"],
                                 "edge_id": f["properties"]["edge_id"],
                                 "condition_source": zone["source_id"],
                                 "geometry_role": "named_feature_reference_not_treatment_extent",
                                 "runtime_override": False}})
    config["network_reference"] = {
        "path": str(NETWORK.relative_to(ROOT)).replace("\\", "/"),
        "sha256": hashlib.sha256(NETWORK.read_bytes()).hexdigest(),
        "rights": "OpenStreetMap ODbL-1.0; same attribution as pedestrian network",
        "use": "Internal review line positions; no canopy change"}
    config["additional_osm_reference"] = {
        "path": str(OSM.relative_to(ROOT)).replace("\\", "/"),
        "sha256": hashlib.sha256(OSM.read_bytes()).hexdigest(),
        "rights": "OpenStreetMap ODbL-1.0",
        "use": "Named landmark and road reference positions; no treatment footprint"}
    config["derived_reference"] = str(OUTPUT.relative_to(ROOT)).replace("\\", "/")
    CONFIG.write_text(json.dumps(config, indent=2) + "\n", encoding="utf8")
    OUTPUT.write_text(json.dumps({
        "type": "FeatureCollection", "coordinate_reference": "LOCAL_METRES",
        "origin": {"easting": 489600, "northing": 5461100, "crs": "EPSG:3157"},
        "licence": "ODbL-1.0 for trail geometry",
        "geometry_role": "Review references, not forest treatment boundaries",
        "features": selected}, indent=2) + "\n", encoding="utf8")

    park = json.loads((ROOT / "data/derived/park_boundary.geojson").read_text(encoding="utf8"))
    fig, ax = plt.subplots(figsize=(9, 9))
    for feature in park["features"]:
        for polygon in ([shape(feature["geometry"])] if feature["geometry"]["type"] == "Polygon"
                        else shape(feature["geometry"]).geoms):
            x, y = polygon.exterior.xy
            ax.fill(x, y, color="#eff2ea", edgecolor="#6b756b", linewidth=0.8)
    colors = {"2024 Phase II": "#48758a", "2025 advanced Phase III": "#b26a35",
              "2026 Phase III": "#803e7d", "2025 one-tree report": "#b22832"}
    shown = set()
    for f in selected:
        phase = f["properties"]["phase"]
        geom = shape(f["geometry"])
        x, y = geom.xy
        ax.plot(x, y, color=colors[phase], linewidth=2, marker="o" if geom.geom_type == "Point" else None,
                label=phase if phase not in shown else None)
        shown.add(phase)
    for zone in config["review_areas"]:
        bounds = zone["reference_extent_local_m"]
        ax.annotate(zone["short_label"], ((bounds[0]+bounds[2])/2, (bounds[1]+bounds[3])/2),
                    xytext=(5, 5), textcoords="offset points", fontsize=8,
                    bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none", "pad": 1})
    ax.set_aspect("equal")
    ax.set_xlabel("Local east (m)")
    ax.set_ylabel("Local north (m)")
    ax.set_title("Stanley Park: dated forest condition review areas\nLocation references only; no canopy deletion mask", fontsize=12)
    ax.legend(loc="lower left", fontsize=8)
    fig.text(0.5, 0.02, "2022 canopy remains unchanged. Treatment counts do not locate removed crowns.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(PLOT, dpi=180)
    print(json.dumps({"review_areas": len(config["review_areas"]), "reference_edges": len(selected),
                      "active_runtime_overrides": len([o for o in config["overrides"] if o.get("apply")]),
                      "geometry_changed": False}))


if __name__ == "__main__":
    main()
