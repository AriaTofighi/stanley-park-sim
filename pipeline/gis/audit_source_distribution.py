"""Check the explicit source bundle without copying files or running an app."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {'.txt', '.md', '.json', '.geojson', '.osm', '.py', '.npz', '.h'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    register_path = ROOT / 'manifests/source-distribution.json'
    register = json.loads(register_path.read_text(encoding='utf8'))
    failures = []
    file_rows = 0
    mesh_rows = 0
    excluded = set(register['excluded_research_files'])

    def check(relative, expected=None):
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT) or path.suffix not in ALLOWED or relative in excluded:
            failures.append({'path': relative, 'failure': 'unapproved source path or file type'})
            return
        if not path.is_file():
            failures.append({'path': relative, 'failure': 'missing'})
        elif expected and digest(path) != expected.lower():
            failures.append({'path': relative, 'failure': 'hash mismatch'})

    for group in register['groups']:
        for relative in group['files']:
            check(relative)
            file_rows += 1
        manifest = json.loads((ROOT / group['mesh_manifest']).read_text(encoding='utf8'))
        for mesh in manifest[group.get('mesh_collection', 'meshes')]:
            relative = mesh[group.get('mesh_path_property', 'path')].replace('\\', '/')
            if not relative.startswith(group['mesh_root']) or not relative.endswith('.npz'):
                failures.append({'path': relative, 'failure': 'outside registered mesh folder'})
            check(relative, mesh.get('sha256'))
            mesh_rows += 1
    check(register['notice'])
    seam = json.loads((ROOT / 'evidence/blender-pavement-closing-seam-support.json').read_text())
    seam_inputs = seam['source_inputs'] + [
        {'path': 'pipeline/blender/pavement_seam_support.py', 'sha256': seam['helper_sha256']},
        {'path': 'data/derived/surface-control-points.json', 'sha256': seam['controls_sha256']},
        {'path': 'evidence/unreal-surface-transfer-v25-failure.json', 'sha256': seam['failure_sha256']},
    ]
    for item in seam_inputs:
        check(item['path'], item['sha256'])
    result = {
        'kind': 'Read-only source-bundle path/hash audit, not a packaging run or application test',
        'checked_utc': datetime.now(timezone.utc).isoformat(),
        'groups': len(register['groups']), 'mesh_rows': mesh_rows,
        'explicit_file_rows': file_rows, 'seam_dependency_hashes_checked': len(seam_inputs),
        'failures': failures, 'packaging_success_claimed': False,
        'register_sha256': digest(register_path),
    }
    for relative in ['evidence/source-bundle-readiness-v26.json',
                     'evidence/site-completions/source-bundle-readiness.json']:
        (ROOT / relative).write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
