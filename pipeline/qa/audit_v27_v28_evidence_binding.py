"""Read-only package/source comparison for the fixed recorder-finalization change."""
from pathlib import Path
import datetime
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
OLD = 'builds/Windows-Roam'
NEW = 'builds/Windows-M1-v28'


def load(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8-sig'))


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def key(path):
    for base in (OLD, NEW):
        if path.startswith(base + '/'):
            return '$PACKAGE/' + path[len(base) + 1:]
    return path


def audit():
    old_path = 'evidence/build-m1-v27-provenance.json'
    new_path = 'evidence/build-m1-v28-provenance.json'
    old, new = load(old_path), load(new_path)
    old_rows = {key(x['path']): x for x in old['files']}
    new_rows = {key(x['path']): x for x in new['files']}
    allowed = {'unreal/Source/StanleyParkSim/' + name for name in (
        'SPRideCapture.cpp', 'SPRideCapture.h', 'SPRidingDiagnostics.cpp', 'SPRidingDiagnostics.h')}
    allowed.add('$PACKAGE/StanleyParkSim/Binaries/Win64/StanleyParkSim.exe')
    rows, failures = [], []
    for name in sorted(set(old_rows) | set(new_rows)):
        before, after = old_rows.get(name), new_rows.get(name)
        if not (before and after):
            failures.append('Different sealed path set: ' + name)
            continue
        before_file = ROOT / before['path']
        if name in allowed and name.startswith('unreal/Source/'):
            before_file = ROOT / 'evidence/v27-source-before-final-frame-fix' / Path(name).name
        old_ok = before_file.is_file() and digest(before_file) == before['sha256']
        after_file = ROOT / after['path']
        new_ok = after_file.is_file() and digest(after_file) == after['sha256']
        identical = before['sha256'] == after['sha256']
        rows.append(dict(key=name, v27_path=before['path'], v28_path=after['path'],
            v27_sha256=before['sha256'], v28_sha256=after['sha256'],
            v27_bound_file_matches=old_ok, v28_bound_file_matches=new_ok,
            identical=identical, allowed_change=name in allowed))
        if not old_ok or not new_ok:
            failures.append('Bound file mismatch: ' + name)
        if not identical and name not in allowed:
            failures.append('Unexpected change: ' + name)

    snapshots = []
    for field in ('world_snapshot', 'export_snapshot', 'import_snapshot', 'join_fixture_snapshot'):
        a, b = ROOT / old[field], ROOT / new[field]
        identical = a.read_bytes() == b.read_bytes()
        snapshots.append(dict(kind=field, v27=old[field], v28=new[field],
            v27_sha256=digest(a), v28_sha256=digest(b), identical=identical))
        if not identical:
            failures.append('Snapshot differs: ' + field)

    review_path = 'evidence/ride-capture-final-frame-v28-independent-review.json'
    review = load(review_path)
    for row in review['files']:
        name = 'unreal/Source/StanleyParkSim/' + row['name']
        if (old_rows[name]['sha256'] != row['v27_backup_sha256']
                or new_rows[name]['sha256'] != row['v28_source_sha256']):
            failures.append('Sealed code differs from reviewed diff: ' + name)
    if not review['review_pass']:
        failures.append('Independent source review did not pass')

    indices = {base: load(base + '/SourceData/source-bundle-index.json') for base in (OLD, NEW)}
    bundle_rows, bundle_maps, bundle_audits = [], [], []
    legacy = load('evidence/source-bundle-provenance-audit-v27.json')['legacy_flat_pedestrian_copies']
    register = load('manifests/source-distribution.json')
    for base, index in indices.items():
        bundle = ROOT / base / 'SourceData'
        expected = set()
        for row in index['files']:
            relative = Path(row['group']) / row['project_path']
            expected.add(relative)
            path = bundle / relative
            if not path.is_file() or digest(path) != row['sha256']:
                failures.append('Source bundle mismatch: ' + str(path))
        mapping = {(z['group'], z['project_path']): z['sha256'] for z in index['files']}
        bundle_maps.append(mapping)
        bundle_rows.append(dict(package=base, index_sha256=digest(bundle / 'source-bundle-index.json'),
            register_sha256=index['register_sha256'], rows=len(index['files']), unique_rows=len(mapping)))
        expected.update(Path(p) for p in ('source-bundle-index.json', 'source-distribution.json', 'OSM-DATA-LICENCE.txt'))
        for row in legacy:
            relative = Path(row['packaged_path']).relative_to(Path(OLD) / 'SourceData')
            expected.add(relative)
            if digest(bundle / relative) != row['sha256']:
                failures.append('Legacy copy mismatch: ' + base + '/' + str(relative))
        for relative, source in (('source-distribution.json', 'manifests/source-distribution.json'),
                ('OSM-DATA-LICENCE.txt', register['notice'])):
            if digest(bundle / relative) != digest(ROOT / source):
                failures.append('Copied register/notice mismatch: ' + base + '/' + relative)
        actual = {p.relative_to(bundle) for p in bundle.rglob('*') if p.is_file()}
        unexpected = sorted(str(p) for p in actual - expected)
        missing = sorted(str(p) for p in expected - actual)
        media = sorted(str(p) for p in actual if p.suffix.lower() in {'.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff'})
        if unexpected or missing or media:
            failures.append('Unexpected/missing/research source files: ' + base)
        bundle_audits.append(dict(package=base, actual_files=len(actual), unexpected=unexpected, missing=missing, research_media=media))
    bundle_equal = bundle_maps[0] == bundle_maps[1]
    if not bundle_equal:
        failures.append('Source bundle contents differ')

    result = dict(schema_version=1, audit_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        scope='Independent sealed v27/v28 code, content and source-bundle comparison; no application tests or final M1 acceptance.',
        provenance=[dict(path=p, sha256=digest(ROOT / p)) for p in (old_path, new_path)],
        review=dict(path=review_path, sha256=digest(ROOT / review_path)), rows=rows, snapshots=snapshots,
        source_bundles=bundle_rows, source_bundle_rows_identical=bundle_equal,
        source_bundle_file_audits=bundle_audits, allowed_changed_files=sorted(allowed),
        actual_changed_files=[z['key'] for z in rows if not z['identical']], failures=failures,
        audit_pass=not failures,
        post_terminal_difference='v28 holds pedal/steer at zero and brake at one only while pending capture frames/writes drain, after saved terminal values freeze.',
        conditional_evidence_use='A valid complete v27 full-lap log AND video can support unchanged v28 world/controller coverage. Failed/remaining capture fixtures still need v28 repeats. An incomplete v27 full video cannot close the lap gate.',
        m1_complete=False)
    output = ROOT / 'evidence/m1-v27-v28-cross-build-audit.json'
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: result[k] for k in ('actual_changed_files', 'source_bundle_rows_identical', 'source_bundle_file_audits', 'failures', 'audit_pass')}, indent=2))
    return not failures


if __name__ == '__main__':
    raise SystemExit(0 if audit() else 1)
