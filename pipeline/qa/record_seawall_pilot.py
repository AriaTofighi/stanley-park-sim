"""Record completed authoring work and explicit still-image observations.

This writes provenance only. It does not open, run, or test the application.
The review entries below refer to images the coordinator actually opened.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATE = "20261002"


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8-sig"))


def binding(path):
    file = ROOT / path
    return {"path": path, "bytes": file.stat().st_size,
            "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}


def save(path, value):
    (ROOT / path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


groups = [
    (["seawall-blender-bird-rest-01"], "blender_rest_pose",
     "The body and shoulder-pivot wings form a coherent small gull with grey and white surfaces. "
     "The simple asset is suitable for a first distant model. Flight motion is not reviewed."),
    (["seawall-blender-tree-library-01"], "blender_library",
     "All six source models are upright with visible trunks, branches and closed foliage clumps. "
     "The shapes are stylized first-pass assets, not finished close-view trees."),
    ([f"seawall-initial-{s:05d}" for s in [0, 5350, 6200]], "retained_fault",
     "The water shows strong repeated parallel bands and distant dark patterns. "
     "The fixed sky reads as overcast. Water was revised after these views."),
    ([f"seawall-trees-{s:05d}" for s in [1200, 2400, 7500]], "retained_fault",
     "Tree instances tilt strongly and overlap the apparent route space. "
     "A positional Rotator call put intended yaw into pitch. This version was replaced."),
    ([f"seawall-corrected-{s:05d}" for s in [0, 1200, 2400, 6200, 7500]], "intermediate",
     "Trees are upright after named rotation arguments. Nearby water appears too uniform. "
     "Coarse crowns, flat terrain materials and simple shore forms remain visible."),
    ([f"seawall-water3-{s:05d}" for s in [0, 2400, 6200, 7500]], "provisional_water",
     "Irregular nearby ripple patches are visible and the distant surface is smoother. "
     "Strong V1 bands are reduced. Broad patches and simple reflectance remain. "
     "These stills do not accept motion, temporal stability or performance."),
    ([f"seawall-saved-{s:05d}" for s in [1200, 7500]], "retained_reload_fault",
     "The old coarse canopy reappears over detailed trees after editor restart. "
     "Temporary editor hiding was not persisted. Component visibility was then saved explicitly."),
    ([f"seawall-persistent-{s:05d}" for s in [1200, 7500]], "saved_authoring_result",
     "After another map load, upright detailed trees and the intended reduced coarse canopy are visible. "
     "The duplicate canopy seen in the previous reload images is gone. "
     "Large unselected coarse crowns and simple foliage remain visible; further art work is required."),
]
reviews = []
for names, stage, observation in groups:
    for name in names:
        reviews.append({"image": binding(f"evidence/{name}.png"),
                        "capture_record": binding(f"evidence/{name}.json"),
                        "opened_and_inspected": True, "stage": stage,
                        "observation": observation})
visual_path = f"evidence/seawall-visual-review-{DATE}.json"
save(visual_path, {
    "recorded_utc": datetime.now(timezone.utc).isoformat(),
    "scope": "Actual Blender and Unreal authoring stills; no gameplay acceptance",
    "image_count": len(reviews), "reviews": reviews,
    "application_test_run": False, "motion_review_complete": False,
    "performance_verified": False, "milestone_complete": False,
})

baseline_path = f"evidence/seawall-source-baseline-{DATE}.json"
comparison_path = f"evidence/seawall-source-comparison-{DATE}.json"
comparison = []
for item in read(baseline_path)["files"]:
    current = binding(item["path"])
    comparison.append({"path": item["path"], "baseline_sha256": item["sha256"],
                       "current_sha256": current["sha256"],
                       "unchanged": item["sha256"] == current["sha256"]})
save(comparison_path, {"recorded_utc": datetime.now(timezone.utc).isoformat(),
                      "scope": "Original M1 authoring sources after final Seawall save",
                      "files": comparison, "all_unchanged": all(x["unchanged"] for x in comparison)})

tree_pointer = read("exports/seawall-trees/latest.json")
tree = read(tree_pointer["manifest"])
tree_apply = f"exports/seawall-trees/{tree['version']}/unreal-apply.json"
water = read("evidence/seawall-water-sky.json")
source_paths = [
    "blender/StanleyPark_Seawall.blend", "blender/SeawallBirds.blend",
    "unreal/Content/Maps/StanleyParkSeawall.umap",
    "unreal/Binaries/Win64/UnrealEditor-StanleyParkSim.dll",
    "unreal/Source/StanleyParkSim/SPSeawallBirds.cpp",
    "unreal/Source/StanleyParkSim/SPSeawallBirds.h",
    "unreal/Source/StanleyParkSim/SPWorldDirector.cpp",
    "unreal/Source/StanleyParkSim/SPWorldDirector.h",
    "unreal/Content/WorldData/seawall-birds.json",
    "manifests/seawall-birds.json", "manifests/seawall-birds-export.json",
    "manifests/seawall-tree-settings.json", "manifests/seawall-water-sky.json",
    "pipeline/blender/build_seawall_tree_library.py",
    "pipeline/blender/build_seawall_bird.py", "pipeline/blender/inspect_seawall_assets.py",
    "pipeline/unreal/import_seawall_trees.py", "pipeline/unreal/import_seawall_bird.py",
    "pipeline/unreal/apply_seawall_water_sky.py", "pipeline/unreal/park_toolset.py",
    "tools/unreal-mcp/capture_seawall_views.py", "scripts/open-seawall-editor.ps1",
    "docs/SEAWALL-RELEASE-PLAN.md", "docs/SEAWALL-VISUAL-PILOT.md",
    tree_pointer["manifest"], tree_apply,
]
evidence_paths = [
    "evidence/build-editor-seawall-v1.log", "evidence/seawall-bird-import-20261002.json",
    "evidence/seawall-trees-apply-05.json", "evidence/seawall-water-sky-apply-03.json",
    "evidence/seawall-water-sky-baseline.json", "evidence/seawall-saved-map-reload.json",
    "evidence/seawall-editor-loaded-cvars.json", "evidence/seawall-editor-no-pie.json",
    baseline_path, comparison_path, visual_path,
]
asset_paths = [p.relative_to(ROOT).as_posix() for p in sorted(
    (ROOT / "unreal/Content/StanleyPark/Seawall").rglob("*.uasset"))]
result = {
    "recorded_utc": datetime.now(timezone.utc).isoformat(),
    "status": "First visual integration; M2 remains open",
    "engine": water["engine"], "map": "/Game/Maps/StanleyParkSeawall",
    "workers": {"count": 3, "model": "GPT-6 Astra", "reasoning": "high",
                "service_tier": "priority", "fast_selector_available": False},
    "trees": {"version": tree["version"], "instances": read(tree_apply)["instances"],
              "models": len(tree["trees"]), "lods_per_model": 3,
              "rejected_candidates_retained_coarse": len(tree["rejected"]),
              "pilot": tree["pilot"], "apply_success": read(tree_apply)["success"]},
    "water_sky": {"fingerprint": water["fingerprint"], "apply_success": water["success"],
                  "materials": water["materials"]},
    "birds": {"count": 6, "enabled_by_default_on_seawall_map": True,
              "editor_module_compiled": True, "motion_run": False},
    "build": {"target": "StanleyParkSimEditor", "platform": "Win64",
              "configuration": "Development", "result": "Succeeded",
              "log": "evidence/build-editor-seawall-v1.log"},
    "original_m1_sources_unchanged": all(x["unchanged"] for x in comparison),
    "application_tests_run": False, "new_standalone_package": False,
    "visual_release_accepted": False, "performance_verified": False,
    "computer_use_released": True,
    "remaining": ["Near-route tree shapes, materials and coarse-crown transitions",
                  "Immediate shore, cliff and path-edge detail",
                  "Water and bird motion review when application tests are requested",
                  "Measured scene performance and full-route release work"],
    "source_bindings": [binding(p) for p in source_paths],
    "evidence_bindings": [binding(p) for p in evidence_paths],
    "new_namespace_assets": [binding(p) for p in asset_paths],
}
save(f"evidence/seawall-integration-{DATE}.json", result)
print(json.dumps({"status": result["status"], "reviewed_images": len(reviews),
                  "tree_instances": result["trees"]["instances"], "assets": len(asset_paths),
                  "original_m1_sources_unchanged": result["original_m1_sources_unchanged"]}))
