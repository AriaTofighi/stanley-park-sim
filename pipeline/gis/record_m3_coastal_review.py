"""Bind manually inspected coastal frames to their retained capture records."""
from pathlib import Path
import json, hashlib
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
draft=json.loads((ROOT/'evidence/m3-coastal-review-observations-draft.json').read_text())
reviews=draft['reviews']
def row(fid,result,route,observations,limits,follow=None):
    reviews.append(dict(id=fid,result=result,route_recognition=route,views=[dict(kind=k,id=fid+'_'+suffix,observation=o) for k,suffix,o in observations],pair_consistency='Both retained frames show the same form and occlusion. No change in form was observed.',accuracy_limits=limits,required_follow_up=follow,accepted=False))
row('ART_96','recognizable','recognizable',[
 ('route','route_0','The stepped stone base, upright shaft and ring cross are present. The close view crops the top.'),
 ('route','route_m40','The complete ring cross and stepped base are visible ahead, clear of the paved route.'),
 ('form-only','form_only','The full base and shaft are visible from the side. The edge-on cross is difficult to read against the tree.')],['Exact inscription, ornament and stone finish are not established.'],'Optional front close view in the extra sidecar.')
row('ART_315','unresolved','hidden',[
 ('route','route_0','The cliff hides the source search point; no tablet or cairn is visible.'),
 ('route','route_m40','The cliff hides the source search point; no tablet or cairn is visible.'),
 ('form-only','form_only','This camera lies below the terrain. It shows water and the backfaces of terrain, with trees above. It cannot establish the target form.')],['The source register has an approximate point and no linked mesh. Neither form nor presence is accepted.'],'Above-terrain context camera in extra sidecar; retain unresolved model status.')
row('SP_lions_gate','recognizable','recognizable',[
 ('route','route_0','Bridge deck, curved main cables, hangers and the far green braced tower are visible above the water.'),
 ('route','route_m40','Bridge deck, curved cables, hangers and far tower remain visible from the second route position.'),
 ('form-only','form_only','Both towers, the suspension span and the northern approach trestles form one continuous bridge.')],['The bridge remains a source-derived structural model. Fine deck details and exact paint finish are not established.'])
frames=[];bindings={}
for r in reviews:
    default='evidence/m3-views/m3-v3-landmark-supplemental' if r['id']=='SP_lions_gate' else 'evidence/m3-views/m3-v3-landmark-final'
    for v in r['views']:
        folder=v.get('folder',default)
        for suffix in ['-settle-first','']:
            image=ROOT/folder/v['kind']/(v['id']+suffix+'.png');meta=image.with_suffix('.json');m=json.loads(meta.read_text())
            assert sha(image)==m['image_sha256'],str(image)
            binding=ROOT/m['source_binding'];assert sha(binding)==m['source_binding_sha256'],str(binding)
            bindings[m['source_binding']]=dict(sha256=sha(binding),hashes=json.loads(binding.read_text())['hashes'])
            frames.append(dict(feature_id=r['id'],view_id=v['id'],kind=v['kind'],image=image.relative_to(ROOT).as_posix(),image_sha256=sha(image),capture_metadata_sha256=sha(meta),source_binding=m['source_binding'],source_binding_sha256=sha(binding),inspected_actual_original_frame=True))
common=set.intersection(*(set(b['hashes']) for b in bindings.values()))
conflicts={p:{k:v['hashes'][p] for k,v in bindings.items()} for p in common if len({v['hashes'][p] for v in bindings.values()})>1}
out=dict(schema_version=1,scope='Manual inspection of 80 original retained frames for 13 coastal landmarks, including both frames of the linked Brockton route boundary. This is scoped visual evidence only.',reviews=reviews,frames=frames,source_bindings=bindings,common_source_binding_conflicts=conflicts,actual_frames_inspected=len(frames),application_tests_run=False,visual_review_complete_for_scope=True,overall_acceptance=False)
(ROOT/'evidence/m3-landmark-review-coastal-final.json').write_text(json.dumps(out,indent=2))
print(json.dumps(dict(reviews=len(reviews),frames=len(frames),binding_conflicts=list(conflicts))))
