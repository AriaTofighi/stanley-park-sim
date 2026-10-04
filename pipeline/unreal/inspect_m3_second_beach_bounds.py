"""Read actual imported bounds without changing editor assets or actors."""
from pathlib import Path
import json
import unreal
ROOT=Path(__file__).resolve().parents[2]
pointer=json.loads((ROOT/'exports/m3-second-beach-detail/latest.json').read_text())
source=json.loads((ROOT/pointer['manifest']).read_text())
assets=unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
rows=[]
for item in source['assets']:
    mesh=assets.load_asset(source['asset_root']+'/Meshes/'+item['name'])
    row=dict(name=item['name'],expected_bounds_cm=item['bounds_min_cm']+item['bounds_max_cm'],loaded=mesh is not None)
    if isinstance(mesh,unreal.StaticMesh):
        box=mesh.get_bounding_box();actual=[box.min.x,box.min.y,box.min.z,box.max.x,box.max.y,box.max.z]
        row.update(actual_bounds_cm=actual,delta_cm=[a-b for a,b in zip(actual,row['expected_bounds_cm'])],
            import_file=mesh.get_editor_property('asset_import_data').get_first_filename())
    rows.append(row)
result=dict(manifest=pointer['manifest'],assets=rows,read_only=True)
(ROOT/'evidence/m3-second-beach-native-bounds-diagnosis.json').write_text(json.dumps(result,indent=2))
