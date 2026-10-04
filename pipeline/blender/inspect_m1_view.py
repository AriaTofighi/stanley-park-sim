"""Set and retain a live Blender viewport review through its official MCP.

This does not simulate a ride or mark an inspection as passed. The caller must
open the saved image and record the actual result against the current package.
"""
import hashlib
import json
import math
import struct
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]


def inspect(view_id, capture_id, paired_unreal_evidence=None):
    if not capture_id.replace('-', '').replace('_', '').isalnum():
        raise ValueError('Use a simple evidence name')
    source = ROOT / 'manifests/m1-inspection-views.json'
    row = json.loads(source.read_text(encoding='utf8'))['views'][view_id]
    area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in area.regions if r.type == 'WINDOW')
    viewport = area.spaces.active
    paired = None
    output_size = (1600,1000)
    requested_fov = row.get('inspection_horizontal_fov_degrees')
    requested_lens = row.get('inspection_viewport_lens_mm',50.)
    if paired_unreal_evidence:
        paired_path = (ROOT/paired_unreal_evidence).resolve()
        if not paired_path.is_relative_to((ROOT/'evidence').resolve()):
            raise ValueError('Paired capture must be a saved evidence record')
        paired_record = json.loads(paired_path.read_text(encoding='utf8'))
        if paired_record['view'] != view_id:
            raise ValueError('Paired Unreal capture uses another camera')
        if hashlib.sha256((ROOT/paired_record['image']).read_bytes()).hexdigest() != paired_record['image_sha256']:
            raise ValueError('Paired Unreal image hash has changed')
        actual = paired_record['viewport_capture']
        location = actual['cameraLocation']
        actual_eye = [location['y']/100,location['x']/100,location['z']/100]
        delta = [b-a for a,b in zip(row['eye'],row['target'])]
        expected_angles = dict(pitch=math.degrees(math.atan2(delta[2],math.hypot(*delta[:2]))),
            yaw=math.degrees(math.atan2(delta[0],delta[1])),roll=0.)
        if math.dist(actual_eye,row['eye']) > .001 or any(
            abs((actual['cameraRotation'][key]-angle+180)%360-180) > .01
            for key,angle in expected_angles.items()):
            raise ValueError('The saved Unreal camera pose no longer matches this view record')
        requested_fov = float(actual['cameraFOV'])
        output_size = tuple(actual['decoded_png_dimensions_px'])
        paired = dict(path=paired_path.relative_to(ROOT).as_posix(),
            sha256=hashlib.sha256(paired_path.read_bytes()).hexdigest(),
            image=paired_record['image'],image_sha256=paired_record['image_sha256'],
            actual_unreal_camera_fov_degrees=requested_fov,output_dimensions_px=output_size)
    eye, target = Vector(row['eye']), Vector(row['target'])
    viewport.region_3d.view_rotation = (target-eye).to_track_quat('-Z', 'Y')
    viewport.region_3d.view_location = target
    viewport.region_3d.view_distance = (eye-target).length
    viewport.region_3d.view_perspective = 'PERSP'
    viewport.region_3d.update()
    prior_lens = float(viewport.lens)
    prior_projection = viewport.region_3d.window_matrix.copy()
    if requested_fov is not None:
        requested_fov = float(requested_fov)
        if not 1 < requested_fov < 170:
            raise ValueError('Inspection horizontal FOV is outside the useful range')
        # SpaceView3D is not a 36 mm sensor camera. Calibrate its effective
        # sensor span from the current projection instead of assuming one.
        effective_sensor_width = 2*prior_lens/abs(prior_projection[0][0])
        viewport.lens = effective_sensor_width/(2*math.tan(math.radians(requested_fov/2)))
    elif requested_lens is not None:
        viewport.lens = float(requested_lens)
    viewport.region_3d.update()
    projection = viewport.region_3d.window_matrix.copy()
    actual_fov = math.degrees(2*math.atan(1/abs(projection[0][0])))
    if requested_fov is not None and abs(actual_fov-requested_fov) > .05:
        viewport.lens = prior_lens
        raise ValueError('The actual viewport projection does not match the requested FOV')
    actual_view = dict(viewport_lens_mm=float(viewport.lens),
        viewport_horizontal_fov_degrees=actual_fov,
        viewport_vertical_fov_degrees=math.degrees(2*math.atan(1/abs(projection[1][1]))),
        viewport_region_dimensions_px=[region.width,region.height],
        viewport_projection_matrix=[list(r) for r in projection],
        requested_horizontal_fov_degrees=requested_fov,
        camera_equivalent_lens_mm_36mm_sensor=18/math.tan(math.radians(actual_fov/2)),
        prior_viewport_lens_mm=prior_lens,
        note='Projection-derived viewport FOV; 36 mm camera-equivalent lens is not the SpaceView3D lens.')
    viewport.clip_start = .25 if (eye-target).length < 30 else 2
    viewport.clip_end = 30000
    viewport.shading.type = 'SOLID'
    viewport.shading.color_type = 'MATERIAL'
    viewport.overlay.show_overlays = False
    scene = bpy.context.scene
    output = ROOT / 'evidence' / (capture_id + '.png')
    if output.exists():
        raise FileExistsError('Retain earlier reviews; use a new capture ID')
    old = (scene.render.filepath, scene.render.resolution_x,
           scene.render.resolution_y, scene.render.resolution_percentage)
    blend_hash_before = hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest()
    try:
        scene.render.filepath = str(output)
        scene.render.resolution_x, scene.render.resolution_y = output_size
        scene.render.resolution_percentage = 100
        with bpy.context.temp_override(area=area, region=region):
            bpy.ops.render.opengl(write_still=True, view_context=True)
    finally:
        (scene.render.filepath, scene.render.resolution_x,
         scene.render.resolution_y, scene.render.resolution_percentage) = old
    png = output.read_bytes()
    if png[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('The saved viewport image is not PNG')
    actual_view['saved_png_dimensions_px'] = list(struct.unpack('>II',png[16:24]))
    actual_view['saved_image_vertical_fov_from_horizontal_and_aspect_degrees'] = math.degrees(2*math.atan(
        math.tan(math.radians(actual_fov/2))*actual_view['saved_png_dimensions_px'][1]/actual_view['saved_png_dimensions_px'][0]))
    blend_hash_after = hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest()
    if blend_hash_before != blend_hash_after:
        raise RuntimeError('The source blend changed on disk during inspection')
    result = dict(view=view_id, camera=row, scene=scene.name,
                  image=output.relative_to(ROOT).as_posix(),
                  method='Live Blender viewport render through official MCP',
                  actual_viewport=actual_view,paired_unreal_evidence=paired,
                  view_manifest_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  image_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                  source_blend_sha256=blend_hash_after,source_blend_unchanged_on_disk=True,
                  source_blend=str(Path(bpy.data.filepath).relative_to(ROOT)).replace('\\','/'),
                  authored_mesh_count=sum(o.type=='MESH' and bool(o.get('pipeline_owner')) for o in scene.objects),
                  inspected=False, accepted=False)
    output.with_suffix('.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf8')
    return result
