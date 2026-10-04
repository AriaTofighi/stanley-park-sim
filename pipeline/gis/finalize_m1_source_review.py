"""Write the human-readable fixed review and update its acceptance metadata."""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]


def load(path):
    return json.loads((ROOT/path).read_text(encoding="utf8"))


def save(path,value):
    (ROOT/path).write_text(json.dumps(value,indent=2)+"\n",encoding="utf8")


def digest(path):
    return hashlib.sha256((ROOT/path).read_bytes()).hexdigest()


def main():
    report=load("evidence/m1-source-review/review-results.json")
    repeat = not report.get("height_route_file_unchanged", True)
    repeat_pass = repeat and report.get("all_frozen_authored_heights_current", False)
    for area in report["horizontal_reviews"]:
        if area["id"] in ["XY_REVIEW_04", "XY_REVIEW_20"]:
            band = next(b for b in area["bands"] if b["role"] == "bicycle_probable")
            repeat_pass &= band["actual_mesh_excess_past_source_band_along_transect_m"] <= .25
    if not repeat_pass:
        raise ValueError("This repeat has not passed the fixed XY04/20 and unchanged-height checks; retain its JSON and resolve it before writing a passing summary")
    max_grade_difference = max(abs(z.get("grade_difference_percentage_points", 0.)) for z in report["height_reviews"])
    rows=[]
    text=["# M1 fixed source review", "", "Review date: 27 September 2026. No application test was run. This is the fixed source-to-model repeat after the XY04/20 correction, using the v15 saved pavement triangles. It does not certify absolute survey accuracy.", "",
          "The user approved M1 with recorded accuracy limits. See plan section 13.7 and `M1-MEASUREMENT-EXCEPTIONS.md`. Accepted independent survey controls remain zero. The two corrected source comparisons now pass their 0.25 m edge-pick uncertainty check. Blender and runtime inspection are separate acceptance work.", "",
          "All 20 fixed XY areas and all ten fixed height areas are retained. Source-only pixels were picked before the route was compared. The ten probable bicycle-band centre intersections fall inside their picked bands. Four areas have canopy-obscured bicycle pavement; two are junctions; two have only combined pavement; one is a partly visible inner lane and one is an inner roadway candidate. These are 20 reviewed areas, not 20 independent hard-feature controls.", "",
          "## XY observations", "", "Positive midpoint offset follows the direction from the first picked edge to the second. The excess uses the actual saved pavement triangles; the width field uses the current effective runtime profile. Excess is measured along the image transect, not perpendicular to the path. Width and edge picks remain estimates. Walking bands are retained separately in the JSON and CSV; a distance from the bicycle centre to the walking path is not a bicycle error.", "",
          "| Area | Source interpretation | Bicycle centre offset from picked midpoint (m) | Actual strip excess along transect (m) |", "|---|---|---:|---:|"]
    for area in report["horizontal_reviews"]:
        probable=[b for b in area["bands"] if b["role"]=="bicycle_probable"]
        if probable:
            b=probable[0]
            values=[f"{b['centre_offset_from_reference_midpoint_m']:+.2f}",f"{b['actual_mesh_excess_past_source_band_along_transect_m']:.2f}"]
        else:values=["Not accepted as a unique bicycle band","—"]
        text.append(f"| {area['id']} | {area['status']} | {values[0]} | {values[1]} |")
        for b in area["bands"]:
            rows.append({"area":area["id"],"status":area["status"],"role":b["role"],"source_station_m":b.get("nearest_source_station_m"),"centre_offset_m":b.get("centre_offset_from_reference_midpoint_m"),"centre_outside_band_m":b.get("centre_outside_reference_band_m"),"actual_width_m":b.get("actual_profile_width_m"),"actual_transect_excess_m":b.get("actual_mesh_excess_past_source_band_along_transect_m"),"source_panel":area["source_panel"]})
    with (ROOT/"evidence/m1-source-review/xy-review.csv").open("w",newline="",encoding="utf8") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    text += ["", "The original XY04 and XY20 placement failures are preserved in `evidence/m1-source-review/pre-v14/`, with a hash index and the original comparison images. The fixed source PNGs and picks are unchanged. The source windows are 1355.234–1464.147 m at Brockton and 8931.185–9041.304 m south of Lost Lagoon. The new actual triangle comparisons give XY04 0.183 m transect excess and XY20 0.000 m. Both are within the documented 0.25 m source-edge pick uncertainty. Both repeated images were opened and inspected.", "",
             "`pipeline/gis/refine_pavement_alignment.py` supplies endpoint-preserving curves, local estimated width changes and ground refits. Its retained review checks the edges between every fixed source knot, at 0.25 m spacing. Maximum edge distance outside the source envelope is 0.163 m at XY04 and 0.229 m at XY20; all 28 fixed transects pass. Initial constant-width and taper failures remain in `evidence/m1-pavement-alignment/`. This is a local source-fit result, not an independent survey result.", "",
             "XY02/03 must not be moved to the exposed outer pavement. The inner bicycle candidate is under canopy. XY09 retains 0.632 m and XY15 retains 0.350 m excess beyond an inferred bicycle band. Both images were reopened: the excess enters the adjoining paved walking band, not a clear grass separator. They remain lane-width allocation limits, not passed lane-boundary checks. Other smaller edge excesses remain in the table. None proves absolute survey error.", "", "## Height observations", "",
             "The 2016 acquisition is separate but has no verified local accuracy certificate or paired historical surface inspection. City 2022 planes are checks against the same data used to build the route. A plane fit requires at least eight classified ground points within 0.6 m. All ten locations remain; Z09 has five points and no accepted fit.", "",
             "| Area | City ground points | Model minus City plane (m) | Plane RMS (m) | Grade difference (percentage points) | Model minus 2016 (m) |", "|---|---:|---:|---:|---:|---:|"]
    zrows=[]
    for z in report["height_reviews"]:
        value=lambda key,d=3: f"{z[key]:+.{d}f}" if key in z else "Unfit"
        text.append(f"| {z['id']} | {z['city_ground_point_count']} | {value('authored_minus_city_plane_m')} | {value('city_plane_residual_rms_m')} | {value('grade_difference_percentage_points')} | {z['difference_m']:+.3f} |")
        zrows.append({k:z.get(k) for k in ["id","runtime_chainage_m","city_ground_point_count","authored_minus_city_plane_m","city_plane_residual_rms_m","grade_difference_percentage_points","difference_m","current_route_distance_from_fixed_anchor_m","current_route_height_change_m","authored_height_is_current_route","visual_source_observation","temporal_surface_identity_verified","accepted_independent_control"]})
    with (ROOT/"evidence/m1-source-review/height-review.csv").open("w",newline="",encoding="utf8") as f:
        writer=csv.DictWriter(f,fieldnames=list(zrows[0]));writer.writeheader();writer.writerows(zrows)
    text += ["", "The route-file hash changed. Projection of each fixed original XY onto the current piecewise route verifies that all ten local positions and heights are unchanged: maximum XY distance 1.14e-13 m and height change 8.89e-16 m. The original height comparisons therefore remain applicable at these same locations. No controls were moved or replaced.", "",
             f"The nine valid City plane fits differ by at most 0.0247 m. Their current local grade differences reach {max_grade_difference:.3f} percentage points; a 1.2 m plane and a 5 m route derivative have different spatial support. No grade certification is claimed. All ten 2016 differences are within 0.092 m. Same-surface identity across 2016/2022 remains unverified at all ten places. The complete 948-station report and both failures in its predefined 538-sample flat subset remain in `evidence/corridor/independent-height-comparison.csv`.", "",
             "## Evidence and repeat method", "", "- `manifests/m1-control-validation-protocol.json`: frozen station selection and current M1 decision.", "- `manifests/m1-source-feature-picks.json`: source PNG hashes and unchanged manual picks.", "- `evidence/m1-source-review/source-panels.json`: 30 source panels, tile hashes, local bounds and capture dates.", "- `evidence/m1-source-review/review-results.json`: all observations, all walking candidates and actual mesh input hashes.", "- `evidence/m1-source-review/*-comparison.png`: red current centre, cyan picked band, yellow picked ends, magenta actual pavement outline.", "- `pipeline/gis/evaluate_m1_source_review.py`: repeat against unchanged picks after a route edit. Preserve this result before the repeat.", "", "Source panels were visually inspected. The 0.1 m output pixel is a display grid, not an accuracy claim; several fixed panels use coarser cached service levels. The higher-resolution correction crops are separate so the original references remain unchanged.", "",
             "Roof forms, inland water levels and canopy condition are not certified by these route comparisons. Each keeps its own source/estimate record. The survey delivery report, monument surface associations and height-realization identity remain later accuracy work.", ""]
    (ROOT/"docs/M1-SOURCE-REVIEW-RESULTS.md").write_text("\n".join(text),encoding="utf8")
    protocol=load("manifests/m1-control-validation-protocol.json")
    protocol["original_gate_unchanged"]=False
    protocol["m1_acceptance_decision"]={"date":"2026-09-27","user_choice":"Complete M1 with recorded accuracy limits","authority":"docs/M1-MEASUREMENT-EXCEPTIONS.md; development plan section 13.7","absolute_accuracy_accepted":False,"independent_certification_required_for_m1":False}
    protocol["completed_source_review"]={"path":"evidence/m1-source-review/review-results.json","sha256":digest("evidence/m1-source-review/review-results.json"),"xy_areas":20,"height_areas":10,"independent_controls_accepted":0,"route_corrections_pending":[] if repeat_pass else ["XY04","XY20"],"fixed_repeat_pass":bool(repeat_pass),"original_failure_snapshot":"evidence/m1-source-review/pre-v14/snapshot.json","application_inspection":"separate root acceptance work"}
    xy={r["id"]:r for r in report["horizontal_reviews"]}
    for row in protocol["horizontal_reviews"]:
        row["status"]="source_area_review_complete_"+xy[row["id"]]["status"]
        row["reference_review"]="evidence/m1-source-review/review-results.json#"+row["id"]
        row["source_pick_file"]="manifests/m1-source-feature-picks.json"
    save("manifests/m1-control-validation-protocol.json",protocol)
    acceptance=load("manifests/m1-source-acceptance.json")
    acceptance["m1_accuracy_decision"]=protocol["m1_acceptance_decision"]
    acceptance["accepted_independent_controls"]["original_later_certification_minimum_horizontal"]=20
    acceptance["accepted_independent_controls"]["original_later_certification_minimum_height"]=10
    acceptance["accepted_independent_controls"]["independent_certification_required_for_m1"]=False
    for gate in acceptance["gates"]:
        if gate["number"]==7:
            gate["status"]="fixed_source_review_and_two_correction_repeats_complete_accuracy_unverified" if repeat_pass else "fixed_source_review_repeat_failed"
            gate["close_action"]="Retain all 20 XY / 10 height areas and the pre-v14 failures. Absolute accuracy stays unverified. Root must still inspect corrected pavement in Blender and runtime; independent survey certification is later work under the user decision."
            gate["evidence_snapshots"].append({"path":"evidence/m1-source-review/review-results.json","exists":True,"sha256":digest("evidence/m1-source-review/review-results.json")})
    save("manifests/m1-source-acceptance.json",acceptance)
    print("Saved fixed review, CSVs and amended acceptance metadata; no application test or geometry change.")


if __name__ == "__main__":
    main()
