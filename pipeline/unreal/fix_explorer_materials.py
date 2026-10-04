"""Assign and save the authored character materials in the current editor."""
from pathlib import Path
import json
import unreal

ROOT = Path(__file__).resolve().parents[2]
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
if editor.get_game_world() is not None:
    raise RuntimeError('Stop Play before changing the character asset')
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
mesh = assets.load_asset('/Game/StanleyPark/Explorer/SK_Explorer')
slots = list(mesh.get_editor_property('materials'))
rows = []
for index, slot in enumerate(slots):
    name = str(slot.get_editor_property('imported_material_slot_name'))
    material = assets.load_asset('/Game/StanleyPark/Explorer/' + name)
    if material is None:
        raise RuntimeError('Missing material: ' + name)
    slot.set_editor_property('material_interface', material)
    slots[index] = slot
    rows.append(dict(slot=index, name=name, material=material.get_path_name()))
mesh.set_editor_property('materials', slots)
if not assets.save_loaded_asset(mesh, only_if_is_dirty=False):
    raise RuntimeError('Character mesh save failed')
for slot in mesh.get_editor_property('materials'):
    if slot.get_editor_property('material_interface') is None:
        raise RuntimeError('Character material assignment failed')
assets.save_directory('/Game/StanleyPark/Explorer', only_if_is_dirty=True, recursive=False)
result = dict(materials=rows, saved=True)
(ROOT/'evidence/explorer-material-repair.json').write_text(json.dumps(result, indent=2))
unreal.log('SP_EXPLORER_MATERIALS: saved all eight material assignments')
