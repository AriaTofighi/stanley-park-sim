"""Acquire an independent 2016 NRCan DTM crop for path/control comparison."""
import json
from acquire_sources import RAW, MANIFESTS, save_json
from build_terrain import crop_raster

origin = json.loads((MANIFESTS / "world-origin.json").read_text())
search = json.loads((RAW / "nrcan/hrdem-search.json").read_text())
source = next(f for f in search["features"] if f["id"] == "BC-Lower_Mainland_2016-1m")
collection = json.loads((RAW / "nrcan/hrdem-collection.json").read_text())
record = crop_raster(source, "terrain_2016_reference", (488100, 5459300, 491900, 5462700),
                     1, origin, collection, write_mesh=False)
record["intended_use"] = "Independent historical ground surface for path modelling and comparison"
save_json(MANIFESTS / "geospatial-terrain_2016_reference.json", record)
