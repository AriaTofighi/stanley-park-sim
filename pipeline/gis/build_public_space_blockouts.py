"""Export named M1 ground-space source polygons; do not alter terrain or run apps.

OSM geometry remains a separately attributed source layer. The authoring layer
adds identity/material intent, never surveyed accuracy or public-access claims.
"""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter

from pyproj import Transformer
from shapely.geometry import Polygon, LineString, mapping

ROOT = Path(__file__).resolve().parents[2]
RAW = "data/routes/raw/osm/park-map-20260927.osm"
OUT = ROOT/"data/derived/public-spaces"
SELECTION = []


def add(way, component, name, feature, group, material, mode="surface_patch", **extra):
    SELECTION.append({"way_id":way,"component_id":component,"name":name,
                      "feature_id":feature,"m1_group":group,"material_role":material,
                      "display_mode":mode,**extra})


add(36748248,"BrocktonOval","Brockton Oval rugby pitch","SP_cricket_pavilion","M1-F03","sports_grass")
add(58304177,"BrocktonWestField","Brockton west soccer/baseball field","SP_cricket_pavilion","M1-F03","sports_grass")
add(58304185,"BrocktonCricketNorth","Brockton north cricket field","SP_cricket_pavilion","M1-F03","sports_grass")
add(715158278,"BrocktonCricketSouth","Brockton south cricket field","SP_cricket_pavilion","M1-F03","sports_grass")
add(1253556548,"TotemPrecinct","Brockton Point Totem Poles precinct","SP_totem_precinct","M1-F03","public_space","boundary_only",limit="Visitor court, lawn and planting are mixed inside this attraction boundary. Do not fill it with uniform paving or infer individual pole positions.")
add(1332537258,"TotemNorthCourt","Concrete waterfront viewing court north of Totem precinct","SP_totem_precinct","M1-F03","concrete",identity_note="A small waterfront court north of the attraction. This is not a claim to include the main visitor court or individual pole positions.")
add(88310489,"VarietyWaterPark","Variety Kids Water Park splash-pad outline","SP_water_park","M1-F05","splash_pad",limit="Pad outline only. Jet positions, low structures, water state and equipment require separate source work.")
add(190670686,"VarietyWaterParkApproach","Water-park paved approach and crossing source envelope","SP_water_park","M1-F05","asphalt","boundary_only",access_note="Source bicycle=dismount; does not define the full seawall restriction boundary.",limit="The polygon includes a crossing of Stanley Park Drive. Do not fill or change the road from this envelope. Separate its pavement pieces from the road and existing paths before any surface authoring.")
add(190670673,"LumbermanPlayground","Lumberman's Arch playground ground space","SP_water_park","M1-F05","play_sand")
add(363832218,"NatureHousePlaza","Lost Lagoon Nature House viewing plaza","SP_nature_house","M1-F07","concrete",level_review_required=True,limit="Nature House lies under the viewing plaza. Inspect the road/plaza level before draping; this outline is not a roof or a lower building footprint.")
add(5405078,"LostLagoonOuterEdge","Lost Lagoon outer water-edge source boundary","SP_lost_lagoon","M1-F07","water_edge","boundary_only",source_relation_id=17060821,limit="Outer member of the Lost Lagoon water relation only. Its island holes are not in this component. Do not fill it or replace the separately authored water surface; compare its shore alignment.")
add(190668729,"NorthLagoonWetland","North Lost Lagoon wetland near the mapped biofiltration pond","SP_biofiltration","M1-F07","wetland","boundary_only",identity_note="The official map locates Biofiltration Pond in this vicinity. The OSM wetland boundary is not a surveyed basin footprint, wall or operating water level.")
add(190668733,"WestLagoonWetland","West Lost Lagoon wetland source boundary","SP_lost_lagoon","M1-F07","wetland","boundary_only")
add(503109511,"CeperleyWetland","Ceperley Meadow wetland source boundary","SP_ceperley","M1-F08","wetland","boundary_only",limit="This wetland is southwest of Lost Lagoon. It is not the biofiltration pond shown on the official map. Exclude it from a uniform meadow surface.")
add(49547890,"PitchPuttEnvelope","Stanley Park Pitch and Putt site envelope","SP_pitch_putt","M1-F08","golf_lawn","boundary_only",limit="The site contains trees, paths and lawns. Do not turn the whole boundary into flat grass or delete canopy.")
for way,part in [(49547893,"South"),(217913504,"North")]:
    add(way,"CeperleyMeadow"+part,"Ceperley Meadow "+part.lower(),"SP_ceperley","M1-F08","meadow",exclude_component_ids=["CeperleyWetland","WestLagoonWetland"],limit="A meadow source outline can overlap wetland. Subtract the named wetland polygons, paths, roads, buildings and water before authoring grass. Do not remove trees from a source envelope.")
