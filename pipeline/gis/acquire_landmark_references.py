"""Keep landmark identity and measurement references separate from model rights."""
import json
from urllib.parse import urlencode
from datetime import datetime, timezone
from pathlib import Path
from pyproj import Transformer
from acquire_sources import API, RAW, MANIFESTS, get_json, records, download, save_json

ROOT = Path(__file__).resolve().parents[2]
metadata, meta_record = get_json(API + "public-art", RAW / "city/public-art-metadata.json")
query = "neighbourhood = 'Stanley Park' OR sitename like '%Stanley%'"
response, reference = get_json(API + "public-art/records?" + urlencode(dict(limit=100, where=query)),
    RAW / "city/public-art-park-records-0.json")
if response["total_count"] > 100:
    raise RuntimeError("Landmark query needs pagination")
rows, refs = response["results"], [reference]
origin = json.loads((MANIFESTS / "world-origin.json").read_text())
transform = Transformer.from_crs(4326, 3157, always_xy=True)
features = []
for row in rows:
    position = row.get("geo_point_2d")
    xy = transform.transform(position["lon"], position["lat"]) if position else None
    features.append(dict(id=str(row["registryid"]), name=row["title_of_work"],
        source="City public-art registry", url=row.get("url"),
        position_local_m=[xy[0] - origin["easting"], xy[1] - origin["northing"]] if xy else None,
        location_description=row.get("locationonsite"), status=row.get("status"),
        description=row.get("descriptionofwork"), material=row.get("primarymaterial"),
        accuracy="Address-based approximate point; not a surveyed placement control",
        reproduction_rights="Registry metadata licence does not grant artwork or photograph reproduction rights",
        model_status="Unbuilt; obtain dimensions and current placement evidence"))
sources = [dict(meta_record, intended_use="Identity and approximate location", rights=metadata["metas"]["default"]["license"]), *refs]
previous_path = MANIFESTS / "landmark-sources.json"
previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
previous_sources = {item["url"]: item for item in previous.get("sources", [])}
for name, url, period in [
    ("lions-gate-heritage.html", "https://www.canada.ca/en/news/archive/2010/05/lions-gate-bridge-national-historic-site.html", "2010-05; page details 2016-12-15"),
    ("lions-gate-risk-2018.pdf", "https://www2.gov.bc.ca/assets/gov/driving-and-transportation/reports-and-reference/reports-and-studies/lower-mainland/2018-03-16-lions-gate-risk-assessment.pdf", "2018-03-16"),
    ("city-landmarks.html", "https://vancouver.ca/parks-recreation-culture/landmarks-in-stanley-park.aspx", "Undated page; accessed 2026-09-26"),
]:
    # Retain failed downloads. A separate, explicit retry can update them later.
    if previous_sources.get(url, {}).get("status") == "unavailable":
        sources.append(previous_sources[url])
        continue
    try:
        record = download(url, RAW / "landmarks" / name, max_bytes=30_000_000)
        record.update(status="downloaded", intended_use="Measurement and identity reference only", rights="Reference only; do not distribute page images or text", period=period)
    except Exception as error:
        record = dict(url=url, status="unavailable", error=str(error), period=period)
    sources.append(record)
save_json(ROOT / "data/derived/landmark-registry.json", dict(features=features))
save_json(MANIFESTS / "landmark-sources.json", dict(retrieved_utc=datetime.now(timezone.utc).isoformat(),
    sources=sources, limitation="Identity register only. Individual geometry and location acceptance remain open."))
print(json.dumps(dict(features=[dict(id=x["id"], name=x["name"], position=x["position_local_m"]) for x in features],
    references=[dict(url=x["url"], status=x.get("status", "downloaded")) for x in sources]), indent=2))
