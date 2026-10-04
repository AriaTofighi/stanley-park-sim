"""Review independent monuments without equating every monument with the ground.

The full source reports stay internal. A matching nearby height is useful
evidence, but does not identify a bolt in aerial data or verify its wall offset.
"""
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import RegularGridInterpolator

from height_reference import VancouverHeightConversion

ROOT = Path(__file__).resolve().parents[2]
REVIEWS = {
    590034: dict(name='Prospect Point', current_condition='GOOD', condition_date='2025-06-27',
                 condition_method='Visible GeoNetBC record, read 2026-09-26 local',
                 surface='Brass bolt on the paved lookout; 1981 location sketch inspected',
                 issue='Exact bolt centre and unchanged local surface need positive identification',
                 diagram='https://geonetbc.gov.bc.ca/geonetbc/Photos/590034%5C590034.gif'),
    432062: dict(name='Brockton Point', current_condition='GOOD', condition_date='2025-06-19',
                 condition_method='Visible GeoNetBC record, read 2026-09-26 local',
                 surface='Rock post in concrete, north of Park Drive and west of bike bollards',
                 issue='Marker top relative to surrounding pavement is not established'),
    476242: dict(name='Coal Harbour bridge', current_condition=None, condition_date=None,
                 surface='Rock post set in a bridge',
                 issue='Ground below the bridge is not the monument surface; current record not checked'),
    163956: dict(name='Ferguson Point', current_condition=None, condition_date=None,
                 surface='Brass bolt set flush in a concrete wall',
                 issue='Wall-top return must be identified; ground is not interchangeable; current record not checked'),
}


def number(pattern, text):
    match = re.search(pattern, text)
    if not match:
        raise ValueError(f'Missing published field: {pattern}')
    return float(match.group(1))


