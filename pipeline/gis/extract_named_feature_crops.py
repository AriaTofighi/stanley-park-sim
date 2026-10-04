"""Bounded raw survey crops for individually identified M1 forms.

Crop centres only select data. They are not accepted placement controls.
"""
import json
import zipfile
from pathlib import Path

import laspy
import numpy as np

from acquire_sources import digest, save_json
from height_reference import VancouverHeightConversion

ROOT = Path(__file__).resolve().parents[2]
FEATURES = [
    ('prospect-light', (122.7, 1271.6), 15, '489000_5462000'),
    ('prospect-lookout', (70, 1245), 40, '489000_5462000'),
    ('prospect-cafe', (40, 1125), 45, '489000_5462000'),
    ('lumberman-arch', (900, -5), 90, '490000_5461000'),
    ('nine-clock-gun', (1855, -506), 20, '491000_5460000'),
]

def main():
    conversion = VancouverHeightConversion()
    origin = json.loads((ROOT/'manifests/world-origin.json').read_text(encoding='utf8'))
    for tile in sorted({x[3] for x in FEATURES}):
        pending = [x for x in FEATURES if x[3] == tile and not (ROOT/f'data/derived/named-{x[0]}-survey.npz').exists()]
        if not pending:
            continue
        buckets = {x[0]: [[], [], []] for x in pending}
        archive = ROOT/f'data/raw/city/lidar2022/{tile}.zip'
        with zipfile.ZipFile(archive) as z:
            with z.open(f'{tile}.las') as stream, laspy.open(stream) as reader:
                for chunk in reader.chunk_iterator(1_000_000):
                    x, y = np.asarray(chunk.x)-origin['easting'], np.asarray(chunk.y)-origin['northing']
                    classes = np.asarray(chunk.classification)
                    for name, centre, radius, _ in pending:
                        take = ((x-centre[0])**2+(y-centre[1])**2<radius**2)&(classes!=7)
                        if not take.any():
                            continue
                        h = conversion.to_cgvd2013(x[take]+origin['easting'],y[take]+origin['northing'],np.asarray(chunk.z)[take])
                        buckets[name][0].append(np.column_stack((x[take],y[take],h)).astype(np.float32))
                        buckets[name][1].append(np.column_stack((np.asarray(chunk.red)[take],np.asarray(chunk.green)[take],np.asarray(chunk.blue)[take])))
                        buckets[name][2].append(classes[take])
        for name, centre, radius, _ in pending:
            xyz,rgb,classes = [np.concatenate(p) for p in buckets[name]]
            out = ROOT/f'data/derived/named-{name}-survey.npz'
            np.savez_compressed(out,xyz=xyz,rgb=rgb,classification=classes)
            save_json(ROOT/f'manifests/named-{name}-survey.json',dict(
                id=name,extraction_centre_local_m=centre,extraction_radius_m=radius,
                source=f'manifests/lidar2022-{tile}.json',source_period='2022-09-07/09',
                vertical_datum='CGVD2013',licence='Open Government Licence - Vancouver',
                placement_accepted=False,returns=len(xyz),output=dict(path=out.relative_to(ROOT).as_posix(),sha256=digest(out))))
            print(name,len(xyz),flush=True)

if __name__ == '__main__':
    main()
