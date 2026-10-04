"""Maintain generated Seawall content without changing visible asset quality."""
import hashlib
import json
import shutil
from pathlib import Path
import unreal

ROOT = Path(__file__).resolve().parents[2]
MAP = '/Game/Maps/StanleyParkSeawall'


def organize():
    editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    if editor.get_game_world() is not None or editor.get_editor_world().get_path_name().split('.')[0] != MAP:
        raise RuntimeError('Open the Seawall map and stop Play before organization')
    catalog = json.loads((ROOT/'manifests/active-assets.json').read_text())
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    collections = unreal.get_editor_subsystem(unreal.CollectionManagerSubsystem)
    world_actors = list(actors.get_all_level_actors())
    # M3 retains these actors as its source and reversible restoration baseline.
    protected = set()
    forest = catalog['layers'].get('forest')
    if forest:
        manifest = json.loads((ROOT/forest['manifest']).read_text())
        protected = {row['replaced_m2_actor'] for row in manifest['coarse_replacements']}
    crowns = catalog['layers'].get('crowns')
    if crowns:
        manifest = json.loads((ROOT/crowns['manifest']).read_text())
        protected.update(row['replaced_actor'] for row in manifest['coarse_replacements'])
    retired = [a for a in world_actors if a.get_actor_label().startswith('SM_SWCanopy_')
               and a.get_actor_label() not in protected
               and unreal.Name('SP_SeawallTrees') in a.tags and a.get_editor_property('hidden')]
    if not levels.save_current_level():
        raise RuntimeError('Cannot preserve current edits before making the archive')
    source = ROOT/'unreal/Content/Maps/StanleyParkSeawall.umap'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    archive = ROOT/'unreal/SourceArchives'/('StanleyParkSeawall_'+digest[:12]+'.umap')
    archive.parent.mkdir(exist_ok=True)
    if not archive.exists():
        shutil.copy2(source, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise RuntimeError('Map archive does not match')
    removed = [a.get_actor_label() for a in retired]
    for actor in retired:
        if not actors.destroy_actor(actor):
            raise RuntimeError('Cannot remove retired canopy actor')
    # Keep clear site subgroups instead of one large list of landmarks and buildings.
    site_groups = [('SM_Building', 'Buildings'), ('SM_Named', 'NamedSites'),
                   ('SM_Skyline', 'DistantSkyline'), ('SM_Nav', 'Navigation'),
                   ('SM_PublicSpace', 'PublicSpaces')]
    for actor in actors.get_all_level_actors():
        name = actor.get_actor_label()
        if name in protected:
            actor.set_folder_path('StanleyPark/90_SourceReference/Canopy')
        elif name.startswith(('SM_SWCanopy_', 'SM_M3Canopy_', 'SM_M3Crown')):
            actor.set_folder_path('StanleyPark/20_Seawall/Trees')
        elif isinstance(actor, unreal.InstancedFoliageActor):
            actor.set_folder_path('StanleyPark/20_Seawall/Foliage')
        elif str(actor.get_folder_path()) == 'StanleyPark/10_Sites':
            group = next((g for prefix, g in site_groups if name.startswith(prefix)), 'Landmarks')
            actor.set_folder_path('StanleyPark/10_Sites/'+group)
    if not levels.save_current_level():
        raise RuntimeError('Cannot save the organized map')
    # Collections provide active views without redirectors or asset path changes.
    groups = {}
    for layer, entry in catalog['layers'].items():
        if 'unreal' not in entry:
            continue
        root = entry['unreal']
        groups['SP_Active_'+layer.title()] = list(registry.get_assets_by_path(root, recursive=True))
    # Traverse registry metadata, without loading historical material or texture packages.
    pending = list(catalog['layers']['water_sky']['materials'])
    seen = set()
    water = []
    options = unreal.AssetRegistryDependencyOptions(include_hard_package_references=True,
        include_soft_package_references=True, include_searchable_names=False,
        include_soft_management_references=False, include_hard_management_references=False)
    while pending:
        package = pending.pop().split('.')[0]
        if package in seen or not package.startswith('/Game/StanleyPark/Seawall/WaterSky/'):
            continue
        seen.add(package)
        water.extend(registry.get_assets_by_package_name(package))
        pending.extend(str(p) for p in registry.get_dependencies(package, options))
    groups['SP_Active_WaterSky'] = water
    counts = {}
    for name, data in groups.items():
        collection = collections.create_or_empty_collection(unreal.CollectionContainerSource(),
                         name, unreal.CollectionShareType.LOCAL)
        if collection is None or not data or not collections.add_asset_datas_to_collection(collection, data):
            raise RuntimeError('Cannot update collection: '+name)
        counts[name] = len(data)
    result = dict(removed=removed, collections=counts,
                  archive=archive.relative_to(ROOT).as_posix(), archive_sha256=digest,
                  application_tests_run=False)
    (ROOT/'evidence/seawall-active-collections.json').write_text(json.dumps(result, indent=2))
    return result


result = organize()
