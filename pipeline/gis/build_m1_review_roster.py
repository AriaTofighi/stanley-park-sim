"""Fix review areas before manual source comparison; never grant accuracy acceptance."""
from pathlib import Path
import csv
import hashlib
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
ROUTE = ROOT / "data/derived/paved-circuit-runtime.json"
HEIGHTS = ROOT / "evidence/corridor/independent-height-comparison.csv"
OUTPUT = ROOT / "manifests/m1-control-validation-protocol.json"


def main():
    route = json.loads(ROUTE.read_text(encoding="utf8"))
    chainage = np.array(route["chainage_runtime_m"])
    points = np.array(route["points_local_m"])
    length = float(chainage[-1])
    horizontal = []
    for i in range(20):
        station = length * i / 20
        position = [float(np.interp(station, chainage, points[:, axis])) for axis in range(3)]
        horizontal.append({
            "id": f"XY_REVIEW_{i + 1:02d}", "runtime_chainage_m": station,
            "search_anchor_local_m": position, "search_radius_m": 50,
            "anchor_is_control": False, "reference_feature": None,
            "reference_xy_m": None, "model_xy_m": None, "residual_m": None,
            "status": "manual_hard_feature_selection_pending",
            "accepted_independent_control": False})
    with HEIGHTS.open(encoding="utf8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    vertical = []
    for i in range(10):
        candidates = [row for row in rows
                      if i * length / 10 <= float(row["runtime_chainage_m"]) < (i + 1) * length / 10
                      and row["flat_reference_subset"] == "True"]
        if not candidates:
            vertical.append({"id": f"Z_REVIEW_{i + 1:02d}", "status": "no_flat_reference",
                             "accepted_independent_control": False})
            continue
        row = candidates[0]
        vertical.append({
            "id": f"Z_REVIEW_{i + 1:02d}",
            "runtime_chainage_m": float(row["runtime_chainage_m"]),
            "search_anchor_local_m": [float(row["x_m"]), float(row["y_m"])],
            "authored_height_m": float(row["authored_height_m"]),
            "reference_2016_height_m": float(row["hrdem_2016_height_m"]),
            "difference_m": float(row["difference_m"]),
            "comparison_within_015m": abs(float(row["difference_m"])) <= 0.15,
            "status": "same_surface_and_reference_accuracy_review_pending",
            "accepted_independent_control": False})
    output = {
        "purpose": "Fixed cross-source review roster, not survey control certification",
        "original_gate_unchanged": True, "accepted_independent_control_count": 0,
        "absolute_accuracy_accepted": False,
        "coordinate_reference": "Local metres; EPSG:3157 origin E489600 N5461100; project CGVD2013 heights",
        "route_length_m": length,
        "inputs": [{"path": str(p.relative_to(ROOT)).replace("\\", "/"),
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in [ROUTE, HEIGHTS]],
        "horizontal_selection": "20 equal-chainage anchors, hard feature within 50 m; anchors are not controls",
        "vertical_selection": "First pre-existing flat-rule sample in each route tenth, selected without residual filtering",
        "rules": ["Retain failures and unmeasurable areas", "Do not adjust geometry to the check controls",
                  "Do not convert same-source export checks into independent survey acceptance",
                  "Revalidate hashes before using this roster after a route edit"],
        "horizontal_reviews": horizontal, "vertical_reviews": vertical,
        "protocol": "docs/M1-GEOGRAPHIC-VALIDATION-PROTOCOL.md"}
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"horizontal_review_areas": len(horizontal), "vertical_review_areas": len(vertical),
                      "absolute_accuracy_accepted": False,
                      "vertical_comparisons_within_015m": sum(r.get("comparison_within_015m", False) for r in vertical)}))


if __name__ == "__main__":
    main()
