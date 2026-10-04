"""Write the current asset index from existing export pointers; no editor required."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf-8-sig'))


def versioned_layer(name, directory=None):
    directory = directory or f'exports/seawall-{name}'
    pointer = read(f'{directory}/latest.json')
    path = ROOT / pointer['manifest']
    if hashlib.sha256(path.read_bytes()).hexdigest() != pointer['sha256']:
        raise RuntimeError(f'{name}: export pointer does not match the manifest')
    manifest = read(pointer['manifest'])
    return dict(pointer=f'{directory}/latest.json', manifest=pointer['manifest'],
                version=manifest['version'], unreal=manifest['asset_root'],
                instances=len(manifest.get('instances', [])),
                targets=len(manifest.get('targets', [])),
                retired_exports=[p.name for p in sorted(path.parent.parent.iterdir())
                                 if p.is_dir() and p.name != manifest['version']])


def main():
    water = read('evidence/seawall-water-sky.json')
    catalog = dict(schema_version=1,
        working_blend='blender/StanleyPark_Seawall.blend',
        assembly_blend='blender/StanleyPark_Assembly.blend',
        editable_modules='manifests/blender-modules.json',
        explorer_source='blender/Explorer.blend',
        explorer_manifest='manifests/explorer.json',
        working_map='/Game/Maps/StanleyParkSeawall',
        protected_m1_blend='blender/StanleyPark_Blockout.blend',
        protected_m1_map='/Game/Maps/StanleyPark',
        layers=dict(trees=versioned_layer('trees'), shore=versioned_layer('shore'),
                    birds=dict(manifest='manifests/seawall-birds-export.json',
                               unreal='/Game/StanleyPark/Seawall/Birds'),
                    water_sky=dict(manifest='manifests/seawall-water-sky.json',
                                   applied_record='evidence/seawall-water-sky.json',
                                   materials=[row['path'] for row in water['materials']])),
        archives=dict(blender='blender/archive', unreal='unreal/SourceArchives',
                      note='Old export versions stay at their recorded paths for source recovery.'),
        workflow='docs/ASSET-WORKFLOW.md')
    for name, directory in [('forest', 'exports/m3-forest'), ('edges', 'exports/m3-edges'),
                            ('landmarks', 'exports/seawall-landmarks'),
                            ('crowns', 'exports/m3-crown-repair'),
                            ('edge_skirts', 'exports/m3-edge-skirts'),
                            ('landmark_forms', 'exports/m3-landmark-forms'),
                            ('siwash_crown', 'exports/m3-siwash-crown'),
                            ('landmark_detail', 'exports/m3-landmark-detail'),
                            ('north_approach', 'exports/m3-north-approach'),
                            ('urban_surfaces', 'exports/m3-urban-surfaces'),
                            ('support_gap_patches', 'exports/m3-support-gap-patches'),
                            ('second_beach_detail', 'exports/m3-second-beach-detail'),
                            ('precinct_relief', 'exports/m3-precinct-relief'),
                            ('landmark_winding', 'exports/m3-landmark-winding'),
                            ('shore_to_shore', 'exports/m3-shore-to-shore'),
                            ('rowing_club_detail', 'exports/m3-rowing-club-detail'),
                            ('wetsuit_form', 'exports/m3-wetsuit-form'),
                            ('ride_cliff_gaps', 'exports/m3-ride-cliff-gaps')]:
        if (ROOT/directory/'latest.json').exists():
            catalog['layers'][name] = versioned_layer(name, directory)
    for name, pattern in [('path_materials', 'm3-path-material-repair-*.json'),
                          ('skirt_lighting', 'm3-skirt-normal-repair-*.json')]:
        records = sorted((ROOT/'evidence').glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in records:
            record = read(path.relative_to(ROOT))
            if record.get('success'):
                catalog['layers'][name] = dict(applied_record=path.relative_to(ROOT).as_posix(),
                    applied_record_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    unreal=record['asset_root'])
                break
    destination = ROOT / 'manifests/active-assets.json'
    destination.write_text(json.dumps(catalog, indent=2) + '\n', encoding='utf-8')
    print(destination.relative_to(ROOT).as_posix())


if __name__ == '__main__':
    main()
