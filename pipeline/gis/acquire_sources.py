"""Acquire authoritative GIS inputs with immutable downloads and a size ceiling."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw"
DERIVED = ROOT / "data/derived"
MANIFESTS = ROOT / "manifests"
API = "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/"
# Full-park 2022 LAS archives exceed the initial catalogue-only allowance.
# The verified C: free space was >80 GB before these ~12 GB source downloads.
LIMIT = 20_000_000_000


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, path, max_bytes=LIMIT):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return {"url": url, "path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": digest(path)}
    part = path.with_suffix(path.suffix + ".part")
    used = sum(p.stat().st_size for p in RAW.rglob("*") if p.is_file() and p != part)
    allowance = min(max_bytes, LIMIT - used)
    if allowance <= 0:
        raise RuntimeError("Raw download ceiling reached")
    request = urllib.request.Request(url, headers={"User-Agent": "StanleyPark-GIS/0.1 (source acquisition)"})
    with urllib.request.urlopen(request, timeout=120) as response:
        length = int(response.headers.get("Content-Length", 0))
        if length > allowance:
            raise RuntimeError(f"Download {length} exceeds remaining allowance {allowance}: {url}")
        count = 0
        last = time.monotonic()
        with part.open("wb") as stream:
            while chunk := response.read(4 * 1024 * 1024):
                count += len(chunk)
                if count > allowance:
                    raise RuntimeError("Download exceeded configured ceiling")
                stream.write(chunk)
                if time.monotonic() - last > 15:
                    print(f"{path.name}: {count / 1e6:.1f} MB", flush=True)
                    last = time.monotonic()
    part.replace(path)
    return {"url": url, "path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": digest(path)}


def get_json(url, path):
    record = download(url, path, max_bytes=20_000_000)
    return json.loads(path.read_text(encoding="utf-8")), record


def records(dataset, where=None):
    results = []
    evidence = []
    for offset in range(0, 10000, 100):
        params = {"limit": 100, "offset": offset}
        if where:
            params["where"] = where
        url = API + dataset + "/records?" + urllib.parse.urlencode(params)
        obj, rec = get_json(url, RAW / "city" / f"{dataset}-records-{offset}.json")
        evidence.append(rec)
        results.extend(obj["results"])
        if len(results) >= obj["total_count"]:
            break
    return results, evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dem", action="store_true")
    args = parser.parse_args()
    provenance = []
    datasets = ["parks-polygon-representation", "shoreline-2002", "lidar-2022", "digital-elevation-model", "lidar-2013"]
    metadata = {}
    for dataset in datasets:
        obj, rec = get_json(API + dataset, RAW / "city" / f"{dataset}-metadata.json")
        metadata[dataset] = obj
        provenance.append(rec)
    parks, refs = records("parks-polygon-representation", "park_name='Stanley Park'")
    provenance.extend(refs)
    if len(parks) != 1:
        raise RuntimeError(f"Expected one Stanley Park polygon, got {len(parks)}")
    boundary = shape(parks[0]["geom"]["geometry"])
    project_crs = CRS.from_epsg(3157)
    to_grid = Transformer.from_crs(4326, project_crs, always_xy=True)
    projected = transform(to_grid.transform, boundary)
    e0 = round(projected.centroid.x / 100) * 100
    n0 = round(projected.centroid.y / 100) * 100
    origin = {
        "schema_version": 1,
        "immutable": True,
        "horizontal_crs": "EPSG:3157",
        "horizontal_crs_name": project_crs.name,
        "horizontal_crs_wkt": project_crs.to_wkt(),
        "easting": e0, "northing": n0, "height": 0.0,
        "units": "metres", "axes": {"x": "east", "y": "north", "z": "up"},
        "vertical_datum": "City native heights; resolve individual source headers before combination",
        "height_origin_note": "Zero subtractive offset only; not a claim of ocean level.",
        "source": "City Stanley Park boundary; origin is its projected centroid rounded to 100 m",
        "city_regional_realization_note": "EPSG:3157 records the general NAD83(CSRS) UTM10 grid. Regional 4.0.0.BC.1.GVRD realization differences remain an accuracy limitation until control is checked.",
    }
    origin_path = MANIFESTS / "world-origin.json"
    if origin_path.exists():
        old = json.loads(origin_path.read_text(encoding="utf-8"))
        if any(old.get(k) != origin[k] for k in ("easting", "northing", "height", "horizontal_crs")):
            raise RuntimeError("Refusing to move immutable world origin")
        origin = old
    save_json(origin_path, origin)
    local = transform(lambda x, y, z=None: (x-e0, y-n0), projected)
    for name, geom, crs in [("park_boundary_wgs84", boundary, "EPSG:4326"), ("park_boundary_utm", projected, "EPSG:3157"), ("park_boundary", local, "LOCAL_METRES; see manifests/world-origin.json")]:
        save_json(DERIVED / f"{name}.geojson", {"type": "FeatureCollection", "coordinate_reference": crs, "features": [{"type": "Feature", "properties": {"name": "Stanley Park", "source": "parks-polygon-representation", "horizontal_accuracy": "not independently checked"}, "geometry": mapping(geom)}]})
    coast, refs = records("shoreline-2002")
    provenance.extend(refs)
    features = []
    roi = projected.buffer(1500)
    for i, item in enumerate(coast):
        geom = transform(to_grid.transform, shape(item["geom"]["geometry"]))
        clipped = geom.intersection(roi)
        if clipped.is_empty:
            continue
        clipped = transform(lambda x, y, z=None: (x-e0, y-n0), clipped)
        features.append({"type": "Feature", "properties": {"id": f"coast_{i}", "capture_year": 2002, "approximate": True, "tidal_meaning": "unknown"}, "geometry": mapping(clipped)})
    save_json(DERIVED / "shoreline.geojson", {"type": "FeatureCollection", "coordinate_reference": "LOCAL_METRES; see manifests/world-origin.json", "features": features})
    lidar, refs = records("lidar-2022")
    provenance.extend(refs)
    selected = [r for r in lidar if shape(r["geom"]["geometry"]).intersects(boundary)]
    save_json(MANIFESTS / "geospatial-lidar-selection.json", {"source": "lidar-2022", "tiles": selected, "status": "index only; tile content not downloaded"})
    save_json(MANIFESTS / "geospatial-acquisition.json", {"retrieved_utc": datetime.now(timezone.utc).isoformat(), "raw_limit_bytes": LIMIT, "records": provenance, "park_area_projected_m2": projected.area, "park_bounds_utm": list(projected.bounds), "park_bounds_local": list(local.bounds), "licence": "Open Government Licence - Vancouver", "licence_url": "https://opendata.vancouver.ca/pages/licence/", "attribution": "Contains information licensed under the Open Government Licence – Vancouver."})
    print(json.dumps({"origin": [e0, n0, 0], "bounds": list(projected.bounds), "lidar_tiles": [r["name"] for r in selected], "shore_features": len(features)}), flush=True)
    if args.dem:
        import re
        desc = metadata["digital-elevation-model"]["metas"]["default"]["description"]
        urls = re.findall(r'href="(https:[^"]+\.zip)"', desc)
        if len(urls) != 1:
            raise RuntimeError("DEM source URL is ambiguous")
        rec = download(urls[0], RAW / "city" / "DEM_2013_TIF.zip")
        provenance.append(rec)
        save_json(MANIFESTS / "geospatial-dem-download.json", {"source": "digital-elevation-model", "record": rec, "metadata": metadata["digital-elevation-model"]["metas"]["default"]})
        print("DEM acquisition complete", flush=True)


if __name__ == "__main__":
    main()
