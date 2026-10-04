"""Read-only comparison of the 1,159 protected original mesh objects."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def check():
    baseline_path = ROOT/'evidence/m3-baseline-20261003/blender-original-geometry.json'
    before = json.loads(baseline_path.read_text())
    after = []
    for row in before:
        obj = bpy.data.objects.get(row['name'])
        if obj is None:
            after.append(dict(name=row['name'], missing=True))
            continue
        coordinates = np.empty(len(obj.data.vertices)*3, dtype=np.float32)
        obj.data.vertices.foreach_get('co', coordinates)
        indices = np.empty(len(obj.data.loops), dtype=np.int32)
        obj.data.loops.foreach_get('vertex_index', indices)
        after.append(dict(name=obj.name,
            geometry_sha256=hashlib.sha256(coordinates.tobytes()+indices.tobytes()).hexdigest(),
            matrix=[list(r) for r in obj.matrix_world], collision=obj.get('collision')))
    changes = [dict(before=a, after=b) for a,b in zip(before,after) if a != b]
    record = dict(time_utc=datetime.now(timezone.utc).isoformat(),
        baseline_sha256=hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
        source_objects=len(before), unchanged=not changes, changes=changes)
    (ROOT/'evidence/m3-original-geometry-comparison.json').write_text(json.dumps(record,indent=2))
    return dict(source_objects=len(before), unchanged=not changes, changes=len(changes))


if __name__ in {'__main__','<run_path>'}:
    result = check()
