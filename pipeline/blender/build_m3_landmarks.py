"""Author original M3 landmark surfaces in the separate Seawall source.

Run through the Blender connection. This pass only changes object material slots.
No source mesh, shape, transform, collision, M1 material or shared mesh is edited.
"""
from pathlib import Path
import hashlib
import json
import re

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OWNER = 'seawall_m3_landmarks'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def geometry_state(obj):
    """Byte-level source geometry and transform binding; material slots excluded."""
    coordinates = np.empty(len(obj.data.vertices) * 3, dtype=np.float32)
    obj.data.vertices.foreach_get('co', coordinates)
    indices = np.empty(len(obj.data.loops), dtype=np.int32)
    obj.data.loops.foreach_get('vertex_index', indices)
    return dict(geometry_sha256=hashlib.sha256(coordinates.tobytes()+indices.tobytes()).hexdigest(),
                matrix=[list(row) for row in obj.matrix_world], collision=obj.get('collision'))


def profile(name):
    low = name.lower()
    if any(x in low for x in ('wood', 'cedar')):
        return dict(kind='timber', channel=1, tile_m=1.4, contrast=.34, roughness=.86, metallic=0., relief_m=.0015)
    if any(x in low for x in ('bronze', 'gun')):
        return dict(kind='metal', channel=2, tile_m=.8, contrast=.16, roughness=.46, metallic=.65, relief_m=.0001)
    if any(x in low for x in ('steel', 'cable', 'green', 'flashing')):
        return dict(kind='painted-metal', channel=2, tile_m=1.8, contrast=.10, roughness=.50, metallic=.25, relief_m=.0001)
    if any(x in low for x in ('glass', 'lanterndark')):
        return dict(kind='opaque-glazing', channel=2, tile_m=2., contrast=.025, roughness=.20, metallic=.1, relief_m=0.)
    if 'roof' in low:
        return dict(kind='roof', channel=0, tile_m=1.2, contrast=.22, roughness=.84, metallic=0., relief_m=.0007)
    if any(x in low for x in ('stone', 'concrete', 'foundation', 'pool_rim', 'pool_floor')):
        return dict(kind='mineral', channel=0, tile_m=1.8, contrast=.30, roughness=.88, metallic=0., relief_m=.0018)
    return dict(kind='painted-masonry', channel=2, tile_m=1.1, contrast=.13, roughness=.76, metallic=0., relief_m=.0003)


def texture(folder):
    n = 512
    rng = np.random.default_rng(301073)
    f = np.fft.fftfreq(n)
    radius = np.hypot(f[:, None], f[None, :])
    def noise(power):
        spectrum = (radius + .008) ** -power
        spectrum[0, 0] = 0
        a = np.fft.ifft2(np.fft.fft2(rng.normal(size=(n,n))) * spectrum).real
        return a / max(a.std(), 1e-9)
    stone = noise(1.25)
    y, x = np.mgrid[:n, :n] / n
    # Every term has integer spatial frequency: all texture edges tile.
    timber = np.sin(2*np.pi*(x*35 + .36*np.sin(y*2*np.pi) + .18*np.sin(x*6*np.pi)))
    timber += .3*np.sin(x*2*np.pi*91 + .4*np.sin(y*4*np.pi))
    paint = noise(.7)
    pixels = np.stack((np.clip(.5+stone*.13,0,1), np.clip(.5+timber*.21,0,1),
                       np.clip(.5+paint*.12,0,1), np.ones((n,n))), axis=-1)
    name = 'T_M3LandmarkGrain_' + folder.name
    image = bpy.data.images.get(name) or bpy.data.images.new(name,width=n,height=n,alpha=False)
    image.colorspace_settings.name = 'Non-Color'
    image.pixels.foreach_set(pixels.astype(np.float32).ravel())
    image.filepath_raw = str(folder/'T_M3LandmarkGrain.png')
    image.file_format = 'PNG'
    image.save()
    return image


def make_material(name, color, spec, image, version):
    label = 'M_M3Landmark_'+re.sub(r'[^A-Za-z0-9_]', '_', name)+'_'+version
    material = bpy.data.materials.get(label)
    if material: return material
    material = bpy.data.materials.new(label)
    material.use_nodes = True
    material.diffuse_color = (*color, 1.)
    nodes, links = material.node_tree.nodes, material.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    bsdf.inputs['Roughness'].default_value = spec['roughness']
    bsdf.inputs['Metallic'].default_value = spec['metallic']
    coords = nodes.new('ShaderNodeTexCoord')
    scale = nodes.new('ShaderNodeVectorMath'); scale.operation = 'SCALE'
    scale.inputs[3].default_value = 1/spec['tile_m']
    links.new(coords.outputs['Object'], scale.inputs[0])
    sample = nodes.new('ShaderNodeTexImage'); sample.image=image
    sample.projection='BOX'; sample.projection_blend=.3
    links.new(scale.outputs[0], sample.inputs['Vector'])
    split=nodes.new('ShaderNodeSeparateColor'); split.mode='RGB'
    links.new(sample.outputs['Color'], split.inputs[0])
    adjust=nodes.new('ShaderNodeMath'); adjust.operation='MULTIPLY_ADD'
    links.new(split.outputs[spec['channel']],adjust.inputs[0])
    adjust.inputs[1].default_value=spec['contrast']*2
    adjust.inputs[2].default_value=1-spec['contrast']
    tint=nodes.new('ShaderNodeMixRGB'); tint.blend_type='MULTIPLY'; tint.inputs[0].default_value=1
    tint.inputs[1].default_value=(*color,1)
    links.new(adjust.outputs[0],tint.inputs[2]); links.new(tint.outputs[0],bsdf.inputs['Base Color'])
    if spec['relief_m']:
        bump=nodes.new('ShaderNodeBump'); bump.inputs['Distance'].default_value=spec['relief_m']
        links.new(split.outputs[spec['channel']],bump.inputs['Height']); links.new(bump.outputs[0],bsdf.inputs['Normal'])
    material['pipeline_owner']=OWNER
    return material


