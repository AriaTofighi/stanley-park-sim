"""Author an original low-poly, rigged park explorer and four in-place FBX clips.

Run in background Blender. The character is independent of the environment.
Coordinates are authored directly in Unreal centimetres: +X forward, +Y right.
"""
import bpy
import math
import json
import hashlib
from pathlib import Path
from mathutils import Vector, Quaternion

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'exports/explorer'
OUT.mkdir(exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.file_preview_type = 'NONE'
scene = bpy.context.scene
scene.name = 'SP_Explorer'
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = .01
scene.render.fps = 30
materials = {}
for name, color in {'Jacket':(.055,.25,.24,1), 'Trousers':(.085,.11,.15,1),
                    'Boots':(.045,.05,.055,1), 'Skin':(.53,.30,.18,1),
                    'Pack':(.68,.26,.08,1), 'Trim':(.8,.72,.48,1),
                    'Hair':(.045,.027,.018,1), 'Eyes':(.018,.018,.018,1)}.items():
    mat = bpy.data.materials.new('M_Explorer_'+name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = color
    bsdf.inputs['Roughness'].default_value = .8
    materials[name] = mat

bpy.ops.object.armature_add(enter_editmode=True)
rig = bpy.context.object
rig.name = 'Rig_Explorer'
rig.data.name = 'SKEL_Explorer'
rig.data.edit_bones.remove(rig.data.edit_bones[0])
bone_defs = [('root',(0,0,0),(0,0,10),None),
             ('pelvis',(0,0,88),(0,0,103),'root'),
             ('spine',(0,0,103),(0,0,132),'pelvis'),
             ('head',(0,0,145),(0,0,172),'spine')]
for side, y in [('l',-1),('r',1)]:
    bone_defs += [(f'upperarm_{side}',(0,22*y,137),(0,29*y,111),'spine'),
                  (f'forearm_{side}',(0,29*y,111),(2,30*y,88),f'upperarm_{side}'),
                  (f'hand_{side}',(2,30*y,88),(3,30*y,80),f'forearm_{side}'),
                  (f'thigh_{side}',(0,11*y,89),(0,11*y,48),'pelvis'),
                  (f'calf_{side}',(0,11*y,48),(0,11*y,10),f'thigh_{side}'),
                  (f'foot_{side}',(0,11*y,10),(16,11*y,7),f'calf_{side}')]
for name, head, tail, parent in bone_defs:
    bone = rig.data.edit_bones.new(name)
    bone.head, bone.tail = head, tail
    if parent:
        bone.parent = rig.data.edit_bones[parent]
bpy.ops.object.mode_set(mode='OBJECT')
parts = []

def part(name, center, scale, material, bone, bevel=0):
    if bevel:
        bpy.ops.mesh.primitive_cube_add(size=2, location=center)
    else:
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=1, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        modifier = obj.modifiers.new('Soft edges','BEVEL')
        modifier.width = bevel
        modifier.segments = 2
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    obj.data.materials.append(materials[material])
    group = obj.vertex_groups.new(name=bone)
    group.add(list(range(len(obj.data.vertices))),1,'REPLACE')
    parts.append(obj)
    return obj

def limb(name, a, b, radius, material, bone):
    mid = (Vector(a)+Vector(b))*.5
    obj = part(name,mid,(radius,radius,(Vector(b)-Vector(a)).length*.59),material,bone)
    obj.rotation_euler = (Vector(b)-Vector(a)).to_track_quat('Z','Y').to_euler()

part('Jacket torso',(0,0,122),(13,22,25),'Jacket','spine',4)
part('Jacket hem',(0,0,99),(13,20,9),'Jacket','pelvis',3)
part('Neck',(0,0,146),(6,7,8),'Skin','head')
part('Face',(0,0,160),(10,10,14),'Skin','head')
part('Hair cap',(-1,0,169),(10.2,10.2,7),'Hair','head')
part('Nose',(10,0,159),(3,2.4,3),'Skin','head')
for y in [-4,4]:
    part('Eye',(9,y,163),(1.4,1.4,1.2),'Eyes','head')
    part('Brow',(9,y,166),(1.2,2,.7),'Hair','head')
part('Backpack',(-17,0,119),(8,16,21),'Pack','spine',4)
part('Pack pocket',(-25,0,114),(2,12,10),'Pack','spine',2)
part('Zipper',(13.3,0,122),(.6,.7,21),'Trim','spine',.3)
for side,y in [('l',-1),('r',1)]:
    part('Shoulder strap',(12,14*y,126),(2,2.5,18),'Pack','spine',1)
    limb('Upper sleeve',(0,22*y,136),(0,29*y,111),8,'Jacket','upperarm_'+side)
    limb('Lower sleeve',(0,29*y,112),(2,30*y,91),6.5,'Jacket','forearm_'+side)
    part('Hand',(3,30*y,85),(5,5,7),'Skin','hand_'+side)
    limb('Upper trousers',(0,11*y,89),(0,11*y,48),10,'Trousers','thigh_'+side)
    limb('Lower trousers',(0,11*y,48),(0,11*y,12),7.5,'Trousers','calf_'+side)
    part('Hiking boot',(6,11*y,7),(14,8,7),'Boots','foot_'+side,3)
    part('Boot sole',(6,11*y,2),(14,8,2),'Trim','foot_'+side,1)

bpy.ops.object.select_all(action='DESELECT')
for obj in parts:
    obj.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
mesh = bpy.context.object
mesh.name = 'SK_Explorer'
# Freeze mesh coordinates at the rig origin, preserving vertex groups.
bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
mesh.parent = rig
modifier = mesh.modifiers.new('Explorer skin','ARMATURE')
modifier.object = rig
rig.show_in_front = True
for bone in rig.pose.bones:
    bone.rotation_mode = 'XYZ'

clips = {}
def swing(name, angle):
    bone = rig.pose.bones[name]
    axis = bone.bone.matrix_local.to_3x3().inverted() @ Vector((0,1,0))
    bone.rotation_euler = Quaternion(axis, angle).to_euler()

for name, frames in [('Idle',60),('Walk',30),('Run',20),('Jump',24)]:
    rig.animation_data_clear()
    for frame in range(1,frames+2):
        phase = 2*math.pi*(frame-1)/frames
        for bone in rig.pose.bones:
            bone.rotation_euler = (0,0,0)
            bone.location = (0,0,0)
        if name in ('Walk','Run'):
            amplitude = .5 if name=='Walk' else .85
            for side, offset in [('l',0),('r',math.pi)]:
                wave = math.sin(phase+offset)
                swing('thigh_'+side, -amplitude*wave)
                swing('calf_'+side, max(0,wave)*(1.0 if name=='Walk' else 1.6))
                swing('upperarm_'+side, amplitude*.7*wave)
                swing('forearm_'+side, -.3 if name=='Walk' else -1.0)
            rig.pose.bones['pelvis'].location.y = abs(math.sin(phase))* (1.4 if name=='Walk' else 3)
        elif name=='Jump':
            for side in ('l','r'):
                swing('thigh_'+side, -.4)
                swing('calf_'+side, .7)
                swing('upperarm_'+side, .5)
                swing('forearm_'+side, -.8)
        else:
            rig.pose.bones['spine'].rotation_euler.x = .018*math.sin(phase)
        for bone in rig.pose.bones:
            bone.keyframe_insert('rotation_euler',frame=frame,group=bone.name)
            bone.keyframe_insert('location',frame=frame,group=bone.name)
    action = rig.animation_data.action
    action.name = 'A_Explorer_'+name
    action.use_fake_user = True
    scene.frame_start,scene.frame_end = 1,frames+1
    scene.frame_set(1)
    bpy.ops.object.select_all(action='DESELECT')
    rig.select_set(True)
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = rig
    path = OUT/(name+'.fbx')
    bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'MESH','ARMATURE'},
        use_space_transform=False,axis_forward='Y',axis_up='Z',global_scale=1,
        apply_unit_scale=True,apply_scale_options='FBX_SCALE_NONE',add_leaf_bones=False,
        bake_anim=True,bake_anim_use_nla_strips=False,bake_anim_use_all_actions=False,
        bake_anim_use_all_bones=True,bake_anim_simplify_factor=0,path_mode='STRIP',mesh_smooth_type='FACE')
    clips[name] = dict(file=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
rig.animation_data.action = bpy.data.actions['A_Explorer_Idle']
scene.frame_end=61
scene.frame_set(1)
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            s=area.spaces.active
            s.shading.type='SOLID'
            s.shading.color_type='MATERIAL'
            s.region_3d.view_location=(0,0,90)
            s.region_3d.view_distance=330
            s.region_3d.view_rotation=Vector((-1,-1,-.3)).to_track_quat('-Z','Y')
            s.clip_end=10000
rig.select_set(False)
bpy.context.view_layer.objects.active=mesh
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/Explorer.blend'),compress=True)
record=dict(source='blender/Explorer.blend',clips=clips,vertices=len(mesh.data.vertices),
            polygons=len(mesh.data.polygons),bones=len(rig.data.bones),
            materials={m.name:list(m.diffuse_color) for m in materials.values()},
            coordinates='centimetres, +X forward, +Y right, +Z up',application_tests_run=False)
(ROOT/'manifests/explorer.json').write_text(json.dumps(record,indent=2))
