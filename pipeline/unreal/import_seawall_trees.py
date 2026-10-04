"""Import only the Seawall tree sidecar into an explicitly selected working map.

MCP invocation: runpy.run_path(script, init_globals={
    'SP_SEAWALL_MAP_PATH': '/Game/Maps/StanleyParkSeawall'})
The map must already be open. This does not open a map or run the application.
"""
import hashlib
import json
import os
from pathlib import Path

import unreal

ROOT = Path(__file__).resolve().parents[2]
OWNER = "SP_SeawallTrees"
ASSET_PREFIX = "/Game/StanleyPark/Seawall/Trees/"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply(map_path):
    pointer = json.loads((ROOT / "exports/seawall-trees/latest.json").read_text())
    source = ROOT / pointer["manifest"]
    if digest(source) != pointer["sha256"]:
        raise RuntimeError("Tree manifest changed after export")
    manifest = json.loads(source.read_text())
    cfg = manifest["settings"]
    if map_path != cfg["map_path"] or map_path == "/Game/Maps/StanleyPark":
        raise RuntimeError("The tree stage requires the separate Seawall map")
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split(".")[0] != map_path:
        raise RuntimeError("Open the requested Seawall map before applying trees")
    root = manifest["asset_root"]
    if not root.startswith(ASSET_PREFIX):
        raise RuntimeError("The tree asset namespace is invalid")
    # Validate every source before any editor mutation.
    for path, expected in manifest["input_hashes"].items():
        if path not in {"live_clearance_meshes","live_ground_meshes"} and digest(ROOT / path) != expected:
            raise RuntimeError("Tree placement input changed: " + path)
    for tree in manifest["trees"]:
        for lod in tree["lods"]:
            if digest(ROOT / lod["fbx"]) != lod["sha256"]:
                raise RuntimeError("Tree FBX hash mismatch")
    for entry in manifest["coarse_replacements"]:
        item = entry["replacement"]
        if item and digest(ROOT / item["fbx"]) != item["sha256"]:
            raise RuntimeError("Coarse canopy FBX hash mismatch")
    for texture in manifest.get("textures", []):
        if digest(ROOT / texture["path"]) != texture["sha256"]:
            raise RuntimeError("Tree texture hash mismatch")
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
    meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    materials = {}
    record_path = ROOT / "exports/seawall-trees" / manifest["version"] / "unreal-apply.json"
    record = dict(success=False, map=map_path, manifest_sha256=digest(source),
                  version=manifest["version"], restored_actors=[], hidden_originals=[], foliage_types=[])
    record_path.write_text(json.dumps(record, indent=2))

    textures = {}
    for item in manifest.get("textures", []):
        path = root + "/Textures/" + item["name"]
        texture = assets.load_asset(path)
        if texture is None:
            task = unreal.AssetImportTask()
            for key, value in dict(filename=str(ROOT/item["path"]), destination_path=root+"/Textures",
                    destination_name=item["name"], automated=True, replace_existing=False, save=False,
                    factory=unreal.TextureFactory()).items():
                task.set_editor_property(key,value)
            tools.import_asset_tasks([task])
            texture = assets.load_asset(path)
        if not isinstance(texture,unreal.Texture2D):
            raise RuntimeError("Cannot import tree texture: "+path)
        texture.set_editor_property("srgb",item["srgb"])
        texture.set_editor_property("compression_settings",unreal.TextureCompressionSettings.TC_NORMALMAP
            if item["role"]=="normal" else unreal.TextureCompressionSettings.TC_DEFAULT)
        if item["role"]=="normal":
            # Blender stores OpenGL tangent normals; Unreal uses DirectX normals.
            texture.set_editor_property("flip_green_channel",True)
        if item["role"] in {"foliage_mask","whole_tree_mask"}:
            texture.set_editor_property("do_scale_mips_for_alpha_coverage",True)
            texture.set_editor_property("alpha_coverage_thresholds",unreal.Vector4(0,0,0,.24 if item["role"]=="whole_tree_mask" else .32))
        assets.save_loaded_asset(texture)
        textures[item["name"]]=texture

    def material(name, color):
        if name in materials:
            return materials[name]
        # Preserve the first incomplete graph under its original asset name.
        graph_name = name + "_Graph02"
        path = root + "/Materials/" + graph_name
        mat = assets.load_asset(path)
        if mat is None:
            mat = tools.create_asset(graph_name,root+"/Materials",unreal.Material,unreal.MaterialFactoryNew())
            if mat is None:
                raise RuntimeError("Cannot create tree material "+path)
            spec = manifest.get("material_specs",{}).get(name)
            mel = unreal.MaterialEditingLibrary
            def node(cls):
                return mel.create_material_expression(mat,cls)
            def link(source,output,target,input_name):
                names = [str(value) for value in mel.get_material_expression_input_names(target)]
                actual = input_name if input_name in names else (names[0] if len(names)==1 else None)
                if actual is None or not mel.connect_material_expressions(source,output,target,actual):
                    raise RuntimeError(f"Cannot connect tree shader {input_name}; engine inputs: {names}")
            def property_link(source,output,prop):
                if not mel.connect_material_property(source,output,prop):
                    raise RuntimeError("Cannot connect tree shader property "+str(prop))
            if spec:
                tex = node(unreal.MaterialExpressionTextureSample)
                tex.set_editor_property("texture",textures[spec["texture"]])
                tex.set_editor_property("sampler_type",unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
                base,base_output=tex,"RGB"
                if spec.get("color_scale",1)!=1:
                    base=node(unreal.MaterialExpressionMultiply)
                    base.set_editor_property("const_b",spec["color_scale"])
                    link(tex,"RGB",base,"A")
                    base_output=""
                property_link(base,base_output,unreal.MaterialProperty.MP_BASE_COLOR)
                mat.set_editor_property("two_sided",spec["two_sided"])
                if spec["masked"]:
                    mat.set_editor_property("blend_mode",unreal.BlendMode.BLEND_MASKED)
                    mat.set_editor_property("opacity_mask_clip_value",spec["opacity_mask_clip"])
                    mat.set_editor_property("shading_model",unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
                    property_link(tex,"A",unreal.MaterialProperty.MP_OPACITY_MASK)
                    translucency=node(unreal.MaterialExpressionMultiply)
                    translucency.set_editor_property("const_b",.28)
                    link(base,base_output,translucency,"A")
                    property_link(translucency,"",unreal.MaterialProperty.MP_SUBSURFACE_COLOR)
                if spec["masked"] and spec.get("wind",True):
                    # Small leaf motion only. Geometry and route clearance stay fixed.
                    clock=node(unreal.MaterialExpressionTime)
                    speed=node(unreal.MaterialExpressionMultiply)
                    speed.set_editor_property("const_b",.18)
                    link(clock,"",speed,"A")
                    wave=node(unreal.MaterialExpressionSine)
                    link(speed,"",wave,"Input")
                    axis=node(unreal.MaterialExpressionConstant3Vector)
                    axis.set_editor_property("constant",unreal.LinearColor(.7,.35,.10,1))
                    motion=node(unreal.MaterialExpressionMultiply)
                    link(wave,"",motion,"A")
                    link(axis,"",motion,"B")
                    property_link(motion,"",unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
                if spec.get("normal_texture"):
                    normal=node(unreal.MaterialExpressionTextureSample)
                    normal.set_editor_property("texture",textures[spec["normal_texture"]])
                    normal.set_editor_property("sampler_type",unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
                    property_link(normal,"RGB",unreal.MaterialProperty.MP_NORMAL)
            else:
                base=node(unreal.MaterialExpressionConstant3Vector)
                base.set_editor_property("constant",unreal.LinearColor(*color))
                property_link(base,"",unreal.MaterialProperty.MP_BASE_COLOR)
            rough=node(unreal.MaterialExpressionConstant)
            rough.set_editor_property("r",spec["roughness"] if spec else .9)
            property_link(rough,"",unreal.MaterialProperty.MP_ROUGHNESS)
            mel.set_base_material_usage(mat,unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES,True)
            mel.recompile_material(mat)
            assets.set_metadata_tag(mat,"SP_TreeGraphComplete","2")
            assets.save_loaded_asset(mat)
        if assets.get_metadata_tag(mat,"SP_TreeGraphComplete") != "2":
            raise RuntimeError("Incomplete tree material graph retained for review: "+path)
        materials[name]=mat
        return mat

    def require_mesh_bounds(mesh, item, name):
        box = mesh.get_bounding_box()
        actual = [box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z]
        expected = item["bounds_min_cm"] + item["bounds_max_cm"]
        if max(abs(a - b) for a, b in zip(actual, expected)) > 1:
            raise RuntimeError("Tree FBX axis or scale mismatch: " + name)

    def import_mesh(item, name, lods=None):
        path = root + "/Meshes/" + name
        mesh = assets.load_asset(path)
        spec = hashlib.sha256(json.dumps([item, lods], sort_keys=True).encode()).hexdigest()
        if mesh is not None:
            require_mesh_bounds(mesh, item, name)
            saved_spec = assets.get_metadata_tag(mesh,"SP_SeawallSpec")
            if saved_spec != spec:
                source_data = mesh.get_editor_property("asset_import_data")
                imported_file = Path(source_data.get_first_filename()).resolve() if source_data else None
                if saved_spec or imported_file != (ROOT/item["fbx"]).resolve():
                    raise RuntimeError("Cannot repair unmatched tree asset: "+path)
                if mesh.get_num_lods() != (len(lods) if lods else 1):
                    raise RuntimeError("Incomplete tree LOD import retained for review: "+path)
                # A previous apply completed the FBX/LOD import but stopped in
                # material construction. Repair only this exact source asset.
                for index,slot in enumerate(mesh.get_editor_property("static_materials")):
                    slot_name = str(slot.get_editor_property("imported_material_slot_name"))
                    if slot_name not in item["materials"]:
                        raise RuntimeError("Unknown tree material slot: "+slot_name)
                    mesh.set_material(index,material(slot_name,item["materials"][slot_name]))
                assets.set_metadata_tag(mesh,"SP_SeawallSpec",spec)
                assets.save_loaded_asset(mesh)
            return mesh
        options = unreal.FbxImportUI()
        for key, value in dict(import_mesh=True, import_as_skeletal=False, import_materials=False,
                               import_textures=False, automated_import_should_detect_type=False,
                               mesh_type_to_import=unreal.FBXImportType.FBXIT_STATIC_MESH).items():
            options.set_editor_property(key, value)
        for key, value in dict(combine_meshes=True, convert_scene=False, convert_scene_unit=False,
                               force_front_x_axis=False, generate_lightmap_u_vs=False, auto_generate_collision=False,
                               transform_vertex_to_absolute=True, build_nanite=False).items():
            options.static_mesh_import_data.set_editor_property(key, value)
        options.static_mesh_import_data.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
        task = unreal.AssetImportTask()
        for key, value in dict(filename=str(ROOT / item["fbx"]), destination_path=root + "/Meshes",
                               destination_name=name, automated=True, replace_existing=False, save=True,
                               factory=unreal.FbxFactory(), options=options).items():
            task.set_editor_property(key, value)
        tools.import_asset_tasks([task])
        mesh = assets.load_asset(path)
        if not isinstance(mesh, unreal.StaticMesh):
            raise RuntimeError("Tree mesh import failed: " + path)
        require_mesh_bounds(mesh, item, name)
        if lods:
            for index, lod in enumerate(lods[1:], 1):
                if meshes.import_lod(mesh, index, str(ROOT / lod["fbx"])) != index:
                    raise RuntimeError("Tree LOD import failed: " + name)
            if not meshes.set_lod_screen_sizes(mesh, cfg["lod_screen_sizes"]):
                raise RuntimeError("Cannot set tree LOD sizes")
        for index, slot in enumerate(mesh.get_editor_property("static_materials")):
            imported = str(slot.get_editor_property("imported_material_slot_name"))
            if imported not in item["materials"]:
                raise RuntimeError("Unknown tree material slot: " + imported)
            mesh.set_material(index, material(imported, item["materials"][imported]))
        assets.set_metadata_tag(mesh, "SP_SeawallSpec", spec)
        assets.save_loaded_asset(mesh)
        return mesh

    unreal.SystemLibrary.execute_console_command(world, "Interchange.FeatureFlags.Import.FBX 0")
    imported = {tree["id"]: import_mesh(tree["lods"][0], tree["id"], tree["lods"]) for tree in manifest["trees"]}
    coarse = {entry["object_name"]: import_mesh(entry["replacement"], entry["replacement"]["name"])
              for entry in manifest["coarse_replacements"] if entry["replacement"]}
    # Preflight original actor names before hiding any coarse tile.
    by_label = {}
    for actor in actors.get_all_level_actors():
        by_label.setdefault(actor.get_actor_label(), []).append(actor)
    for entry in manifest["coarse_replacements"]:
        if len(by_label.get(entry["object_name"], [])) != 1:
            raise RuntimeError("Expected one original canopy actor: " + entry["object_name"])
    foliage = {}
    for tree_id, mesh in imported.items():
        name = "FT_" + tree_id.removeprefix("SM_")
        path = root + "/Foliage/" + name
        ft = assets.load_asset(path)
        if ft is None:
            ft = tools.create_asset(name, root + "/Foliage", unreal.FoliageType_InstancedStaticMesh,
                                    unreal.FoliageType_InstancedStaticMeshFactory())
            if ft is None:
                raise RuntimeError("Cannot create foliage type")
            ft.set_editor_property("mesh", mesh)
            ft.set_editor_property("enable_density_scaling", False)
            ft.set_editor_property("enable_cull_distance_scaling", False)
            ft.set_editor_property("cull_distance", unreal.Int32Interval(0, cfg["cull_distance_cm"]))
            ft.set_editor_property("cast_shadow", True)
            ft.set_editor_property("receives_decals", False)
            body = ft.get_editor_property("body_instance")
            body.set_editor_property("collision_enabled", unreal.CollisionEnabled.NO_COLLISION)
            ft.set_editor_property("body_instance", body)
            assets.set_metadata_tag(ft, "SP_Owner", OWNER)
            assets.save_loaded_asset(ft)
        if assets.get_metadata_tag(ft, "SP_Owner") != OWNER:
            raise RuntimeError("Foliage type ownership mismatch")
        foliage[tree_id] = ft
        record["foliage_types"].append(path)
    # UE 5.8 exposes add/remove on the foliage actor, but its query methods are
    # absent. Resolve our saved foliage types, then query their mesh components.
    # Include every version so a retry also captures a failed, unsaved apply.
    owned_foliage = {ft.get_path_name(): ft for ft in foliage.values()}
    namespace_types = {}
    for path in assets.list_assets(ASSET_PREFIX.rstrip("/"), recursive=True, include_folder=False):
        if "/Foliage/" not in path:
            continue
        ft = assets.load_asset(path)
        if not isinstance(ft, unreal.FoliageType_InstancedStaticMesh):
            continue
        namespace_types[ft.get_path_name()] = ft
        if assets.get_metadata_tag(ft, "SP_Owner") == OWNER:
            owned_foliage[ft.get_path_name()] = ft
    mesh_to_type = {}
    for path, ft in owned_foliage.items():
        mesh = ft.get_editor_property("mesh")
        if mesh is None or not mesh.get_path_name().startswith(ASSET_PREFIX):
            raise RuntimeError("Owned foliage has a missing or external mesh: " + path)
        mesh_path = mesh.get_path_name()
        if mesh_path in mesh_to_type and mesh_to_type[mesh_path] != path:
            raise RuntimeError("Cannot resolve two owned foliage types with the same mesh: " + mesh_path)
        mesh_to_type[mesh_path] = path
    for path, ft in namespace_types.items():
        mesh = ft.get_editor_property("mesh")
        if path not in owned_foliage and mesh is not None and mesh.get_path_name() in mesh_to_type:
            raise RuntimeError("An unowned foliage type uses an owned tree mesh: " + path)

    def component_records(include_transforms=False):
        rows = {path: dict(foliage_type=path, instance_count=0, components=[], transforms=[])
                for path in owned_foliage}
        for actor in actors.get_all_level_actors():
            if not isinstance(actor, unreal.InstancedFoliageActor):
                continue
            for component in actor.get_components_by_class(unreal.FoliageInstancedStaticMeshComponent):
                mesh = component.get_editor_property("static_mesh")
                path = mesh_to_type.get(mesh.get_path_name()) if mesh is not None else None
                if path is None:
                    continue
                count = component.get_instance_count()
                row = rows[path]
                row["instance_count"] += count
                row["components"].append(dict(actor=actor.get_path_name(), component=component.get_path_name(),
                                               static_mesh=mesh.get_path_name(), instance_count=count))
                if include_transforms:
                    for index in range(count):
                        transform = component.get_instance_transform(index, world_space=True)
                        if transform is None:
                            raise RuntimeError(f"Cannot preserve foliage instance {component.get_path_name()}:{index}")
                        row["transforms"].append(dict(
                            translation=[transform.translation.x, transform.translation.y, transform.translation.z],
                            rotation=[transform.rotation.x, transform.rotation.y, transform.rotation.z, transform.rotation.w],
                            scale=[transform.scale3d.x, transform.scale3d.y, transform.scale3d.z]))
        return list(rows.values())

    visibility_tag_prefix = "SP_TreePriorVisibility_"

    def mesh_visibility_records(actor):
        rows = []
        for component in actor.get_components_by_class(unreal.StaticMeshComponent):
            visible = bool(component.get_editor_property("visible"))
            hidden = bool(component.get_editor_property("hidden_in_game"))
            saved = next((str(tag) for tag in component.get_editor_property("component_tags")
                          if str(tag).startswith(visibility_tag_prefix)), None)
            bits = saved[len(visibility_tag_prefix):] if saved else None
            if bits is not None and (len(bits) != 2 or any(bit not in "01" for bit in bits)):
                raise RuntimeError("Invalid saved component visibility: " + component.get_path_name())
            rows.append(dict(component=component.get_path_name(), visible=visible, hidden_in_game=hidden,
                prior_visible=visible if bits is None else bits[0] == "1",
                prior_hidden_in_game=hidden if bits is None else bits[1] == "1", prior_tag=saved))
        return rows

    def set_mesh_visibility(actor, enabled):
        # Component bVisible is serialized. Temporary actor editor hiding alone
        # does not survive a map reload. Keep the first component state in tags.
        # enabled=None restores that state when a source tile is no longer replaced.
        states = {row["component"]: row for row in mesh_visibility_records(actor)}
        actor.modify()
        for component in actor.get_components_by_class(unreal.StaticMeshComponent):
            state = states[component.get_path_name()]
            component.modify()
            if enabled is False and state["prior_tag"] is None:
                tags = list(component.get_editor_property("component_tags"))
                tags.append(unreal.Name(visibility_tag_prefix + str(int(state["visible"]))
                                        + str(int(state["hidden_in_game"]))))
                component.set_editor_property("component_tags", tags)
            visible = state["prior_visible"] if enabled is None else enabled
            hidden = state["prior_hidden_in_game"] if enabled is None else not enabled
            component.set_visibility(visible, propagate_to_children=False)
            component.set_hidden_in_game(hidden, propagate_to_children=False)

    # Save exact world transforms before replacing owned instances or hiding actors.
    prior_instances = component_records(include_transforms=True)
    owned_coarse = [a for a in actors.get_all_level_actors() if unreal.Name(OWNER) in a.tags]
    previous_originals = []
    for actor in actors.get_all_level_actors():
        tag = next((str(t) for t in actor.tags if str(t).startswith("SP_TreePriorHidden_")), None)
        if tag:
            previous_originals.append((actor, tag.endswith("1")))
            record["restored_actors"].append(dict(label=actor.get_actor_label(), hidden=actor.get_editor_property("hidden"),
                editor_hidden=actor.is_temporarily_hidden_in_editor(), restore_hidden=tag.endswith("1"),
                mesh_visibility=mesh_visibility_records(actor)))
    for entry in manifest["coarse_replacements"]:
        actor = by_label[entry["object_name"]][0]
        # Preserve the initial state across repeated applications.
        tag_prefix = "SP_TreePriorHidden_"
        old_tag = next((str(t) for t in actor.tags if str(t).startswith(tag_prefix)), None)
        old_hidden = actor.get_editor_property("hidden") if old_tag is None else old_tag.endswith("1")
        record["hidden_originals"].append(dict(label=entry["object_name"], hidden=old_hidden,
            editor_hidden=actor.is_temporarily_hidden_in_editor(), current_hidden=actor.get_editor_property("hidden"),
            mesh_visibility=mesh_visibility_records(actor)))
    record["prior_owned_instances"] = prior_instances
    record["prior_owned_coarse"] = [dict(label=a.get_actor_label(), path=a.get_path_name(),
        hidden=a.get_editor_property("hidden"), editor_hidden=a.is_temporarily_hidden_in_editor(),
        mesh_visibility=mesh_visibility_records(a)) for a in owned_coarse]
    # Each attempt retains its restoration file, including failed attempts.
    attempt = 1
    while record_path.with_name(f"unreal-restore-{attempt:03d}.json").exists():
        attempt += 1
    restoration_path = record_path.with_name(f"unreal-restore-{attempt:03d}.json")
    restoration_path.write_text(json.dumps(record, indent=2))
    # Remove only this stage's foliage types. Other foliage in the level survives.
    for ft in owned_foliage.values():
        unreal.InstancedFoliageActor.remove_all_instances(world, ft)
    remaining = [row for row in component_records() if row["instance_count"]]
    if remaining:
        raise RuntimeError("Instances remain after owned foliage removal; stop before adding duplicates: "
                           + json.dumps(remaining))
    for actor in owned_coarse:
        set_mesh_visibility(actor, enabled=False)
        actor.set_actor_hidden_in_game(True)
        actor.set_is_temporarily_hidden_in_editor(True)
    for actor, initial_hidden in previous_originals:
        set_mesh_visibility(actor, enabled=None)
        actor.set_actor_hidden_in_game(initial_hidden)
        actor.set_is_temporarily_hidden_in_editor(initial_hidden)
    grouped = {tree_id: [] for tree_id in imported}
    for row in manifest["instances"]:
        east, north, up = row["position_local_m"]
        transform = unreal.Transform(location=unreal.Vector(north * 100, east * 100, up * 100),
            # UE 5.8 constructor order is roll, pitch, yaw. Use named arguments.
            rotation=unreal.Rotator(pitch=0.0, yaw=row["yaw_degrees"], roll=0.0),
            scale=unreal.Vector(*row["scale"]))
        if abs(transform.rotation.x) > 1e-6 or abs(transform.rotation.y) > 1e-6:
            raise RuntimeError("Tree transform must rotate only around its vertical axis")
        grouped[row["tree_id"]].append(transform)
    for tree_id, transforms in grouped.items():
        if transforms:
            unreal.InstancedFoliageActor.add_instances(world, foliage[tree_id], transforms)
    for entry in manifest["coarse_replacements"]:
        original = by_label[entry["object_name"]][0]
        prior = next(r for r in record["hidden_originals"] if r["label"] == entry["object_name"])
        tags = list(original.tags)
        if not any(str(t).startswith("SP_TreePriorHidden_") for t in tags):
            tags.append(unreal.Name("SP_TreePriorHidden_" + str(int(prior["hidden"]))))
            original.tags = tags
        set_mesh_visibility(original, enabled=False)
        original.set_actor_hidden_in_game(True)
        original.set_is_temporarily_hidden_in_editor(True)
        item = entry["replacement"]
        if item:
            matching = by_label.get(item["name"], [])
            if len(matching) > 1:
                raise RuntimeError("Duplicate Seawall coarse actor")
            actor = matching[0] if matching else actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*item["position_cm"]))
            actor.set_actor_label(item["name"])
            actor.static_mesh_component.set_static_mesh(coarse[entry["object_name"]])
            actor.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
            if unreal.Name(OWNER) not in actor.tags:
                actor.tags = list(actor.tags) + [unreal.Name(OWNER)]
            set_mesh_visibility(actor, enabled=True)
            actor.set_actor_hidden_in_game(False)
            actor.set_is_temporarily_hidden_in_editor(False)
    final_rows = component_records()
    actual_counts = {row["foliage_type"]: row["instance_count"] for row in final_rows}
    expected_counts = {path: 0 for path in owned_foliage}
    for tree_id, transforms in grouped.items():
        expected_counts[foliage[tree_id].get_path_name()] = len(transforms)
    count = sum(actual_counts.values())
    if actual_counts != expected_counts or count != len(manifest["instances"]):
        raise RuntimeError("Tree instance count differs from the placement manifest")
    # Foliage assignment can update material usage flags after the first save.
    # Persist only this version's materials, including assets reused on a retry.
    material_assets = [assets.load_asset(path) for path in assets.list_assets(
        root + "/Materials", recursive=True, include_folder=False)]
    if not assets.save_loaded_assets(material_assets):
        raise RuntimeError("Cannot save the Seawall tree material usage flags")
    if not levels.save_current_level():
        raise RuntimeError("Cannot save the Seawall map")
    record.update(success=True, instances=count, restoration=restoration_path.relative_to(ROOT).as_posix(),
                  component_instance_counts=final_rows, visual_review_complete=False, application_run=False)
    record_path.write_text(json.dumps(record, indent=2))
    return record


requested_map = globals().get("SP_SEAWALL_MAP_PATH") or os.environ.get("SP_SEAWALL_MAP_PATH")
if not requested_map:
    raise RuntimeError("Pass SP_SEAWALL_MAP_PATH through runpy.run_path or the process environment")
result = apply(requested_map)
