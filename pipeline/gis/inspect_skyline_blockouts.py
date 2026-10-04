"""Numerical and static geometry inspection; does not run the application."""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
DATA=json.loads((ROOT/'manifests/skyline-blockouts.json').read_text(encoding='utf8'))
OUT=ROOT/'evidence'


def load_meshes():
    meshes={}
    for item in DATA['inputs']+DATA['meshes']:
        assert hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()==item['sha256'],item['path']
    for m in DATA['meshes']:
        with np.load(ROOT/m['path']) as d:v=d['vertices']+d['anchor'];f=d['faces']
        assert np.isfinite(v).all() and f.min()>=0 and f.max()<len(v)
        meshes[m['name']]=(m,v,f)
    return meshes


def part_data(meshes):
    result={}
    for m,v,f in meshes.values():
        for p in m['parts']:
            result[p['part_id']]=(v[f[p['first_triangle']:p['first_triangle']+p['triangle_count']]],m['color'])
    return result


def collection(ax,triangles,color):
    # A fixed sun direction makes the coarse geometry legible without implying
    # that these preview colours are final materials.
    n=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]);n/=np.linalg.norm(n,axis=1)[:,None]
    light=np.array([-.35,.5,.79]);shade=.5+.5*np.abs(n@light)
    colors=np.clip(np.asarray(color[:3])[None,:]*shade[:,None]+.06,0,1)
    ax.add_collection3d(Poly3DCollection(triangles,facecolors=colors,edgecolors='none',zsort='average'))


def scene(ax,parts,lookup,elev=10,azim=130):
    points=[]
    for p in parts:
        t,color=lookup[p['id']];collection(ax,t,color);points.append(t.reshape(-1,3))
    v=np.vstack(points);lo=v.min(0);hi=v.max(0);size=hi-lo
    ax.set(xlim=(lo[0]-size[0]*.05,hi[0]+size[0]*.05),ylim=(lo[1]-size[1]*.05,hi[1]+size[1]*.05),zlim=(lo[2],hi[2]+size[2]*.03))
    ax.set_box_aspect(np.maximum(size,1));ax.view_init(elev=elev,azim=azim);ax.set_proj_type('ortho');ax.set_axis_off()


def main():
    meshes=load_meshes();lookup=part_data(meshes);parts=DATA['parts']
    assert len(lookup)==len(parts)
    bases={};errors=[]
    for p in parts:
        height=p['shared_base']['height_m'];key=p['parent_id']
        if key in bases:assert height==bases[key]
        bases[key]=height
        if p['role']=='TensionMembrane':
            actual=lookup[p['id']][0][:,:,2].max();expected=p['dimensions']['peak_cgvd2013_m']
            errors.append(abs(actual-expected))
    assert len(errors)==5 and max(errors)<1e-6
    podia=[p for p in parts if p['role'].startswith('ResidualPodium')]
    assert all(p['bounds_max_m'][2]-p['shared_base']['height_m']<=14.000001 for p in podia)
    stack=[p for p in parts if p['parent_id']=='way_223089079_0'];assert len(stack)==4
    assert abs(max(p['bounds_max_m'][2]-p['shared_base']['height_m'] for p in stack)-161)<1e-6
    assert DATA['check_summary']['triangles']<200000
    report=dict(kind='Offline numerical and static inspection, not an application test',
        source_hashes_valid=True,all_vertex_arrays_finite=True,part_ranges_unique=True,
        shared_parent_bases=len(bases),parent_residuals_below_14m=len(podia),
        stack_four_boxes_161m=True,canada_sail_count=5,maximum_sail_peak_error_m=max(errors),
        triangles=DATA['check_summary']['triangles'],excluded_fragments=DATA['excluded'],
        blender_inspection=False,runtime_inspection=False,accuracy_accepted=False)
    (OUT/'skyline-numerical-inspection.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    landmarks=[('223089079','The Stack: four boxes',130),('611334033','Alberni: estimated curved body',40),
        ('362187535','Paradox: OSM rotated parts',130),('91998136','Shangri-La: stepped tower parts',130),
        ('653660958','Butterfly: source lobes',130),('1371268997','Harbour Centre: shaft and disks',130),
        ('223635729','Canada Place: five membranes',130),('687478069','Landmark on Robson: current towers',130)]
    fig=plt.figure(figsize=(16,11),facecolor='#e8edf0')
    for i,(oid,title,azim) in enumerate(landmarks):
        ax=fig.add_subplot(2,4,i+1,projection='3d',facecolor='#e8edf0')
        parents=['way_'+oid+'_0']
        if oid=='1371268997':parents.extend(['way_139571552_0','way_143682595_0'])
        subset=[p for p in parts if p['parent_id'] in parents]
        scene(ax,subset,lookup,elev=15 if oid=='223635729' else 8,azim=azim)
        ax.set_title(title,fontsize=10,pad=-2)
    fig.suptitle('M1 distant skyline geometry - static inspection, not a Blender or runtime image',fontsize=16)
    fig.text(.5,.025,'Current OSM XY; tagged, historic or estimated dimensions. Neutral colours. No facade detail. Per-part limits remain in the manifest.',ha='center',fontsize=10)
    fig.subplots_adjust(left=.015,right=.985,bottom=.06,top=.92,wspace=.05,hspace=.02)
    fig.savefig(OUT/'skyline-landmark-shapes.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(16,6),facecolor='#e8edf0');ax.set_facecolor('#e8edf0')
    az,el=np.radians([130,7]);camera=np.array([np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)])
    right=np.array([-np.sin(az),np.cos(az),0]);up=np.cross(camera,right)
    triangles=np.concatenate([lookup[p['id']][0] for p in parts])
    color=np.concatenate([np.tile(lookup[p['id']][1][:3],(len(lookup[p['id']][0]),1)) for p in parts])
    normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]);normal/=np.linalg.norm(normal,axis=1)[:,None]
    shade=.5+.5*np.abs(normal@np.array([-.35,.5,.79]));color=np.clip(color*shade[:,None]+.06,0,1)
    order=np.argsort(triangles.mean(1)@camera);projected=np.stack((triangles@right,triangles@up),axis=2)
    ax.add_collection(PolyCollection(projected[order],facecolors=color[order],edgecolors='none'))
    ax.autoscale();ax.set_aspect('equal');ax.set_axis_off()
    ax.set_title('M1 downtown / West End massing - geographic geometry, view from the northwest')
    fig.text(.5,.06,'Static mesh inspection. Terrain, water, lighting, haze and trees are omitted. This is not the final view from the park.',ha='center')
    fig.subplots_adjust(left=.02,right=.98,bottom=.12,top=.9);fig.savefig(OUT/'skyline-overview.png',dpi=150);plt.close(fig)
    print(json.dumps({k:v for k,v in report.items() if k!='excluded_fragments'}))


if __name__=='__main__':main()
