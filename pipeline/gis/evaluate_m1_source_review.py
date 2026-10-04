"""Compare frozen manual source picks with the current route. Never edit geometry."""
from pathlib import Path
import hashlib
import json
import math

import numpy as np
import shapely
from PIL import Image, ImageDraw
from shapely.geometry import LineString, Point

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evidence/m1-source-review"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    route_path = ROOT / "data/derived/paved-circuit-runtime.json"
    route = json.loads(route_path.read_text(encoding="utf8"))
    xyz = np.array(route["points_local_m"])
    chainage = np.array(route["chainage_runtime_m"])
    line = LineString(xyz[:, :2])
    footprint = line.buffer(float(route["development_width_m"]) / 2)
    surface_path = ROOT / "manifests/surface-model.json"
    surface = json.loads(surface_path.read_text(encoding="utf8"))
    pavement_triangles = []
    mesh_inputs = []
    for row in surface["pavement"]:
        if row["role"] != "pavement":
            continue
        mesh_path = ROOT / row["path"]
        if digest(mesh_path) != row["sha256"]:
            raise ValueError(f"Pavement source changed: {mesh_path}")
        with np.load(mesh_path) as mesh:
            vertices = mesh["vertices"] + mesh["anchor"]
            pavement_triangles.extend(shapely.polygons(vertices[mesh["faces"], :2]))
        mesh_inputs.append({"path": row["path"], "sha256": row["sha256"]})
    actual_footprint = shapely.union_all(pavement_triangles)
    if "width_m" in route:
        widths = np.asarray(route["width_m"], dtype=float)
        width_source = "Effective width_m saved in current runtime route"
    else:
        with np.load(ROOT / "data/derived/paved-circuit-proposal.npz") as profile:
            widths = profile["width_m"].copy()
        width_source = "Original proposal widths; runtime has no effective width field"
    if len(widths) != len(xyz) or not np.isfinite(widths).all():
        raise ValueError("Effective width profile does not match the runtime route")
    picks_path = ROOT / "manifests/m1-source-feature-picks.json"
    picks = json.loads(picks_path.read_text(encoding="utf8"))
    panels = {r["id"]:r for r in json.loads((OUT/"source-panels.json").read_text(encoding="utf8"))["records"]}
    roster = json.loads((ROOT/"manifests/m1-control-validation-protocol.json").read_text(encoding="utf8"))
    height_reference_route_hash = next(r["sha256"] for r in roster["inputs"] if r["path"] == "data/derived/paved-circuit-runtime.json")
    height_route_unchanged = digest(route_path) == height_reference_route_hash
    xy_results = []
    for pick in picks["records"]:
        panel = panels[pick["id"]]
        if digest(ROOT/panel["source_panel"]) != pick["source_panel_sha256"]:
            raise ValueError(f"Source pixels changed after picks were locked: {pick['id']}")
        left,bottom,right,top = panel["local_bounds_m"]
        def local(pixel):
            return np.array([left+(pixel[0]+.5)*.1,top-(pixel[1]+.5)*.1])
        def pixel(point):
            return ((point[0]-left)/.1-.5,(top-point[1])/.1-.5)
        result = dict(pick)
        image = Image.open(ROOT/panel["source_panel"]).copy()
        draw = ImageDraw.Draw(image)
        clipped = actual_footprint.intersection(shapely.box(left, bottom, right, top))
        parts = [clipped] if clipped.geom_type == "Polygon" else list(getattr(clipped, "geoms", []))
        for part in parts:
            if part.geom_type == "Polygon":
                draw.line([pixel(p) for p in part.exterior.coords], fill="magenta", width=2)
        visible = ((xyz[:,0]>left-10)&(xyz[:,0]<right+10)&(xyz[:,1]>bottom-10)&(xyz[:,1]<top+10))
        for i in np.flatnonzero(visible[:-1]&visible[1:]):
            draw.line([pixel(xyz[i]),pixel(xyz[i+1])],fill="red",width=3)
        result["bands"] = []
        for band in pick["source_bands"]:
            a,b = map(local,band["edge_pixels_xy"])
            middle=(a+b)/2
            unit=(b-a)/np.linalg.norm(b-a)
            cross=LineString([middle-unit*50,middle+unit*50])
            crossing=line.intersection(cross)
            candidates=([crossing] if crossing.geom_type=="Point" else
                        [g for g in getattr(crossing,"geoms",[]) if g.geom_type=="Point"])
            entry=dict(band,reference_edges_local_m=[a.tolist(),b.tolist()],model_intersection_local_m=None)
            if candidates:
                hit=min(candidates,key=lambda p:p.distance(Point(middle)))
                hit_xy=np.array(hit.coords[0]);length=float(np.linalg.norm(b-a));along=float((hit_xy-a)@unit)
                entry.update(model_intersection_local_m=hit_xy.tolist(),
                             centre_offset_from_reference_midpoint_m=float((hit_xy-middle)@unit),
                             centre_outside_reference_band_m=max(0.,-along,along-length),
                             source_intercept_length_m=length)
                nearest = int(np.argmin(np.linalg.norm(xyz[:, :2] - hit_xy, axis=1)))
                entry["nearest_source_station_m"] = route["chainage_source_m"][nearest]
                entry["nearest_runtime_station_m"] = float(chainage[nearest])
                entry["actual_profile_width_m"] = float(widths[nearest])
                actual_clip = actual_footprint.intersection(cross)
                actual_parts = [actual_clip] if actual_clip.geom_type == "LineString" else [g for g in getattr(actual_clip, "geoms", []) if g.geom_type == "LineString"]
                if actual_parts:
                    actual_part = min(actual_parts, key=lambda p: p.distance(hit))
                    actual_q = np.array(actual_part.coords)
                    actual_lo, actual_hi = sorted([(actual_q[0]-a)@unit, (actual_q[-1]-a)@unit])
                    entry["actual_mesh_excess_past_source_band_along_transect_m"] = float(max(0., -actual_lo, actual_hi-length))
                    entry["actual_mesh_crossline_edges_local_m"] = [actual_q[0].tolist(), actual_q[-1].tolist()]
                clip=footprint.intersection(cross)
                parts=[clip] if clip.geom_type=="LineString" else [g for g in getattr(clip,"geoms",[]) if g.geom_type=="LineString"]
                if parts:
                    part=min(parts,key=lambda p:p.distance(hit));q=np.array(part.coords)
                    lo,hi=sorted([(q[0]-a)@unit,(q[-1]-a)@unit])
                    entry["authored_3m_strip_excess_past_source_band_m"]=float(max(0.,-lo,hi-length))
                draw.ellipse((pixel(hit_xy)[0]-5,pixel(hit_xy)[1]-5,pixel(hit_xy)[0]+5,pixel(hit_xy)[1]+5),fill="red")
            else:
                entry["diagnostic"]="No model centre intersection within 100 m source transect"
            draw.line(band["edge_pixels_xy"],fill="cyan",width=3)
            for pt in band["edge_pixels_xy"]:
                draw.ellipse((pt[0]-4,pt[1]-4,pt[0]+4,pt[1]+4),fill="yellow")
            draw.text((band["edge_pixels_xy"][0][0]+5,band["edge_pixels_xy"][0][1]+5),band["role"],fill="yellow")
            result["bands"].append(entry)
        result["overlay"]=f"evidence/m1-source-review/{pick['id']}-comparison.png"
        image.save(ROOT/result["overlay"])
        xy_results.append(result)

    z_results=[]
    groups={}
    for item in roster["vertical_reviews"]:
        x,y=item["search_anchor_local_m"]
        tile=f"lidar2022_{math.floor((x+489600)/1000)*1000}_{math.floor((y+5461100)/1000)*1000}.npz"
        groups.setdefault(tile,[]).append(item)
    visibility={1:"visible pavement at junction",2:"canopy obscures the exact pavement sample",3:"pavement partly obscured at inner road edge",
                4:"canopy obscures the exact pavement sample",5:"visible waterfront pavement",6:"visible waterfront pavement",
                7:"visible pavement near Siwash Rock",8:"visible pavement at Third Beach",9:"canopy obscures the exact pavement sample",10:"visible path north of the planted median"}
    for tile,items in groups.items():
        file=ROOT/"data/derived"/tile
        with np.load(file) as package:
            ground=package["ground"]
        for item in items:
            x,y=item["search_anchor_local_m"]
            take=(abs(ground[:,0]-x)<=.6)&(abs(ground[:,1]-y)<=.6)
            near=ground[take,:3].astype(float)
            radius=np.linalg.norm(near[:,:2]-[x,y],axis=1)
            near=near[radius<=.6]
            record=dict(item,source_panel=panels[item["id"]]["source_panel"],
                        visual_source_observation=visibility[int(item["id"][-2:])],
                        temporal_surface_identity_verified=False,
                        city_point_source=file.relative_to(ROOT).as_posix(),
                        city_ground_radius_m=.6,city_ground_point_count=len(near))
            # Keep the original control anchor. A route-file hash can change
            # while this local segment remains exactly the same. Project the
            # fixed XY onto every current segment and retain the distance.
            delta = xyz[1:, :2] - xyz[:-1, :2]
            t = np.clip(np.sum((np.array([x, y]) - xyz[:-1, :2]) * delta, axis=1) / np.maximum(np.sum(delta * delta, axis=1), 1e-20), 0., 1.)
            projected = xyz[:-1, :2] + delta * t[:, None]
            segment = int(np.argmin(np.linalg.norm(projected - [x, y], axis=1)))
            fixed_distance = float(np.linalg.norm(projected[segment] - [x, y]))
            current_height = float(xyz[segment, 2] + t[segment] * (xyz[segment+1, 2] - xyz[segment, 2]))
            height_change = current_height - item["authored_height_m"]
            record.update(current_route_closest_xy_m=projected[segment].tolist(), current_route_distance_from_fixed_anchor_m=fixed_distance,
                          current_route_height_m=current_height, current_route_height_change_m=height_change,
                          authored_height_is_current_route=fixed_distance < 1e-7 and abs(height_change) < 1e-7)
            if fixed_distance < 1e-7:
                record["current_route_minus_2016_m"] = current_height - item["reference_2016_height_m"]
            else:
                record["height_repeat_limit"] = "Current centreline moved from the fixed height anchor. Keep the original comparison historical; do not transfer it to another XY."
            if len(near)>=8:
                matrix=np.column_stack((near[:,0]-x,near[:,1]-y,np.ones(len(near))))
                fit,residual,rank,_=np.linalg.lstsq(matrix,near[:,2],rcond=None)
                station=float(chainage[int(np.argmin(np.linalg.norm(xyz[:,:2]-[x,y],axis=1)))])
                endpoints=np.array([[np.interp(station+d,chainage,xyz[:,i]) for i in range(3)] for d in [-2.5,2.5]])
                tangent=endpoints[1,:2]-endpoints[0,:2]; tangent/=np.linalg.norm(tangent)
                authored_grade=(endpoints[1,2]-endpoints[0,2])/np.linalg.norm(endpoints[1,:2]-endpoints[0,:2])*100
                record.update(city_plane_rank=int(rank),city_plane_height_m=float(fit[2]),
                              city_plane_residual_rms_m=float(np.sqrt(np.mean((matrix@fit-near[:,2])**2))),
                              authored_minus_city_plane_m=float(item["authored_height_m"]-fit[2]),
                              authored_grade_percent=float(authored_grade),city_plane_grade_percent=float(fit[:2]@tangent*100),
                              grade_difference_percentage_points=float(authored_grade-fit[:2]@tangent*100))
                if fixed_distance < 1e-7:
                    record["current_route_minus_city_plane_m"] = float(current_height - fit[2])
            else:
                record["city_plane_status"]="Insufficient classified ground returns; no fit accepted"
            record["accepted_independent_control"]=False
            z_results.append(record)
        del ground
    z_results.sort(key=lambda r:r["id"])
    report={"scope":"Fixed 20 XY / 10 height blockout review; no geometry edit or independent survey certification",
            "inputs":[{"path":p.relative_to(ROOT).as_posix(),"sha256":digest(p)} for p in [route_path,picks_path,surface_path,ROOT/"data/derived/paved-circuit-proposal.npz"]],
            "actual_pavement_mesh_inputs":mesh_inputs,
            "width_source":width_source,
            "footprint_note":"Magenta outlines and actual_mesh values use the union of saved pavement triangles. The old authored_3m_strip values are comparison diagnostics only; they do not represent local width changes. Transect excess is not perpendicular clearance.",
            "xy_selection":"Source-only manual pavement-band intercepts locked before residual calculation; all 20 areas retained",
            "xy_result_limits":"A bicycle_probable label is image interpretation. Walking strips and roadway candidates are separate. Midpoint offsets do not prove a bike-lane error where lane use or edges are unclear.",
            "height_result_limits":"2016 comparison is a separate acquisition with unverified local accuracy. City 2022 local plane is source-fit consistency, not independent control. Historical surface identity is unverified.",
            "height_reference_route_sha256":height_reference_route_hash,
            "height_route_file_unchanged":height_route_unchanged,
            "all_frozen_authored_heights_current":all(r["authored_height_is_current_route"] for r in z_results),
            "absolute_accuracy_accepted":False,"horizontal_reviews":xy_results,"height_reviews":z_results}
    (OUT/"review-results.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf8")
    print(json.dumps({"xy_locations":len(xy_results),"height_locations":len(z_results),
                      "bicycle_probable_comparisons":[{"id":r['id'],"offset_m":round(b.get('centre_offset_from_reference_midpoint_m',float('nan')),2),
                          "outside_band_m":round(b.get('centre_outside_reference_band_m',float('nan')),2)}
                         for r in xy_results for b in r['bands'] if b['role']=='bicycle_probable'],
                      "city_plane_excess_015m":[r['id'] for r in z_results if abs(r.get('authored_minus_city_plane_m',0))>.15]}))


if __name__ == "__main__":
    main()
