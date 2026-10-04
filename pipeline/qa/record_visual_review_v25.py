"""Retain root observations of images opened during the M1 review."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
rows = [
    ('blender-yelton-wide-r2-v24', 'blocked_view', 'The camera is inside a canopy proxy. The pole cannot be inspected.'),
    ('blender-ground-golf-greens-v24', 'partial_view', 'Crowns cover most of the overview. Some greens and the clubhouse are visible.'),
    ('blender-ground-community-garden-v24', 'blocked_view', 'A foreground roof and wall cover the garden.'),
    ('blender-ground-railway-tracks-v24', 'partial_view', 'Station, canopy and curved rail sections are visible. Crowns cover the middle.'),
    ('blender-ground-biofilter-v24', 'partial_view', 'The rim, path and water proxy are visible. Canopy forms intersect the water proxy. Water alignment is not accepted.'),
    ('blender-ground-rose-gardens-v24', 'm1_form_visible', 'Paths and beds are visible without an obvious hole.'),
    ('blender-ground-greig-garden-v24', 'blocked_view', 'Crowns cover the target.'),
    ('blender-site-heron-habitat-v24', 'blocked_view', 'The camera is inside a canopy proxy.'),
    ('blender-site-devonian-pond-v24', 'partial_view', 'The source ground envelope is visible. Only small proxy water patches show in the basin. Operating pond water is not accepted.'),
    ('blender-site-hallelujah-v24', 'partial_view', 'Shore, parallel paths and habitat context are visible. The stone marker is not clearly identifiable.'),
    ('blender-site-port-view-v24', 'm1_form_visible', 'Projecting ground and approach forms are visible with the port beyond. Coarse steep terrain remains; this does not accept walking contact.'),
    ('blender-site-rock-garden-v24', 'partial_view', 'Beds and paths near the Pavilion are visible. Crowns cover the centre.'),
    ('blender-site-painters-circle-v24', 'm1_form_visible', 'Oval ground sections and the crossing path are visible without an obvious gap.'),
    ('blender-site-portrait-painters-v24', 'm1_form_visible', 'The path surrounds the grass island. No path cut across the island is visible.'),
    ('blender-site-salmon-lower-pool-v24', 'partial_view', 'Crowns cover most of the basin. A small ground and water strip is visible. Water is not accepted.'),
    ('blender-site-waterpark-low-forms-v24', 'partial_view', 'The pad and low play forms are visible. A canopy proxy intersects the rock mass; source review is pending.'),
    ('blender-site-pitch-putt-clubhouse-v24', 'm1_form_visible', 'The coarse building mass meets the ground beside the path. Some greens are visible beyond.'),
]
for number in ['006', '036', '045']:
    rows.append((f'blender-join-{number}-v25-dedup-repeat', 'specific_repair_partial',
                 'The broad duplicate-face strip is gone. A fine transverse boundary remains at the chunk seam. Pavement and branch surfaces meet visibly. Runtime contact remains pending.'))
reviews = []
for name, status, observation in rows:
    path = ROOT / 'evidence' / (name + '.png')
    reviews.append(dict(image=path.relative_to(ROOT).as_posix(), image_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        status=status, observation=observation))
output = ROOT / 'evidence/m1-root-visual-review-v25.json'
if output.exists():
    raise FileExistsError(output)
output.write_text(json.dumps(dict(scope='Root review of opened live Blender viewport images; no runtime acceptance.',
                                  reviews=reviews, full_m1_accepted=False), indent=2)+'\n', encoding='utf8')
print(json.dumps(dict(reviews=len(reviews), output=str(output))))
