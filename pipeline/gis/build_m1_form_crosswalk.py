"""Link M1 form groups to actual source meshes and named review views.

File evidence only. An export entry does not prove live or packaged acceptance.
"""
import json
import sys
from pathlib import Path
from collections import defaultdict
from build_public_space_meshes import ROOT, digest, save

PACKAGES=[
 'manifests/cedar-arch-blockout.json','manifests/west-landmark-blockouts.json',
 'manifests/siwash-approach-blockout.json','manifests/named-building-blockouts.json',
 'manifests/named-feature-blockouts.json','manifests/named-waterfront-blockouts.json',
 'manifests/harbour-interior-building-blockouts.json','manifests/lagoon-structure-blockouts.json',
 'manifests/route-sculpture-blockouts.json','manifests/air-india-blockout.json',
 'manifests/railway-structure-blockouts.json','manifests/nature-house-threshold.json',
 'manifests/lumberman-facility-blockouts.json','manifests/ground-space-blockouts.json',
 'manifests/totem-precinct-forms.json','manifests/site-completion-blockouts.json','manifests/waterpark-low-forms.json',
 'data/derived/public-spaces/public-space-meshes.json']
ALIASES={'SP_empress_figurehead':['SP_empress_japan'],'SP_second_beach':['SP_second_pool']}
VIEWS={
 'M1-F01':['public_lumberman_grounds','lumberman_lower_south'],
 'M1-F02':['hollow_tree','siwash_lookout'],
 'M1-F03':['public_brockton_grounds','public_totem_court'],
 'M1-F04':['sculpture_empress_japan','sculpture_girl_wetsuit','sculpture_harry_jerome','sculpture_shore_to_shore'],
 'M1-F05':['public_lumberman_grounds','lumberman_lower_north'],
 'M1-F06':['third_beach_building','third_beach_roof','second_pool','air_india'],
 'M1-F07':['nature_house_upper','nature_house_lower','jubilee'],
 'M1-F08':['public_south_grounds','ceperley_approach'],
 'M1-F09':['public_pavilion'],
 'M1-F10':['railway_station','railway_cafe','cob_house'],
 'M1-F11':['harbour_deadman'],
 'M1-F12':['skyline_coal_harbour','skyline_canada_place','skyline_english_bay','northshore_seaspan','northshore_vancouverwharves','northshore_g3']}
REMAINING={
 'M1-F01':['Confirm the fourth horizontal arch member against an adequate close source; the three-log mass is not a four-member completion claim.'],
 'M1-F02':['Source massing and Siwash connector exist. Review rider approach, Hollow Tree cavity and lookout contact in the live world.'],
 'M1-F03':['Totem package contains eight display-pole envelopes, Yelton and two People portals. Rear forms use bounded estimates; southwest portal and full court extent retain explicit source limits. Review visible M1 precinct layout.'],
 'M1-F04':['People/Yelton emitted meshes are linked. Fine carving, faces, paint and exact inscriptions remain later art. The unplaced southwest portal source gap stays explicit.'],
 'M1-F05':['Pad, internal boat ground patch and two measured coarse low forms exist. Review their placement and contact. Detailed play equipment and seasonal spray remain later scope.'],
 'M1-F06':['Named buildings/pool/memorial wall exist. Beach/backshore access and memorial plaza coverage require explicit inspection; aggregate coastal terrain is not proof of each ground form.'],
 'M1-F07':['Biofilter includes only terrain-backed wetland rim and a dated visible pool. The local water level uses an explicit lagoon proxy; no measured basin berm is claimed.'],
 'M1-F08':['Court/field surfaces and golf greens/tees exist. Source clubhouse footprint overlaps measured cover by86.1%; use that park mass, not a skyline duplicate. Review enclosure forms. Individual play equipment and sports simulation are later scope.'],
 'M1-F09':['Painter areas have finite source ground forms. Rock Garden links existing Pavilion-south terrain, canopy and garden context; individual rock/botanical detail remains later scope. Shakespeare and named site selection bounds are explicitly inferred. Review each site rather than count a hidden outline.'],
 'M1-F10':['Railway structures and at-grade tracks exist. Non-player bridge/tunnel tracks are later detail unless a critical visible gap remains. Salmon channel has source and inferred-under-canopy pieces; local pond water is unmeasured. Heron habitat links2022canopy around the City-identified ParkLane trees; no active nest or fauna simulation is claimed.'],
 'M1-F11':['Deadman roofs exist and public access remains excluded. Hallelujah links existing shore/grass/tree forms. Devonian has source ground/pond basin, and Port View has a source-traced paved projection plus existing terrain. Review named landform identity and sightlines.'],
 'M1-F12':['Current skyline and North Shore mesh lists exist. Required sightline and runtime checks remain separate; mesh count is not visual acceptance.']}
