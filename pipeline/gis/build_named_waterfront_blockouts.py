"""Measured outlines and survey roof forms for two waterfront facilities.

Manual traces are explicit review inputs, not exact architectural boundaries.
No live Blender or application operation occurs here.
"""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import Delaunay, cKDTree
from shapely.geometry import Polygon, Point
from shapely import contains_xy
import build_named_feature_blockouts as geom
from acquire_sources import save_json

ROOT=geom.ROOT
geom.OUT=ROOT/'data/derived/named-waterfront';geom.OUT.mkdir(exist_ok=True)
geom.COLORS.update(marina_roof=[.58,.61,.61],pool_water=[.27,.66,.68],pool_rim=[.81,.79,.69],dock=[.43,.38,.28])
# Local metre traces reviewed on City 2022 imagery with a 10 m grid.
# These select roof returns. They are not architectural wall boundaries.
SHED_TRACES=[
 ('WestWide',[(984,-828),(1007,-815),(1038,-867),(1016,-881)]),
 ('WestNarrow',[(1012,-818),(1030,-812),(1051,-852),(1037,-860)]),
 ('WestEnd',[(1028,-875),(1050,-863),(1072,-900),(1049,-914)]),
 ('MiddleWestUpper',[(1052,-817),(1063,-810),(1080,-840),(1068,-848)]),
 ('MiddleWestLower',[(1070,-848),(1088,-837),(1114,-881),(1099,-891)]),
 ('MiddleEastUpper',[(1065,-807),(1074,-802),(1092,-831),(1083,-836)]),
 ('MiddleEastLower',[(1091,-835),(1102,-829),(1134,-881),(1122,-889)]),
 ('LongWest',[(1130,-810),(1143,-800),(1196,-885),(1184,-892)]),
 ('LongEast',[(1145,-798),(1158,-790),(1215,-878),(1200,-888)]),
 ('LongEnd',[(1207,-886),(1226,-881),(1243,-908),(1224,-920)]),
 ('MainSouth',[(1187,-778),(1197,-772),(1257,-864),(1245,-872)]),
 ('SouthOuter',[(1242,-817),(1300,-774),(1310,-787),(1254,-830)]),
 ('SouthInner',[(1229,-803),(1307,-748),(1316,-759),(1237,-815)]),
 ('SouthSmall',[(1234,-821),(1243,-814),(1256,-837),(1248,-842)]),
 ('NorthInner',[(1185,-747),(1192,-743),(1195,-748),(1325,-652),(1334,-665),(1202,-760),(1194,-763)]),
 ('NorthOuter',[(1205,-762),(1336,-667),(1347,-682),(1210,-773)]),
 ('CentralServiceWest',[(1146,-782),(1160,-774),(1165,-782),(1151,-790)]),
 ('CentralServiceMain',[(1156,-764),(1175,-754),(1183,-768),(1165,-779)]),
 ('CentralServiceEntrance',[(1171,-744),(1181,-737),(1187,-746),(1177,-751)]),
]
POOL_TRACE=[(292,858),(337,754),(410,649),(454,590),(476,599),(501,589),(514,570),(650,550),(674,548),(684,581),(706,601),(728,600),(748,583),(751,555),(974,534),(1022,536),(1075,552),(1101,575),(1108,605),(1130,632),(1161,648),(1173,690),(1175,731),(1164,770),(1251,800),(1235,847),(1208,889),(1175,925),(1149,952),(1146,978),(1164,992),(1115,1012),(1060,1029),(992,1033),(920,1028),(865,1010),(799,985),(759,1054)]

def traced(points,left,top,pixel):
    a=np.asarray(points,float)
    return np.column_stack((left+(a[:,0]+.5)*pixel,top-(a[:,1]+.5)*pixel))

def boundary_walls(vertices,faces,base):
    counts={};directions={}
    for tri in faces:
        for a,b in zip(tri,np.roll(tri,-1)):
            key=tuple(sorted((int(a),int(b))));counts[key]=counts.get(key,0)+1;directions[key]=(int(a),int(b))
    vv=[];ff=[]
    for key,count in counts.items():
        if count!=1:continue
        a,b=directions[key];p0,p1=vertices[a],vertices[b];n=len(vv)
        vv.extend([p0,p1,[p1[0],p1[1],base],[p0[0],p0[1],base]]);ff.append((n+3,n+2,n+1,n))
    return vv,ff

