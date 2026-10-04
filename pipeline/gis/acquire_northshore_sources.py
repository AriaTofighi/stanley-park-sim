"""Bounded source capture for distant North Shore industrial forms only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from acquire_sources import ROOT, download, save_json

OUT=ROOT/'data/raw/northshore'
REQUESTS=[
    ('osm-west-20260927.osm','https://api.openstreetmap.org/api/0.6/map?bbox=-123.142,49.300,-123.107,49.325'),
    ('osm-central-20260927.osm','https://api.openstreetmap.org/api/0.6/map?bbox=-123.107,49.299,-123.080,49.321'),
    ('osm-east-20260927.osm','https://api.openstreetmap.org/api/0.6/map?bbox=-123.080,49.296,-123.055,49.316'),
    ('osm-lynn-20260927.osm','https://api.openstreetmap.org/api/0.6/map?bbox=-123.055,49.294,-123.025,49.312'),
    ('richardson-storage-project.pdf','https://www.richardson.ca/wp-content/uploads/2015/12/Richardson-Vancouver-TerminalGrain-Storage-Project-Proj.pdf'),
    ('seaspan-goliath-project.pdf','https://www.supremehm.com/wp-content/uploads/2015/07/SST-Project-Sheet-Seaspan-Goliath.pdf'),
    ('fibreco-project-2017.pdf','https://www.fibrecoterminalenhancement.com/Project%20Overview%20-%20Permit%20Application%20March%202017%20R2%20.pdf'),
    ('kiewit-g3-primary.pdf','https://www.kiewit.com/wp-content/uploads/2023/04/Insert-Foreign-Direct-Investment_230428a_av.pdf'),
]


def fetch(item):
    filename,url=item
    try:
        record=download(url,OUT/filename,max_bytes=25000000)
        if filename.endswith('.pdf') and not (OUT/filename).read_bytes().startswith(b'%PDF'):
            return dict(**record,status='not_a_pdf',error='The old source domain now returns HTML. No evidence extracted.',incorporation='Excluded unavailable-source response')
        return dict(**record,status='saved',incorporation='ODbL source data' if filename.endswith('.osm') else 'Research reference only; not a game asset')
    except Exception as exc:return dict(url=url,path=(OUT/filename).relative_to(ROOT).as_posix(),status='unavailable',error=str(exc))


def main():
    with ThreadPoolExecutor(max_workers=2) as pool:records=list(pool.map(fetch,REQUESTS))
    result=dict(acquired_utc=datetime.now(timezone.utc).isoformat(),files=records,
        scope='Seven finite dominant industrial groups along North Shore; all other acquired map features are unused',
        licence='OSM ODbL-1.0; primary project documents reference only',accepted=False)
    save_json(ROOT/'manifests/northshore-source-acquisition.json',result)
    for r in records:print(r['path'],r['status'],r.get('bytes'),flush=True)


if __name__=='__main__':main()
