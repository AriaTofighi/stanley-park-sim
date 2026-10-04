"""Replace only the Siwash green envelope with source-positioned original foliage.

The protected rock and original crown meshes are retained. Root/branch form is
an explicit interpretation of the measured vegetation envelope, not a stem survey.
"""
import hashlib
import json
import math
import random
import runpy
from collections import defaultdict
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OWNER = "SP_M3SiwashCrown"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads((ROOT/path).read_text(encoding="utf-8"))


def author_crown(points, rock, lod, helpers):
    geometry = helpers["Geometry"]()
    low, high = points.min(0), points.max(0)
    # The original top-cap polygon is an observed 15.3 m rock section. Its
    # vertex mean is interior to the convex fitted ring and is the root anchor.
    ring = np.asarray(rock["rings"][-1])
    root = ring.mean(0)
    root[2] -= .03
    centre = points.mean(0)
    stem_tip = np.r_[centre[:2], high[2]-.40]
    stem = [root, root*.70+stem_tip*.30, root*.35+stem_tip*.65, stem_tip]
    geometry.tube(stem, [.16, .125, .075, .027], [10, 8, 6, 5][lod])
    voxel = [.35, .48, .65, .90][lod]
    groups = defaultdict(list)
    for point in points:
        groups[tuple(np.floor((point-low)/voxel).astype(int))].append(point)
    clusters = [(key, np.mean(values, axis=0)) for key, values in sorted(groups.items())]
    limbs = defaultdict(list)
    for key, point in clusters:
        angle = math.atan2(point[1]-centre[1], point[0]-centre[0])
        limbs[int((angle+math.pi)/(math.tau/8))%8, int((point[2]-low[2])/1.5)].append(point)
    limb_tips = {}
    for key, values in sorted(limbs.items()):
        tip = np.mean(values, axis=0)
        fraction = np.clip((tip[2]-root[2])/(stem_tip[2]-root[2]), .15, .86)
        origin = root*(1-fraction)+stem_tip*fraction
        bend = origin*.35+tip*.65+np.array([0, 0, .08])
        geometry.tube([origin, bend, tip], [.055, .030, .012], [7, 6, 5, 4][lod])
        limb_tips[key] = tip
    for key, point in clusters:
        seed = int(hashlib.sha256((str(key)+str(lod)).encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        angle = math.atan2(point[1]-centre[1], point[0]-centre[0])
        group_key = int((angle+math.pi)/(math.tau/8))%8, int((point[2]-low[2])/1.5)
        origin = limb_tips[group_key]
        twig_start = origin*.55+point*.45
        if lod < 3:
            geometry.tube([origin, twig_start, point], [.013, .008, .003], 4 if lod == 0 else 3)
        for spray in range([3, 3, 2, 2][lod]):
            theta = rng.uniform(0, math.tau)
            direction = np.array([math.cos(theta), math.sin(theta), rng.uniform(-.35, .55)])
            across = np.array([-math.sin(theta), math.cos(theta), rng.uniform(-.25, .25)])
            length = [.62, .78, .95, 1.18][lod]*rng.uniform(.8, 1.15)
            width = length*rng.uniform(.55, .78)
            geometry.card(point-direction*length*.40, direction, across, length, width,
                          0 if spray%2 else 1, fold=.10, flip=bool(seed%2))
    # Retain the measured crown extents. Only a few spray tips at the sample
    # boundary are trimmed to the observed envelope; no solid shell is added.
    geometry.vertices = [tuple(np.maximum(low, np.minimum(high, value))) for value in geometry.vertices]
    return geometry, dict(classified_returns=len(points), foliage_clusters=len(clusters),
        branch_groups=len(limbs), voxel_m=voxel, inferred_root_local_m=root.tolist(),
        root_support="Mean of the measured highest rock ring, embedded 0.03 m into its top cap",
        inferred_stem_tip_local_m=stem_tip.tolist())


def build():
    if Path(bpy.data.filepath).resolve() != (ROOT/"blender/StanleyPark_Seawall.blend").resolve():
        raise RuntimeError("Open the Seawall working blend")
    paths = ["pipeline/blender/build_m3_siwash_crown.py", "manifests/coastal-landmark-blockouts.json",
             "manifests/siwash-rock-survey.json", "data/derived/siwash-rock-survey.npz",
             "exports/seawall-trees/0551a03260b4/manifest.json", "pipeline/blender/build_m3_forest.py"]
    hashes = {path: sha(ROOT/path) for path in paths}
    version = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:12]
    directory = ROOT/"exports/m3-siwash-crown"/version
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory/"manifest.json"
    collection_name = OWNER+"_"+version
    if bpy.data.collections.get(collection_name):
        if not manifest_path.exists():
            raise RuntimeError("Incomplete Siwash crown layer; retain it for review")
        saved = read(manifest_path.relative_to(ROOT))
        if any(sha(ROOT/item["fbx"]) != item["sha256"] for item in saved["lods"]):
            raise RuntimeError("Siwash crown export changed")
        (directory.parent/"latest.json").write_text(json.dumps(dict(
            manifest=manifest_path.relative_to(ROOT).as_posix(), sha256=sha(manifest_path)), indent=2))
        return dict(reused=True, manifest=manifest_path.relative_to(ROOT).as_posix())
    baseline = read("exports/seawall-trees/0551a03260b4/manifest.json")
    bridge = runpy.run_path(str(ROOT/"pipeline/blender/build_m3_forest.py"), run_name="siwash_tree_helpers")
    helpers = bridge["frozen_helpers"](baseline)
    rock = read("manifests/coastal-landmark-blockouts.json")["landmarks"][0]
    survey = read("manifests/siwash-rock-survey.json")
    if rock["id"] != "siwash-rock" or sha(ROOT/survey["output"]["path"]) != survey["output"]["sha256"] or rock["source_sha256"] != survey["output"]["sha256"]:
        raise RuntimeError("Siwash measurement source binding changed")
    source = np.load(ROOT/survey["output"]["path"])
    points, classes = source["xyz"].astype(float), source["classification"]
    points = points[(np.linalg.norm(points[:, :2]-[-941., 691.], axis=1)<12)
                    & (classes == 5) & (points[:, 2]>14)]
    if not np.allclose(points.min(0), rock["crown_bounds_min_m"], atol=1e-7) or not np.allclose(points.max(0), rock["crown_bounds_max_m"], atol=1e-7):
        raise RuntimeError("Crown returns no longer reproduce the source envelope")
    original = bpy.data.objects.get("SM_SiwashRock_CrownEnvelope")
    rock_obj = bpy.data.objects.get("SM_SiwashRock_SurveyEnvelope")
    prototype = bpy.data.objects.get(baseline["trees"][0]["id"]+"_LOD0")
    if original is None or rock_obj is None or prototype is None:
        raise RuntimeError("Protected Siwash sources or accepted material library missing")
    if not np.allclose(original.location, [*rock["centre_local_m"], 0], atol=1e-6):
        raise RuntimeError("Protected crown anchor changed")
    collection = bpy.data.collections.new(collection_name)
    bpy.context.scene.collection.children.link(collection)
    anchor = np.array([*rock["centre_local_m"], 0.])
    name = "SM_M3SiwashCrown_"+version
    lods, source_records = [], []
    for lod in range(4):
        geometry, record = author_crown(points, rock, lod, helpers)
        geometry.vertices = [(np.asarray(p)-anchor).tolist() for p in geometry.vertices]
        obj = helpers["make_object"](name+f"_LOD{lod}", geometry, collection, list(prototype.data.materials), tuple(anchor))
        obj["pipeline_owner"], obj["source_id"] = OWNER, "Siwash 2022 classified vegetation crop"
        lods.append(helpers["export_object"](obj, directory, bpy.context.scene))
        source_records.append(record)
        if lod > 0:
            obj.hide_set(True)
            obj.hide_render = True
    visibility = dict(hide_render=original.hide_render, hide_viewport=original.hide_viewport, hide_set=original.hide_get())
    manifest = dict(schema_version=1, version=version, owner=OWNER, input_hashes=hashes,
        asset_root="/Game/StanleyPark/Seawall/M3SiwashCrown/v_"+version, asset_name=name,
        replaced_actor=original.name, protected_rock_actor=rock_obj.name,
        baseline_asset_root=baseline["asset_root"], source_period=survey["survey_period"],
        vertical_datum=survey["vertical_datum"], original_classified_returns=len(points),
        crown_bounds_min_m=points.min(0).tolist(), crown_bounds_max_m=points.max(0).tolist(),
        position_local_m=anchor.tolist(), lods=lods, lod_screen_sizes=[1.0, .36, .15, .055],
        lod_source_records=source_records, prior_blender_visibility=visibility,
        geometry_preservation="Original rock and crown mesh datablocks, transforms and collision remain unchanged; only crown visibility is replaced in Seawall.",
        source_limits="2022 class-5 returns set foliage sample positions and bounds. Generic evergreen needles, root, branches and stem form are inferred. No individual species or present-day tree condition is certified.",
        external_artwork=[], visual_review_complete=False, application_run=False)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    original.hide_render = True
    original.hide_set(True)
    (directory.parent/"latest.json").write_text(json.dumps(dict(
        manifest=manifest_path.relative_to(ROOT).as_posix(), sha256=sha(manifest_path)), indent=2))
    return dict(version=version, manifest=manifest_path.relative_to(ROOT).as_posix(),
        classified_returns=len(points), lod_triangles=[row["triangles"] for row in lods])


if __name__ in {"__main__", "<run_path>"}:
    result = build()
