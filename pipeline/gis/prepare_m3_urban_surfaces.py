"""Freeze a material-only city/infrastructure override plan from source metadata."""
from collections import Counter
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    inputs = ['manifests/blender-export.json', 'manifests/skyline-blockouts.json',
              'manifests/underpass-survey.json', 'manifests/underpass-dimensions.json',
              'manifests/underpass-reference-sources.json',
              'manifests/m3-urban-surface-settings.json',
              'pipeline/gis/prepare_m3_urban_surfaces.py']
    hashes = {p: sha(ROOT / p) for p in inputs}
    settings = json.loads((ROOT / inputs[-2]).read_text())
    exported = json.loads((ROOT / inputs[0]).read_text())
    targets = []
    for asset in exported['assets']:
        if not asset['name'].startswith(tuple(settings['prefixes'])) or not asset.get('place_in_level', True):
            continue
        slots = []
        for i, name in enumerate(asset['materials']):
            if name not in settings['profiles']:
                continue
            color = asset['material_colors'][i][:3]
            if len(color) != 3 or not all(0 <= c <= 1 for c in color):
                raise ValueError('Invalid source material color: ' + asset['name'])
            slots.append(dict(slot=i, source_material=name, color=color,
                              two_sided=asset['material_two_sided'][name],
                              profile=settings['profiles'][name]))
        if slots:
            targets.append(dict(name=asset['name'], asset_path=asset['asset_path'],
                source_id=asset['source_id'], position_cm=asset['position_cm'],
                bounds_min_cm=asset['bounds_min_cm'], bounds_max_cm=asset['bounds_max_cm'], slots=slots))
    payload = dict(schema_version=1, settings=settings, input_hashes=hashes, targets=targets)
    version = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]
    payload.update(version=version, asset_root='/Game/StanleyPark/Seawall/UrbanSurfaces/v_' + version)
    folder = ROOT / 'exports/m3-urban-surfaces' / version
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder / 'manifest.json'
    serialized = json.dumps(payload, indent=2) + '\n'
    if manifest.exists() and manifest.read_text() != serialized:
        raise RuntimeError('Frozen urban manifest already differs')
    manifest.write_text(serialized)
    pointer = dict(version=version, manifest=manifest.relative_to(ROOT).as_posix(), sha256=sha(manifest))
    (folder.parent / 'latest.json').write_text(json.dumps(pointer, indent=2) + '\n')
    print(json.dumps(dict(**pointer, targets=len(targets),
        profiles=dict(Counter(s['profile']['kind'] for t in targets for s in t['slots']))), indent=2))


if __name__ == '__main__':
    build()
