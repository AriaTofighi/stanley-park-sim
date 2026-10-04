"""Link individually reviewed named geometry; do not grant runtime acceptance."""
import json
from pathlib import Path
import numpy as np
from acquire_sources import digest, save_json

ROOT=Path(__file__).resolve().parents[2]
PACKAGES=['named-feature-blockouts','named-building-blockouts','named-waterfront-blockouts','west-landmark-blockouts','cedar-arch-blockout','siwash-approach-blockout',
          'harbour-interior-building-blockouts','route-sculpture-blockouts','lagoon-structure-blockouts','nature-house-threshold','air-india-blockout','railway-structure-blockouts','totem-precinct-forms']
MAP='https://vancouver.ca/files/cov/stanley-park-map-and-guide.pdf'
LANDMARKS='https://vancouver.ca/parks-recreation-culture/landmarks-in-stanley-park.aspx'

# These are finite M1 ground-form/identity tasks. Detailed surfaces and sculpture
# artwork remain later work. Existing aggregate terrain does not prove these.
GROUPS=[
 ('M1-F01','Lumberman cedar arch',['SP_lumberman_arch'],'Locate the actual cedar members under the canopy using close ground reference plus the retained survey crop; fit the four-member form. The concession is a separate building.'),
 ('M1-F02','Hollow Tree and Siwash lookout',['SP_hollow_tree','SP_siwash_lookout'],'Locate and mass the hollow stump and the separate old-searchlight lookout platform. Do not substitute ordinary trees or Siwash Rock itself.'),
 ('M1-F03','Brockton public courts and fields',['SP_totem_precinct','SP_cricket_pavilion'],'Trace the Totem Pole court, visitor approaches and two named field outlines. Building roofs exist; court/field geometry and measured pole silhouettes remain separate.'),
 ('M1-F04','Route sculpture silhouettes',['SP_empress_japan','SP_girl_wetsuit','SP_harry_jerome','SP_shore_to_shore','SP_people_amongst','SP_yelton_pole'],'Confirm each current position against independent ground imagery/survey before a simple silhouette. Defer faces, carving, inscriptions, patina and exact artwork to M4.'),
 ('M1-F05','North-side water park',['SP_water_park'],'Trace the hard-surface play area and principal low structures; retain its separate relation to the cedar arch and concession.'),
 ('M1-F06','West coast beach spaces',['SP_third_beach','SP_second_beach','SP_air_india'],'Identify Third Beach facilities individually, trace both beach/backshore access spaces and the memorial plaza. Existing terrain is only aggregate coast geometry.'),
 ('M1-F07','Lost Lagoon public edge',['SP_nature_house','SP_jubilee','SP_biofiltration'],'Identify Nature House and its plaza, the fountain support/island under restoration, and the biofiltration pond envelope. Do not render an operating fountain from old photos.'),
 ('M1-F08','South park recreation grounds',['SP_ceperley','SP_tennis','SP_pitch_putt','SP_lawn_bowling'],'Trace the meadow, court enclosures, bowling green and golf open-space boundaries; identify visible clubhouse roof forms. Playground equipment and sport simulation are later scope.'),
 ('M1-F09','Gardens and public clearings',['SP_air_force_garden','SP_community_garden','SP_painters_circle','SP_portrait_painters','SP_rock_garden','SP_rose_garden','SP_shakespeare','SP_greig_garden'],'Trace named ground spaces and main paths from imagery and official-map context. Individual flowers, beds and statuary detail belong to M4.'),
 ('M1-F10','Interior visitor facilities and habitat',['SP_cob_house','SP_train','SP_salmon_stream','SP_heron_colony'],'Identify Cob House and railway exterior buildings, railway clearing/track envelope, stream and colony area. Do not create arbitrary buildings from map label positions.'),
 ('M1-F11','Harbour edge and entrances',['SP_deadman','SP_hallelujah','SP_devonian','SP_port_view'],'Identify Deadman Island roof silhouettes and shore/access boundary, and trace named viewpoint/entrance spaces. Deadman remains closed to public traversal.'),
 ('M1-F12','Distant built silhouettes',[],'Measure a finite set of visible Downtown/Coal Harbour towers, Canada Place/harbour structures and North Shore port forms from each critical route viewpoint. Regional terrain exists, but no named city skyline assets are exported.'),
]

