"""Preserve the fixed pre-v14 review without changing source images or picks."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evidence/m1-source-review/pre-v14"
OUT.mkdir(exist_ok=True)
files = [p for p in (ROOT / "evidence/m1-source-review").glob("*") if p.is_file()]
files += [ROOT / name for name in ["docs/M1-SOURCE-REVIEW-RESULTS.md", "manifests/m1-control-validation-protocol.json", "manifests/m1-source-feature-picks.json"]]
records = []
for path in files:
    target = OUT / path.name
    if target.exists() and target.read_bytes() != path.read_bytes():
        raise RuntimeError(f"The preserved result differs: {target}")
    shutil.copy2(path, target)
    records.append({"original": path.relative_to(ROOT).as_posix(), "saved": target.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
(OUT / "snapshot.json").write_text(json.dumps({"purpose": "Frozen review before v14 correction; all failures retained", "files": records}, indent=2) + "\n", encoding="utf8")
print(f"Preserved {len(records)} review files")
