"""Extract nearby returns around referenced names, without treating names as controls."""
import json
import zipfile
from pathlib import Path
import laspy
import numpy as np
from pyproj import Transformer
from acquire_sources import ROOT, digest, save_json
from height_reference import VancouverHeightConversion

features = [
    dict(id='lions-gate-north-ground',easting=490046.62800598,northing=5462724.85253906,radius_m=140.,
        source='manifests/lions-gate-blockout.json',
        reference_date='Centre fitted to 2022 tower envelope; wider crop for the visible rock berm'),
    dict(id='brockton-lighthouse', lon=-123.116807, lat=49.3006974, radius_m=45.,
        source='https://veterans.gc.ca/en/remembrance/memorials/canada/brockton-point-lighthouse',
        reference_date='Page modified 2025-05-25; crowd-sourced location, not a survey'),
    dict(id='siwash-rock', lon=-(123+9/60+21/3600), lat=49+18/60+31/3600, radius_m=60.,
        source='https://apps.gov.bc.ca/pub/bcgnws/names/76640.html',
        reference_date='BC geographical names; approximate centre; accessed 2026-09-26'),
]
origin = json.loads((ROOT/'manifests/world-origin.json').read_text())
transform = Transformer.from_crs(4326,3157,always_xy=True)
conversion = VancouverHeightConversion()
for feature in features:
    output = ROOT/f"data/derived/{feature['id']}-survey.npz"
    if output.exists():
        print('Existing crop',feature['id'],flush=True)
        continue
    e,n = (feature['easting'],feature['northing']) if 'easting' in feature else transform.transform(feature['lon'],feature['lat'])
    center = np.array([e-origin['easting'],n-origin['northing']])
    radius = feature['radius_m']
    tiles = [(x,y) for x in range(int((e-radius)//1000)*1000,int((e+radius)//1000)*1000+1,1000)
             for y in range(int((n-radius)//1000)*1000,int((n+radius)//1000)*1000+1,1000)]
    parts, colors, classifications, sources = [],[],[],[]
    for x,y in tiles:
        tile=f'{x}_{y}'
        archive=ROOT/f'data/raw/city/lidar2022/{tile}.zip'
        if not archive.exists():
            raise FileNotFoundError(archive)
        with zipfile.ZipFile(archive) as z:
            with z.open(f'{tile}.las') as stream, laspy.open(stream) as reader:
                for chunk in reader.chunk_iterator(1_000_000):
                    px,py=np.asarray(chunk.x),np.asarray(chunk.y)
                    take=((px-e)**2+(py-n)**2<radius**2)&(np.asarray(chunk.classification)!=7)
                    height=conversion.to_cgvd2013(px[take],py[take],np.asarray(chunk.z)[take])
                    parts.append(np.column_stack((px[take]-origin['easting'],py[take]-origin['northing'],height)))
                    colors.append(np.column_stack((np.asarray(chunk.red)[take],np.asarray(chunk.green)[take],np.asarray(chunk.blue)[take])))
                    classifications.append(np.asarray(chunk.classification)[take])
        sources.append(f'manifests/lidar2022-{tile}.json')
    points=np.concatenate(parts).astype(np.float32)
    np.savez_compressed(output,xyz=points,rgb=np.concatenate(colors),classification=np.concatenate(classifications))
    save_json(ROOT/f"manifests/{feature['id']}-survey.json",dict(**feature,
        center_local_m=center.tolist(),source_accuracy='Name point is for extraction only; measured placement must be fitted and inspected',
        sources=sources,vertical_datum='CGVD2013',survey_period='2022-09-07/09',
        bounds_min=points.min(0).tolist(),bounds_max=points.max(0).tolist(),returns=len(points),
        output=dict(path=output.relative_to(ROOT).as_posix(),sha256=digest(output)),accepted=False))
    print(feature['id'],len(points),center.tolist(),flush=True)