add(753146619,"CeperleyField","Ceperley multi-use field","SP_ceperley","M1-F08","sports_grass")
add(175616392,"CeperleyPlayground","Ceperley Playground ground space","SP_ceperley","M1-F08","play_sand")
add(363401534,"CeperleyBasketball","Ceperley basketball court","SP_ceperley","M1-F08","court_asphalt")
for way,part in [(190670670,"North"),(190670671,"South")]:
    add(way,"LawnBowling"+part,"Stanley Park lawn bowling "+part.lower()+" green","SP_lawn_bowling","M1-F08","bowling_grass")
tennis = list(range(1067411314,1067411320))+list(range(1067411323,1067411335))+list(range(1088862323,1088862327))
for index,way in enumerate(tennis,1):
    area="Lagoon Drive" if way>=1088862323 else "English Bay"
    add(way,f"Tennis_{index:02}",area+f" tennis playing area {index}","SP_tennis","M1-F08","court_tennis",limit="Source polygon is the playing rectangle. Court surrounds, fences, posts and line widths remain separate M1/M4 work.")
add(921530492,"AirForceGarden","Air Force Garden of Remembrance","SP_air_force_garden","M1-F09","garden","boundary_only")
for way,part in [(503109512,"West"),(503109517,"East")]:
    add(way,"GreigGarden"+part,"Ted and Mary Greig Rhododendron Garden "+part.lower()+" envelope","SP_greig_garden","M1-F09","garden","boundary_only",limit="Garden envelope includes existing trees and paths. No individual shrub or canopy removal is implied.")
for way,part in [(58305162,"East"),(58305175,"West")]:
    add(way,"RoseGarden"+part,"Rose Garden "+part.lower()+" envelope","SP_rose_garden","M1-F09","garden","boundary_only",source_relation_id=17813331,limit="Relation provides garden identity. The envelope includes lawns and paths; individual bed polygons are separate.")
for index,way in enumerate(list(range(1086865331,1086865341))+[1086867502],1):
    add(way,f"PavilionGardenBed_{index:02}",f"Pavilion garden bed {index}","SP_rose_garden","M1-F09","garden_bed",identity_note="OSM supplies an unnamed garden polygon; the City map and aerial context place it in the Pavilion/perennial garden area. It is not assigned a flower species.")