def main():
    path=ROOT/'manifests/critical-features.json';record=json.loads(path.read_text(encoding='utf8'));rows={x['id']:x for x in record['features']}
    for row in rows.values():
        row['sources']=[x for x in row.get('sources',[]) if x.get('url')!='https://vancouver.ca/parks-recreation-culture/totem-poles.aspx']
    if 'SP_lumberman_concession' not in rows:
        entry=dict(id='SP_lumberman_concession',name="Lumberman's Arch concession",kind='building',critical=True,
            critical_reason='Individually identified visitor facility beside water park; separate from cedar arch',sources=[dict(url=MAP,printed_revision='2026-05-19',page=2,rights='Reference only')],
            position_local_m=None,position_status='Named survey roof location',linked_meshes=[],acceptance=False,owner='Environment artist; GIS review')
        record['features'].append(entry);rows[entry['id']]=entry
    grouped={}
    for package in PACKAGES:
        manifest=ROOT/f'manifests/{package}.json';data=json.loads(manifest.read_text())
        for feature in data['features']:
            fid='SP_prospect_lookout' if feature['id']=='SP_prospect_cafe' else feature['id']
            entry=grouped.setdefault(fid,dict(features=[],assets=[],manifests=[]))
            entry['features'].append(feature);entry['assets'].extend(x for x in data['assets'] if x['feature_id']==feature['id'])
            entry['manifests'].append(dict(path=manifest.relative_to(ROOT).as_posix(),sha256=digest(manifest)))
    for fid,values in grouped.items():
        row=rows[fid];assets=values['assets'];features=values['features'];positions=[]
        for feature in features:
            m=feature['measured'];centre=m.get('centre_local_m',m.get('centroid_local_m'))
            if centre is None:
                these=[x for x in assets if x['feature_id']==feature['id']]
                lo=np.min([x['bounds_min_m'] for x in these],axis=0);hi=np.max([x['bounds_max_m'] for x in these],axis=0);centre=((lo+hi)/2)[:2].tolist()
            positions.append(dict(component=feature['id'],local_xy_m=centre,meaning='Survey/model group centre; not a geodetic control'))
            existing={x.get('url',x.get('path')) for x in row['sources']}
            for source in feature['sources']:
                if source in existing:continue
                row['sources'].append(dict(**({'url':source} if source.startswith('http') else {'path':source}),
                    rights='Reference only; do not distribute page/photo content' if source.startswith('http') else 'See linked source record; City derivatives use OGL-Vancouver',accessed='2026-09-27'))
        row.update(linked_meshes=[x['name'] for x in assets],position_local_m=positions[0]['local_xy_m'],component_positions=positions,
            position_status='Individually identified source form in the shared local coordinate system; absolute accuracy remains unverified',
            source_status='City 2022 survey/imagery cross-checked against official 2026 map and individual identity references',
            model_status='M1 measured massing generated; Blender and runtime inspection remain separate acceptance steps',
            dimension_status='Measured roof/outline data and explicit estimates in linked manifests; M4 facade/art detail unfinished',
            named_source_manifests=values['manifests'],m1_geometry_available=True,acceptance=False,runtime_inspection_accepted=False,
            m1_limits=[x['limits'] for x in features],next_action='Import stable packages; inspect form, source alignment and public-path contact; retain any failures')
    coastal=json.loads((ROOT/'manifests/coastal-landmark-blockouts.json').read_text())['landmarks']
    for source,fid in zip(coastal,['SP_siwash','SP_brockton_light']):
        row=rows[fid];row['position_local_m']=source['centre_local_m'];row['position_status']='City 2022 source-fit centre; absolute accuracy unverified'
        row['named_source_manifests']=[dict(path='manifests/coastal-landmark-blockouts.json',sha256=digest(ROOT/'manifests/coastal-landmark-blockouts.json'))];row['m1_geometry_available']=True
    # Link old water objects to their specific source/level records, not merely
    # to a generic terrain tile or an unreviewed roof aggregate.
    export=json.loads((ROOT/'manifests/blender-export.json').read_text())['assets'];byname={x['name']:x for x in export}
    for fid,name in [('SP_lost_lagoon','SM_Water_LostLagoon'),('SP_beaver_lake','SM_Water_BeaverLake')]:
        row=rows[fid];a=byname[name];lo=np.array(a['bounds_min_cm']);hi=np.array(a['bounds_max_cm']);centre=(lo+hi)/200
        row['position_local_m']=[float(centre[1]),float(centre[0])];row['position_status']='Model bounds centre; shoreline is generalized BC FWA geometry'
        row['named_source_manifests']=[dict(path=p,sha256=digest(ROOT/p)) for p in ['manifests/water-references.json','manifests/water-levels.json']];row['m1_geometry_available']=True
    if 'SP_lumberman_arch' not in grouped:
        rows['SP_lumberman_arch']['model_status']='Cedar arch not modeled; source location remains unresolved under canopy. Concession does not satisfy this feature.'
        rows['SP_lumberman_arch']['next_action']='Use retained named-lumberman-arch survey crop and City cedar-arch references to identify the actual four-member assembly.'
    else:
        rows['SP_lumberman_arch']['next_action']='Inspect the three observed fitted log axes and estimated radii/mound. The second horizontal member named in the 2019 memo remains unresolved; do not count it as complete.'
    for group,title,ids,task in GROUPS:
        for fid in ids:
            row=rows[fid];row['m1_remaining_group']=group;row['m1_remaining_task']=task
    for row in record['features']:
        row.setdefault('m1_geometry_available',bool(row.get('linked_meshes')))
        if row.get('kind')=='art' and 'm1_remaining_group' not in row and row.get('critical',True):
            row['m1_scope']='Identity/source register retained; detailed sculpture and exact artwork production belong to M4. No fabricated marker model.'
        if row.get('kind')=='memorial' and 'm1_remaining_group' not in row:
            row['m1_scope']='Memorial site identity retained. Inspectable plaza/base massing needed if it affects a public path or a required viewpoint; inscriptions/sculpture detail belong to M4.'
    record['m1_named_geometry_review']='All current map/art records classified; important missing ground forms remain explicit. Linked assets do not imply M1 acceptance.'
    record['inventory_complete']=False
    record['inventory_limit']='Named structure and artwork massing is source linked below. Ground spaces, skyline, gates, facilities and route signs have separate registers. See manifests/m1-form-group-crosswalk.json for the current cross-package coverage; named assets alone do not close a whole form group.'
    record['m1_remaining_form_groups']=[dict(id=i,name=n,feature_ids=ids,task=t,
        status='See current cross-package review in manifests/m1-form-group-crosswalk.json; no acceptance granted by this inventory script',
        named_geometry_features=[fid for fid in ids if fid in grouped]) for i,n,ids,t in GROUPS]
    record['finite_named_form_gaps']=[
        dict(feature='SP_totem_precinct',remaining='Eight display envelopes plus separate Yelton envelope exist. Two rear forms have estimated dimensions and 2 m position/2.5 m height working uncertainty. Some name-to-pole assignments remain provisional.',next_action='Inspect all nine envelopes, retain bounded estimates, and resolve exact carved shapes and identities during detailed art production.'),
        dict(feature='SP_people_amongst',remaining='Southern portal is measured and northern portal is a bounded ortho/photo setting estimate. Southwest portal remains unplaced. Candidate boxes [1543,-398,1564,-380] and [1564,-388,1584,-368] fit the official southwest-of-path relation but canopy prevents a unique match.',next_action='Retain this missing visible form explicitly. A ground view showing the portal, gift shop and path bend together, or a post-centre site plan, is needed for a supported placement. No arbitrary gate is inserted.'),
        dict(feature='SP_air_india',remaining='Main curved wall and low name/seat arc exist. Seat ends, timber split and width are bounded estimates. Associated paving stones and inscriptions remain unfinished.',next_action='Inspect source alignment and collision; exact lettering, masonry and timber slats belong to detailed production.'),
        dict(feature='SP_nature_house',remaining='v23 lower-front terrain check passed; root reported full facade visible without spikes. Rear threshold numerically joins the actual terrain at a 0.025 m step. Side railing extent and runtime access remain unverified.',next_action='Inspect updated upper threshold and runtime contact. Side edges are retaining edges, not ramps; no accessibility-grade certification is claimed.'),
        dict(feature='SP_lumberman_arch',remaining='Three observed log axes are modeled; one additional horizontal member described in the memo is unresolved.',next_action='Keep the partial source statement visible; obtain a matching view before adding another log.'),
    ]
    for fid in ['SP_totem_precinct','SP_people_amongst','SP_air_india']:
        rows[fid]['model_status']='M1 massing contains measured and explicitly bounded estimated components; see component methods and unresolved forms in linked manifests'
        rows[fid]['position_status']='Mixed source-fit and estimated component positions; group centre is not a survey control'
    record['totals']=dict(features=len(record['features']),critical=sum(x.get('critical',False) for x in record['features']),
        linked_blockout_features=sum(bool(x['linked_meshes']) for x in record['features']),accepted_features=sum(bool(x['acceptance']) for x in record['features']))
    save_json(path,record)
    output=dict(scope='Named blockout coverage review; no Blender/application acceptance',inventory_sha256=digest(path),
        individually_linked_packages=list(grouped),remaining_form_groups=record['m1_remaining_form_groups'],
        m4_detail='Artwork faces/carving/inscriptions, exact tree bark, facade openings/material detail, furniture, planting species and water-play equipment',
        uncounted=['Unnamed SM_BuildingMass tile aggregates','Regional terrain as a substitute for buildings','Map label centres as exact building placements'])
    save_json(ROOT/'evidence/named-feature-inventory-audit.json',output)
    print(json.dumps(record['totals']))

if __name__=='__main__':main()
