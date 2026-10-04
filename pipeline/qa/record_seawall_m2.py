"""Bind the coordinator's completed M2 review to saved source and evidence files.

This records supplied review decisions. It does not perform a visual review or run
the application, and cannot turn an unreviewed capture into an accepted result.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf8'))


def binding(path):
    full = ROOT / path
    return dict(path=path, bytes=full.stat().st_size,
                sha256=hashlib.sha256(full.read_bytes()).hexdigest())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--review', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    review = read(args.review)
    if not review['m2_review_complete']:
        raise RuntimeError('The coordinator review remains incomplete')
    original = []
    for item in read('evidence/seawall-source-baseline-20261002.json')['files']:
        current = binding(item['path'])
        original.append(dict(**current, baseline_sha256=item['sha256'], unchanged=current['sha256'] == item['sha256']))
    if not all(row['unchanged'] for row in original):
        raise RuntimeError('Original M1 source changed')
    tree_path = read('exports/seawall-trees/latest.json')['manifest']
    tree = read(tree_path)
    applied_tree = read(f"exports/seawall-trees/{tree['version']}/unreal-apply.json")
    water = read('evidence/seawall-water-sky.json')
    if not applied_tree['success'] or not water['success']:
        raise RuntimeError('A layer apply did not pass')
    source_paths = [
        'blender/StanleyPark_Seawall.blend', 'blender/SeawallBirds.blend',
        'unreal/Content/Maps/StanleyParkSeawall.umap',
        'unreal/Binaries/Win64/UnrealEditor-StanleyParkSim.dll',
        tree_path, f"exports/seawall-trees/{tree['version']}/unreal-apply.json",
        'exports/seawall-shore/d2a3c472791b/manifest.json',
        'pipeline/unreal/park_toolset.py', 'tools/unreal-mcp/capture_seawall_views.py',
        'tools/unreal-mcp/aim_seawall_bird_review.py', 'scripts/open-seawall-editor.ps1',
        'pipeline/qa/record_seawall_m2.py', 'pipeline/qa/summarize_seawall_checks.py',
        'pipeline/qa/sample_seawall_gpu.py',
    ]
    for folder, pattern in [('pipeline/blender', '*seawall*.py'),
                            ('pipeline/unreal', '*seawall*.py'),
                            ('manifests', 'seawall*.json'),
                            ('docs', 'SEAWALL*.md')]:
        source_paths.extend(p.relative_to(ROOT).as_posix() for p in (ROOT / folder).glob(pattern))
    source_paths.extend(p.relative_to(ROOT).as_posix() for p in (ROOT / 'unreal/Source/StanleyParkSim').glob('*') if p.suffix in ('.h', '.cpp'))
    source_paths.extend(p.relative_to(ROOT).as_posix() for p in (ROOT / 'unreal/Content/WorldData').glob('*.json'))
    assets = [binding(p.relative_to(ROOT).as_posix()) for p in sorted((ROOT / 'unreal/Content/StanleyPark/Seawall').rglob('*.uasset'))]
    record = dict(recorded_utc=datetime.now(timezone.utc).isoformat(),
                  status='M2 visual pilot complete with recorded limits',
                  scope='Separate authoring map and bounded visual/motion/timing checks. M3 full-route scenery and M4 standalone release remain open.',
                  review=binding(args.review), tree_version=tree['version'],
                  tree_instances=applied_tree['instances'], water_fingerprint=water['fingerprint'],
                  original_m1_files=original, original_m1_sources_unchanged=True,
                  source_bindings=[binding(p) for p in sorted(set(source_paths))],
                  evidence_bindings=[binding(p) for p in review['evidence_paths']],
                  namespace_assets_including_retained_earlier_versions=assets,
                  new_standalone_package=False)
    destination = ROOT / args.output
    if destination.exists():
        raise FileExistsError(destination)
    destination.write_text(json.dumps(record, indent=2), encoding='utf8')
    print(json.dumps(dict(status=record['status'], sources=len(record['source_bindings']),
                          assets=len(assets), evidence=len(record['evidence_bindings']))))


if __name__ == '__main__':
    main()
