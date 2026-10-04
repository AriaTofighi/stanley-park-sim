"""Record immutable package hashes and the matching exported world description."""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def record(version, package_directory='builds/Windows'):
    if not version.replace('-', '').isalnum():
        raise ValueError('Use a simple version name')
    target = ROOT / 'evidence' / f'build-{version}-provenance.json'
    snapshot = ROOT / 'evidence' / f'world-{version}.json'
    manifest_snapshot = ROOT / 'evidence' / f'export-{version}.json'
    import_snapshot = ROOT / 'evidence' / f'import-{version}.json'
    join_snapshot = ROOT / 'evidence' / f'join-fixtures-{version}.json'
    if any(p.exists() for p in (target, snapshot, manifest_snapshot, import_snapshot, join_snapshot)):
        raise FileExistsError('Keep earlier evidence; use a new version name')
    export_path = ROOT / 'manifests/blender-export.json'
    import_path = ROOT / 'evidence/unreal-import.json'
    import_record = json.loads(import_path.read_text(encoding='utf8'))
    export_hash = hashlib.sha256(export_path.read_bytes()).hexdigest()
    if not import_record.get('success') or import_record.get('export_manifest_sha256') != export_hash:
        raise ValueError('A successful Unreal import must match the current export before sealing a build')
    package = (ROOT / package_directory / 'StanleyParkSim').resolve()
    if not package.is_relative_to(ROOT):
        raise ValueError('Package directory must be inside the project')
    paths = sorted((package / 'Content/Paks').glob('*'))
    paths += [package / 'Binaries/Win64/StanleyParkSim.exe',
              ROOT / 'manifests/blender-export.json',
              ROOT / 'pipeline/blender/export_assets.py',
              ROOT / 'pipeline/unreal/import_world.py',
              ROOT / 'pipeline/unreal/adjust_inspection_lighting.py',
              ROOT / 'blender/StanleyPark_Blockout.blend',
              ROOT / 'evidence/unreal-import.json']
    paths += sorted((ROOT / 'unreal/Config').glob('*.ini'))
    paths += sorted((ROOT / 'unreal/Source/StanleyParkSim').glob('*.h'))
    paths += sorted((ROOT / 'unreal/Source/StanleyParkSim').glob('*.cpp'))
    records = []
    for path in paths:
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        records.append(dict(path=path.relative_to(ROOT).as_posix(),
                            bytes=path.stat().st_size, sha256=digest))
    world = (ROOT / 'unreal/Content/WorldData/world.json').read_bytes()
    join_path = ROOT / 'unreal/Content/WorldData/join_checks.json'
    join_bytes = join_path.read_bytes()
    join_record = json.loads(join_bytes)
    if join_record['source_world_sha1'].lower() != hashlib.sha1(world).hexdigest():
        raise ValueError('The join fixtures must match the current world before sealing')
    snapshot.write_bytes(world)
    join_snapshot.write_bytes(join_bytes)
    # Keep the manifest contents as well as their hashes. Later authoring must
    # not erase the description needed to review an earlier sealed package.
    shutil.copyfile(export_path, manifest_snapshot)
    shutil.copyfile(import_path, import_snapshot)
    record = dict(created_utc=datetime.now(timezone.utc).isoformat(),
                  scope='Packaged Development build and corresponding imported world',
                  files=records, world_snapshot=snapshot.relative_to(ROOT).as_posix(),
                  export_snapshot=manifest_snapshot.relative_to(ROOT).as_posix(),
                  import_snapshot=import_snapshot.relative_to(ROOT).as_posix(),
                  join_fixture_snapshot=join_snapshot.relative_to(ROOT).as_posix(),
                  join_fixture_sha256=hashlib.sha256(join_bytes).hexdigest(),
                  world_sha256=hashlib.sha256(world).hexdigest())
    target.write_text(json.dumps(record, indent=2) + '\n', encoding='utf8')
    print(f'Saved {target.relative_to(ROOT)} with {len(records)} file hashes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('version')
    parser.add_argument('--package-directory', default='builds/Windows')
    args = parser.parse_args()
    record(args.version, args.package_directory)
