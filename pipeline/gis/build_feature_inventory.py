"""Turn the map and public-art register into a per-feature M1 work register.

An approximate map/registry point is not an accepted model location. Existing
unnamed roof masses do not satisfy a named landmark merely because they exist.
"""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
MAP_URL='https://vancouver.ca/files/cov/stanley-park-map-and-guide.pdf'
CITY_LANDMARKS='https://vancouver.ca/parks-recreation-culture/landmarks-in-stanley-park.aspx'
CITY_MONUMENTS='https://vancouver.ca/parks-recreation-culture/monuments-and-sculptures.aspx'

# Listed separately where one name describes a public space and an artwork.
# City art IDs link exact registry identity; no fuzzy name matching is used.
MAP_ITEMS=[
 ('air_force_garden','Air Force Garden of Remembrance','garden',None,''),
 ('air_india','Air India Memorial','memorial',None,''),
 ('beaver_lake','Beaver Lake','water',None,'SM_Water_BeaverLake'),
 ('biofiltration','Biofiltration Pond','wetland',None,''),
 ('brockton_light','Brockton Point Lighthouse','structure',None,'SM_Brockton_'),
 ('chief_undersea','Chief of the Undersea World','art','81',''),
 ('cob_house','Cob House','building',None,''),
 ('community_garden','Community Garden','garden',None,''),
 ('empress_japan','Empress of Japan Figurehead','art','98',''),
 ('girl_wetsuit','Girl in a Wetsuit Statue','art','97',''),
 ('harry_jerome','Harry Jerome Statue','art','162',''),
 ('heron_colony','Heron Colony','habitat',None,''),
 ('hollow_tree','Hollow Tree','natural_landmark',None,''),
 ('japanese_memorial','Japanese Canadian War Memorial','memorial','86',''),
 ('jubilee','Jubilee Fountain','structure','158',''),
 ('lord_stanley','Lord Stanley Statue','art','84',''),
 ('lumberman_arch',"Lumberman's Arch",'structure','99',''),
 ('nine_oclock',"Nine O'Clock Gun",'structure',None,''),
 ('painters_circle',"Painters' Circle",'public_space',None,''),
 ('port_view','Port of Vancouver Viewpoint','viewpoint',None,''),
 ('portrait_painters','Portrait Painters area','public_space',None,''),
 ('prospect_light','Prospect Point Lighthouse','structure',None,''),
 ('prospect_lookout','Prospect Point Lookout and Cafe','viewpoint',None,''),
 ('queen_victoria','Queen Victoria Memorial','memorial','82',''),
 ('restoration_donor','Restoration Donor Monument','memorial',None,''),
 ('robert_burns','Robert Burns Statue','art','83',''),
 ('rock_garden','Rock Garden','garden',None,''),
 ('rose_garden','Rose and Perennial Garden','garden',None,''),
 ('salmon_stream','Salmon Demonstration Stream','wetland',None,''),
 ('shakespeare','Shakespeare Memorial and Garden','garden','88',''),
 ('siwash','Siwash Rock','natural_landmark',None,'SM_SiwashRock_'),
 ('siwash_lookout','Siwash Rock Viewpoint (Old Searchlight)','viewpoint',None,''),
 ('pavilion','Stanley Park Pavilion','building',None,''),
 ('people_amongst','People Amongst the People','art','424',''),
 ('shore_to_shore','Shore to Shore','art','596',''),
 ('yelton_pole','Yelton Memorial Pole','art','563',''),
 ('totem_precinct','Totem Pole public space','public_space',None,''),
 ('greig_garden','Ted and Mary Greig Rhododendron Garden','garden',None,''),
 ('cricket_pavilion','Brockton Cricket Pavilion and fields','building',None,''),
 ('lawn_bowling','Stanley Park Lawn Bowling Club','public_space',None,''),
 ('rowing_club','Vancouver Rowing Club','building',None,''),
 ('yacht_club','Royal Vancouver Yacht Club','building',None,''),
 ('aquarium','Vancouver Aquarium exterior','building',None,''),
 ('malkin_bowl','Malkin Bowl','structure',None,''),
 ('water_park','Variety Kids Water Park','public_space',None,''),
 ('second_pool','Second Beach Swimming Pool','structure',None,''),
 ('ceperley','Ceperley Meadow, field and playground','public_space',None,''),
 ('tennis','English Bay and Lagoon Drive tennis courts','public_space',None,''),
 ('pitch_putt','Stanley Park Pitch and Putt','public_space',None,''),
 ('teahouse','Ferguson Point and Teahouse','building',None,''),
 ('nature_house','Lost Lagoon Nature House and viewing plaza','building',None,''),
 ('lost_lagoon','Lost Lagoon','water',None,'SM_Water_LostLagoon'),
 ('train','Stanley Park miniature railway exterior','structure',None,''),
 ('third_beach','Third Beach and facilities','shore_space',None,''),
 ('second_beach','Second Beach and facilities','shore_space',None,''),
 ('deadman','Deadman Island public-view silhouette and access boundary','context',None,''),
 ('lions_gate','Lions Gate Bridge and visible approaches','context',None,'SM_LionsGate_'),
 ('hallelujah','Hallelujah Point','shore_space',None,''),
 ('devonian','Devonian Harbour Park entrance connection','entry',None,''),
]


