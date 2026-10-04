"""Build source-only panels at frozen review areas from cached City tiles.

No tile download, geometry edit, source feature pick or acceptance is performed.
The panels have pixel coordinates so a reviewer can lock the reference before
seeing a model residual. The level of the cached imagery is recorded explicitly.
"""
from pathlib import Path
import hashlib
import json
import math

import numpy as np
from PIL import Image, ImageDraw
from pyproj import Transformer
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evidence/m1-source-review"
TILES = ROOT / "data/raw/corridor/ortho-tiles"
SPAN = 100.0
PIXEL = 0.1


def build_panel(item, service):
    x, y = item["search_anchor_local_m"][:2]
    bounds = [489600+x-SPAN/2, 5461100+y-SPAN/2, 489600+x+SPAN/2, 5461100+y+SPAN/2]
    web = Transformer.from_crs(3157, 3857, always_xy=True).transform_bounds(*bounds)
    ox, oy = service["tileInfo"]["origin"].values()
    dest = np.zeros((3,1000,1000), dtype=np.uint8)
    coverage = np.zeros((1000,1000), dtype=np.uint8)
    all_tiles = []
    levels = []
    for level in [18, 19, 20, 21]:
        res = next(r["resolution"] for r in service["tileInfo"]["lods"] if r["level"] == level)
        step = res * 256
        c0, c1 = math.floor((web[0]-ox)/step), math.floor((web[2]-ox)/step)
        r0, r1 = math.floor((oy-web[3])/step), math.floor((oy-web[1])/step)
        tiles = [(r,c,TILES/f"{level}-{r}-{c}.jpg") for r in range(r0,r1+1) for c in range(c0,c1+1)]
        tiles = [(r,c,p) for r,c,p in tiles if p.is_file()]
        if not tiles:
            continue
        mosaic = np.zeros(((r1-r0+1)*256, (c1-c0+1)*256, 3), dtype=np.uint8)
        mask = np.zeros(mosaic.shape[:2],dtype=np.uint8)
        for r,c,p in tiles:
            mosaic[(r-r0)*256:(r-r0+1)*256, (c-c0)*256:(c-c0+1)*256] = np.array(Image.open(p).convert("RGB"))
            mask[(r-r0)*256:(r-r0+1)*256, (c-c0)*256:(c-c0+1)*256] = level
        layer = np.zeros_like(dest)
        layer_mask = np.zeros_like(coverage)
        warp = dict(src_transform=from_origin(ox+c0*256*res,oy-r0*256*res,res,res),src_crs=3857,
                    dst_crs=3157,dst_transform=from_origin(bounds[0],bounds[3],PIXEL,PIXEL))
        reproject(np.moveaxis(mosaic,2,0),layer,resampling=Resampling.bilinear,**warp)
        reproject(mask,layer_mask,resampling=Resampling.nearest,**warp)
        use = layer_mask > 0
        dest[:,use] = layer[:,use]
        coverage[use] = level
        all_tiles.extend(tiles)
        levels.append(level)
    if not np.any(coverage):
        return {"id": item["id"], "status": "cached_ortho_missing"}
    pic = Image.fromarray(np.moveaxis(dest,0,2))
    path = OUT/f"{item['id']}-source.png"
    pic.save(path)
    Image.fromarray(coverage).save(OUT/f"{item['id']}-coverage.png")
    return {"id":item["id"], "status":"source_panel_ready", "source_panel":path.relative_to(ROOT).as_posix(),
            "local_bounds_m":[bounds[0]-489600,bounds[1]-5461100,bounds[2]-489600,bounds[3]-5461100],
            "output_pixel_size_m":PIXEL,"output_size_px":[1000,1000],"cached_tile_level":max(levels),
            "cached_levels_used":levels,"coverage_fraction":float(np.mean(coverage>0)),
            "coverage_map":(OUT/f"{item['id']}-coverage.png").relative_to(ROOT).as_posix(),
            "coverage_map_values":"0 is no source; values 18-21 identify cached tile level for each pixel",
            "pixel_to_local":"x=left+(column+0.5)*0.1; y=top-(row+0.5)*0.1",
            "capture_period":"2022-06-06/2022-07-01", "licence":"Open Government Licence - Vancouver",
            "source_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "tiles":[{"path":p.relative_to(ROOT).as_posix(),"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for _,_,p in all_tiles]}


def main():
    OUT.mkdir(exist_ok=True, parents=True)
    (OUT/".gitignore").write_text("*.png\n",encoding="utf8")
    config = json.loads((ROOT/"manifests/m1-control-validation-protocol.json").read_text(encoding="utf8"))
    service = json.loads((ROOT/"data/raw/corridor/orthophoto-service.json").read_text(encoding="utf8"))
    records = [build_panel(item,service) for item in config["horizontal_reviews"]+config["vertical_reviews"]]
    (OUT/"source-panels.json").write_text(json.dumps({"scope":"Source-only review panels; no model overlay or control acceptance",
        "absolute_accuracy_accepted":False,"records":records},indent=2)+"\n",encoding="utf8")
    for prefix in ["XY", "Z"]:
        items = [r for r in records if r["id"].startswith(prefix) and r["status"]=="source_panel_ready"]
        for start in range(0,len(items),4):
            sheet = Image.new("RGB",(1400,1500),"white")
            draw = ImageDraw.Draw(sheet)
            for i,r in enumerate(items[start:start+4]):
                col,row = i%2,i//2; x0,y0 = col*700,row*750+40
                pic = Image.open(ROOT/r["source_panel"]).resize((700,700))
                sheet.paste(pic,(x0,y0));draw.text((x0+10,y0-30),f"{r['id']} | cached L{r['cached_tile_level']} | 100m square | source only",fill="black")
                for p in [0,250,500,750]:
                    q=round(p*.7); draw.text((x0+q+2,y0+2),str(p),fill="yellow")
                    draw.text((x0+2,y0+q+10),str(p),fill="yellow")
            sheet.save(OUT/f"{prefix}-source-sheet-{start//4+1}.png")
    print(json.dumps({"panels":len(records),"ready":sum(r['status']=='source_panel_ready' for r in records),
                     "missing":[r['id'] for r in records if r['status']!='source_panel_ready']}))


if __name__ == "__main__":
    main()
