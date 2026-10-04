"""Acquire open-licensed BC coastline geometry for the regional ocean mask.

TRIM EBM Ocean was assessed but is Access Only. Do not incorporate that layer.
The FWA linework is a regional reference, not a seawall engineering survey.
"""
import json
from pathlib import Path
from urllib.parse import urlencode
from datetime import datetime, timezone
import numpy as np
from acquire_sources import download, save_json

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/corridor"
SERVICE = "https://delivery.maps.gov.bc.ca/arcgis/rest/services/whse/bcgw_pub_whse_basemapping/MapServer"
origin = json.loads((ROOT / "manifests/world-origin.json").read_text())
records = []

def acquire(name, layer, filename, padding, simplify):
    identifier = {"fwa-coast":"87b1d6a7-d4d1-4c25-a879-233becdbffed",
                  "fwa-lakes":"cb1e3aba-d3fe-4de1-a2d4-b8b6650fb1f6"}[name]
    metadata_path = RAW / f"{name}-metadata.json"
    metadata_record = download("https://catalogue.data.gov.bc.ca/api/3/action/package_show?id=" + identifier,
                               metadata_path, max_bytes=2_000_000)
    records.append(metadata_record)
    metadata = json.loads(metadata_path.read_text())["result"]
    if metadata["license_title"] != "Open Government Licence - British Columbia":
        raise RuntimeError(f"Unexpected rights for {name}")
    grid = np.load(ROOT / "data/derived" / filename)
    bounds = [float(grid["x"][0]) + origin["easting"] - padding,
              float(grid["y"][0]) + origin["northing"] - padding,
              float(grid["x"][-1]) + origin["easting"] + padding,
              float(grid["y"][-1]) + origin["northing"] + padding]
    features = []
    for offset in range(0, 20000, 1000):
        params = dict(f="json", where="1=1", geometry=",".join(map(str, bounds)),
                      geometryType="esriGeometryEnvelope", inSR=3157,
                      spatialRel="esriSpatialRelIntersects", outSR=3157,
                      returnGeometry="true", outFields="*", orderByFields="OBJECTID",
                      maxAllowableOffset=simplify, geometryPrecision=3,
                      resultOffset=offset, resultRecordCount=1000)
        url = f"{SERVICE}/{layer}/query?{urlencode(params)}"
        path = RAW / f"{name}-{offset:05d}.json"
        record = download(url, path, max_bytes=40_000_000)
        page = json.loads(path.read_text())
        if "error" in page:
            raise RuntimeError(page["error"])
        if page.get("spatialReference", {}).get("wkid") != 3157:
            raise RuntimeError("Unexpected query CRS")
        features.extend(page["features"])
        record.update(license=metadata["license_title"], license_url=metadata["license_url"],
                      capture_period="Mixed source dates; metadata revision is not capture date",
                      metadata_modified=metadata["metadata_modified"],
                      use="regional ocean mask" if layer == 91 else "lake boundary reference",
                      generalization_metres=simplify)
        records.append(record)
        print(name, offset, len(page["features"]), flush=True)
        if not page.get("exceededTransferLimit"):
            break
    else:
        raise RuntimeError("Query paging limit reached")
    save_json(RAW / f"{name}-merged.json", dict(spatialReference={"wkid":3157}, features=features))

acquire("fwa-coast", 91, "terrain_surroundings.npz", 1000, 2)
acquire("fwa-lakes", 20, "terrain_park.npz", 100, 0)
save_json(ROOT / "manifests/water-references.json", dict(
    retrieved_utc=datetime.now(timezone.utc).isoformat(), records=records,
    excluded=[dict(source="TRIM EBM Ocean", reason="Access Only licence; not used in geometry")],
    attribution="Contains information licensed under the Open Government Licence – British Columbia."))
