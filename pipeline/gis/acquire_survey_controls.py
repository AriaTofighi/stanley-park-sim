"""Acquire control monument references; their map symbols are not surface controls."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/raw/corridor'
sources=[]

def fetch(url,name):
    path=OUT/name
    if not path.exists():
        with urllib.request.urlopen(url,timeout=20) as response:
            body=response.read(4_000_001)
        if len(body)>4_000_000:raise RuntimeError('Control reference exceeds size limit')
        path.write_bytes(body)
    sources.append(dict(url=url,path=path.relative_to(ROOT).as_posix(),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return json.loads(path.read_text())

item=fetch('https://maps.vancouver.ca/portal/sharing/rest/content/items/0993333c9fbc4463acd6653a191ae32a?f=json','property-service-item.json')
service=fetch(item['url']+'?f=pjson','property-service.json')
layer=fetch(item['url']+'/94?f=pjson','survey-monuments-layer.json')
q=urllib.parse.urlencode(dict(f='json',where='1=1',geometry='488000,5459500,491600,5462600',
    geometryType='esriGeometryEnvelope',inSR=26910,spatialRel='esriSpatialRelIntersects',
    outFields='*',returnGeometry='true'))
city=fetch(item['url']+'/94/query?'+q,'survey-monuments-park.json')
q=urllib.parse.urlencode(dict(service='WFS',version='2.0.0',request='GetFeature',
    typeNames='pub:WHSE_REFERENCE.MASCOT_GEODETIC_CONTROL',outputFormat='application/json',
    srsName='EPSG:3157',cql_filter="BBOX(GEOMETRY,488000,5459500,491600,5462600,'EPSG:3157')"))
bc=fetch('https://openmaps.gov.bc.ca/geo/pub/WHSE_REFERENCE.MASCOT_GEODETIC_CONTROL/ows?'+q,'mascot-park-controls.json')
report=dict(retrieved_utc=datetime.now(timezone.utc).isoformat(),sources=sources,
    city_count=len(city.get('features',[])),bc_count=len(bc.get('features',[])),
    city_rights='City of Vancouver reference layer; no licence grant in service item. Reference only.',
    bc_rights='Open Government Licence - British Columbia; MASCOT Geodetic Control Monuments',
    catalogue='https://catalogue.data.gov.bc.ca/dataset/mascot-geodetic-control-monuments',
    limits='City layer has XY map locations and IDs, no elevation or accuracy. BC index links to full monument reports. A monument must be identified on the source surface and its current condition checked before it can validate the world. No positional acceptance follows from this download.',
    accepted=False)
(ROOT/'manifests/survey-control-sources.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['city_count','bc_count','accepted']},indent=2))
for feature in bc.get('features',[])[:8]:print(feature['properties'])
