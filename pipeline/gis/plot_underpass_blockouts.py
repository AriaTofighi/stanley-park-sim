"""Plan and section review from source points and the exact M1 mesh package."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]


def main():
    record = json.loads((ROOT / "data/derived/underpass-blockouts.json").read_text())
    runtime = json.loads((ROOT / "data/derived/paved-circuit-runtime.json").read_text())
    source_s, route = np.array(runtime["chainage_source_m"]), np.array(runtime["points_local_m"])
    for site in record["sites"]:
        name = site["id"]
        ortho_name = "return-crossing" if name == "Ceperley" else "entrance-underpass"
        base = ROOT / f"evidence/corridor/ortho-utm/{ortho_name}"
        bounds = json.loads(base.with_suffix(".json").read_text())["local_bounds_m"]
        fig, axes = plt.subplots(1, 2, figsize=(14, 6), layout="constrained")
        axes[0].imshow(plt.imread(base.with_suffix(".png")), extent=[bounds[0], bounds[2], bounds[1], bounds[3]])
        roof_start, roof_end = site["roof_source_m"]
        focus = route[(source_s >= roof_start - 12) & (source_s <= roof_end + 12)]
        axes[0].plot(focus[:, 0], focus[:, 1], color="yellow", linewidth=1.2, label="Existing route centre")
        for item in record["meshes"]:
            if item["site"] != name or item["reference_only"]:
                continue
            with np.load(ROOT / item["path"]) as mesh:
                v, f = mesh["vertices"] + mesh["anchor"], mesh["faces"]
            if item["role"] == "Deck":
                points = v[:, :2].reshape(-1, 4, 2)
                outline = np.vstack((points[:, 0], points[::-1, 1], points[:1, 0]))
                axes[0].plot(outline[:, 0], outline[:, 1], color="cyan", linewidth=1.4, label="Estimated roof boundary")
        margin = 5
        axes[0].set(xlim=(focus[:, 0].min() - margin, focus[:, 0].max() + margin), ylim=(focus[:, 1].min() - margin, focus[:, 1].max() + margin),
                    xlabel="Local east (m)", ylabel="Local north (m)", title="2022 orthophoto and authored roof extent")
        axes[0].set_aspect("equal")
        axes[0].legend(fontsize=8)

        dense_s = np.arange(roof_start - 8, roof_end + 8, .1)
        dense = np.column_stack([np.interp(dense_s, source_s, route[:, i]) for i in range(3)])
        with np.load(ROOT / site["survey_path"]) as survey:
            q, c = survey["xyz"], survey["classification"]
        distance, index = cKDTree(dense[:, :2]).query(q[:, :2])
        mask = np.isin(c, [1, 2]) & (distance < 1.5) & (q[:, 2] < 8)
        axes[1].scatter(dense_s[index[mask]], q[mask, 2], s=.35, color="#586c89", alpha=.3, label="2022 LiDAR classes 1/2, within 1.5 m")
        axes[1].plot(dense_s, dense[:, 2], color="#b22e26", lw=2, label="Existing interpolated floor")
        s = site["station_source_m"]
        axes[1].fill_between(s, site["ceiling_center_z_m"], site["deck_center_z_m"], color="#898c90", alpha=.8, label="M1 roof slab; underside estimated")
        axes[1].plot(s, site["ceiling_center_z_m"], color="black", lw=1)
        for x in (roof_start, roof_end):
            axes[1].axvspan(x - 2, x + 2, color="orange", alpha=.1)
        axes[1].set(xlim=(roof_start - 8, roof_end + 8), ylim=(min(dense[:, 2]) - .3, 7), xlabel="SOURCE chainage (m), not runtime chainage", ylabel="Height CGVD2013 (m)",
                    title=f"Clearance {site['clearance_m']:.1f} m; width {site['clear_width_m']:.1f} m; portal uncertainty ±2 m")
        axes[1].legend(fontsize=8, loc="upper right")
        axes[1].grid(alpha=.2)
        fig.suptitle(f"{name}: M1 structural estimate — not an as-built survey", fontsize=15)
        target = ROOT / f"evidence/corridor/underpass-{name.lower()}-blockout-review.png"
        fig.savefig(target, dpi=150)
        plt.close(fig)
        print(target)


if __name__ == "__main__":
    main()
