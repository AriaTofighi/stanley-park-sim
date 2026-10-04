"""Copy only confirmed inward components; reverse winding without moving vertices."""
from pathlib import Path
import hashlib
import json
import runpy

import bpy
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
OWNER='SP_M3LandmarkWinding'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def geometry(obj):
    mesh=obj.data
    return dict(vertices=[tuple(v.co) for v in mesh.vertices],faces=[list(p.vertices) for p in mesh.polygons],
        materials=[m.name for m in mesh.materials],slots=[p.material_index for p in mesh.polygons],
        smooth=[p.use_smooth for p in mesh.polygons],matrix=[list(r) for r in obj.matrix_world],collision=obj.get('collision'))


def build():
    if Path(bpy.data.filepath).resolve()!=(ROOT/'blender/StanleyPark_Seawall.blend').resolve():raise RuntimeError('Open Seawall source')
    audit_path='evidence/m3-landmark-winding-diagnosis.json';audit=json.loads((ROOT/audit_path).read_text())
    helpers=runpy.run_path(str(ROOT/'pipeline/blender/build_seawall_tree_library.py'),run_name='winding_export')
    check=runpy.run_path(str(ROOT/'pipeline/blender/diagnose_m3_landmark_winding.py'),run_name='winding_components')['components']
    paths=['pipeline/blender/build_m3_landmark_winding.py','pipeline/blender/diagnose_m3_landmark_winding.py','pipeline/blender/build_seawall_tree_library.py',audit_path]
    inputs={p:sha(ROOT/p) for p in paths}
    for path,digest in audit['input_hashes'].items():
        if sha(ROOT/path)!=digest:raise RuntimeError('Winding audit source changed: '+path)
        inputs[path]=digest
    version=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:12]
    folder=ROOT/'exports/m3-landmark-winding'/version;path=folder/'manifest.json'
    if path.exists():raise RuntimeError('Immutable winding export exists')
    source_records={r['name']:r for r in audit['assets']}
    originals=[bpy.data.objects[name] for name in audit['affected_asset_names']]
    before={o.name:geometry(o) for o in originals}
    collection=bpy.data.collections.new(OWNER+'_'+version);bpy.context.scene.collection.children.link(collection)
    folder.mkdir(parents=True,exist_ok=True);assets=[]
    for original in originals:
        baseline=before[original.name];record=source_records[original.name]
        vertex_hash=hashlib.sha256(np.asarray(baseline['vertices'],dtype='<f8').tobytes()).hexdigest()
        if vertex_hash!=record['vertex_positions_sha256']:raise RuntimeError('Vertex audit differs: '+original.name)
        if hashlib.sha256(json.dumps(baseline['faces']).encode()).hexdigest()!=record['faces_sha256']:raise RuntimeError('Face audit differs: '+original.name)
        if original.data.has_custom_normals:raise RuntimeError('Custom normals need an explicit repair path')
        if any(abs(original.scale[i]-1)>1e-8 for i in range(3)) or any(abs(v)>1e-8 for v in original.rotation_euler):raise RuntimeError('Unexpected source transform')
        source=json.loads((ROOT/record['source_manifest']).read_text());src=next(a for a in source['assets'] if a['name']==original.name)
        obj=original.copy();obj.data=original.data.copy();obj.name='SM_M3Winding_'+original.name.removeprefix('SM_')+'_'+version;obj.data.name=obj.name
        collection.objects.link(obj);obj.hide_render=False;obj.hide_viewport=False;obj.hide_set(False)
        mesh=obj.data;affected=sorted({i for part in record['components'] if part['repair_required'] for i in part['face_indexes']})
        # Preserve every corner UV by vertex, not by old corner order.
        uv={layer.name:{i:{mesh.loops[j].vertex_index:tuple(layer.data[j].uv) for j in mesh.polygons[i].loop_indices} for i in affected} for layer in mesh.uv_layers}
        for i in affected:mesh.polygons[i].flip()
        mesh.update()
        for layer in mesh.uv_layers:
            for i in affected:
                for j in mesh.polygons[i].loop_indices:layer.data[j].uv=uv[layer.name][i][mesh.loops[j].vertex_index]
        for layer in mesh.uv_layers:
            for i in affected:
                for j in mesh.polygons[i].loop_indices:
                    if tuple(layer.data[j].uv)!=uv[layer.name][i][mesh.loops[j].vertex_index]:raise RuntimeError('Winding repair changed corner UV')
        after=geometry(obj)
        if after['vertices']!=baseline['vertices']:raise RuntimeError('Winding repair moved vertices')
        for key in ['materials','slots','smooth','matrix','collision']:
            if after[key]!=baseline[key]:raise RuntimeError('Winding repair changed '+key)
        for i,(a,b) in enumerate(zip(baseline['faces'],after['faces'])):
            if sorted(a)!=sorted(b):raise RuntimeError('Winding repair changed face membership')
            if i not in affected and a!=b:raise RuntimeError('Winding repair changed unaffected face')
        checked=check(after['vertices'],after['faces'])
        if any(c['repair_required'] for c in checked):raise RuntimeError('Winding repair left inward components')
        obj['pipeline_owner']=OWNER;obj['collision']='none';obj['feature_id']=src['feature_id'];obj['winding_source']=original.name
        item=helpers['export_object'](obj,folder,bpy.context.scene)
        if item['bounds_min_cm']!=src['bounds_min_cm'] or item['bounds_max_cm']!=src['bounds_max_cm']:raise RuntimeError('Winding repair changed bounds')
        if item['position_cm']!=src['position_cm']:raise RuntimeError('Winding repair changed position')
        item.update(feature_id=src['feature_id'],source_label=src.get('source_label',original.name),position_local_m=list(obj.location),
            original_name=original.name,original_manifest=record['source_manifest'],
            original_asset_root=source['asset_root'],material_paths={m.name:source['asset_root']+'/Materials/'+m.name for m in mesh.materials},
            vertex_positions_sha256=vertex_hash,faces_reversed=affected,
            corrected_components=sum(c['repair_required'] for c in record['components']),remaining_inward_components=0,
            invariant_vertices_bounds_transforms_materials=True)
        assets.append(item)
    if before!={o.name:geometry(o) for o in originals}:raise RuntimeError('Original decorative geometry changed')
    hidden=[dict(name=o.name,hide_render=o.hide_render,hide_viewport=o.hide_viewport,hide_set=o.hide_get()) for o in originals]
    manifest=dict(schema_version=1,version=version,owner=OWNER,input_hashes=inputs,assets=assets,
        asset_root='/Game/StanleyPark/Seawall/LandmarkWinding/v_'+version,hidden_originals=hidden,
        settings=dict(materials=[],limits='Winding-only copies of 15 confirmed affected decorative assets. All vertices, bounds, transforms, slots, materials and corner UVs remain fixed. Original assets and collision remain intact. Broad artwork and source-location limits are unchanged.'),
        original_geometry_collision_unchanged=True,new_collision='none',visual_acceptance=False,geographic_accuracy_accepted=False,
        vertices_bounds_transforms_materials_invariant=True,affected_asset_count=len(assets),affected_face_count=sum(len(a['faces_reversed']) for a in assets))
    path.write_text(json.dumps(manifest,indent=2)+'\n');(folder.parent/'latest.json').write_text(json.dumps(dict(manifest=path.relative_to(ROOT).as_posix(),sha256=sha(path)),indent=2)+'\n')
    for o in originals:o.hide_render=True;o.hide_set(True)
    return dict(version=version,manifest=path.relative_to(ROOT).as_posix(),assets=len(assets),reversed_faces=manifest['affected_face_count'],invariants=True)


if __name__ in {'__main__','<run_path>'}:
    result=build()
