"""Record root observations of the eight opened v26 Unreal site images."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
observations = {
    'site_port_view_r2': ('visible', 'The shore projection, approach, harbour water and downtown silhouettes are visible. Ground triangles remain coarse. No contact acceptance follows from this still.'),
    'site_rock_garden_r2': ('partial', 'Paths and brown bed envelopes are visible beside the Pavilion. Canopy envelopes hide part of the central garden; this is garden layout only.'),
    'site_painters_circle_r2': ('partial', 'Light oval ground sections and their crossing path are visible. Foreground canopy hides part of the perimeter.'),
    'site_portrait_painters_r2': ('partial', 'Grass and bordering paths are visible below the crowns. The full island perimeter is not visible from this camera.'),
    'site_salmon_lower_pool_r2': ('partial', 'The basin ground envelope is visible. Only a narrow blue water proxy shows; operating water level is not accepted.'),
    'site_waterpark_low_forms_r2': ('visible', 'Low red play mass, sloped pad and small white fixtures meet the ground. The foreground slope hides part of the pad; finished play detail is absent.'),
    'site_waterpark_rock_r2': ('visible', 'The complete front of the coarse rock play mass and its base are visible. Crowns partly frame its ends. No visible hole at its ground contact.'),
    'site_pitch_putt_clubhouse_r2': ('visible', 'The clubhouse mass and adjacent path are visible with grounded wall bottoms. The roof is mostly hidden by this low angle; no facade detail is claimed.'),
}
rows = []
for view, (status, observation) in observations.items():
    path = ROOT / 'evidence' / f'unreal-{view}-v26.png'
    rows.append(dict(image=path.relative_to(ROOT).as_posix(), image_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), status=status, observation=observation))
target = ROOT / 'evidence/m1-unreal-root-site-visual-review-v26.json'
with target.open('x', encoding='utf8') as output:
    json.dump(dict(scope='Root opened-image review of live MCP captures. Coarse M1 site forms only; no ride or final art acceptance.', reviews=rows), output, indent=2)
    output.write('\n')
