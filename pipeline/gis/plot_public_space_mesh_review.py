"""Plot actual exported public-space footprints on the fixed source images."""
from collections import defaultdict
from pathlib import Path
import hashlib
import json

import numpy as np
from PIL import Image, ImageDraw
import shapely

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evidence/public-spaces"


def main():
    manifest_path = ROOT / "data/derived/public-spaces/public-space-meshes.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf8"))
    triangles = defaultdict(list)
    for row in manifest["meshes"]:
        path = ROOT / row["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"Changed public-space mesh: {path}")
        with np.load(path) as mesh:
            xyz = mesh["vertices"] + mesh["anchor"]
            triangles[row["component_id"]].extend(shapely.polygons(xyz[mesh["faces"], :2]))
    footprints = {k: shapely.union_all(v) for k, v in triangles.items()}
    records = []
    for name in ["public-spaces-brockton", "public-spaces-central", "public-spaces-south", "named-lumberman-wide"]:
        source = ROOT / "evidence/corridor/ortho-utm" / name
        meta = json.loads(source.with_suffix(".json").read_text(encoding="utf8"))
        left, bottom, right, top = meta["local_bounds_m"]
        pixel = meta["pixel_size_m"]
        image = Image.open(source.with_suffix(".png")).convert("RGB")
        draw = ImageDraw.Draw(image)
        transform = lambda p: ((p[0] - left) / pixel - .5, (top - p[1]) / pixel - .5)
        included = []
        for key, footprint in footprints.items():
            if not footprint.intersects(shapely.box(left, bottom, right, top)):
                continue
            for polygon in shapely.get_parts(footprint):
                draw.line([transform(p) for p in polygon.exterior.coords], fill="orange", width=3)
                for ring in polygon.interiors:
                    draw.line([transform(p) for p in ring.coords], fill="magenta", width=3)
            point = footprint.representative_point()
            draw.text(transform([point.x, point.y]), key, fill="orange", stroke_width=1, stroke_fill="black")
            included.append(key)
        draw.rectangle((5, 5, 1250, 40), fill="black")
        draw.text((10, 10), "City 2022 image | orange: actual public-space mesh | magenta: exclusions | hidden site references not filled", fill="white")
        path = OUT / (name + "-mesh-review.png")
        image.save(path)
        records.append({"source": source.with_suffix(".json").relative_to(ROOT).as_posix(), "review_image": path.relative_to(ROOT).as_posix(), "components": included})
    (OUT / "mesh-review-panels.json").write_text(json.dumps({"manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(), "panels": records}, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"panels": len(records), "components": len(footprints)}))


if __name__ == "__main__":
    main()
