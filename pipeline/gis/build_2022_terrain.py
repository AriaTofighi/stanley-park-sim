"""Build measured 2022 park terrain and independent water-level records.

The 2013 fallback and synthetic lake bed are stored in separate masks. The source
archive, point coordinates and earlier terrain products are never overwritten.
"""
import csv
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
import shapely
from shapely.geometry import Polygon, mapping
from acquire_sources import ROOT,save_json,digest


def main():
    origin=json.loads((ROOT/"manifests/world-origin.json").read_text())
    baseline=np.load(ROOT/"data/derived/terrain_park.npz")
    x,y=baseline["x"],baseline["y"]
    z=baseline["z"].copy()
    measured=np.zeros(z.shape,bool)
    density=np.zeros(z.shape,np.uint16)
    references=[];water_points=[]
    for file in sorted((ROOT/"data/derived").glob("lidar2022_*.npz")):
        with np.load(file) as p:
            ground=p["ground"]
            water_points.append(p["water"])
            if not len(ground):continue
            tile_e,tile_n=map(int,file.stem.split("_")[1:])
            ix=np.flatnonzero((x>=tile_e-origin["easting"])&(x<tile_e+1000-origin["easting"]))
            iy=np.flatnonzero((y>=tile_n-origin["northing"])&(y<tile_n+1000-origin["northing"]))
            if not len(ix) or not len(iy):continue
            xx,yy=np.meshgrid(x[ix],y[iy]);points=np.column_stack((xx.ravel(),yy.ravel()))
            tree=cKDTree(ground[:,:2]);d,k=tree.query(points,k=8,workers=4)
            valid=d[:,0]<=3
            weight=1/np.maximum(d,.08)**2
            h=(ground[k,2]*weight).sum(1)/weight.sum(1)
            target_y,target_x=np.meshgrid(iy,ix,indexing="ij")
            ty,tx=target_y.ravel()[valid],target_x.ravel()[valid]
            z[ty,tx]=h[valid];measured[ty,tx]=True
            density[ty,tx]=(d[valid]<=2).sum(axis=1)
            references.append(dict(file=file.relative_to(ROOT).as_posix(),sha256=digest(file),grid_cells=int(valid.sum())))
            print(file.stem,int(valid.sum()),flush=True)
            del tree,ground,d,k
    water=np.concatenate(water_points)
    xx,yy=np.meshgrid(x,y)
    lake_bed=np.zeros(z.shape,bool)
    lake_features=[]
    for feature in json.loads((ROOT/"data/raw/corridor/fwa-lakes-merged.json").read_text())["features"]:
        name=feature["attributes"]["GNIS_NAME_1"]
        rings=[np.asarray(r)-[origin["easting"],origin["northing"]] for r in feature["geometry"]["rings"]]
        polygon=Polygon(rings[0],rings[1:])
        mask=shapely.contains_xy(polygon.buffer(-5),water[:,0],water[:,1])
        observations=water[mask,2]
        if len(observations)>=20:
            level=float(np.median(observations))
            source="2022 City LAS class-9 water returns; geoid-converted median, 5m interior buffer"
            uncertainty="Flight-day level, not a fixed operating level; spread and source accuracy retained"
        else:
            inside=shapely.contains_xy(polygon.buffer(-20),xx,yy)
            level=float(np.nanmedian(baseline["z"][inside]))
            source="Historic 2013 NRCan DTM interior water-surface proxy; no 2022 class-9 returns"
            uncertainty="Beaver Lake marsh cover prevents current water measurement; validate in later field/photo survey"
        inside=shapely.contains_xy(polygon,xx,yy)
        # The source contains no bathymetric survey. This concealed development
        # bed prevents a historic raster water surface from covering the new lake.
        z[inside]=np.minimum(z[inside],level-.5);lake_bed|=inside
        lake_features.append(dict(type="Feature",geometry=mapping(polygon),properties=dict(
            name=name,height_m=level,vertical_datum="CGVD2013",height_source=source,
            measured_returns=int(len(observations)),uncertainty=uncertainty,
            percentiles_m=np.percentile(observations,[5,50,95]).tolist() if len(observations) else None,
            shoreline_source="BC FWA lakes; generalized regional geometry, close shoreline approval pending")))
    rows=list(csv.DictReader((ROOT/"data/raw/water/TG_3WL_epoch2010_20190108.csv").open(newline="")))
    ocean=next(r for r in rows if r["Station"]=="Vancouver")
    comparison=next(r for r in rows if r["Station"]=="Point Atkinson")
    save_json(ROOT/"manifests/water-levels.json",dict(vertical_datum="CGVD2013(CGG2013)",
        ocean=dict(height_m=float(ocean["MWL_CGG2013__m_"]),scenario="Fixed mean-water display; no tide simulation",
            reference_epoch=2010,station=ocean,comparison_station=comparison,
            source="DFO CAN-EWLAT TG_3WL_epoch2010_20190108.csv",source_sha256=digest(ROOT/"data/raw/water/can-ewlat.zip"),
            source_url="https://open.canada.ca/data/en/dataset/a3edf193-5c56-4b38-bcc5-c8708c60ce38",
            reported_context="Gauge-based water elevations have approximately 0.1-0.2m uncertainty; not an exact September 2026 tide"),
        lakes=[f["properties"] for f in lake_features],hidden_lake_bed="Synthetic clearance 0.5m below surface, not measured bathymetry"))
    save_json(ROOT/"data/derived/lake-surfaces.geojson",dict(type="FeatureCollection",coordinate_reference="local metres",features=lake_features))
    output=ROOT/"data/derived/terrain_2022_park.npz"
    np.savez_compressed(output,x=x,y=y,z=z,valid=np.isfinite(z),inside_park=baseline["inside_park"],
        measured_2022=measured,synthetic_lake_bed=lake_bed,nearby_return_count=density)
    save_json(ROOT/"manifests/geospatial-terrain_2022_park.json",dict(product=output.relative_to(ROOT).as_posix(),sha256=digest(output),
        origin_sha256=digest(ROOT/"manifests/world-origin.json"),sources=references,resolution_m=2,
        method="8 nearest class-2 returns, inverse-distance squared, maximum nearest-return distance 3m",
        park_measured_fraction=float(measured[baseline["inside_park"]].mean()),
        missing_2022_fallback="Unchanged 2013 NRCan DTM at cells without a nearby 2022 ground return; mask provided",
        lake_bed_cells=int(lake_bed.sum()),height_control_accepted=False,
        vertical_datum="CGVD2013(CGG2013a), regional realization caveat in LiDAR manifests"))
    print("Terrain complete",float(measured[baseline["inside_park"]].mean()),flush=True)


if __name__=="__main__":main()
