"""Acquire measured corridor references; design proposals are not as-built data."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline/gis"))
from acquire_sources import download, save_json

sources = [
    ("maze-gates-2025.pdf", "https://parkboardmeetings.vancouver.ca/2025/20250310/REPORT-EnhancedAccessibilityonSeawallCyclingPath-ReportBack-20250310.pdf", "reference_only", "2025-03-10 report; distinguish existing condition from design options"),
    ("orthophoto-2022-metadata.json", "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/orthophoto-imagery-2022", "Open Government Licence - Vancouver", "2022-06-06 through 2022-07-01 capture"),
    ("orthophoto-portal-item.json", "https://maps.vancouver.ca/portal/sharing/rest/content/items/89af6990b7334aeab8792b50351287a6?f=pjson", "check service item terms", "2022 imagery service descriptor"),
]
records = []
for name, url, rights, period in sources:
    try:
        record = download(url, ROOT / "data/raw/corridor" / name, max_bytes=25_000_000)
        record.update(rights=rights, capture_or_document_period=period, status="downloaded")
    except Exception as error:
        record = dict(url=url, rights=rights, status="unavailable", error=str(error))
    records.append(record)
    print(json.dumps(record), flush=True)
save_json(ROOT / "manifests/corridor-references.json", dict(retrieved_utc=datetime.now(timezone.utc).isoformat(), records=records))
