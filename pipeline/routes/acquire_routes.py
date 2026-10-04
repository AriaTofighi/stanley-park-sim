# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx==0.28.1"]
# ///
"""Acquire immutable City route data. Does not infer permissions or change geometry."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/routes/raw"
SOURCES = {
    "city_bikeways_metadata.json": "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/bikeways",
    "city_bikeways.geojson": "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/bikeways/exports/geojson",
    "city_open_data_licence.html": "https://vancouver.opendatasoft.com/pages/licence/",
    "official_park_map_2026.pdf": "https://vancouver.ca/files/cov/stanley-park-map-and-guide.pdf",
}


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    ledger_path = ROOT / "manifests/routes-sources.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {
        "schema_version": 1,
        "licence": "Open Government Licence - Vancouver for City bikeways; ordinary reference PDFs are separate.",
        "attribution": "Contains information licensed under the Open Government Licence - Vancouver.",
        "sources": [],
    }
    with httpx.Client(follow_redirects=True, timeout=90) as client:
        for filename, url in SOURCES.items():
            path = RAW / filename
            if path.exists():
                print(f"Keep existing immutable file: {path.relative_to(ROOT)}")
                continue
            response = client.get(url)
            entry = {
                "id": filename.split(".")[0], "url": url,
                "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                "http_status": response.status_code,
            }
            if response.is_success:
                path.write_bytes(response.content)
                entry.update(path=str(path.relative_to(ROOT)).replace("\\", "/"),
                             sha256=hashlib.sha256(response.content).hexdigest(),
                             bytes=len(response.content),
                             incorporation="open_data" if filename.startswith("city_bikeways") else "reference_only")
                print(f"Saved {filename}: {len(response.content)} bytes")
            else:
                entry["status"] = "unavailable_do_not_substitute_or_claim_read"
                print(f"Unavailable {filename}: HTTP {response.status_code}")
            ledger["sources"].append(entry)
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
