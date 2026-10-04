"""Keep a MASCOT report as an internal reference under its displayed use terms.

The open map index and the full reports have different reuse conditions.
Never place full reports in a distributed simulation or public repository.
"""
import http.cookiejar
import urllib.parse
import urllib.request
from pathlib import Path
import re
import argparse
import json

root=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser()
parser.add_argument('--gcm',type=int,default=137174)
parser.add_argument('--complete', action='store_true')
args=parser.parse_args()
gcm=args.gcm
index=json.loads((root/'data/raw/corridor/mascot-park-controls.json').read_text(encoding='utf8'))
if gcm not in {f['properties']['GCM_NUMBER'] for f in index['features']}:
    raise ValueError('Choose a monument from the saved park index')
jar=http.cookiejar.CookieJar()
client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
request_uri=f'/pub/mascotw/protected/query1_imf.html?GCM_NO={gcm}&'
url='https://a100.gov.bc.ca'+request_uri
with client.open(url,timeout=20) as response:text=response.read().decode('latin1')
if '<title>MASCOT Disclaimer and Terms Of Use</title>' in text:
    # This is the normal public site's terms form, not authentication.
    data=urllib.parse.urlencode(dict(DISC_REQUEST_URI=request_uri,
        MASCOT_DISCLAIMER_ACCEPT='I Accept the Terms Of Use')).encode()
    with client.open('https://a100.gov.bc.ca/pub/mascotw/public/returnFromDisclaimer',data=data,timeout=20) as response:
        text=response.read().decode('latin1')
    if 'Return to MASCOTW' in text:
        with client.open(url,timeout=20) as response:text=response.read().decode('latin1')
if '<FORM ACTION="/pub/mascotw/protected/gcm_list2.html" METHOD=POST>' in text:
    data=urllib.parse.urlencode(dict(GCM_NO=str(gcm),EOS='0')).encode()
    with client.open('https://a100.gov.bc.ca/pub/mascotw/protected/gcm_list2.html',data=data,timeout=20) as response:
        text=response.read().decode('latin1')
if f'/pub/mascotw/protected/final_long.html?Q_GCM_NO={gcm}' in text:
    with client.open(f'https://a100.gov.bc.ca/pub/mascotw/protected/final_long.html?Q_GCM_NO={gcm}',timeout=20) as response:
        text=response.read().decode('latin1')
if args.complete:
    complete_path=f'/pub/mascotw/protected/longf.html?Q_GCM_NO={gcm}&Q_OPT=1'
    if complete_path not in text:
        raise ValueError('Complete report link was not present in the returned page')
    with client.open('https://a100.gov.bc.ca'+complete_path,timeout=20) as response:
        text=response.read().decode('latin1')
suffix='complete-report' if args.complete else 'report'
path=root/f'data/raw/corridor/mascot-{gcm}-{suffix}.html'
path.write_text(text,encoding='utf8')
print(re.sub('<[^>]+>',' ',text)[:14000])
print('LINKS',re.findall(r'(?:href|src|action)=[\"\x27]([^\"\x27]+)',text,re.I)[:30])
