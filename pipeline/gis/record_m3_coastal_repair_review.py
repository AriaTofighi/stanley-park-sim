"""Bind manual inspection of the actual v4 coastal repair frames."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rows=[
('SP_girl_wetsuit','m3-v4-final-repairs','route','SP_girl_wetsuit_route_0','The boulder and seated bronze silhouette are visible from the actual route. The extended lower body is visible against the stone; fine mask and fin details are too small to judge at this route distance.'),
('SP_girl_wetsuit','m3-v4-final-repairs','route','SP_girl_wetsuit_route_m40','The boulder and small upper figure remain visible near the water, beside a foreground tree. The distant lower body details cannot be resolved.'),
('SP_girl_wetsuit','m3-v4-final-repairs','form-only','SP_girl_wetsuit_form_only','The head, shoulders and connected seated torso are visible from the east side. The rock hides the lower body from this rear angle.'),
('SP_girl_wetsuit','m3-v4-wetsuit-close','form-only','SP_girl_wetsuit_extra_west_close','The hips sit at the rock surface. Both thighs, bent knees, shins and two fins are exposed over its west slope. A forehead mask and connected shoulders, arms and torso are visible. No buried lower body or open mesh surface is seen.'),
('SP_shore_to_shore','m3-v4-final-repairs','route','SP_shore_to_shore_route_0','Human bodies with heads and shoulders are visible on the circular base below the tall central form. They are distant but no longer narrow capped cylinders. No form projects into the paved route.'),
('SP_shore_to_shore','m3-v4-final-repairs','route','SP_shore_to_shore_route_40','The small figure group and central form remain visible between trees from the second route station. No new form obstructs the paved route.'),
('SP_shore_to_shore','m3-v4-final-repairs','form-only','SP_shore_to_shore_form_only','Two complete standing figures have shoulders, bent arms, garments and feet. The third figure is behind the unchanged central form from this angle. The feet meet the circular podium.'),
('SP_shore_to_shore','m3-v4-shore-close','form-only','SP_shore_to_shore_extra_northwest_close','Two standing people are fully visible from the opposite side. The third head, shoulder, arm and a foot are visible behind them. In combination with the east view, the three separate human forms are established. The central tall form and circular stone base remain present.')]
frames=[];bindings={};views=[]
for fid,folder,kind,id,observation in rows:
    v=dict(feature_id=fid,id=id,kind=kind,observation=observation,pair_consistency='Both original retained frames show the same form and occlusion.',frames=[])
    for suffix in ['-settle-first','']:
        p=ROOT/'evidence/m3-views'/folder/kind/(id+suffix+'.png');mp=p.with_suffix('.json');m=json.loads(mp.read_text());bp=ROOT/m['source_binding'];b=json.loads(bp.read_text())
        assert sha(p)==m['image_sha256'],str(p)
        assert sha(bp)==m['source_binding_sha256'],str(bp)
        assert b['hashes']['evidence/m3-final-native-assets-v4.json']=='ba2d1a27d2d8bc7719a26d7f8b50c96cb871b9029b3da52fe3ccbd6fbde8d15f'
        bindings[m['source_binding']]=dict(sha256=sha(bp),hashes=b['hashes'])
        f=dict(feature_id=fid,view_id=id,image=p.relative_to(ROOT).as_posix(),image_sha256=sha(p),capture_metadata_sha256=sha(mp),source_binding=m['source_binding'],source_binding_sha256=sha(bp),inspected_actual_original_frame=True)
        frames.append(f);v['frames'].append(f['image'])
    views.append(v)
common=set.intersection(*(set(v['hashes']) for v in bindings.values()))
conflicts={p:{k:v['hashes'][p] for k,v in bindings.items()} for p in common if len({v['hashes'][p] for v in bindings.values()})>1}
assert not conflicts,conflicts
result=dict(schema_version=1,scope='Manual review of all 16 original frames for two repaired coastal targets. Route and form-only evidence remain distinct. No application test was run.',actual_frames_inspected=len(frames),views=views,frames=frames,source_bindings=bindings,common_source_binding_conflicts=conflicts,
    results=[dict(id='SP_girl_wetsuit',visual_correction_resolved=True,result='Recognizable seated figure with two visible fins in the west form view; source boulder and head centre retained.',limits='Pose, mask shape, anatomy and face are visual estimates. The small route silhouette does not resolve all fine features. Form-only evidence does not establish route visibility.'),dict(id='SP_shore_to_shore',visual_correction_resolved=True,result='Three recognizable connected human forms are established across the two form angles; the tall central source form and circular podium remain.',limits='Pose, garments, faces and detailed carving are estimates. One rear figure is naturally hidden in each angle. The simple central form and stone finish remain source blockouts.')],
    source_checks=['evidence/m3-coastal-build-save-summary.json','evidence/m3-wetsuit-final-skin-source-check.json','evidence/m3-shore-to-shore-import-9b88c0e7c383.json','evidence/m3-wetsuit-form-import-0c9158608c8a.json'],application_tests_run=False,overall_acceptance=False)
output=ROOT/'evidence/m3-coastal-repair-review-v4.json';output.write_text(json.dumps(result,indent=2));print(dict(path=str(output),frames=len(frames),binding_conflicts=len(conflicts)))
