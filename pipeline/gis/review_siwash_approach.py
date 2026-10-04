"""Compare the source roof entrance with exported terrain and path candidates."""
import json
import numpy as np
import shapely
from shapely.geometry import Polygon,Point,LineString,box
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from build_named_feature_blockouts import ROOT,survey
from acquire_sources import save_json,digest


class TerrainQuery:
    def __init__(self,bounds):
        triangles=[];self.inputs=[]
        for item in json.loads((ROOT/'manifests/surface-model.json').read_text())['terrain']:
            p=np.load(ROOT/item['path']);v=p['vertices']+p['anchor']
            if not box(*v[:,:2].min(0),*v[:,:2].max(0)).intersects(box(*bounds)):continue
            t=v[p['faces']];lo=t[:,:,:2].min(1);hi=t[:,:,:2].max(1)
            take=(lo[:,0]<bounds[2])&(hi[:,0]>bounds[0])&(lo[:,1]<bounds[3])&(hi[:,1]>bounds[1])
            t=t[take];normal=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);t=t[abs(normal[:,2])>2e-8]
            if len(t):triangles.append(t);self.inputs.append(dict(path=item['path'],sha256=digest(ROOT/item['path'])))
        self.triangles=np.concatenate(triangles);self.polygons=shapely.polygons(self.triangles[:,:,:2]);self.tree=shapely.STRtree(self.polygons)

    def height(self,xy):
        xy=np.asarray(xy);p=Point(xy);hits=self.tree.query(p.buffer(1e-6),predicate='intersects')
        if not len(hits):return np.nan
        tri=self.triangles[hits[0]];uv=np.linalg.solve(np.column_stack((tri[1,:2]-tri[0,:2],tri[2,:2]-tri[0,:2])),xy-tri[0,:2])
        return tri[0,2]+uv@(tri[1:,2]-tri[0,2])


def main():
    d=json.loads((ROOT/'manifests/west-landmark-blockouts.json').read_text());f=next(f for f in d['features'] if f['id']=='SP_siwash_lookout')
    m=f['measured'];xy=np.array(m['roof_outline_local_m']);roof=Polygon(xy);origin=np.array(m['roof_plane_origin_m']);plane=np.array(m['roof_plane']);centre=np.array(roof.centroid.coords[0])
    height=lambda p:(p-origin)@plane[:2]+plane[2]
    terrain=TerrainQuery([-940,632,-900,670]);q,c=survey('siwash-lookout');ground=q[c==2]
    edges=[]
    for a,b in zip(xy,np.roll(xy,-1,axis=0)):
        if ((a+b)/2-centre)@np.array([1.,-1.])<=1.8:continue
        samples=np.linspace(a,b,11);h=np.array([terrain.height(p) for p in samples]);edges.append(dict(a=a.tolist(),b=b.tolist(),roof_h_m=height(samples).tolist(),terrain_h_m=h.tolist(),height_gap_m=(height(samples)-h).tolist()))
    ped=json.loads((ROOT/'data/routes/derived/pedestrian-network.json').read_text());near=[]
    for e in ped['edges']:
        line=LineString(e['coordinates_local_xy_m'])
        if line.distance(roof)<25:near.append(e)
    fig,axes=plt.subplots(1,3,figsize=(18,7));meta=json.loads((ROOT/'evidence/corridor/ortho-utm/named-siwash-lookout.json').read_text());b=meta['local_bounds_m']
    axes[0].imshow(plt.imread(ROOT/'evidence/corridor/ortho-utm/named-siwash-lookout.png'),extent=[b[0],b[2],b[1],b[3]])
    for ax in axes:
        ax.plot(*np.vstack((xy,xy[0])).T,'r-',lw=2)
        for e in near:
            p=np.array(e['coordinates_local_xy_m']);ax.plot(*p.T,lw=1,label=e['edge_id'])
        for e in edges:ax.plot(*np.array([e['a'],e['b']]).T,'c-',lw=3)
        ax.set_xlim(-935,-908);ax.set_ylim(635,669);ax.set_aspect('equal')
    scatter=axes[1].scatter(*ground[:,:2].T,c=ground[:,2],s=3,vmin=18,vmax=25);fig.colorbar(scatter,ax=axes[1],shrink=.7,label='CGVD2013 H (m)')
    axes[2].tripcolor(terrain.triangles[:,:,0].ravel(),terrain.triangles[:,:,1].ravel(),np.arange(len(terrain.triangles)*3).reshape(-1,3),facecolors=terrain.triangles[:,:,2].mean(1),vmin=18,vmax=25,edgecolors='#777777',lw=.3)
    axes[0].set_title('City ortho: source roof (red), open edge (cyan)');axes[1].set_title('Raw classified ground returns');axes[2].set_title('Final v14 terrain triangle heights')
    fig.tight_layout();fig.savefig(ROOT/'evidence/named-features/siwash-approach-source-review.png',dpi=145)
    result=dict(feature='SP_siwash_lookout',terrain_inputs=terrain.inputs,open_roof_edges=edges,nearby_pedestrian_edges=[dict(id=e['edge_id'],coordinates=e['coordinates_local_xy_m'],tags=e['source_tags']) for e in near],application_acceptance=False)
    save_json(ROOT/'evidence/siwash-approach-contact-review.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
