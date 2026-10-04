"""Extract the observed Lions Gate corridor, including unclassified structure returns.

The approximate crop comes from the inspected 2022 orthophoto. It does not set
the final bridge axis or dimensions. Those will be fitted to the saved returns.
"""
import json
import zipfile
from pathlib import Path
import laspy
import numpy as np
from acquire_sources import ROOT, digest, save_json
from height_reference import VancouverHeightConversion

origin = json.loads((ROOT / "manifests/world-origin.json").read_text())
conversion = VancouverHeightConversion()
# Crop centres only, read from the georeferenced overview. Not survey controls.
a, b = np.array([206., 1220.]), np.array([445., 1625.])
direction = (b-a) / np.linalg.norm(b-a)
normal = np.array([-direction[1], direction[0]])
parts, colors, classes, sources = [], [], [], []
for tile in ["489000_5462000", "490000_5462000"]:
    archive = ROOT / f"data/raw/city/lidar2022/{tile}.zip"
    with zipfile.ZipFile(archive) as source:
        with source.open(f"{tile}.las") as stream, laspy.open(stream) as las:
            for chunk in las.chunk_iterator(1_000_000):
                xy = np.column_stack((np.asarray(chunk.x)-origin["easting"], np.asarray(chunk.y)-origin["northing"]))
                along, across = (xy-a)@direction, (xy-a)@normal
                classification = np.asarray(chunk.classification)
                take = (along > -220) & (along < 720) & (abs(across) < 25) & (classification != 7)
                xy, native = xy[take], np.asarray(chunk.z)[take]
                height = conversion.to_cgvd2013(xy[:,0]+origin["easting"], xy[:,1]+origin["northing"], native)
                parts.append(np.column_stack((xy, height)))
                colors.append(np.column_stack((np.asarray(chunk.red)[take], np.asarray(chunk.green)[take], np.asarray(chunk.blue)[take])))
                classes.append(classification[take])
    sources.append(dict(tile=tile, manifest=f"manifests/lidar2022-{tile}.json"))
    print(tile, sum(len(x) for x in parts), flush=True)
output = ROOT / "data/derived/lions-gate-survey.npz"
np.savez_compressed(output, xyz=np.concatenate(parts).astype(np.float32), rgb=np.concatenate(colors), classification=np.concatenate(classes))
save_json(ROOT / "manifests/lions-gate-survey.json", dict(sources=sources,
    bounds_method="25m either side of a coarse orthophoto axis; crop only",
    preliminary_centres_local_m=[a.tolist(), b.tolist()],
    vertical_datum="CGVD2013; conversion is recorded in each source manifest",
    output=dict(path=output.relative_to(ROOT).as_posix(), sha256=digest(output)),
    reference_date="2022-09-07/09", accepted=False))
print("Extracted", sum(len(x) for x in parts), flush=True)
