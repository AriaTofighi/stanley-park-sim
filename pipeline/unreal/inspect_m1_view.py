"""Set named review views without changing authored geometry or game state."""
import json
import math
import runpy
from pathlib import Path
import unreal

ROOT=Path(__file__).resolve().parents[2]

def inspect(view):
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    if editor.get_game_world() is not None:raise RuntimeError('Stop play before setting an editor view')
    if view=='material_transfer':
        return runpy.run_path(str(ROOT/'pipeline/unreal/inspect_vertex_colors.py'))['inspect']()
    if view=='surface_failures':
        return runpy.run_path(str(ROOT/'pipeline/unreal/inspect_surface_failures.py'))['inspect']()
    if view=='source_surface_transfer':
        return runpy.run_path(str(ROOT/'pipeline/unreal/check_source_surface_ray_transfer.py'))['check']()
    if view=='girl_visibility':
        return runpy.run_path(str(ROOT/'pipeline/unreal/inspect_girl_visibility.py'))['inspect']()
    # Positions are local east, north, up metres, matching the Blender reviews.
    views={
        'siwash':((-900,650,32),(-942,692,8)),
        'brockton':((1911,-211,12),(1894,-188,10)),
        'lions_gate_west':((-55,1520,75),(350,1450,58)),
        'forest_groups':((1450,120,145),(1250,-100,30)),
    }
    shared = json.loads((ROOT/'manifests/m1-inspection-views.json').read_text(encoding='utf8'))
    views.update({key:(row['eye'],row['target']) for key,row in shared['views'].items()})
    if view in ['ride_start','cliff_shadow']:
        graph=json.loads((ROOT/'unreal/Content/WorldData/world.json').read_text())
        points=next(row for row in graph['routes'] if row['id']=='main_circuit')['points']
        station=0.;index=0;target=620000 if view=='cliff_shadow' else 0
        for i in range(len(points)-1):
            if station>=target:index=i;break
            station+=math.dist(points[i],points[i+1])
        eye=[points[index][1]/100,points[index][0]/100,points[index][2]/100+1.65]
        other=points[min(index+4,len(points)-1)]
        aim=[other[1]/100,other[0]/100,other[2]/100+1.2]
    elif view in views:eye,aim=views[view]
    else:raise ValueError('Unknown view; choose a key in manifests/m1-inspection-views.json or a legacy review view')
    delta=[b-a for a,b in zip(eye,aim)]
    rotation=unreal.Rotator(pitch=math.degrees(math.atan2(delta[2],math.hypot(*delta[:2]))),
        yaw=math.degrees(math.atan2(delta[0],delta[1])),roll=0)
    editor.set_level_viewport_camera_info(unreal.Vector(eye[1]*100,eye[0]*100,eye[2]*100),rotation)
    return dict(view=view,eye_local_m=list(eye),target_local_m=list(aim),scope='Editor still view only')
