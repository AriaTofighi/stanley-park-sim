"""Read NVIDIA device telemetry during a manually started bounded review."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
parser.add_argument('--seconds', type=int, default=40)
args = parser.parse_args()
if not 1 <= args.seconds <= 60:
    raise ValueError('Use a bounded 1 to 60 second sample')
rows = []
for _ in range(args.seconds):
    started = time.monotonic()
    result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,memory.used,utilization.gpu',
                             '--format=csv,noheader,nounits'], check=True, capture_output=True, text=True)
    name, total, used, utilization = [v.strip() for v in result.stdout.strip().split(',')]
    rows.append(dict(time_utc=datetime.now(timezone.utc).isoformat(), device=name,
                     total_mib=float(total), used_mib=float(used), utilization_percent=float(utilization)))
    time.sleep(max(0, 1 - (time.monotonic() - started)))
record = dict(scope='Whole GPU device, including editor, Blender, desktop and other processes; '
                    'not exclusive application VRAM.', samples=rows,
              maximum_used_mib=max(r['used_mib'] for r in rows))
Path(args.output).write_text(json.dumps(record, indent=2), encoding='utf8')
print(json.dumps({k:v for k,v in record.items() if k != 'samples'}))
