"""Read-only detail for retained failed scene rays. Do not change collision."""
import json
from pathlib import Path
import unreal

ROOT = Path(__file__).resolve().parents[2]


def inspect():
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    original = json.loads((ROOT/'evidence/unreal-surface-transfer-v25-failure.json').read_text())
    rows = []
    for index, row in enumerate(original['points']):
        if row['residual_m'] is not None and abs(row['residual_m']) <= .01:
            continue
        p = row['source_m']
        start = unreal.Vector(p[1]*100, p[0]*100, p[2]*100+200)
        end = unreal.Vector(start.x,start.y,start.z-400)
        hit = unreal.SystemLibrary.line_trace_single(world,start,end,unreal.TraceTypeQuery.ECC_VISIBILITY,
                                                    True,[],unreal.DrawDebugTrace.NONE,True)
        values = hit.to_dict() if hit else {}
        entry = dict(index=index,source_m=p,hit={k:str(v) for k,v in values.items()})
        if values.get('hit_actor'):
            entry['actor_label'] = values['hit_actor'].get_actor_label()
        if values.get('hit_component'):
            component = values['hit_component']
            mesh = component.get_editor_property('static_mesh')
            entry['mesh_path'] = mesh.get_path_name() if mesh else None
            entry['collision_enabled'] = str(component.get_collision_enabled())
            entry['use_default_collision'] = component.get_editor_property('use_default_collision')
            entry['collision_profile'] = str(component.get_collision_profile_name())
            entry['collision_object_type'] = str(component.get_collision_object_type())
            entry['visibility_response'] = str(component.get_collision_response_to_channel(unreal.CollisionChannel.ECC_VISIBILITY))
            entry['actor_tags'] = [str(t) for t in values['hit_actor'].tags]
        if not hit or index == 2000:
            stencil = []
            for distance_m in [.00001,.0001,.001,.01]:
                for dx,dy in [(distance_m,0),(-distance_m,0),(0,distance_m),(0,-distance_m)]:
                    ray_start = unreal.Vector(start.x+dy*100,start.y+dx*100,start.z)
                    ray_end = unreal.Vector(end.x+dy*100,end.y+dx*100,end.z)
                    adjacent = unreal.SystemLibrary.line_trace_single(world,ray_start,ray_end,unreal.TraceTypeQuery.ECC_VISIBILITY,
                                                                       True,[],unreal.DrawDebugTrace.NONE,True)
                    detail = adjacent.to_dict() if adjacent else {}
                    stencil.append(dict(offset_east_north_m=[dx,dy],hit=bool(adjacent),
                                        height_m=detail['location'].z/100 if adjacent else None,
                                        actor_label=detail['hit_actor'].get_actor_label() if detail.get('hit_actor') else None))
            entry['diagnostic_neighbour_rays'] = stencil
        rows.append(entry)
    out = ROOT/'evidence/unreal-surface-failure-hit-details-v26.json'
    if out.exists():
        raise FileExistsError(out)
    out.write_text(json.dumps(dict(scope='Read-only diagnostic rays; no collision changes or acceptance.',rows=rows),indent=2)+'\n')
    return dict(rows=len(rows),evidence=out.relative_to(ROOT).as_posix())
