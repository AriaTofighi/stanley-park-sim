"""Bind or verify saved M3 runtime files without controlling an application."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b''):
            value.update(block)
    return value.hexdigest()

def files():
    paths = set((ROOT/'unreal/Content/StanleyPark/Seawall').rglob('*.uasset'))
    for relative in ['unreal/Content/Maps/StanleyParkSeawall.umap',
                     'unreal/Content/WorldData/world.json',
                     'data/derived/paved-circuit-runtime.json',
                     'unreal/Config/DefaultEngine.ini', 'unreal/Config/DefaultGame.ini']:
        path = ROOT/relative
        if path.is_file():
            paths.add(path)
    paths.update((ROOT/'unreal/Binaries/Win64').glob('UnrealEditor-StanleyParkSim*.dll'))
    paths.update((ROOT/'unreal/Source/StanleyParkSim').glob('*.cpp'))
    paths.update((ROOT/'unreal/Source/StanleyParkSim').glob('*.h'))
    return sorted(paths)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    current = {path.relative_to(ROOT).as_posix():dict(sha256=sha(path), bytes=path.stat().st_size)
               for path in files()}
    if args.verify:
        expected = json.loads(args.record.read_text())['files']
        differences = sorted(key for key in set(expected)|set(current) if expected.get(key)!=current.get(key))
        print(json.dumps(dict(unchanged=not differences, file_count=len(current), differences=differences)))
        if differences:
            raise SystemExit(1)
    else:
        with args.record.open('x', encoding='utf8') as stream:
            json.dump(dict(time_utc=datetime.now(timezone.utc).isoformat(), files=current,
                scope='Saved native Seawall assets, map, world, route, available game DLLs and project configuration. Includes retained asset versions. Does not certify unsaved editor state.',
                acceptance=False), stream, indent=2)
        print(json.dumps(dict(record=str(args.record), sha256=sha(args.record), file_count=len(current))))

if __name__=='__main__':
    main()
