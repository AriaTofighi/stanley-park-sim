"""Compare protected source bytes with the recorded M3 starting state."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    baseline_path = ROOT/'evidence/m3-baseline-20261003/sources.json'
    baseline = json.loads(baseline_path.read_text())
    rows = []
    for row in baseline['files']:
        if row.get('snapshot'):
            # Working Seawall content is expected to change. Its exact start
            # remains archived; test that archived file against its original hash.
            path = ROOT/row['snapshot']
        else:
            path = ROOT/row['path']
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(dict(path=path.relative_to(ROOT).as_posix(),
                         expected=row['sha256'], actual=actual, unchanged=actual==row['sha256']))
    record = dict(time_utc=datetime.now(timezone.utc).isoformat(),
                  success=all(row['unchanged'] for row in rows), files=rows)
    (ROOT/'evidence/m3-source-preservation.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(dict(success=record['success'], files=len(rows))))
    if not record['success']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
