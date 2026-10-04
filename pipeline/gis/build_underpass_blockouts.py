"""Create two editable, evidence-labelled underpass packages. Does not run apps.

The roof span is independent of the larger floor interpolation envelope. The
active shell covers the riding bay only; unresolved adjacent bays are not
given collision. Existing terrain and pavement support meshes need the
explicit cavity integration recorded in the output before this can be ridden.
"""
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import median_filter
import shapely
from shapely.geometry import Polygon, mapping

from acquire_sources import ROOT, digest, save_json


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf8"))


def prism(sections):
    """Closed ruled solid; station order is right low, left low, right high, left high."""
    vertices = np.asarray(sections).reshape(-1, 3)
    faces = [[0, 2, 1], [1, 2, 3]]
    for i in range(len(sections) - 1):
        a = 4 * i
        for tri in ((0, 1, 4), (1, 5, 4), (2, 6, 3), (3, 6, 7),
                    (0, 4, 2), (2, 4, 6), (1, 3, 5), (3, 7, 5)):
            faces.append([a + t for t in tri])
    a = 4 * (len(sections) - 1)
    faces.extend([[a, a + 1, a + 2], [a + 1, a + 3, a + 2]])
    return vertices, np.asarray(faces, dtype=np.int32)


def mesh_checks(vertices, faces):
    triangles = vertices[faces]
    area = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1) * .5
    edges = np.sort(np.concatenate((faces[:, :2], faces[:, 1:], faces[:, [2, 0]])), axis=1)
    _, count = np.unique(edges, axis=0, return_counts=True)
    # Translate to keep volume summation numerically stable.
    tri = triangles - vertices.mean(axis=0)
    volume = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6
    result = {"nonfinite_values": int((~np.isfinite(vertices)).sum()),
              "degenerate_triangles": int((area < 1e-10).sum()),
              "nonmanifold_edges": int((count != 2).sum()), "signed_volume_m3": float(volume)}
    if result["nonfinite_values"] or result["degenerate_triangles"] or result["nonmanifold_edges"] or volume <= 0:
        raise ValueError(f"Invalid closed underpass mesh: {result}")
    return result


