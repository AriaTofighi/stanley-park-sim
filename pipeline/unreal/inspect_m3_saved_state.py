"""Report dirty packages and whether visible Seawall meshes use them."""
from datetime import datetime, timezone
from pathlib import Path
import json
import unreal

ROOT = Path(__file__).resolve().parents[2]


def inspect():
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    if editor.get_game_world() is not None:
        raise RuntimeError('Inspect saved state before Play')
    world = editor.get_editor_world()
    if world.get_path_name() != '/Game/Maps/StanleyParkSeawall.StanleyParkSeawall':
        raise RuntimeError('Expected the separate Seawall map')
    utility = unreal.EditorLoadingAndSavingUtils
    dirty_content = sorted(p.get_path_name() for p in utility.get_dirty_content_packages())
    dirty_maps = sorted(p.get_path_name() for p in utility.get_dirty_map_packages())
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    visible_refs = {}
    for actor in actors.get_all_level_actors():
        if not isinstance(actor, unreal.StaticMeshActor):
            continue
        component = actor.static_mesh_component
        if not component.is_visible() or component.static_mesh is None:
            continue
        visible_refs[actor.get_actor_label()] = component.static_mesh.get_path_name().split('.')[0]
    affected = {label: path for label, path in visible_refs.items() if path in dirty_content}
    result = dict(time_utc=datetime.now(timezone.utc).isoformat(),
        map=world.get_path_name(), dirty_content_packages=dirty_content,
        dirty_map_packages=dirty_maps, visible_static_meshes_using_dirty_packages=affected,
        scope='Read-only saved-state inspection. Static mesh references only; no runtime or visual acceptance.',
        application_tests_run=False)
    filename = ROOT/'evidence'/('m3-saved-state-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'.json')
    filename.write_text(json.dumps(result, indent=2))
    return dict(report=filename.relative_to(ROOT).as_posix(), **result)


if __name__ in {'__main__', '<run_path>'}:
    result = inspect()