def main():
    conversion = VancouverHeightConversion()
    origin = json.loads((ROOT/'manifests/world-origin.json').read_text(encoding='utf8'))
    with np.load(ROOT/'data/derived/terrain_2022_park.npz') as grid:
        terrain = RegularGridInterpolator((grid['y'],grid['x']),grid['z'],bounds_error=False,fill_value=np.nan)
    rows = []
    fig, axes = plt.subplots(2, 2, figsize=(11, 9), dpi=150)
    for ax, (gcm, review) in zip(axes.flat, REVIEWS.items()):
        source = ROOT/f'data/raw/corridor/mascot-{gcm}-complete-report.html'
        text = html.unescape(re.sub('<[^>]+>', ' ', source.read_text(encoding='utf8')))
        text = ' '.join(text.split())
        if f'GCM No: {gcm}' not in text or 'CVD28GVRD2018' not in text:
            raise ValueError(f'Unexpected control identity or datum: {source}')
        east = number(r'Easting ([0-9.]+) m', text)
        north = number(r'Northing ([0-9.]+) m', text)
        height28 = number(r'Elevation ([0-9.]+) Metres', text)
        height = float(conversion.to_cgvd2013([east], [north], [height28])[0])
        xy = np.array([east-origin['easting'], north-origin['northing']])
        tile = f'{int(east//1000)*1000}_{int(north//1000)*1000}'
        with np.load(ROOT/f'data/derived/lidar2022_{tile}.npz') as data:
            ground = data['ground']
        dist2 = ((ground[:,:2]-xy)**2).sum(1)
        index = int(dist2.argmin())
        nearest = ground[index]
        nearby = ground[dist2 <= 1.0]
        neighbourhood = ground[dist2 <= 25.0]
        model_height = float(terrain(xy[None, ::-1])[0])
        row = dict(gcm=gcm, **review,
            source_url=f'https://a100.gov.bc.ca/pub/mascotw/protected/longf.html?Q_GCM_NO={gcm}&Q_OPT=1',
            current_url=f'https://geonetbc.gov.bc.ca/geonetbc/gcm/details/{gcm}',
            report_path=source.relative_to(ROOT).as_posix(), report_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            report_rights='Internal measurement reference only; full report is excluded from Git and the game',
            horizontal_datum='NAD83(CSRS) 4.0.0.BC.1.MVRD', horizontal_publication='2019-12-02',
            vertical_datum='CVD28GVRD2018', vertical_publication='2018-10-31',
            published_easting_m=east, published_northing_m=north, published_height_m=height28,
            converted_height_m=height, position_local_m=xy.tolist(),
            nearby_ground_count=len(nearby), nearest_ground_distance_m=float(np.sqrt(dist2[index])),
            nearest_ground_height_m=float(nearest[2]), nearest_ground_minus_marker_m=float(nearest[2]-height),
            nearby_ground_native_height_range_m=np.percentile(nearby[:,3],[0,50,100]).tolist() if len(nearby) else None,
            terrain_height_m=model_height if np.isfinite(model_height) else None,
            terrain_minus_marker_m=model_height-height if np.isfinite(model_height) else None,
            accepted_independent_control=False)
        rows.append(row)
        scatter=ax.scatter(neighbourhood[:,0]-xy[0],neighbourhood[:,1]-xy[1],
                           c=neighbourhood[:,2]-height, cmap='coolwarm', vmin=-.5, vmax=.5, s=3)
        ax.plot(0,0,'kx',ms=10,mew=1.5,label='Published marker XY')
        ax.set(xlabel='East offset (m)',ylabel='North offset (m)',
               title=f"{gcm}: {review['name']}\nNearest ground minus marker: {row['nearest_ground_minus_marker_m']:+.3f} m")
        ax.set_aspect('equal'); ax.legend(loc='lower left',fontsize=7)
    fig.suptitle('Independent marker review — ground association is not yet accepted', fontsize=12)
    fig.subplots_adjust(left=.08,right=.85,top=.90,bottom=.07,hspace=.30,wspace=.30)
    for ax in axes.flat:ax.title.set_fontsize(10)
    fig.colorbar(scatter,cax=fig.add_axes([.90,.16,.02,.65]),extend='both',
                 label='Ground return minus marker height (m)')
    fig.savefig(ROOT/'evidence/corridor/geodetic-control-review.png')
    # A visible independent web-service calculation checks the geoid arithmetic.
    # Its epoch transformation is not the same operation as the fixed local grids.
    local_height = rows[0]['converted_height_m']
    report = dict(created_utc=datetime.now(timezone.utc).isoformat(),
        accepted_independent_control_count=0,
        scope='Four independent monument candidates; physical surface association remains open',
        controls=rows,
        conversion_cross_check=dict(gcm=590034,
            source_url='https://geonetbc.gov.bc.ca/geonetbc/gcm/details/590034',
            method='GeoNetBC visible selectors: NAD83(CSRS), UTM, CGVD2013, CGG2013a, epoch 2010.0',
            observed_utm_m=[489666.641,5462349.373], observed_height_m=57.291,
            project_grid_only_height_m=local_height, height_difference_m=local_height-57.291,
            interpretation='3 mm agreement checks the grid conversion. Epoch motion and published rounding differ. This is not a new surveyed height or an absolute accuracy certification.'),
        limits=['A height match does not locate a small marker in the point cloud.',
                'Bridge and wall markers cannot be compared directly with classified ground.',
                'The source reports do not publish a height standard deviation.',
                'CGVD28GVRD versus its 2018 refresh and horizontal realization need source confirmation.',
                'No geometry or datum offset was adjusted to fit these values.'])
    (ROOT/'evidence/corridor/geodetic-control-review.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    ledger_path=ROOT/'manifests/survey-control-sources.json'
    ledger=json.loads(ledger_path.read_text(encoding='utf8'))
    ledger['detailed_report_review']='evidence/corridor/geodetic-control-review.json'
    ledger['current_service']='https://geonetbc.gov.bc.ca/geonetbc/'
    ledger['current_service_note']='GeoNetBC has replaced MASCOT. Current condition records can be newer than the legacy long forms.'
    ledger['accepted']=False
    ledger_path.write_text(json.dumps(ledger,indent=2)+'\n',encoding='utf8')
    print(json.dumps({r['gcm']:{k:r[k] for k in ['nearest_ground_minus_marker_m','terrain_minus_marker_m','accepted_independent_control']} for r in rows},indent=2))


if __name__=='__main__':main()
