"""Create and export a three-bone, one-second measured animation fixture."""
import bpy
import json
import math
import hashlib
from pathlib import Path
from mathutils import Matrix,Vector

ROOT=Path(__file__).resolve().parents[2]
park=bpy.data.scenes['StanleyPark_M1']
scene=bpy.data.scenes.get('SP_AnimationFixture') or bpy.data.scenes.new('SP_AnimationFixture')
bpy.context.window.scene=scene
scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.
scene.render.fps=30;scene.frame_start=1;scene.frame_end=31
if bpy.context.object and bpy.context.object.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
for obj in list(scene.objects):
    if obj.get('pipeline_owner')=='animation_fixture':bpy.data.objects.remove(obj,do_unlink=True)
bpy.ops.object.armature_add(enter_editmode=True)
rig=bpy.context.object;rig.name='Rig_AnimationFixture';rig['pipeline_owner']='animation_fixture'
root=rig.data.edit_bones[0];root.name='SP_Root';root.head=(0,0,0);root.tail=(0,0,.5)
hinge=rig.data.edit_bones.new('SP_Hinge');hinge.head=root.tail;hinge.tail=(0,0,1.5);hinge.parent=root;hinge.use_connect=True
marker=rig.data.edit_bones.new('SP_Marker');marker.head=hinge.tail;marker.tail=(0,0,1.7);marker.parent=hinge;marker.use_connect=True
bpy.ops.object.mode_set(mode='OBJECT')
vertices=[];faces=[]
for z0,z1,half in [(0,.5,.12),(.5,1.5,.07),(1.5,1.7,.12)]:
    offset=len(vertices)
    vertices.extend([(x,y,z) for z in [z0,z1] for x,y in [(-half,-half),(half,-half),(half,half),(-half,half)]])
    faces.extend([tuple(offset+i for i in f) for f in [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]])
mesh=bpy.data.meshes.new('SK_AnimationFixture');mesh.from_pydata(vertices,[],faces);mesh.update()
obj=bpy.data.objects.new('SK_AnimationFixture',mesh);scene.collection.objects.link(obj);obj['pipeline_owner']='animation_fixture'
for i,name in enumerate(['SP_Root','SP_Hinge','SP_Marker']):
    group=obj.vertex_groups.new(name=name);group.add(list(range(i*8,(i+1)*8)),1.,'REPLACE')
modifier=obj.modifiers.new('EditableArmature','ARMATURE');modifier.object=rig;obj.parent=rig
mat=bpy.data.materials.get('M_AnimationFixture') or bpy.data.materials.new('M_AnimationFixture')
mat.diffuse_color=(.85,.3,.08,1.);mesh.materials.append(mat)
pose=rig.pose.bones['SP_Hinge'];pose.rotation_mode='XYZ'
for frame,angle in [(1,0.),(16,math.pi*.5),(31,0.)]:
    pose.rotation_euler=(angle,0,0);pose.keyframe_insert('rotation_euler',frame=frame,group='SP_Hinge')
rig.animation_data.action.name='A_Fixture_Hinge_OneSecond'
samples=[]
for frame in [1,8.5,16,23.5,31]:
    scene.frame_set(int(frame),subframe=frame-int(frame));bpy.context.view_layer.update()
    bones={}
    for bone in rig.pose.bones:
        point=rig.matrix_world@bone.head
        bones[bone.name]=[point.y*100,point.x*100,point.z*100]
    samples.append(dict(seconds=(frame-1)/30,bone_heads_unreal_cm=bones))
scene.frame_set(1)
copies=[]
rotation=Matrix.Rotation(-math.pi/2,4,'Z')
copy_rig=rig.copy();copy_rig.data=rig.data.copy();copy_rig.data.transform(rotation);scene.collection.objects.link(copy_rig);copies.append(copy_rig)
copy_mesh=obj.copy();copy_mesh.data=mesh.copy();copy_mesh.data.transform(rotation);copy_mesh.parent=copy_rig
copy_mesh.modifiers[0].object=copy_rig;scene.collection.objects.link(copy_mesh);copies.append(copy_mesh)
bpy.ops.object.select_all(action='DESELECT')
for item in copies:item.select_set(True)
bpy.context.view_layer.objects.active=copy_rig
out=ROOT/'exports/fbx/SK_AnimationFixture.fbx'
try:
    bpy.ops.export_scene.fbx(filepath=str(out),use_selection=True,object_types={'MESH','ARMATURE'},
        use_space_transform=False,axis_forward='Y',axis_up='Z',global_scale=1.,apply_unit_scale=True,
        apply_scale_options='FBX_SCALE_NONE',bake_space_transform=False,add_leaf_bones=False,
        primary_bone_axis='Y',secondary_bone_axis='X',use_armature_deform_only=False,
        bake_anim=True,bake_anim_use_nla_strips=False,bake_anim_use_all_actions=False,
        bake_anim_use_all_bones=True,bake_anim_step=1.,bake_anim_simplify_factor=0.,
        path_mode='STRIP',use_custom_props=False,mesh_smooth_type='FACE')
finally:
    for item in copies:bpy.data.objects.remove(item,do_unlink=True)
scene.frame_set(16)
eye,target=Vector((3,-4,2.5)),Vector((0,-.35,.9))
for area in bpy.context.screen.areas:
    if area.type=='VIEW_3D':
        s=area.spaces.active;s.region_3d.view_perspective='PERSP'
        s.region_3d.view_rotation=(target-eye).to_track_quat('-Z','Y');s.region_3d.view_distance=(target-eye).length;s.region_3d.view_location=target
        s.shading.type='SOLID';s.shading.color_type='MATERIAL';s.overlay.show_overlays=True
manifest=dict(blender=bpy.app.version_string,source_scene=scene.name,source_blend='blender/StanleyPark_Blockout.blend',
    fbx=out.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
    fps=30,frames=[1,31],duration_seconds=1.,bone_names=['SP_Root','SP_Hinge','SP_Marker'],samples=samples,
    translation_tolerance_cm=1.,duration_tolerance_seconds=1/30,engine_pass=False,
    source_rights='Original authored diagnostic fixture; no external assets')
(ROOT/'manifests/animation-fixture.json').write_text(json.dumps(manifest,indent=2)+'\n')
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/StanleyPark_Blockout.blend'))
result=dict(scene=scene.name,fbx=str(out),sample_count=len(samples),engine_pass=False)