add(732702648,"MalkinBowlGround","Malkin Bowl audience-space envelope","SP_malkin_bowl","M1-F09","event_lawn","boundary_only",limit="The source theatre outline does not separate stage, seating fixtures and lawn. Existing building meshes stay separate.")
for way in [241887212,241887213,241887215,241887216,660884658,660884659]:
    add(way,f"MiniatureRail_{way}","Miniature railway alignment segment","SP_train","M1-F10","rail_reference","line_reference",limit="Alignment only. Bridge and tunnel segments must not be draped onto ground. Public ride access, track-bed width and current service are not established by this geometry.")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf8")


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    source = ET.parse(ROOT/RAW).getroot()
    nodes={int(n.get("id")):(float(n.get("lon")),float(n.get("lat"))) for n in source.findall("node")}
    ways={int(w.get("id")):w for w in source.findall("way")}
    relations={int(r.get("id")):r for r in source.findall("relation")}
    transform=Transformer.from_crs(4326,3157,always_xy=True)
    raw_features, local_features, rows, failures = [],[],[],[]
    for config in SELECTION:
        way=ways[config["way_id"]]
        refs=[int(n.get("ref")) for n in way.findall("nd")]
        if any(n not in nodes for n in refs):
            failures.append({"way_id":config["way_id"],"reason":"Missing referenced node"});continue
        tags={t.get("k"):t.get("v") for t in way.findall("tag")}
        wgs=[nodes[n] for n in refs]
        coords=[(e-489600,n-5461100) for e,n in [transform.transform(*p) for p in wgs]]
        is_line=config["display_mode"]=="line_reference"
        geom=LineString(coords) if is_line else Polygon(coords)
        original=LineString(wgs) if is_line else Polygon(wgs)
        if not geom.is_valid or (not is_line and refs[0]!=refs[-1]):
            failures.append({"way_id":config["way_id"],"reason":"Invalid or unclosed source polygon"});continue
        property={**config,"source_type":"OpenStreetMap way","source_url":f"https://www.openstreetmap.org/way/{config['way_id']}",
                  "source_file":RAW,"source_timestamp":way.get("timestamp"),"source_version":int(way.get("version")),
                  "source_tags":tags,"source_node_ids":refs,"source_last_edit_is_survey_date":False,
                  "source_geometry_edited":False,"licence":"ODbL-1.0","attribution":"© OpenStreetMap contributors",
                  "official_map":"data/routes/raw/official-park-map-2026.pdf","official_map_revision":"2026-05-19",
                  "absolute_accuracy_accepted":False,"surveyed_boundary":False,"release_accepted":False,
                  "collision":"none; source footprint does not define contact or legal access",
                  "expected_object_name":"SM_PublicSpace_"+config["component_id"],
                  "terrain_contract":"Clip to final terrain triangles after the pavement/underpass update. Keep a small display lift; use terrain contact. Exclude roads, bicycle/walking pavement, buildings, wetlands and independent water meshes. Apply component-specific exclusions. Do not change terrain elevation or remove trees.",
                  "area_m2":None if is_line else float(geom.area),"length_m":float(geom.length),"bounds_local_m":list(geom.bounds)}
        if "source_relation_id" in config:
            relation=relations[config["source_relation_id"]]
            property["source_relation_tags"]={t.get("k"):t.get("v") for t in relation.findall("tag")}
        if is_line:
            property["gauge_m"]=float(tags["gauge"])/1000 if "gauge" in tags else None
            property["grade_separated"]=tags.get("bridge")=="yes" or tags.get("tunnel")=="yes"
        fid="PS_OSM_"+str(config["way_id"])
        raw_features.append({"type":"Feature","id":fid,"properties":{"way_id":config["way_id"],"source_tags":tags,"timestamp":way.get("timestamp"),"licence":"ODbL-1.0"},"geometry":mapping(original)})
        local_features.append({"type":"Feature","id":fid,"properties":property,"geometry":mapping(geom)})
        rows.append(property)
    exclusions=[]
    local_by_id={f["properties"]["component_id"]:f for f in local_features}
    from shapely.geometry import shape
    for row in rows:
        for excluded in row.get("exclude_component_ids",[]):
            overlap=shape(local_by_id[row["component_id"]]["geometry"]).intersection(shape(local_by_id[excluded]["geometry"]))
            exclusions.append({"component_id":row["component_id"],"exclude_component_id":excluded,"overlap_m2":float(overlap.area),"applied_to_source_geometry":False,"must_apply_before_surface_mesh":True})
    source_path=OUT/"osm-source-polygons-wgs84.geojson"
    local_path=OUT/"public-space-blockouts-local.geojson"
    save(source_path,{"type":"FeatureCollection","name":"Unedited selected OSM source polygons and railway lines","features":raw_features})
    save(local_path,{"type":"FeatureCollection","name":"M1 source-linked public spaces; local metres","features":local_features})
    manifest={"schema_version":1,"kind":"Source-linked coarse ground-space package; no terrain or app changes",
              "horizontal_crs":"EPSG:3157","origin_m":[489600,5461100],"axes":"X east, Y north; no Z assigned",
              "source_period":"City orthophoto June 6–July 1 2022; OSM edits through saved September 27 2026 extract; official map May 19 2026 revision",
              "absolute_accuracy_accepted":False,"licence":"ODbL-1.0 for source and derived OSM database",
              "attribution":"© OpenStreetMap contributors","licence_url":"https://opendatacommons.org/licenses/odbl/1-0/",
              "source_file":{"path":RAW,"sha256":sha(ROOT/RAW)},
              "official_map":{"path":"data/routes/raw/official-park-map-2026.pdf","sha256":sha(ROOT/"data/routes/raw/official-park-map-2026.pdf"),"role":"Reference identity only; no map graphics incorporated"},
              "original_geometry":{"path":source_path.relative_to(ROOT).as_posix(),"sha256":sha(source_path)},
              "authoring_geometry":{"path":local_path.relative_to(ROOT).as_posix(),"sha256":sha(local_path)},
              "features":rows,"counts":{"components":len(rows),"by_m1_group":dict(Counter(r["m1_group"] for r in rows)),"by_display_mode":dict(Counter(r["display_mode"] for r in rows))},
              "failures":failures,"required_surface_exclusions":exclusions,"m1_group_completion_claimed":False,
              "remaining":["Totem pole positions/forms and most visitor-court paving","Water-park low structures and jet layout","Nature House building/plaza level; fountain support and current restoration condition","Court surrounds and fences","Community Garden, Shakespeare Garden and Rock Garden boundaries not identified from reliable geometry in this package","Railway clearing/buildings, Cob House and heron-colony area"]}
    save(ROOT/"manifests/public-space-blockouts.json",manifest)
    save(ROOT/"evidence/public-spaces/numerical-check.json",{"kind":"Source geometry checks, not application test","selected":len(SELECTION),"exported":len(rows),"failures":failures,"finite_valid_geometry":not failures,"required_surface_exclusions":exclusions})
    print(json.dumps({"counts":manifest["counts"],"failures":failures}))


if __name__=="__main__":main()