def main():
    config_path = "manifests/underpass-dimensions.json"
    runtime_path = "data/derived/paved-circuit-runtime.json"
    register, runtime = read_json(config_path), read_json(runtime_path)
    source_s = np.asarray(runtime["chainage_source_m"])
    runtime_s = np.asarray(runtime["chainage_runtime_m"])
    route = np.asarray(runtime["points_local_m"])
    tangent = np.gradient(route[:, :2], axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    normals = np.column_stack((-tangent[:, 1], tangent[:, 0]))
    # The exported effective profile includes approved local width/crossfall
    # edits. The immutable fit proposal is not the final pavement geometry.
    widths, falls = np.asarray(runtime["width_m"]), np.asarray(runtime["crossfall"])
    if widths.shape != source_s.shape or falls.shape != source_s.shape or not np.isfinite(np.r_[widths, falls]).all():
        raise ValueError('Missing or invalid effective runtime pavement profile')
    right, left = route.copy(), route.copy()
    for sign, edge in ((-1, right), (1, left)):
        edge[:, :2] += sign * normals * widths[:, None] * .5
        edge[:, 2] += sign * widths * falls * .5

    def sample(s):
        p = np.column_stack([np.interp(s, source_s, route[:, i]) for i in range(3)])
        r = np.column_stack([np.interp(s, source_s, right[:, i]) for i in range(3)])
        l = np.column_stack([np.interp(s, source_s, left[:, i]) for i in range(3)])
        # Cross section interpolates actual pavement edges; extensions match its seam.
        n = (l[:, :2] - r[:, :2])
        w = np.linalg.norm(n, axis=1)
        n /= w[:, None]
        fall = (l[:, 2] - r[:, 2]) / w
        return p, n, w, fall

    out = ROOT / "data/derived/underpasses"
    out.mkdir(parents=True, exist_ok=True)
    meshes, sites, openings = [], [], []
    for cfg in register["sites"]:
        name = cfg["id"]
        start, end = cfg["roof_source_m"]
        stations = np.linspace(start, end, int(np.ceil((end - start) / .5)) + 1)
        p, n, width, fall = sample(stations)
        clear_half, wall = cfg["clear_width_m"] * .5, cfg["wall_thickness_m"]
        with np.load(ROOT / f"data/derived/underpass-{name.lower()}-survey.npz") as survey:
            q, classes = survey["xyz"], survey["classification"]
        band = cfg["deck_height_band_m"]
        q = q[np.isin(classes, [1, 2]) & (q[:, 2] >= band[0]) & (q[:, 2] <= band[1])]
        # Road deck top is a robust local lower quantile, not a fabricated ceiling.
        # Vehicles/railings can survive the height band; retain raw sample diagnostics.
        top, deck_samples = [], []
        for point, normal in zip(p, n):
            delta = q[:, :2] - point[:2]
            across = delta @ normal
            along = delta @ np.array([normal[1], -normal[0]])
            z = q[(np.abs(along) <= .6) & (np.abs(across) <= clear_half), 2]
            if len(z) < 8:
                raise ValueError(f"Insufficient deck support: {name}, point {point}, returns {len(z)}")
            top.append(np.quantile(z, .25))
            deck_samples.append({"count": len(z), "p10_m": float(np.quantile(z, .1)),
                                 "p25_m": float(np.quantile(z, .25)), "median_m": float(np.median(z)),
                                 "p90_m": float(np.quantile(z, .9))})
        raw_top = np.asarray(top)
        top = median_filter(raw_top, size=5, mode="nearest")
        underside = p[:, 2] + cfg["clearance_m"]
        minimum_thickness = float(np.min(top - underside - np.abs(fall) * (clear_half + wall)))
        if minimum_thickness < .12:
            raise ValueError(f"Roof cannot fit the configured clearance: {name}, slab minimum {minimum_thickness:.3f} m")
        anchor = np.r_[np.floor(p[0, :2] / 10) * 10, 0.]

        def section_mesh(role, positions, normal, crossfall, lo, hi, lower, upper, collision="complex", reference=False):
            lo, hi = np.broadcast_to(lo, len(positions)), np.broadcast_to(hi, len(positions))
            lower, upper = np.broadcast_to(lower, len(positions)), np.broadcast_to(upper, len(positions))
            sections = []
            for i, point in enumerate(positions):
                section = []
                for offset, z in ((lo[i], lower[i]), (hi[i], lower[i]), (lo[i], upper[i]), (hi[i], upper[i])):
                    section.append([*(point[:2] + normal[i] * offset), z + crossfall[i] * offset])
                sections.append(section)
            vertices, faces = prism(sections)
            checks = mesh_checks(vertices, faces)
            mesh_name = f"{'REF' if reference else 'SM'}_Underpass_{name}_{role}"
            path = out / f"{mesh_name}.npz"
            np.savez_compressed(path, vertices=vertices - anchor, faces=faces, anchor=anchor)
            item = {"name": mesh_name, "site": name, "role": role, "path": path.relative_to(ROOT).as_posix(),
                    "sha256": digest(path), "vertices": len(vertices), "triangles": len(faces),
                    "collision": collision, "reference_only": reference, "checks": checks}
            meshes.append(item)
            return item

        section_mesh("Deck", p, n, fall, -clear_half - wall, clear_half + wall, underside, top)
        for side, lo, hi in (("Right", -clear_half - wall, -clear_half), ("Left", clear_half, clear_half + wall)):
            section_mesh(f"Wall{side}", p, n, fall, lo, hi, p[:, 2] - .2, underside)

        # Short floor extensions taper to the unchanged bicycle pavement at portals.
        # These are structural floor strips, not a claim about public path width.
        taper = cfg["approach_taper_m"]
        opening_start, opening_end = max(cfg["floor_envelope_source_m"][0], start - taper), min(cfg["floor_envelope_source_m"][1], end + taper)
        fs = np.unique(np.r_[np.arange(opening_start, opening_end, .5), stations, opening_end])
        fp, fn, fw, ff = sample(fs)
        factor = np.minimum(np.clip((fs - opening_start) / max(start - opening_start, .01), 0, 1),
                            np.clip((opening_end - fs) / max(opening_end - end, .01), 0, 1))
        half = fw * .5 + np.maximum(.001, (clear_half - fw * .5) * factor)
        # A 5 mm construction overlap closes the sub-millimetre slivers between
        # different station tessellations. Keep the cavity and legal bay width
        # unchanged. The floor follows the same crossfall plane at this overlap.
        floor_overlap_m=.005
        for side, lo, hi in (("Right", -half, -fw * .5), ("Left", fw * .5, half)):
            section_mesh(f"FloorExtension{side}", fp, fn, ff, lo-floor_overlap_m, hi+floor_overlap_m,
                         fp[:, 2] - cfg["floor_slab_thickness_m"], fp[:, 2])
        a, b = fp[:, :2] - fn * half[:, None], fp[:, :2] + fn * half[:, None]
        polygon = Polygon(np.vstack((a, b[::-1])))
        if not polygon.is_valid:
            raise ValueError(f"Self-intersecting underpass cavity: {name}")
        # Check actual exported floor footprints plus unchanged riding pavement.
        base_right = fp[:, :2] - fn * fw[:, None] * .5
        base_left = fp[:, :2] + fn * fw[:, None] * .5
        floor_pieces = [Polygon(np.vstack((base_right, base_left[::-1])))]
        for item in meshes:
            if item["site"] == name and item["role"].startswith("FloorExtension"):
                with np.load(ROOT / item["path"]) as mesh:
                    positions = (mesh["vertices"] + mesh["anchor"]).reshape(-1, 4, 3)
                floor_pieces.append(Polygon(np.vstack((positions[:, 2, :2], positions[::-1, 3, :2]))))
        uncovered_area = float(polygon.difference(shapely.union_all(floor_pieces)).area)
        if uncovered_area > 1e-7:
            raise ValueError(f"Underpass cut is not covered by floor: {name}, {uncovered_area} m2")
        expected_right_z = np.interp(fs, source_s, right[:, 2])
        expected_left_z = np.interp(fs, source_s, left[:, 2])
        seam_error = float(max(np.max(np.abs(fp[:, 2] - ff * fw * .5 - expected_right_z)),
                               np.max(np.abs(fp[:, 2] + ff * fw * .5 - expected_left_z))))
        openings.append({"type": "Feature", "geometry": mapping(polygon), "properties": {
            "id": name, "crs": "local metres; EPSG:3157 minus world-origin", "source_start_m": opening_start,
            "source_end_m": opening_end, "roof_source_start_m": start, "roof_source_end_m": end,
            "purpose": "Union into terrain XY opening and remove interior pavement support triangles. Road deck is supplied separately.",
            "accuracy_accepted": False}})
        if cfg.get("design_overall_width_m"):
            overall = cfg["design_overall_width_m"] * .5
            section_mesh("UnlocatedDesignEnvelope", p, n, np.zeros(len(p)), -overall, overall,
                         p[:, 2], p[:, 2] + cfg["clearance_m"], collision="none", reference=True)

        # The active capsule is 0.32 m radius, 0.70 m half height. Use a conservative
        # 1.50 m total floor-to-head envelope, greater than its present contact height.
        checks = {"roof_length_runtime_m": float(np.interp(end, source_s, runtime_s) - np.interp(start, source_s, runtime_s)),
                  "min_ceiling_clearance_m": float(np.min(underside - p[:, 2])),
                  "minimum_slab_thickness_m": minimum_thickness,
                  "capsule_floor_to_top_allowance_m": 1.50,
                  "capsule_head_margin_m": cfg["clearance_m"] - 1.50,
                  "capsule_centerline_lateral_margin_m": clear_half - .32,
                  "first_person_camera_floor_height_allowance_m": 1.60,
                  "first_person_camera_head_margin_m": cfg["clearance_m"] - 1.60,
                  "floor_extension_seam_vertical_error_m": seam_error,
                  "cavity_without_floor_area_m2": uncovered_area,
                  "floor_construction_overlap_m": floor_overlap_m,
                  "deck_quantile_filter_max_change_m": float(np.max(np.abs(top - raw_top))),
                  "interactive_test": "pending; root must integrate cavity and inspect both portals and ride both directions"}
        sites.append({"id": name, "roof_source_m": [start, end],
                      "roof_runtime_m": [float(np.interp(x, source_s, runtime_s)) for x in (start, end)],
                      "floor_envelope_source_m": cfg["floor_envelope_source_m"],
                      "opening_source_m": [opening_start, opening_end],
                      "support_removal_source_m": [opening_start, opening_end],
                      "clear_width_m": cfg["clear_width_m"], "clearance_m": cfg["clearance_m"],
                      "station_source_m": stations.tolist(), "floor_center_xyz": p.tolist(),
                      "ceiling_center_z_m": underside.tolist(), "deck_center_z_m": top.tolist(),
                      "deck_raw_station_samples": deck_samples, "checks": checks,
                      "survey_path": f"data/derived/underpass-{name.lower()}-survey.npz",
                      "survey_sha256": digest(ROOT / f"data/derived/underpass-{name.lower()}-survey.npz"),
                      "release_accepted": False})
        print(name, json.dumps(checks), flush=True)

    inputs = [{"path": path, "sha256": digest(ROOT / path)} for path in (config_path, runtime_path, "manifests/underpass-reference-sources.json")]
    save_json(ROOT / "data/derived/underpass-openings.geojson", {"type": "FeatureCollection", "features": openings})
    save_json(ROOT / "data/derived/underpass-blockouts.json", {
        "schema_version": 1, "inputs": inputs, "sites": sites, "meshes": meshes,
        "openings_path": "data/derived/underpass-openings.geojson",
        "openings_sha256": digest(ROOT / "data/derived/underpass-openings.geojson"),
        "authoring_status": "Geometry generated; live Blender inspection and engine integration pending",
        "integration_required": ["Union cavity polygons into existing terrain cut; do not lower road deck onto tunnel floor.",
                                 "Remove pavement support faces inside the cavity; their old vertical skirts otherwise form false walls.",
                                 "Do not export REF objects. Add only SM meshes to the shared surface manifest after cavity integration.",
                                 "Keep source and runtime chainages distinct. Do not enable any at-grade road transfer here.",
                                 "Inspect roof ends, approach side gaps, floor seams and chase-camera retraction in Blender and runtime."],
        "release_accepted": False})


if __name__ == "__main__":
    main()
