"""Keep a 1 m historic DTM for path review. Do not change runtime geometry."""
from __future__ import annotations

import json

from acquire_sources import RAW, MANIFESTS, save_json
from build_terrain import crop_raster


def main():
    origin = json.loads((MANIFESTS / "world-origin.json").read_text())
    search = json.loads((RAW / "nrcan/hrdem-search.json").read_text())
    source = next(f for f in search["features"]
                  if f["id"] == "VILLE_VANCOUVER-VILLE_VANCOUVER-1m")
    collection = json.loads((RAW / "nrcan/hrdem-collection.json").read_text())
    record = crop_raster(source, "terrain_corridor_reference", (488100, 5459300, 491900, 5462700),
                         1, origin, collection, write_mesh=False, cache_product="terrain_park")
    record["intended_use"] = "Source resolution path review only; no runtime mesh or terrain replacement"
    record["limitations"].append(
        "The 1 m projected grid resamples a 1 m EPSG:3979 DTM. It is not a new survey, "
        "and does not establish 1 m horizontal or vertical accuracy.")
    save_json(MANIFESTS / "geospatial-terrain_corridor_reference.json", record)


if __name__ == "__main__":
    main()
