"""Georeferenced City imagery/DTM overlays for correction review, not textures."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image
from pyproj import Transformer
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline/gis"))
from acquire_sources import download, save_json
RAW = ROOT / "data/raw/corridor"
OUT = ROOT / "evidence/corridor"
OUT.mkdir(parents=True, exist_ok=True)
origin = json.loads((ROOT / "manifests/world-origin.json").read_text())
routes = json.loads((ROOT / "data/routes/derived/park_routes.json").read_text())
service = json.loads((RAW / "orthophoto-service.json").read_text())
url = json.loads((RAW / "orthophoto-portal-item.json").read_text())["url"]
to_web = Transformer.from_crs(3157, 3857, always_xy=True)
to_local = Transformer.from_crs(3857, 3157, always_xy=True)
grid = np.load(ROOT / "data/derived/terrain_park.npz")

def plot_site(name, east, north, half_width=105):
    bounds = to_web.transform_bounds(east + origin["easting"] - half_width,
                                   north + origin["northing"] - half_width,
                                   east + origin["easting"] + half_width,
                                   north + origin["northing"] + half_width)
    level = 19
    resolution = next(x["resolution"] for x in service["tileInfo"]["lods"] if x["level"] == level)
    span = resolution * 256
    ox, oy = service["tileInfo"]["origin"]["x"], service["tileInfo"]["origin"]["y"]
    c0,c1 = math.floor((bounds[0]-ox)/span), math.floor((bounds[2]-ox)/span)
    r0,r1 = math.floor((oy-bounds[3])/span), math.floor((oy-bounds[1])/span)
    tiles = [(r,c) for r in range(r0,r1+1) for c in range(c0,c1+1)]
    def fetch(tile):
        r,c = tile
        path = RAW / "ortho-tiles" / f"{level}-{r}-{c}.jpg"
        rec = download(f"{url}/tile/{level}/{r}/{c}", path, max_bytes=1_000_000)
        return r,c,path,rec
    with ThreadPoolExecutor(max_workers=4) as pool:
        images = list(pool.map(fetch,tiles))
    mosaic = np.zeros(((r1-r0+1)*256,(c1-c0+1)*256,3),dtype=np.uint8)
    for r,c,path,record in images:
        mosaic[(r-r0)*256:(r-r0+1)*256,(c-c0)*256:(c-c0+1)*256] = np.asarray(Image.open(path).convert("RGB"))
    extent = [ox+c0*span,ox+(c1+1)*span,oy-(r1+1)*span,oy-r0*span]
    fig, ax = plt.subplots(figsize=(11,10),dpi=150)
    ax.imshow(mosaic,extent=extent)
    for edge in routes["edges"]:
        p=np.asarray(edge["coordinates_local_xy_m"])
        wx,wy=to_web.transform(p[:,0]+origin["easting"],p[:,1]+origin["northing"])
        if max(wx)<bounds[0] or min(wx)>bounds[2] or max(wy)<bounds[1] or min(wy)>bounds[3]: continue
        ax.plot(wx,wy,color="#ffdd45",linewidth=1,alpha=.9)
        k=len(wx)//2
        if bounds[0]<wx[k]<bounds[2] and bounds[1]<wy[k]<bounds[3]:
            ax.text(wx[k],wy[k],str(edge["source_object_id"]),color="white",fontsize=8,bbox=dict(facecolor="black",alpha=.7,pad=2))
    ax.set_xlim(bounds[0],bounds[2]); ax.set_ylim(bounds[1],bounds[3]); ax.set_aspect("equal")
    ax.set_title(f"{name}: City route lines over 2022 City orthophoto\nReference only; yellow lines are approximate catalogue geometry")
    ax.set_xlabel("Web Mercator easting (m); measure using the project UTM grid")
    fig.text(.06,.01,"City of Vancouver imagery, June-July 2022. Reference use; no imagery is placed in the runtime.",fontsize=8)
    fig.savefig(OUT/f"{name}.png",bbox_inches="tight"); plt.close(fig)
    save_json(OUT/f"{name}.json",dict(site_local_m=[east,north],extent_3857=extent,bounds_3857=bounds,
        capture_period="2022-06-06/2022-07-01",reference_only=True,tiles=[v[3] for v in images]))
    print(name,len(images),flush=True)

if __name__ == "__main__":
    plot_site("entrance",517.55,-817.01)
    edge = next(x for x in routes["edges"] if x["source_object_id"]==2909)
    p=np.asarray(edge["xyz_local_m"])
    k=int(np.argmax(np.abs(np.diff(p[:,2]))/np.linalg.norm(np.diff(p[:,:2],axis=0),axis=1)))
    plot_site("northwest-grade-spike",*p[k,:2],half_width=95)
    boundary=shape(json.loads((ROOT/"data/derived/park_boundary.geojson").read_text())["features"][0]["geometry"])
    fig,ax=plt.subplots(figsize=(11,9),dpi=140)
    ax.imshow(grid["z"],origin="lower",extent=[grid["x"][0],grid["x"][-1],grid["y"][0],grid["y"][-1]],vmin=-3,vmax=80,cmap="terrain")
    if boundary.geom_type=="Polygon": ax.plot(*boundary.exterior.xy,color="magenta",linewidth=1)
    for feature in json.loads((ROOT/"data/derived/shoreline.geojson").read_text())["features"]:
        coast=shape(feature["geometry"])
        for line in coast.geoms if hasattr(coast,"geoms") else [coast]: ax.plot(*line.xy,color="cyan",linewidth=1)
    loop=np.asarray(routes["main_circuit"]["xyz_local_m"]); ax.plot(loop[:,0],loop[:,1],color="black",linewidth=.7)
    ax.set_xlim(grid["x"][0],grid["x"][-1]); ax.set_ylim(grid["y"][0],grid["y"][-1]); ax.set_aspect("equal")
    ax.set_title("2013 DTM, 2002 City shoreline (cyan), park boundary (magenta), main circuit (black)")
    fig.savefig(OUT/"shore-terrain.png",bbox_inches="tight")