def marina():
    fid='SP_yacht_club';p=np.load(ROOT/'data/derived/named-yacht-full-west-survey.npz');q=p['xyz'].astype(float)
    measured=[]
    for tag,px in SHED_TRACES:
        xy=np.array(px,dtype=float);poly=Polygon(xy)
        # Top returns in each cell keep the pitched and stepped roof envelope.
        selected=q[contains_xy(poly,q[:,0],q[:,1])&(q[:,2]>2.8)&(q[:,2]<12)]
        cells=np.floor(selected[:,:2]/.65).astype(int);_,index=np.unique(cells,axis=0,return_inverse=True)
        vertices=[]
        for k in range(index.max()+1):
            group=selected[index==k];limit=np.percentile(group[:,2],75);vertices.append(np.median(group[group[:,2]>=limit],axis=0))
        vertices=np.array(vertices);faces=Delaunay(vertices[:,:2]).simplices
        edges=np.linalg.norm(vertices[faces][:,:,:2]-np.roll(vertices[faces][:,:,:2],1,axis=1),axis=2)
        faces=faces[edges.max(1)<2.0];mid=vertices[faces,:2].mean(1);faces=faces[contains_xy(poly,mid[:,0],mid[:,1])]
        geom.mesh('SM_YachtPort_'+tag+'_RoofSurvey',vertices,faces,'marina_roof',fid)
        vv,ff=boundary_walls(vertices,faces,1.55)
        geom.mesh('SM_YachtPort_'+tag+'_WallsReview',vv,ff,'wall',fid)
        measured.append(dict(tag=tag,trace_local_m=xy.tolist(),returns=len(selected),roof_height_percentiles_m=np.percentile(vertices[:,2],[0,5,50,95,100]).tolist()))
        print(tag,len(selected),len(vertices),len(faces),flush=True)
    geom.feature(fid,'Royal Vancouver Yacht Club Coal Harbour marina',[
        'https://www.royalvan.com/home-ports','https://vancouver.ca/files/cov/stanley-park-map-and-guide.pdf',
        'evidence/corridor/ortho-utm/named-yacht-full.json','manifests/named-yacht-full-west-survey.json'],
        dict(roof_groups=measured,sampling_m=.65),
        dict(wall_base_m=1.55,roof_trace='Local XY traced on City ortho with a 10 m review grid; corners have approximately 1 m trace uncertainty'),
        'Floating roof groups are measured in City LAS; most are not class 6. Dock level and wall extrusion are provisional. Tide, boats, dock network, piles and individual shed walls need further work. Central service roof is not yet assigned to Mermaid Inn by identity. No marina collision or water alignment acceptance.')

def pool():
    fid='SP_second_pool';names=['second-pool','second-pool-west'];parts=[np.load(ROOT/f'data/derived/named-{n}-survey.npz') for n in names]
    q=np.vstack([p['xyz'] for p in parts]).astype(float);c=np.concatenate([p['classification'] for p in parts])
    xy=traced(POOL_TRACE,-700,-730,.1);poly=Polygon(xy);inside=contains_xy(poly,q[:,0],q[:,1])
    water=q[inside&(c==9)];level=float(np.median(water[:,2]))
    # Water produces very few reliable returns. Keep one level, not a false floor.
    gridx,gridy=np.meshgrid(np.arange(xy[:,0].min(),xy[:,0].max(),1),np.arange(xy[:,1].min(),xy[:,1].max(),1))
    grid=np.column_stack((gridx.ravel(),gridy.ravel()));grid=grid[contains_xy(poly,grid[:,0],grid[:,1])];grid=np.vstack((xy,grid))
    triangles=Delaunay(grid).simplices;mid=grid[triangles].mean(1);triangles=triangles[contains_xy(poly,mid[:,0],mid[:,1])]
    geom.mesh('SM_SecondPool_SurfaceReview',np.column_stack((grid,np.full(len(grid),level))),triangles,'pool_water',fid)
    outer=poly.buffer(.7).difference(poly);coping=q[(c==2)&contains_xy(outer,q[:,0],q[:,1])]
    tree=cKDTree(coping[:,:2]);_,idx=tree.query(xy,k=12);rimz=np.median(coping[idx,2],axis=1)
    # Follow an offset polygon to make a narrow coping ribbon, not a solid lid.
    vertices=[];faces=[]
    for k,a in enumerate(xy):
        b=xy[(k+1)%len(xy)];d=(b-a)/np.linalg.norm(b-a);normal=np.array([-d[1],d[0]])
        mid=(a+b)/2
        if poly.contains(Point(mid+normal*.1)):normal=-normal
        n=len(vertices);za=rimz[k]+.015;zb=rimz[(k+1)%len(xy)]+.015
        vertices.extend([[*a,za],[*b,zb],[*(b+normal*.35),zb],[*(a+normal*.35),za]]);faces.append((n,n+1,n+2,n+3))
    geom.mesh('SM_SecondPool_CopingSurvey',vertices,faces,'pool_rim',fid)
    geom.feature(fid,'Second Beach Pool outline and surface',[
        'https://vancouver.ca/parks-recreation-culture/second-beach-pool.aspx','evidence/corridor/ortho-utm/named-second-pool.json',
        'manifests/named-second-pool-survey.json','manifests/named-second-pool-west-survey.json'],
        dict(outline_local_m=xy.tolist(),area_m2=poly.area,water_returns=len(water),water_level_m=level,coping_returns=len(coping),coping_height_range_m=[float(rimz.min()),float(rimz.max())],
             visible_lane_outer_edge_m=float(np.linalg.norm(xy[0]-xy[-1]))),
        dict(coping_width_m=.35,water_state='2022 water retained for M1; September 2026 closed season confirmed but current fill state unknown'),
        'Pool floor, depth, railings, slides and fence are not measured models. City says 50 m lane section and 80 m pool length; the traced outer lane edge is 50.65 m, while freeform pool length definition is unresolved. No false scale adjustment was made. Requires terrain cut; no swimming or collision. Closed after 7 September in 2026.')
    geom.FEATURES[-1]['terrain_cut_polygon_local_m']=xy.tolist()
    geom.FEATURES[-1]['terrain_cut_target_height_m']=level-.25

def main():
    marina();pool()
    save_json(ROOT/'manifests/named-waterfront-blockouts.json',dict(schema_version=1,source_period='City 2022 survey and imagery',target_period='September 2026',features=geom.FEATURES,assets=geom.ASSETS,acceptance=False,
        reference_rights='City survey derivatives use OGL-Vancouver. City and operator web pages are identity references only.'))
    print(json.dumps(dict(features=len(geom.FEATURES),assets=len(geom.ASSETS),triangles=sum(x['triangles'] for x in geom.ASSETS))))

if __name__=='__main__':main()