def build():
    if Path(bpy.data.filepath).resolve() != (ROOT/'blender/StanleyPark_Seawall.blend').resolve():
        raise RuntimeError('Open the separate Seawall source')
    scene=bpy.data.scenes.get('StanleyPark_M1')
    if scene is None or scene.unit_settings.scale_length != 1: raise RuntimeError('Expected metre source scene')
    settings_path=ROOT/'manifests/m3-landmark-settings.json'
    settings=json.loads(settings_path.read_text())
    export_path=ROOT/'manifests/blender-export.json'
    source=json.loads(export_path.read_text())
    route_path=ROOT/'data/derived/paved-circuit-runtime.json'
    route=np.asarray(json.loads(route_path.read_text())['points_local_m'])[:,:2]
    route_steps=np.diff(route,axis=0); lengths=np.linalg.norm(route_steps,axis=1)
    chain=np.r_[0,np.cumsum(lengths)]
    inputs={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in [settings_path,export_path,route_path,Path(__file__)]}
    rows=[]; rejected=[]
    for asset in source['assets']:
        name=asset['name']
        groups=[group for group,prefixes in settings['groups'].items() if name.startswith(tuple(prefixes))]
        if not groups or not asset.get('place_in_level'): continue
        if any(x in name for x in settings['excluded_object_fragments']): continue
        group=groups[0]
        obj=scene.objects.get(asset.get('source_object',name))
        if obj is None or obj.type!='MESH': raise RuntimeError('Missing landmark source '+name)
        centre=np.mean([tuple(obj.matrix_world @ v.co) for v in obj.data.vertices],axis=0)[:2]
        t=np.clip(np.sum((centre-route[:-1])*route_steps,axis=1)/np.maximum(lengths**2,1e-9),0,1)
        distances=np.linalg.norm(centre-(route[:-1]+route_steps*t[:,None]),axis=1)
        nearest=int(distances.argmin()); distance=float(distances[nearest])
        if distance>settings['route_distance_limit_m'] and group not in settings['distance_exempt_groups']:
            rejected.append(dict(name=name,group=group,distance_m=distance)); continue
        slots=[]
        for slot,mat in enumerate(asset['materials']):
            if any(x in mat.lower() for x in settings['exclude_material_fragments']): continue
            if slot>=len(obj.material_slots): raise RuntimeError('Material slot mismatch '+name)
            slots.append(dict(slot=slot,source_material=mat,color=asset['material_colors'][slot][:3],profile=profile(mat)))
        if not slots: continue
        # Bind every concrete local source record, retaining its existing estimates.
        for candidate in re.findall(r'manifests/[A-Za-z0-9_./-]+\.json',asset.get('source_id','')):
            path=ROOT/candidate
            if path.is_file(): inputs[candidate]=sha(path)
        rows.append(dict(name=name,source_object=obj.name,asset_path=asset['asset_path'],
            group=group,source_id=asset.get('source_id'),distance_from_route_m=distance,
            route_station_m=float(chain[nearest]+lengths[nearest]*t[nearest]),slots=slots,
            geometry_before=geometry_state(obj)))
    if not rows: raise RuntimeError('No route-visible landmark material targets')
    version=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:12]
    folder=ROOT/'exports/seawall-landmarks'/version; folder.mkdir(parents=True,exist_ok=True)
    manifest_path=folder/'manifest.json'
    image=texture(folder)
    for row in rows:
        obj=scene.objects[row['source_object']]
        for slot in row['slots']:
            mat=make_material(slot['source_material'],slot['color'],slot['profile'],image,version)
            slot['blender_material']=mat.name
            # Object-linked material slots avoid changing shared mesh datablocks.
            obj.material_slots[slot['slot']].link='OBJECT'
            obj.material_slots[slot['slot']].material=mat
        if row['geometry_before']!=geometry_state(obj): raise RuntimeError('Landmark geometry changed '+obj.name)
    record=dict(schema_version=1,version=version,input_hashes=inputs,asset_root='/Game/StanleyPark/Seawall/Landmarks/v_'+version,
        source_blend='blender/StanleyPark_Seawall.blend',map='/Game/Maps/StanleyParkSeawall',
        texture=dict(name='T_M3LandmarkGrain',path=Path(image.filepath_raw).relative_to(ROOT).as_posix(),sha256=sha(Path(image.filepath_raw))),
        targets=rows,excluded_by_distance=rejected,settings=settings,geometry_collision_unchanged=True,
        application_test=False,visual_acceptance=False)
    manifest_path.write_text(json.dumps(record,indent=2),encoding='utf8')
    (folder.parent/'latest.json').write_text(json.dumps(dict(manifest=manifest_path.relative_to(ROOT).as_posix(),sha256=sha(manifest_path)),indent=2))
    bpy.context.view_layer.update()
    return dict(version=version,targets=len(rows),materials=len({s['blender_material'] for r in rows for s in r['slots']}),manifest=str(manifest_path),saved_blend=False)


if __name__ in {'__main__', '<run_path>'}:
    result=build()
