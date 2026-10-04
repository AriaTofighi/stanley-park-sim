"""Create a source-pixel correction draft. Does not change any route or mesh."""
from pathlib import Path
import hashlib
import json
import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import LineString, Point

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    pick_path = ROOT / "manifests/m1-pavement-correction-source-picks.json"
    picks = json.loads(pick_path.read_text())
    route_path = ROOT / "data/derived/paved-circuit-runtime.json"
    route = json.loads(route_path.read_text())
    xyz = np.array(route["points_local_m"])
    runtime = np.array(route["chainage_runtime_m"])
    source = np.array(route["chainage_source_m"])
    line = LineString(xyz[:, :2])
    with np.load(ROOT / "data/derived/paved-circuit-proposal.npz") as profile:
        widths = profile["width_m"].copy()
    records = []
    for row in picks["records"]:
        meta = json.loads((ROOT / row["source_metadata"]).read_text())
        left, bottom, right, top = meta["local_bounds_m"]
        pixel_m = meta["pixel_size_m"]
        def local(pixel):
            return np.array([left+(pixel[0]+.5)*pixel_m, top-(pixel[1]+.5)*pixel_m])
        def pixel(point):
            return ((point[0]-left)/pixel_m-.5, (top-point[1])/pixel_m-.5)
        image = Image.open(ROOT / row["source_image"]).copy()
        draw = ImageDraw.Draw(image)
        visible = (xyz[:,0] > left) & (xyz[:,0] < right) & (xyz[:,1] > bottom) & (xyz[:,1] < top)
        for i in np.flatnonzero(visible[:-1] & visible[1:]):
            draw.line([pixel(xyz[i]),pixel(xyz[i+1])], fill="red", width=2)
        bands = []
        for endpoints in row["bands_edge_pixels_xy"]:
            a,b = map(local,endpoints)
            mid = (a+b)/2
            direction = (b-a)/np.linalg.norm(b-a)
            crossline = LineString([mid-direction*40,mid+direction*40])
            cross = line.intersection(crossline)
            points = [cross] if cross.geom_type == "Point" else [g for g in getattr(cross,"geoms",[]) if g.geom_type == "Point"]
            if not points:
                raise ValueError(f"No route intersection: {row['id']} {endpoints}")
            hit = min(points, key=lambda p: p.distance(Point(mid)))
            xy = np.array(hit.coords[0])
            index = int(np.argmin(np.linalg.norm(xyz[:, :2]-xy,axis=1)))
            tangent = xyz[min(len(xyz)-1,index+2),:2] - xyz[max(0,index-2),:2]
            tangent /= np.linalg.norm(tangent)
            normal = np.array([-tangent[1],tangent[0]])
            # Route stations are 3D distances; use the local segment projection.
            i = max(0,index-1)
            j = min(len(xyz)-1,index+1)
            segment = xyz[j,:2]-xyz[i,:2]
            t = np.clip((xy-xyz[i,:2])@segment/(segment@segment),0,1)
            station = float(source[i]+t*(source[j]-source[i]))
            ds = float(runtime[i]+t*(runtime[j]-runtime[i]))
            width = float(abs((b-a)@normal))
            offset = float((mid-xy)@normal)
            bands.append({"source_station_m":station,"runtime_station_m":ds,
                          "edge_pixels_xy":endpoints,"edges_local_m":[a.tolist(),b.tolist()],
                          "source_midpoint_local_m":mid.tolist(),"current_route_local_m":xy.tolist(),
                          "left_normal_xy":normal.tolist(),"midpoint_shift_along_left_normal_m":offset,
                          "estimated_width_perpendicular_to_current_route_m":width,
                          "current_profile_width_m":float(widths[index]),
                          "approx_current_strip_excess_perpendicular_m":max(0,abs(offset)+widths[index]/2-width/2)})
            draw.line(endpoints,fill="cyan",width=2)
            q=pixel(mid);draw.ellipse((q[0]-3,q[1]-3,q[0]+3,q[1]+3),fill="yellow")
        bands.sort(key=lambda b:b["source_station_m"])
        selected = row["correction_band_indices_inclusive"]
        correction_bands = bands[selected[0]:selected[1]+1]
        correction_knots = [b["source_midpoint_local_m"] for b in correction_bands]
        if row["id"] == "XY20_LOST_LAGOON_PAVEMENT":
            # The road after the narrow path has a wide pavement envelope. Use
            # only the inward correction needed for a 3 m strip, then rejoin.
            correction_bands = bands
            correction_knots = []
            for index, band in enumerate(bands):
                if index <= selected[1]:
                    target = band["source_midpoint_local_m"]
                else:
                    excess = band["approx_current_strip_excess_perpendicular_m"]
                    shift = excess + .15 if excess > picks["pixel_pick_uncertainty_m"] else 0.
                    shift *= np.sign(band["midpoint_shift_along_left_normal_m"])
                    target = (np.array(band["current_route_local_m"])+np.array(band["left_normal_xy"])*shift).tolist()
                correction_knots.append(target)
        # Exact endpoint joins are retained where source edge uncertainty allows
        # the complete old 3 m strip. Interior source midpoints stay fixed.
        for i in [0,len(correction_bands)-1]:
            if correction_bands[i]["approx_current_strip_excess_perpendicular_m"] <= picks["pixel_pick_uncertainty_m"]:
                correction_knots[i] = correction_bands[i]["current_route_local_m"]
        draw.line([pixel(b["source_midpoint_local_m"]) for b in bands],fill="yellow",width=3)
        output = f"evidence/m1-source-review/{row['id']}-correction-review.png"
        image.save(ROOT/output)
        records.append({**row,"source_image_sha256":sha(ROOT/row["source_image"]),
                        "source_metadata_sha256":sha(ROOT/row["source_metadata"]),
                        "source_station_window_m":[bands[0]["source_station_m"],bands[-1]["source_station_m"]],
                        "correction_source_window_m":[correction_bands[0]["source_station_m"],correction_bands[-1]["source_station_m"]],
                        "correction_centre_knots_local_m":correction_knots,
                        "correction_source_knots_m":[b["source_station_m"] for b in correction_bands],
                        "draft_only":True,"review_overlay":output,"bands":bands,
                        "integration":"Fit a smooth centre curve inside these bicycle edge bands. Keep measured Z separate; re-sample ground after XY changes. Rejoin only where the complete retained strip fits the source band. Review before applying; these points are not an as-built survey."})
    result={"purpose":"Finite local correction draft; no route edits", "apply":False,
            "route_sha256":sha(route_path),"picks_sha256":sha(pick_path),
            "pixel_pick_uncertainty_m":picks["pixel_pick_uncertainty_m"],
            "absolute_accuracy_accepted":False,"records":records}
    (ROOT/"manifests/m1-pavement-correction-draft.json").write_text(json.dumps(result,indent=2)+"\n")
    for row in records:
        print(row["id"], row["source_station_window_m"])
        for b in row["bands"]:
            print(round(b["source_station_m"],1), "shift",round(b["midpoint_shift_along_left_normal_m"],2),"width",round(b["estimated_width_perpendicular_to_current_route_m"],2),"excess",round(b["approx_current_strip_excess_perpendicular_m"],2))


if __name__ == "__main__":
    main()
