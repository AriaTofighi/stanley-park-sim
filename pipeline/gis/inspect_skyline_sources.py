"""Read the acquired skyline source tags without authoring any geometry."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
nodes,ways,relations={},{},{}
for path in sorted((ROOT/'data/raw/skyline').glob('osm-*.osm')):
    for item in ET.parse(path).getroot():
        if item.tag=='node':nodes[item.attrib['id']]=item
        elif item.tag=='way':ways[item.attrib['id']]=item
        elif item.tag=='relation':relations[item.attrib['id']]=item
rows=[]
for kind,items in [('way',ways),('relation',relations)]:
    for key,item in items.items():
        tags={t.attrib['k']:t.attrib['v'] for t in item.findall('tag')}
        if not ('building' in tags or 'building:part' in tags):continue
        if any(k in tags for k in ['height','building:levels','name']):
            rows.append(dict(type=kind,id=key,tags=tags))
(ROOT/'evidence/skyline-source-tags.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf8')
for row in rows:
    t=row['tags']
    if any(word.lower() in t.get('name','').lower() for word in ['Butterfly','Paradox','Hyatt Vancouver','Canada Place','The Stack','Harbour Centre','Alberni by']):
        print(row['type'],row['id'],json.dumps(t,ensure_ascii=True))
print('Total named or dimensioned rows',len(rows))
