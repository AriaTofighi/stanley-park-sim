"""Retain a plan view of candidate paths and withheld structures."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "tmp/matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

graph = json.loads((ROOT / "data/routes/derived/pedestrian-network.json").read_text(encoding="utf8"))
runtime = json.loads((ROOT / "data/derived/paved-circuit-runtime.json").read_text(encoding="utf8"))
fig, ax = plt.subplots(figsize=(11, 11))
colors = {"paved_walk": "#ca9548", "forest_walk": "#628f3f", "unknown_walk": "#7e776b", "shared": "#9183b4", "steps": "#c4544b"}
for category, color in colors.items():
    edges = [e for e in graph["edges"] if e["walking_type"] == category]
    ax.add_collection(LineCollection([e["coordinates_local_xy_m"] for e in edges], colors=color, linewidths=.65, label=f"{category}: {len(edges)} edges"))
withheld = [e for e in graph["edges"] if e["special_surface_review"]]
ax.add_collection(LineCollection([e["coordinates_local_xy_m"] for e in withheld], colors="#d24940", linewidths=1.7, label="Structure/water conflict: withheld"))
p = runtime["points_local_m"]
ax.plot([x[0] for x in p], [x[1] for x in p], color="#235cab", lw=1, label="Existing cycle circuit")
ax.autoscale()
ax.set_aspect("equal")
ax.legend(loc="upper left", fontsize=8)
ax.set_xlabel("Local east (m)")
ax.set_ylabel("Local north (m)")
ax.set_title("Candidate walking graph: source topology, unsurveyed positions")
fig.savefig(ROOT / "evidence/pedestrian-network-plan.png", dpi=150, bbox_inches="tight")
