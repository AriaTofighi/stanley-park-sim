"""Create release ZIPs from a packaged build and an explicit asset allowlist.

Uses only the Python standard library. Does not build, launch, or test the game.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIVATE_TEXT = re.compile(
    r'(?i)(?:[A-Z]:[/\\]+Users[/\\]+[^\s"<>/\\]+|'
    r'\b(?:SecurityToken|api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*["\']?[A-Za-z0-9_+/=-]{16,}|'
    r'\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{40,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)'
)
TEXT_EXTENSIONS = {'.txt', '.md', '.ini', '.json', '.geojson', '.py', '.ps1', '.csv', '.xml', '.osm', '.h'}


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inside_project(path: str) -> Path:
    result = (ROOT / path).resolve()
    if not result.is_relative_to(ROOT):
        raise ValueError('Path is outside the project')
    return result


def check_text(path: Path) -> None:
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return
    content = path.read_text(encoding='utf-8-sig', errors='strict')
    if PRIVATE_TEXT.search(content):
        raise ValueError(f'Private data pattern in {path.relative_to(ROOT)}; review before release')


def add_file(archive: zipfile.ZipFile, path: Path, name: str) -> None:
    if path.is_symlink() or path.is_junction() or not path.is_file():
        raise ValueError(f'Expected a regular file: {path}')
    if Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('Unsafe ZIP member')
    check_text(path)
    archive.write(path, name)


def verify_archive(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f'ZIP checksum failure: {bad}')
        entries = archive.infolist()
        names = [entry.filename.casefold() for entry in entries]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate ZIP members')
        uncompressed = sum(entry.file_size for entry in entries)
    if path.stat().st_size >= 2 * 1024**3:
        raise ValueError('Archive exceeds the 2 GiB release asset limit')
    return {'name': path.name, 'bytes': path.stat().st_size, 'sha256': sha256(path),
            'files': len(entries), 'uncompressed_bytes': uncompressed, 'zip_crc_verified': True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', required=True, help='Project-relative packaged Windows directory')
    parser.add_argument('--output', default='dist/v0.4.0')
    parser.add_argument('--version', default='0.4.0')
    args = parser.parse_args()
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[a-z0-9.]+)?', args.version):
        raise ValueError('Use a semantic version')
    build, output = inside_project(args.build), inside_project(args.output)
    if not (build/'StanleyParkSim.exe').is_file() or not (build/'SourceData/source-bundle-index.json').is_file():
        raise ValueError('Packaged runtime and source-data offer are required')
    output.mkdir(parents=True, exist_ok=True)
    paths = {kind: output/f'StanleyPark-{kind}-v{args.version}.zip' for kind in ['Windows','Assets','SourceData']}
    if any(path.exists() for path in paths.values()):
        raise ValueError('Output archives already exist; preserve them and choose a new directory')

    asset_rows = read_json(ROOT/'manifests/release-assets.json')['files']
    asset_names = set()
    for row in asset_rows:
        path = inside_project(row['path'])
        name = path.relative_to(ROOT).as_posix()
        if not name.startswith(('unreal/Content/','blender/','exports/','data/')):
            raise ValueError('Asset outside the allowed source folders')
        if name.casefold() in asset_names:
            raise ValueError('Duplicate asset path')
        asset_names.add(name.casefold())
        if path.stat().st_size != row['bytes'] or sha256(path) != row['sha256']:
            raise ValueError(f'Asset differs from reviewed manifest: {name}')
        check_text(path)

    excluded = {'.pdb','.log','.utrace','.tmp'}
    runtime_files = []
    for path in sorted(build.rglob('*')):
        if not path.is_file():
            continue
        name = path.relative_to(build).as_posix()
        if 'Saved' in path.relative_to(build).parts or path.suffix.lower() in excluded or name.startswith('Manifest_'):
            continue
        check_text(path)
        runtime_files.append((path, name))
    print(f'Checked {len(asset_rows)} editable assets and {len(runtime_files)} runtime files.', flush=True)

    with zipfile.ZipFile(paths['Windows'], 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path, name in runtime_files:
            add_file(archive,path,name)
    print('Windows archive complete.', flush=True)
    with zipfile.ZipFile(paths['Assets'], 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for row in asset_rows:
            add_file(archive,inside_project(row['path']),row['path'])
    print('Editable asset archive complete.', flush=True)
    with zipfile.ZipFile(paths['SourceData'], 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted((build/'SourceData').rglob('*')):
            if path.is_file():
                add_file(archive,path,path.relative_to(build).as_posix())
        for path in sorted((ROOT/'docs/legal').glob('*.txt')):
            add_file(archive,path,'Notices/'+path.name)

    records = [verify_archive(path) for path in paths.values()]
    base = f'https://github.com/AriaTofighi/stanley-park-sim/releases/download/v{args.version}/'
    for row in records:
        row['url'] = base + row['name']
    record = {'schema_version':1, 'version':args.version, 'configuration':'Shipping',
              'application_test_run_for_publication':False, 'assets':records}
    manifest_path = ROOT/f'manifests/release-v{args.version}.json'
    manifest_path.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    (output/'SHA256SUMS.txt').write_text(''.join(row['sha256']+'  '+row['name']+'\n' for row in records),encoding='utf-8')
    (output/'release-manifest.json').write_bytes(manifest_path.read_bytes())
    print(json.dumps(record,indent=2),flush=True)


if __name__ == '__main__':
    main()
