"""Bounded 2022 survey crops for both underpasses, retaining structure returns."""
import json
import zipfile
from pathlib import Path
import laspy
import numpy as np

from acquire_sources import ROOT, digest, save_json
from height_reference import VancouverHeightConversion

SITES = {
    "Ceperley": {"tile": "489000_5460000", "bounds": [-411, -954, -331, -874]},
    "Chilco": {"tile": "490000_5460000", "bounds": [414, -905, 504, -805]},
}


def main():
    origin = json.loads((ROOT / "manifests/world-origin.json").read_text(encoding="utf8"))
    conversion = VancouverHeightConversion()
    records = []
    for site, config in SITES.items():
        tile = config["tile"]
        output = ROOT / f"data/derived/underpass-{site.lower()}-survey.npz"
        archive = ROOT / f"data/raw/city/lidar2022/{tile}.zip"
        if not output.exists():
            points, classes, colours = [], [], []
            xmin, ymin, xmax, ymax = config["bounds"]
            with zipfile.ZipFile(archive) as source:
                with source.open(f"{tile}.las") as stream, laspy.open(stream) as las:
                    for chunk in las.chunk_iterator(1_000_000):
                        x = np.asarray(chunk.x) - origin["easting"]
                        y = np.asarray(chunk.y) - origin["northing"]
                        c = np.asarray(chunk.classification)
                        take = (x >= xmin) & (x <= xmax) & (y >= ymin) & (y <= ymax) & (c != 7)
                        if not take.any():
                            continue
                        x, y = x[take], y[take]
                        z = conversion.to_cgvd2013(x + origin["easting"], y + origin["northing"], np.asarray(chunk.z)[take])
                        points.append(np.column_stack((x, y, z)))
                        classes.append(c[take])
                        colours.append(np.column_stack((np.asarray(chunk.red)[take], np.asarray(chunk.green)[take], np.asarray(chunk.blue)[take])))
            np.savez_compressed(output, xyz=np.concatenate(points).astype(np.float32), classification=np.concatenate(classes), rgb=np.concatenate(colours))
        with np.load(output) as data:
            counts = {str(int(c)): int((data["classification"] == c).sum()) for c in np.unique(data["classification"])}
        records.append({"site": site, "tile": tile, "source_manifest": f"manifests/lidar2022-{tile}.json", "bounds_local_m": config["bounds"],
                        "path": output.relative_to(ROOT).as_posix(), "sha256": digest(output), "classification_counts": counts})
        print(site, counts, flush=True)
    save_json(ROOT / "manifests/underpass-survey.json", {"schema_version": 1, "capture_dates": ["2022-09-07", "2022-09-09"], "vertical_datum": "CGVD2013",
              "conversion": "Existing VancouverHeightConversion: H2013=H28+HTMVBC00_Abb-CGG2013a", "sources": records,
              "limits": "Airborne survey sees deck and portals. Interior clearances are not measured by a top-down crop.", "release_accepted": False})


if __name__ == "__main__":
    main()
