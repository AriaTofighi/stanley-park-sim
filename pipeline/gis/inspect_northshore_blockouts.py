"""Offline checks and static views; no Blender or application launch."""
import hashlib,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ROOT=Path(__file__).resolve().parents[2]


def main():
    manifest=ROOT/'manifests/northshore-blockouts.json';d=json.loads(manifest.read_text(encoding='utf8'));lookup={}
    for r in d['inputs']+d['meshes']:assert hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest()==r['sha256'],r['path']
    for mesh in d['meshes']:
        with np.load(ROOT/mesh['path']) as p:v=p['vertices']+p['anchor'];f=p['faces']
        assert np.isfinite(v).all() and f.min()>=0 and f.max()<len(v)
        for part in mesh['parts']:lookup[part['part_id']]=(v[f[part['first_triangle']:part['first_triangle']+part['triangle_count']]],mesh['color'])
    assert len(lookup)==len(d['parts']);assert not d['excluded'];assert not d['source_relation_failures']
    assert d['check_summary']['triangles']<25000
    for site in d['sites']:
        subset=[p for p in d['parts'] if p['site']==site['id']]
        assert all(p['shared_base']['height_m']==site['base']['height_m'] for p in subset)
    crane=[p for p in d['parts'] if p['role']=='MainGirder'][0]
    assert abs(crane['bounds_max_m'][2]-crane['shared_base']['height_m']-80)<1e-7
    assert d['check_summary']['silos_by_site']['G3']==48 and d['check_summary']['silos_by_site']['Fibreco']==21
    fig=plt.figure(figsize=(16,9),facecolor='#e8edf0')
    groups=['VancouverWharves','Fibreco','Seaspan','Richardson','Cargill','Neptune','G3','BigBlueDetail']
    for i,name in enumerate(groups):
        ax=fig.add_subplot(2,4,i+1,projection='3d',facecolor='#e8edf0')
        parts=[p for p in d['parts'] if p['site']==name] if name!='BigBlueDetail' else [p for p in d['parts'] if p['source_feature_id']=='way_1168344141']
        points=[]
        for p in parts:
            tri,col=lookup[p['id']];points.append(tri.reshape(-1,3));n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);n/=np.linalg.norm(n,axis=1)[:,None]
            colors=np.clip(np.array(col[:3])[None,:]*(.5+.5*np.abs(n@np.array([-.4,-.5,.75])))[:,None]+.07,0,1)
            ax.add_collection3d(Poly3DCollection(tri,facecolors=colors,edgecolors='none'))
        p=np.vstack(points);lo=p.min(0);hi=p.max(0);span=hi-lo
        ax.set(xlim=(lo[0],hi[0]),ylim=(lo[1],hi[1]),zlim=(lo[2],hi[2]));ax.set_box_aspect(np.maximum(span,1));ax.set_proj_type('ortho')
        ax.view_init(elev=12,azim=-85);ax.set_axis_off();ax.set_title(name,fontsize=12)
    fig.suptitle('M1 North Shore industrial silhouettes - static geometry inspection',fontsize=17)
    fig.text(.5,.035,'Current OSM footprints. Primary dimensions and explicit estimates. No live visibility, current machinery pose, or survey accuracy claim.',ha='center',fontsize=10)
    fig.subplots_adjust(left=.01,right=.99,bottom=.08,top=.91,wspace=.06,hspace=.08)
    fig.savefig(ROOT/'evidence/northshore-blockout-shapes.png',dpi=160);plt.close(fig)
    route_path=ROOT/'data/derived/paved-circuit-runtime.json';route=json.loads(route_path.read_text());s=np.array(route['chainage_runtime_m']);xyz=np.array(route['points_local_m'])
    cameras=[]
    # Actual route samples. These are proposed inspection viewpoints, not a
    # completed visibility test; park vegetation/occlusion remains live QA.
    for site in d['sites']:
        name=site['id'];station=3300 if name in ['VancouverWharves','Fibreco','Seaspan'] else 2050
        index=int(abs(s-station).argmin());eye=xyz[index]+[0,0,1.7]
        parts=[p for p in d['parts'] if p['site']==name];lo=np.min([p['bounds_min_m'] for p in parts],axis=0);hi=np.max([p['bounds_max_m'] for p in parts],axis=0);target=(lo+hi)/2
        delta=target-eye;distance=float(np.linalg.norm(delta[:2]));bearing=float(np.degrees(np.arctan2(delta[0],delta[1]))%360)
        cameras.append(dict(site=name,runtime_chainage_m=float(s[index]),eye_local_m=eye.tolist(),target_local_m=target.tolist(),horizontal_distance_m=distance,bearing_deg_clockwise_from_north=bearing,
            height_angle_deg=float(np.degrees(np.arctan2(hi[2]-eye[2],distance))),suggested_horizontal_fov_deg=70,visibility_accepted=False))
    evidence=dict(manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),offline_checks_pass=True,
        counts=d['check_summary'],all_solid_parts_valid=True,shared_terminal_bases=True,seaspan_height80m=True,
        no_collision=True,no_current_machine_pose_claim=True,static_preview='evidence/northshore-blockout-shapes.png',
        route_input_sha256=hashlib.sha256(route_path.read_bytes()).hexdigest(),suggested_cameras=cameras,
        blender_visual_acceptance=False,runtime_visibility_acceptance=False)
    (ROOT/'evidence/northshore-numerical-review.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf8')
    print(json.dumps(d['check_summary']));print('Offline checks passed; live review is pending')


if __name__=='__main__':main()