PROPOSED={
 'M1-F01':['cedar_arch_close'], 'M1-F03':['totem_main_court_rider'], 'M1-F04':['people_and_yelton'],
 'M1-F05':['waterpark_low_forms'], 'M1-F06':['third_beach_backshore','second_beach_backshore'],
 'M1-F07':['biofilter_ground'], 'M1-F08':['golf_greens_and_clubhouse','tennis_enclosures'],
 'M1-F09':['community_garden_ground','rose_garden_ground','greig_ground','rock_garden_ground','painters_areas'],
 'M1-F10':['rail_ground_and_bridge','salmon_channel','heron_habitat'],
 'M1-F11':['hallelujah_point','devonian_entrance','port_view']}


def main():
    inputs=[];by_feature=defaultdict(list);packages=[]
    for relative in PACKAGES+['manifests/skyline-blockouts.json','manifests/northshore-blockouts.json']:
        p=ROOT/relative
        if not p.exists():continue
        s=json.loads(p.read_text(encoding='utf8'));inputs.append({'path':relative,'sha256':digest(p)})
        rows=s.get('assets',s.get('meshes',[]))
        pack=[]
        for row in rows:
            path=row.get('mesh_path',row.get('path'))
            if not path:continue
            mesh=ROOT/path
            item=dict(name=row['name'],path=path,sha256=row['sha256'],source_manifest=relative,
                source_feature_id=row.get('feature_id'),component_id=row.get('component_id'),
                file_exists=mesh.exists(),source_hash_matches=mesh.exists() and digest(mesh)==row['sha256'])
            if row.get('feature_id'):by_feature[row['feature_id']].append(item)
            pack.append(item)
        packages.append({'manifest':relative,'meshes':pack})
    inventory_path=ROOT/'manifests/critical-features.json'
    views_path=ROOT/'manifests/m1-inspection-views.json'
    export_path=ROOT/'manifests/blender-export.json'
    inventory=json.loads(inventory_path.read_text(encoding='utf8'))
    views=json.loads(views_path.read_text(encoding='utf8'))['views']
    export=json.loads(export_path.read_text(encoding='utf8'))
    final_export='--final-export'in sys.argv
    exported={r['name'] for r in export['assets']} if final_export else set()
    links_path=ROOT/'manifests/m1-existing-site-linkage.json'
    links=json.loads(links_path.read_text(encoding='utf8'))['links'] if links_path.exists()else[]
    if links_path.exists():inputs.append({'path':links_path.relative_to(ROOT).as_posix(),'sha256':digest(links_path)})
    groups=[]
    for group in inventory['m1_remaining_form_groups']:
        features=[]
        for fid in group['feature_ids']:
            meshes=[]
            for alias in [fid]+ALIASES.get(fid,[]):meshes.extend(by_feature[alias])
            existing=[r for r in links if r['feature_id']==fid]
            features.append(dict(feature_id=fid,source_feature_aliases=ALIASES.get(fid,[]),meshes=meshes,existing_geometry_links=existing,
                generated_mesh_count=len(meshes),export_manifest_name_matches=[m['name'] for m in meshes if m['name']in exported],
                status='source_geometry_available_inspection_pending' if meshes else 'existing_source_geometry_linked_review_pending' if existing else 'no_emitted_feature_mesh_found',
                name_match_is_current_geometry_validation=False))
        if group['id']=='M1-F05':
            features.append(dict(feature_id='SP_lumberman_washrooms',relation='Separate below-road facilities, not splash equipment',
                meshes=by_feature['SP_lumberman_washrooms'],generated_mesh_count=len(by_feature['SP_lumberman_washrooms']),
                status='source_geometry_available_inspection_pending'))
        distant=[p for p in packages if p['manifest']in ['manifests/skyline-blockouts.json','manifests/northshore-blockouts.json']] if group['id']=='M1-F12' else []
        groups.append(dict(id=group['id'],name=group['name'],required_task=group['task'],features=features,distant_packages=distant,
            existing_view_ids=[v for v in VIEWS[group['id']] if v in views],
            proposed_view_ids_not_yet_defined=[v for v in PROPOSED.get(group['id'],[]) if v not in views],
            outstanding=REMAINING[group['id']],completeness_accepted=False,interactive_acceptance='not established by this file audit'))
    for p in [inventory_path,views_path,export_path,ROOT/'manifests/m1-reference-period.json']:inputs.append({'path':p.relative_to(ROOT).as_posix(),'sha256':digest(p)})
    authored_deltas=[]
    seam_path=ROOT/'evidence/blender-pavement-closing-seam-support.json'
    if seam_path.exists():
        seam=json.loads(seam_path.read_text(encoding='utf8'))
        inputs.append(dict(path=seam_path.relative_to(ROOT).as_posix(),sha256=digest(seam_path)))
        authored_deltas.append(dict(mesh=seam['mesh'],evidence=seam_path.relative_to(ROOT).as_posix(),
            appended_vertices=seam['appended_vertices'],appended_triangles=seam['appended_triangles'],
            source_npz_unchanged=seam['source_npz_unchanged'],source_controls_unchanged=seam['source_controls_unchanged'],
            export_manifest_name_match=seam['mesh']in exported,
            acceptance='Recorded live Blender construction only; current Unreal and normal-controller repeats remain separate.'))
    result=dict(schema_version=1,review_date='2026-09-27',scope='Finite source-to-form and review-view crosswalk; no app tests',
        inputs=inputs,export_snapshot_asset_count=len(export['assets']) if final_export else None,export_snapshot_is_live_blender_count=False,
        export_comparison='Requested final-export file comparison; not app acceptance'if final_export else'Withheld while root export changes. Repeat with --final-export after freeze.',
        standalone_snapshot='The v27 1159-asset package is sealed in evidence/build-m1-v27-provenance.json with the source-bundle companion audit. Fixed collision transfer and local Lumberman repeat pass; the full circuit is running and final acceptance remains open. The older 288-asset world is historical.',
        authored_export_deltas=authored_deltas,
        accepted_independent_controls=0,absolute_accuracy='Unverified under user-approved M1 accuracy limits; see plan section 13.7 and M1-MEASUREMENT-EXCEPTIONS.md',
        forest_reference_date='M1 measured 2022 baseline under documented planning amendment; current condition unverified; all 10 treatment flags retained; see manifests/m1-reference-period.json.',
        groups=groups,full_m1_complete=False)
    save(ROOT/'manifests/m1-form-group-crosswalk.json',result)
    lines=['# M1 source-to-form crosswalk, 27 September 2026','',
        'This is a file audit. It is not a live Blender, engine or packaged-build acceptance. Generated mesh names are linked below; the JSON file contains each exact mesh path/hash and source feature ID.', '',
        (f'The requested export-manifest comparison contains {len(export["assets"])} assets.'if final_export else'Export counts and name comparisons are withheld while integration changes. Repeat with `--final-export` after the final export.')+' A matching name does not prove that the source geometry is the same as the live scene. The v27 package and source bundle are verified and the local Lumberman repeat passes, but the full circuit and final runtime acceptance remain open. The old 288-asset standalone is historical. No runtime or M1 acceptance is claimed.', '',
        'The v26 closing-seam change adds five vertices and four triangles to the existing `SM_PavementSupport_049` object. Its original NPZ stays unchanged. The exact authored delta, source hashes and helper are recorded in `evidence/blender-pavement-closing-seam-support.json` and `docs/PAVEMENT-CLOSING-SEAM-SUPPORT.md`. This does not add an asset or change the feature-group counts.', '',
        '| Group | Actual feature/mesh coverage | Existing view IDs | Remaining finite work |','|---|---|---|---|']
    for g in groups:
        desc='; '.join(f"{f['feature_id']}: {f['generated_mesh_count']}"+(' + existing land/cover links'if f.get('existing_geometry_links')else'') for f in g['features'])
        if g['distant_packages']:desc='; '.join(f"{p['manifest']}: {len(p['meshes'])}"for p in g['distant_packages'])
        lines.append(f"| {g['id']} {g['name']} | {desc} | {', '.join(g['existing_view_ids'])} | {' '.join(g['outstanding'])} |")
    lines += ['', 'Zero accepted independent survey controls remain recorded. The user accepted M1 with explicit accuracy limits; the original absolute-accuracy target is not certified. Visible placement defects still require correction. The reference-period planning amendment retains the measured 2022 canopy baseline and all 10 treatment flags. It does not assert current-forest accuracy or an accepted user answer; see M1-REFERENCE-PERIOD-AMENDMENT.md.', '',
        'Elevated public-space review cameras show layout; they do not replace rider-height inspection. Proposed views in the JSON are requirements, not saved cameras or completed evidence. Hidden boundaries and source-only bridge/tunnel lines never count as rendered surfaces.', '',
        'After later package changes or export, rerun `pipeline/gis/build_m1_form_crosswalk.py`. Keep the old crosswalk hash with milestone evidence. The feature inventory remains owned by the named-feature authoring stage.']
    (ROOT/'docs/M1-FORM-GROUP-CROSSWALK.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps({'groups':len(groups),'export_snapshot_asset_count':len(export['assets']) if final_export else None,
        'features_without_emitted_or_existing_geometry':[f['feature_id'] for g in groups for f in g['features'] if not f['generated_mesh_count'] and not f.get('existing_geometry_links')]}))


if __name__=='__main__':main()
