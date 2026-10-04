"""Render source polygons over City aerial references for manual review."""
from pathlib import Path
import hashlib
import json
from PIL import Image, ImageDraw
from shapely.geometry import shape,box

ROOT=Path(__file__).resolve().parents[2]
SOURCES=["public-spaces-brockton","public-spaces-central","public-spaces-south","named-lumberman-wide"]


def main():
    data=json.loads((ROOT/"data/derived/public-spaces/public-space-blockouts-local.geojson").read_text())
    output=ROOT/"evidence/public-spaces";output.mkdir(parents=True,exist_ok=True)
    records=[]
    for name in SOURCES:
        base=ROOT/"evidence/corridor/ortho-utm"/name
        meta=json.loads(base.with_suffix(".json").read_text())
        left,bottom,right,top=meta["local_bounds_m"];pixel=meta["pixel_size_m"]
        im=Image.open(base.with_suffix(".png")).convert("RGB");draw=ImageDraw.Draw(im)
        transform=lambda p:((p[0]-left)/pixel-.5,(top-p[1])/pixel-.5)
        included=[]
        for f in data["features"]:
            geom=shape(f["geometry"])
            if not geom.intersects(box(left,bottom,right,top)):continue
            p=f["properties"];color={"surface_patch":"lime","boundary_only":"yellow","line_reference":"cyan"}[p["display_mode"]]
            if geom.geom_type=="Polygon":draw.line([transform(x) for x in geom.exterior.coords],fill=color,width=2)
            else:draw.line([transform(x) for x in geom.coords],fill=color,width=2)
            anchor=geom.representative_point();xy=transform([anchor.x,anchor.y]);text=p["component_id"]
            if "Tennis_" in text:text=text.replace("Tennis_","T")
            if "PavilionGardenBed_" in text:text=text.replace("PavilionGardenBed_","G")
            draw.text(xy,text,fill=color,stroke_width=1,stroke_fill="black")
            included.append(f["id"])
        draw.rectangle((5,5,1250,40),fill="black")
        draw.text((10,10),"City 2022 image | green: surface patch; yellow: mixed site boundary; cyan: railway reference | OSM geometry, not survey certification",fill="white")
        path=output/(name+"-review.png");im.save(path)
        records.append({"source_metadata":base.with_suffix(".json").relative_to(ROOT).as_posix(),
                        "source_image_sha256":hashlib.sha256(base.with_suffix(".png").read_bytes()).hexdigest(),
                        "review_image":path.relative_to(ROOT).as_posix(),"components_visible":included,
                        "image_capture_period":"2022-06-06/2022-07-01","image_licence":"Open Government Licence - Vancouver"})
    (output/"visual-review-panels.json").write_text(json.dumps(records,indent=2)+"\n")
    print(json.dumps({"panels":len(records),"component_ids_in_panels":len(set(x for r in records for x in r['components_visible']))}))


if __name__=="__main__":main()
