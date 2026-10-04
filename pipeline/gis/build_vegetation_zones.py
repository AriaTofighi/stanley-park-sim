"""Clip licensed BC VRI polygons and assign repeatable canopy group proxies.

VRI reference/interpretation/projected dates are separate. No 2026 forest
treatment is inferred, and no cluster is represented as a surveyed tree.
"""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import shapely
from shapely.affinity import translate
from shapely.geometry import shape, mapping, Point
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[2]
SPECIES = {'HW': 'Western hemlock', 'FDC': 'Coast Douglas-fir',
           'CW': 'Western redcedar', 'DR': 'Red alder', 'MB': 'Bigleaf maple',
           'BA': 'Amabilis fir', 'SS': 'Sitka spruce', 'UNKNOWN': 'Unresolved canopy group'}
COLORS = {'TC': '#326445', 'TM': '#74a05a', 'TB': '#b1c65c', 'ST': '#a780af',
          'HG': '#d8cb8d', 'OC': '#8ec5d5', 'LA': '#729eb6', 'UR': '#999999',
          'UNKNOWN': '#dadada'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    raw = ROOT / 'data/raw/forest/bc-vri-park-query.json'
    data = json.loads(raw.read_text())
    if data['numberMatched'] != len(data['features']):
        raise RuntimeError('Incomplete forest query; do not use truncated coverage')
    if not data['crs']['properties']['name'].endswith('::3157'):
        raise RuntimeError('Unexpected forest coordinate reference')
    metadata_file = ROOT / 'data/raw/forest/bc-vri-metadata.json'
    metadata = json.loads(metadata_file.read_text())['result']
    if metadata['license_title'] != 'Open Government Licence - British Columbia':
        raise RuntimeError('Review forest data reuse rights before generation')
    origin = json.loads((ROOT / 'manifests/world-origin.json').read_text())
    boundary_data = json.loads((ROOT / 'data/derived/park_boundary_utm.geojson').read_text())
    boundary = shapely.union_all([shape(f['geometry']) for f in boundary_data['features']])
    polygons, features = [], []
    area = Counter()
    for feature in sorted(data['features'], key=lambda f: f['properties']['FEATURE_ID']):
        geom = shapely.make_valid(shape(feature['geometry'])).intersection(boundary)
        if geom.area <= 1:
            continue
        geom = translate(geom, -origin['easting'], -origin['northing'])
        props = feature['properties']
        species = []
        for i in range(1, 7):
            code, pct = props[f'SPECIES_CD_{i}'], props[f'SPECIES_PCT_{i}']
            if code and pct and pct > 0:
                if code not in SPECIES:
                    raise ValueError(f'Unreviewed species code: {code}')
                species.append(dict(code=code, name=SPECIES[code], percentage=pct))
        record = dict(id=f"VRI_{props['FEATURE_ID']}",
                      polygon_id=props['POLYGON_ID'],
                      primary_cover_code=props['LAND_COVER_CLASS_CD_1'] or 'UNKNOWN',
                      bclcs=[props[f'BCLCS_LEVEL_{i}'] for i in range(1, 6)],
                      species=species, reference_date=props['REFERENCE_DATE'],
                      interpretation_date=props['INTERPRETATION_DATE'],
                      projected_date=props['PROJECTED_DATE'],
                      area_m2=geom.area, accepted_2026_condition=False)
        polygons.append(geom)
        features.append(dict(type='Feature', properties=record, geometry=mapping(geom)))
        area[record['primary_cover_code']] += geom.area
    zone_file = ROOT / 'data/derived/vegetation-zones-local.geojson'
    zone_file.write_text(json.dumps(dict(type='FeatureCollection',
        coordinate_contract='Local metres, X east, Y north; see world-origin.json',
        features=features), indent=2) + '\n', encoding='utf8')
    tree = STRtree(polygons)
    cover_file = ROOT / 'data/derived/cover-blockout.json'
    cover = json.loads(cover_file.read_text())
    assignments, counts = [], Counter()
    for tile in cover['canopy']:
        tile_rows = []
        for cluster in tile['points']:
            x, y = cluster[:2]
            matches = sorted(tree.query(Point(x, y), predicate='intersects'))
            if len(matches) > 1:
                # No unrecorded winner for a polygon overlap.
                raise RuntimeError(f'Overlapping forest polygons at canopy cluster {x},{y}')
            zone = features[matches[0]]['properties'] if len(matches) else None
            code = 'UNKNOWN'
            if zone and zone['species']:
                choices = zone['species']
                weights = np.asarray([r['percentage'] for r in choices], dtype=float)
                key = f"{tile['tile']}:{x:.6f}:{y:.6f}:canopy-groups-v1".encode()
                sample = int.from_bytes(hashlib.sha256(key).digest()[:8], 'big') / 2**64
                index = min(np.searchsorted(np.cumsum(weights) / sum(weights), sample), len(choices) - 1)
                code = choices[index]['code']
            tile_rows.append(dict(x_m=x, y_m=y, species_group=code,
                                  zone_id=zone['id'] if zone else None))
            counts[code] += 1
        assignments.append(dict(tile=tile['tile'], clusters=tile_rows))
    assignment_file = ROOT / 'data/derived/canopy-zone-assignments.json'
    assignment_file.write_text(json.dumps(dict(
        schema_version=1, cover_sha256=digest(cover_file), zones_sha256=digest(zone_file),
        method='Deterministic hash choice from source polygon species percentages; cluster proxy, not individual-tree placement',
        assignments=assignments), indent=2) + '\n', encoding='utf8')
    union = shapely.union_all(polygons)
    record = dict(created_utc=datetime.now(timezone.utc).isoformat(),
        source_query=json.loads((ROOT / 'data/raw/forest/bc-vri-query-source.json').read_text())['url'],
        catalogue='https://catalogue.data.gov.bc.ca/dataset/2ebb35d8-c82f-4a17-9c96-612ac3532d55',
        title=metadata['title'], licence=metadata['license_title'], licence_url=metadata['license_url'],
        attribution='Contains information licensed under the Open Government Licence - British Columbia.',
        coverage='Stanley Park; source polygons clipped to the City park boundary',
        species_code_reference='https://www2.gov.bc.ca/gov/content/industry/forestry/managing-our-forest-resources/tree-seed/tree-seed-centre/seed-testing/codes',
        cover_code_reference='https://www2.gov.bc.ca/assets/gov/farming-natural-resources-and-industry/forestry/stewardship/forest-analysis-inventory/forest-cover-inventories/photo-interpretation/standards/vri_photo_interpretation_procedures_version_38.pdf',
        input_files=[dict(path=p.relative_to(ROOT).as_posix(), sha256=digest(p)) for p in [raw, metadata_file, cover_file]],
        output_files=[dict(path=p.relative_to(ROOT).as_posix(), sha256=digest(p)) for p in [zone_file, assignment_file]],
        polygons=len(features), park_coverage_fraction=union.area / boundary.area,
        polygon_overlap_m2=sum(p.area for p in polygons) - union.area,
        area_by_primary_cover_ha={k: v / 10000 for k, v in area.items()},
        canopy_clusters_by_group=dict(counts), species=SPECIES,
        accepted_2026_condition=False, accepted_near_route_geometry=False,
        limits=['Projected 2025 growth values are not 2025 field measurements.',
                'Reference and interpretation dates vary by polygon; retain them in the output.',
                'No new tree removal or regeneration is inferred from the source.',
                'Canopy cluster heights/centres remain the 2022 LiDAR values.',
                'Species assignment varies the blockout groups, not surveyed individual trees.',
                'Source boundaries do not establish a 2 m positional accuracy.'])
    (ROOT / 'manifests/vegetation-zones.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf8')
    fig, ax = plt.subplots(figsize=(10, 10), dpi=130)
    used = set()
    for geom, feature in zip(polygons, features):
        code = feature['properties']['primary_cover_code']; used.add(code)
        for part in geom.geoms if hasattr(geom, 'geoms') else [geom]:
            if part.geom_type != 'Polygon':
                continue
            ax.fill(*part.exterior.xy, color=COLORS.get(code, COLORS['UNKNOWN']), alpha=.85, linewidth=0)
            for hole in part.interiors:
                ax.fill(*hole.xy, color='white')
    route = np.asarray(json.loads((ROOT / 'data/derived/paved-circuit-runtime.json').read_text())['points_local_m'])
    ax.plot(route[:, 0], route[:, 1], color='black', linewidth=.6)
    ax.set(aspect='equal', xlabel='Local east (m)', ylabel='Local north (m)',
           title='BC VRI vegetation zones with the authored circuit\nDated inventory; 2026 changes remain unresolved')
    ax.legend(handles=[Patch(color=COLORS.get(c, COLORS['UNKNOWN']), label=c) for c in sorted(used)], loc='lower right')
    fig.tight_layout(); fig.savefig(ROOT / 'evidence/vegetation-zones-map.png')
    print(json.dumps({k: record[k] for k in ['polygons', 'park_coverage_fraction',
                                           'polygon_overlap_m2', 'canopy_clusters_by_group']}, indent=2))


if __name__ == '__main__':
    main()
