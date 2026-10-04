"""Save editor work before rebuilding the native character module. No Play."""
import unreal
from pathlib import Path
import json
ROOT = Path(__file__).resolve().parents[2]
if unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world():
    raise RuntimeError('Stop Play before rebuilding')
if not unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True):
    raise RuntimeError('Could not save all dirty packages')
result = dict(saved=True, application_tests_run=False)
(ROOT/'evidence/explorer-editor-saved.json').write_text(json.dumps(result))
unreal.SystemLibrary.quit_editor()
