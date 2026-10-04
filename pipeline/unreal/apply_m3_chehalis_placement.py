"""Apply only the source-bound Chehalis decoration translation."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import json
import shutil
import runpy
import unreal

ROOT=Path(__file__).resolve().parents[2]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def apply():
    editor=unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    if editor.get_game_world() is not None or editor.get_editor_world().get_path_name()!='/Game/Maps/StanleyParkSeawall.StanleyParkSeawall':raise RuntimeError('Open Seawall editor map; stop Play')
    pointer=json.loads((ROOT/'exports/m3-landmark-placement/latest.json').read_text());path=ROOT/pointer['manifest']
    if sha(path)!=pointer['sha256']:raise RuntimeError('Placement manifest differs')
    source=json.loads(path.read_text())
    for p,h in source['input_hashes'].items():
        if sha(ROOT/p)!=h:raise RuntimeError('Placement source differs: '+p)
    helpers=runpy.run_path(str(ROOT/'pipeline/unreal/import_m3_landmark_forms.py'),run_name='placement_helpers')
    invariant=helpers['invariant'];actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    meshes=[a for a in actors.get_all_level_actors() if isinstance(a,unreal.StaticMeshActor) and a.static_mesh_component.static_mesh]
    targets=[a for a in meshes if a.get_actor_label()==source['actor_label']]
    if len(targets)!=1:raise RuntimeError('Expected one Chehalis decoration')
    actor=targets[0];before={a.get_path_name():invariant(a) for a in meshes};old=before[actor.get_path_name()]
    expected=source['original_asset']['position_cm']
    if max(abs(a-b) for a,b in zip(old['position'],expected))>.1:raise RuntimeError('Chehalis actor source position differs')
    if actor.static_mesh_component.get_collision_enabled()!=unreal.CollisionEnabled.NO_COLLISION:raise RuntimeError('Decoration collision must be off')
    levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not levels.save_current_level():raise RuntimeError('Cannot save source map')
    map_path=ROOT/'unreal/Content/Maps/StanleyParkSeawall.umap';digest=sha(map_path)
    archive=ROOT/'unreal/SourceArchives'/('StanleyParkSeawall_'+digest[:12]+'.umap')
    if not archive.exists():shutil.copy2(map_path,archive)
    if sha(archive)!=digest:raise RuntimeError('Map archive differs')
    target=[p+d for p,d in zip(old['position'],source['delta_unreal_cm'])]
    actor.set_actor_location(unreal.Vector(*target),False,False)
    after={a.get_path_name():invariant(a) for a in meshes}
    for key,row in before.items():
        expected_row=dict(row)
        if key==actor.get_path_name():expected_row['position']=target
        if after[key]!=expected_row:raise RuntimeError('Unexpected actor change: '+key)
    if not levels.save_current_level():raise RuntimeError('Cannot save corrected map')
    report=dict(success=True,time_utc=datetime.now(timezone.utc).isoformat(),manifest=pointer['manifest'],manifest_sha256=pointer['sha256'],
        script_sha256=sha(Path(__file__)),before=old,after=after[actor.get_path_name()],archive=archive.relative_to(ROOT).as_posix(),
        unchanged_other_static_mesh_actors=len(meshes)-1,collision_unchanged=True,visual_acceptance=False)
    output=ROOT/'evidence'/('m3-chehalis-placement-'+source['version']+'.json')
    if output.exists():raise RuntimeError('Placement report exists')
    output.write_text(json.dumps(report,indent=2));return report

if __name__ in {'__main__','<run_path>'}:result=apply()
