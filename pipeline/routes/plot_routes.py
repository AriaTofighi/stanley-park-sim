# /// script
# requires-python = ">=3.12"
# dependencies = ["matplotlib==3.10.8"]
# ///
"""Plot data products for route review; does not run the simulation."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
routes = json.loads((ROOT / "data/routes/derived/park_routes.json").read_text(encoding="utf-8"))
boundary = json.loads((ROOT / "data/derived/park_boundary.geojson").read_text(encoding="utf-8"))
loop_ids = {s["edge_id"] for s in routes["main_circuit"]["ordered_edges"]}
for name, bounds in [("park_route_review", None), ("southwest_route_review", (-1520, 570, -1450, -340))]:
    fig, ax = plt.subplots(figsize=(14, 11), constrained_layout=True)
    ax.set_facecolor("#e4eef1")
    for feature in boundary["features"]:
        g = feature["geometry"]
        polygons = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for polygon in polygons:
            ax.fill(*zip(*polygon[0]), color="#f2f3e9", edgecolor="#adb7a1", linewidth=0.4)
    for edge in routes["edges"]:
        xy = edge["coordinates_local_xy_m"]
        on_loop = edge["edge_id"] in loop_ids
        ax.plot(*zip(*xy), color="#0d6587" if on_loop else "#a08361", linewidth=2.2 if on_loop else 0.85)
        mid = xy[len(xy)//2]
        if bounds is None or bounds[0] < mid[0] < bounds[1] and bounds[2] < mid[1] < bounds[3]:
            ax.text(*mid, str(edge["source_object_id"]), fontsize=7, color="#123d51" if on_loop else "#785538", bbox=dict(facecolor="white", alpha=.7, edgecolor="none", pad=.5))
    for order, step in enumerate(routes["main_circuit"]["ordered_edges"], 1):
        edge = next(e for e in routes["edges"] if e["edge_id"] == step["edge_id"])
        points = edge["xyz_local_m"]
        if step["reverse_source_geometry"]:
            points = points[::-1]
        i = len(points)//2
        if i+3 < len(points):
            ax.annotate("", points[i+3][:2], points[i][:2], arrowprops={"arrowstyle": "->", "color":"#cc492b", "lw":1.7})
    if bounds:
        ax.set_xlim(bounds[:2]); ax.set_ylim(bounds[2:])
    ax.set_aspect("equal")
    ax.set_xlabel("Local east (m); UTM E0 = 489600")
    ax.set_ylabel("Local north (m); UTM N0 = 5461100")
    ax.set_title("Stanley Park source route review\nBlue: ordered City circuit (9,441.794 m); brown: other City bikeways; labels: source IDs\nApproximate centreline geometry; no claim of surveyed path edges or legal-zone boundaries")
    ax.grid(alpha=.2)
    fig.savefig(ROOT / f"data/routes/derived/{name}.png", dpi=160)
    plt.close(fig)
