"""Make a UTM-metre orthophoto reference crop with an explicit pixel transform.

These images are survey/model references, not runtime materials. Resampling does
not improve the source's absolute positional accuracy.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image
from pyproj import Transformer
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline/gis"))
from acquire_sources import download, save_json


def build(name, east, north, span=160, pixel=.1):
    origin = json.loads((ROOT/"manifests/world-origin.json").read_text())
    service = json.loads((ROOT/"data/raw/corridor/orthophoto-service.json").read_text())
    base = json.loads((ROOT/"data/raw/corridor/orthophoto-portal-item.json").read_text())["url"]
    centre = [east+origin["easting"], north+origin["northing"]]
    bounds = [centre[0]-span/2, centre[1]-span/2, centre[0]+span/2, centre[1]+span/2]
    web = Transformer.from_crs(3157,3857,always_xy=True).transform_bounds(*bounds)
    level = 18 if pixel >= .3 else 19 if pixel >= .18 else 20 if pixel >= .09 else 21
    resolution = next(x["resolution"] for x in service["tileInfo"]["lods"] if x["level"]==level)
    step = resolution * 256
    ox, oy = service["tileInfo"]["origin"]["x"], service["tileInfo"]["origin"]["y"]
    c0,c1 = math.floor((web[0]-ox)/step), math.floor((web[2]-ox)/step)
    r0,r1 = math.floor((oy-web[3])/step), math.floor((oy-web[1])/step)
    def fetch(rc):
        r,c=rc
        p=ROOT/f"data/raw/corridor/ortho-tiles/{level}-{r}-{c}.jpg"
        return r,c,p,download(f"{base}/tile/{level}/{r}/{c}",p,max_bytes=1_000_000)
    with ThreadPoolExecutor(max_workers=4) as pool:
        sources=list(pool.map(fetch,[(r,c) for r in range(r0,r1+1) for c in range(c0,c1+1)]))
    mosaic=np.zeros(((r1-r0+1)*256,(c1-c0+1)*256,3),np.uint8)
    for r,c,p,_ in sources:
        mosaic[(r-r0)*256:(r-r0+1)*256,(c-c0)*256:(c-c0+1)*256]=np.asarray(Image.open(p).convert("RGB"))
    transform=from_origin(bounds[0],bounds[3],pixel,pixel)
    size=round(span/pixel)
    dest=np.zeros((3,size,size),np.uint8)
    reproject(np.moveaxis(mosaic,2,0),dest,src_transform=from_origin(ox+c0*step,oy-r0*step,resolution,resolution),
              src_crs=3857,dst_crs=3157,dst_transform=transform,resampling=Resampling.bilinear)
    out=ROOT/"evidence/corridor/ortho-utm";out.mkdir(parents=True,exist_ok=True)
    Image.fromarray(np.moveaxis(dest,0,2)).save(out/f"{name}.png")
    with rasterio.open(out/f"{name}.tif","w",driver="GTiff",width=size,height=size,count=3,
        dtype="uint8",crs=3157,transform=transform,compress="deflate") as ds:ds.write(dest)
    save_json(out/f"{name}.json",dict(local_bounds_m=[bounds[0]-origin["easting"],bounds[1]-origin["northing"],bounds[2]-origin["easting"],bounds[3]-origin["northing"]],
        pixel_size_m=pixel,image_size=[size,size],pixel_to_local="x=left+(column+0.5)*pixel; y=top-(row+0.5)*pixel",
        source_crs=3857,output_crs=3157,reference_only=True,capture_period="2022-06-06/2022-07-01",
        attribution="City of Vancouver; Open Government Licence - Vancouver",sources=[s[3] for s in sources]))
    print(name,len(sources),str(out/f"{name}.png"),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("name");p.add_argument("east",type=float);p.add_argument("north",type=float)
    p.add_argument("--span",type=float,default=160);p.add_argument("--pixel",type=float,default=.1);a=p.parse_args()
    build(a.name,a.east,a.north,a.span,a.pixel)
