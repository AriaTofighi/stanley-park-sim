"""Acquire bounded public skyline references; do not infer current geometry yet."""
from datetime import datetime, timezone
import urllib.parse

from acquire_sources import API, ROOT, download, get_json, save_json

OUT = ROOT / 'data/raw/skyline'


def main():
    records = []
    dataset = 'building-footprints-2009'
    metadata, source = get_json(API + dataset, OUT / 'city-building-2009-metadata.json')
    records.append(source)
    # Only Downtown/West End buildings visible from park-side reference views.
    where = "within(geo_point_2d, GEOM'POLYGON((-123.150 49.274,-123.097 49.274,-123.097 49.299,-123.150 49.299,-123.150 49.274))')"
    url = API + dataset + '/exports/geojson?' + urllib.parse.urlencode({'where': where})
    records.append(download(url, OUT / 'city-building-2009-downtown.geojson', max_bytes=20000000))
    # The single downtown box exceeded the OSM map endpoint's node limit (400).
    # Use four bounded requests and preserve every original response separately.
    for index, bbox in enumerate([
        '-123.150,49.274,-123.124,49.287', '-123.124,49.274,-123.097,49.287',
        '-123.150,49.287,-123.124,49.299', '-123.124,49.287,-123.097,49.299'
    ]):
        url = 'https://api.openstreetmap.org/api/0.6/map?bbox=' + bbox
        records.append(download(url, OUT / f'osm-downtown-{index}-20260927.osm', max_bytes=20000000))
    save_json(ROOT / 'manifests/skyline-source-acquisition.json', dict(
        acquired_utc=datetime.now(timezone.utc).isoformat(), files=records,
        sources=[dict(url='https://opendata.vancouver.ca/explore/dataset/building-footprints-2009/',
                      capture='2009', licence='Open Government Licence - Vancouver',
                      use='Historic distant massing reference; check demolition and later towers individually'),
                 dict(url='https://www.openstreetmap.org/copyright', capture='API snapshot 2026-09-27; feature dates vary',
                      licence='ODbL-1.0', use='Current feature names, footprints and tagged dimensions; not survey certification')],
        accepted=False, limitations='Acquisition only. Do not import historical buildings without a current identity/change check.'))
    print('Saved bounded skyline source files and licence register')


if __name__ == '__main__':
    main()
