"""Terrain bases and conservative current-footprint/historic-height matches."""
import json
import re
import numpy as np
import shapely
from shapely.geometry import shape
from pyproj import Transformer
from scipy.interpolate import RegularGridInterpolator


def metres(value):
    if value is None:return None
    text=str(value).strip().lower()
    if ';' in text:return None
    match=re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)\s*(m|metres|meters|ft|feet)?',text)
    if not match:return None
    return float(match[1])*(.3048 if match[2] in ['ft','feet'] else 1)


class HeightSources:
    def __init__(self,root):
        self.root=root;self.grids=[]
        for name in ['terrain_2022_park','terrain_surroundings']:
            with np.load(root/f'data/derived/{name}.npz') as d:
                self.grids.append((name,RegularGridInterpolator((d['y'],d['x']),d['z'],bounds_error=False,fill_value=np.nan)))
        raw=json.loads((root/'data/raw/skyline/city-building-2009-downtown.geojson').read_text())
        project=Transformer.from_crs(4326,3157,always_xy=True)
        def convert(x,y,z=None):
            e,n=project.transform(x,y);return np.asarray(e)-489600,np.asarray(n)-5461100
        from shapely.ops import transform
        self.city=[dict(properties=f['properties'],polygon=transform(convert,shape(f['geometry']))) for f in raw['features']]
        self.tree=shapely.STRtree([r['polygon'] for r in self.city])

    def base(self,polygon):
        p=polygon.representative_point();xy=np.vstack(([p.x,p.y],np.asarray(polygon.exterior.coords)[::max(1,len(polygon.exterior.coords)//8),:2]))
        for name,sampler in self.grids:
            z=sampler(xy[:,::-1]);valid=z[np.isfinite(z)]
            if len(valid)>=len(z)*.75:
                return dict(height_m=float(np.median(valid)),sample_min_m=float(valid.min()),sample_max_m=float(valid.max()),
                    grid=name,samples=len(valid),vertical_datum='CGVD2013',shared_parent_base=True,
                    status='Terrain-based M1 base; not a surveyed building datum')
        raise ValueError('No ground-height coverage for skyline building')

    def historic(self,polygon):
        candidates=[]
        for i in self.tree.query(polygon,predicate='intersects'):
            row=self.city[i];ref=row['polygon'];overlap=polygon.intersection(ref).area
            fit=overlap/polygon.area;ratio=ref.area/polygon.area
            if fit<.8 or not .55<=ratio<=1.8:continue
            props=row['properties'];top=props.get('topelev_m');base=props.get('base_m')
            if top is None or base is None:continue
            height=float(top-base)
            if not 1<height<230:continue
            candidates.append((fit-abs(np.log(ratio))*.15,height,props,fit,ratio))
        if not candidates:return None
        _,height,p,fit,ratio=max(candidates,key=lambda x:x[0])
        return dict(height_m=height,method='City2009 matched top minus shared base; historic scalar only, no historic XY import',
            city_polygon_id=p['id'],city_building_id=p['bldgid'],coverage_fraction=fit,area_ratio=ratio,
            top_geodetic_m=p['topelev_m'],base_geodetic_m=p['base_m'],capture_year=2009,
            datum_note='Height difference cancels vertical datum; positioned on current shared terrain base',
            uncertainty='Height may be stale despite current footprint correspondence')
