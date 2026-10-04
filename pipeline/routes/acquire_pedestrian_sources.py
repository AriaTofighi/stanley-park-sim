"""Acquire one bounded public OSM extract, preserving the first downloaded file."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "manifests/pedestrian-source.json"


def main():
    source = json.loads(LEDGER.read_text(encoding="utf8"))
    path = ROOT / source["path"]
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(source["url"], headers={"User-Agent": "StanleyParkSim-development/0.1"})
        with urllib.request.urlopen(request, timeout=90) as response:
            data = response.read()
        # The dated snapshot is immutable. A newer API response must be saved
        # as a new source version and reviewed rather than replacing it.
        sha = hashlib.sha256(data).hexdigest()
        if sha != source["sha256"]:
            candidate = path.with_name("park-map-refresh-candidate.osm")
            candidate.write_bytes(data)
            raise RuntimeError(f"Current public data differs from the locked source. Review {candidate} and create a new dated ledger.")
        path.write_bytes(data)
    if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
        raise RuntimeError("Source hash differs from its ledger; stop before deriving geometry.")
    print(f"Source retained and hash verified: {path}")


if __name__ == "__main__":
    main()
