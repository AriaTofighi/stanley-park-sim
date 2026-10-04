"""Copy and ingest only completed, catalogued park downloads. No browser state."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
downloads=Path.home()/"Downloads"
tiles=json.loads((ROOT/"manifests/geospatial-lidar-selection.json").read_text())["tiles"]
for item in sorted(tiles,key=lambda t:t["name"]):
    name=item["name"]
    source=downloads/f"{name}.zip"
    dest=ROOT/f"data/raw/city/lidar2022/{name}.zip"
    if not dest.exists():
        if not source.exists():
            print("NOT AVAILABLE",name,flush=True)
            continue
        if shutil.disk_usage(ROOT).free < source.stat().st_size + 10_000_000_000:
            raise RuntimeError("Preserve at least 10GB free while copying survey source")
        shutil.copyfile(source,dest)
    record=ROOT/f"manifests/lidar2022-{name}.json"
    if record.exists() and "canopy_sampling" in json.loads(record.read_text()):
        print("UNCHANGED",name,flush=True)
        continue
    print("INGEST",name,flush=True)
    subprocess.run([sys.executable,str(ROOT/"pipeline/gis/ingest_user_survey.py"),"--tile",name],check=True,cwd=ROOT)