def main():
    registry=json.loads((ROOT/'data/derived/landmark-registry.json').read_text(encoding='utf8'))['features']
    arts={r['id']:r for r in registry}
    export=json.loads((ROOT/'manifests/blender-export.json').read_text(encoding='utf8'))
    assets=[r['name'] for r in export['assets']]
    rows=[];referenced_art=set()
    for slug,name,kind,art_id,prefix in MAP_ITEMS:
        art=arts[art_id] if art_id else None
        if art:referenced_art.add(art_id)
        matched=[n for n in assets if prefix and n.startswith(prefix)]
        row=dict(id='SP_'+slug,name=name,kind=kind,critical=True,
            critical_reason='Official map feature, route landmark, access feature, or named public space',
            sources=[dict(url=MAP_URL,printed_revision='2026-05-19',page=2,rights='Reference only')],
            art_registry_id=art_id,position_local_m=art['position_local_m'] if art else None,
            position_status='Approximate registry point; not accepted' if art else 'Individual placement work required',
            source_status=art['status'] if art else 'Listed on the 2026 City map',
            linked_meshes=matched,model_status='Blockout exists; source acceptance open' if matched else 'Individual blockout not complete',
            dimension_status='See individual measured-source manifests; unresolved parts remain flagged' if matched else 'Measurements and individual references required',
            acceptance=False,owner='Environment artist; GIS review for placement',
            next_action='Compare the individual form, placement and sightlines with dated references')
        if art:
            row['sources'].append(dict(url=art['url'],rights=art['reproduction_rights'],
                                       source_id='city_public_art_'+art_id))
        if slug=='jubilee':
            row['condition_override']='Under restoration on the 2026 map. Do not infer an operating fountain from registry In place.'
        if slug=='deadman':row['access']='Closed to the public on the 2026 map; no public navigation edge'
        if slug=='beaver_lake':row['access']='Walking loop; no inferred cycle permission from universal access'
        rows.append(row)
    for art_id,art in arts.items():
        if art_id in referenced_art:continue
        removed=art['status']=='No longer in place'
        rows.append(dict(id='ART_'+art_id,name=art['name'],kind='art',critical=not removed,
            critical_reason='City public-art inventory; current condition must be confirmed',
            sources=[dict(url=art['url'],rights=art['reproduction_rights'])],
            art_registry_id=art_id,position_local_m=art['position_local_m'],
            position_status='Approximate registry point; not accepted',source_status=art['status'],
            linked_meshes=[],model_status='Excluded from present-day placement pending contrary evidence' if removed else 'Individual blockout not complete',
            dimension_status='Measurements and individual references required',acceptance=False,
            owner='Environment artist; artwork rights review',
            next_action='Retain the exclusion record' if removed else 'Confirm physical presence and obtain model references'))
    ids=[r['id'] for r in rows]
    if len(ids)!=len(set(ids)):raise RuntimeError('Duplicate feature ID')
    record=dict(schema_version=1,target_period='September 2026',
        scope='Named feature inventory seeded from the 2026 City map and complete saved park public-art extract',
        sources_cross_checked=[MAP_URL,CITY_LANDMARKS,CITY_MONUMENTS],
        inventory_complete=False,inventory_limit='Route signs, every junction, repeated infrastructure types and all distant skyline forms require separate coverage records.',
        features=rows,
        totals=dict(features=len(rows),critical=sum(r['critical'] for r in rows),
            linked_blockout_features=sum(bool(r['linked_meshes']) for r in rows),accepted_features=0),
        source_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in [
            'data/routes/raw/official-park-map-2026.pdf','data/derived/landmark-registry.json']})
    (ROOT/'manifests/critical-features.json').write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    lines=['# Named feature work register','',
        'This register checks named coverage. A linked mesh does not prove accuracy. M1 remains open.', '',
        '| Feature | Source state | Individual blockout |', '|---|---|---|']
    for row in rows:lines.append(f"| {row['id']}: {row['name']} | {row.get('condition_override',row['source_status'])} | {row['model_status']} |")
    lines+=['','See `manifests/critical-features.json` for source URLs, rights, owners and next actions.',
            'Unnamed survey roof masses do not count as completed named buildings. Distant terrain does not count as a finished city skyline.','']
    (ROOT/'docs/FEATURE-WORK-REGISTER.md').write_text('\n'.join(lines),encoding='utf8')
    print(json.dumps(record['totals'],indent=2))


if __name__=='__main__':main()
