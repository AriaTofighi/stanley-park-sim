"""Retain the coordinator's actual review of v3 route frames 026 through 037."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'evidence/m3-views/m3-v3-final-route'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

findings = {
    26: 'Beach opening, separate stones and grounded trees are visible. Route is clear. Terrain remains faceted.',
    27: 'Cliff and shore support faces are solid in these frames. Route is clear; angular source slopes remain.',
    28: 'Both cliff turns have solid visible edge faces. No blue opening was identified. Coarse wedges remain visible.',
    29: 'Continuous coastal corridor with stones and trees. Distant skyline stays coarse. No obstructing decoration identified.',
    30: 'Forest-to-beach transition is continuous. Solid triangular source faces remain prominent beside the path.',
    31: 'Open shore and grounded near trees are present. Coarse shore triangles and offshore forms remain; no route obstruction identified.',
    32: 'Pool outline and coping are visible at boundary. The broad tan facility mass needs a source-based facade/canopy correction. Midpoint buildings remain simple.',
    33: 'Underpass opening stays clear. Panel surface detail is visible. Nearby service blocks retain simple forms.',
    34: 'Near tree stems now join their crowns continuously. Open ground and path boundaries are retained. Distant foliage is lighter.',
    35: 'City-facing building surfaces now have window divisions; trees and route remain clear. Facades are generic and not exact reconstructions.',
    36: 'Continuous lagoon-side corridor and windowed city masses. No obstructing new decoration identified; distant shore remains coarse.',
    37: 'Underpass is open and panel material is visible. Tiny blue gap at midpoint pixel (1087,657) beside right support needs correction. Boundary skyline divisions are visible.',
}
rows = []
for section in range(26, 38):
    for kind in ['midpoint', 'boundary']:
        for suffix in ['-settle-first', '']:
            path = FOLDER / kind / f'section_{section:03d}{suffix}.png'
            metadata_path = path.with_suffix('.json')
            metadata = json.loads(metadata_path.read_text())
            binding = ROOT / metadata['source_binding']
            assert sha(path) == metadata['image_sha256']
            assert sha(binding) == metadata['source_binding_sha256']
            rows.append(dict(image=path.relative_to(ROOT).as_posix(), image_sha256=sha(path),
                metadata=metadata_path.relative_to(ROOT).as_posix(), metadata_sha256=sha(metadata_path),
                source_binding=metadata['source_binding'], source_binding_sha256=sha(binding),
                opened_and_reviewed=True, finding=findings[section]))
report = dict(time_utc=datetime.now(timezone.utc).isoformat(), reviewer='Coordinator',
    method='All 48 original PNGs opened with view_image and visually inspected in this conversation.',
    frames=rows, frame_count=len(rows), acceptance=False,
    required_corrections=['Second Beach facility facade/canopy in section032',
                          'Tiny support gap beside midpoint037 underpass'],
    limits=['Editor stills do not establish motion, ride, collision or performance acceptance.',
            'Small seams, coarse source terrain and generic city facades remain visible.',
            'Critical landmark visibility requires the separate targeted views.'])
output = ROOT / 'evidence/m3-root-route-review-v3-final.json'
with output.open('x', encoding='utf8') as stream:
    json.dump(report, stream, indent=2)
print(output.relative_to(ROOT), len(rows), sha(output))
