"""Numerical validation of acquired geographic data; no application is launched."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from pyproj import Transformer
from shapely.geometry import shape
from acquire_sources import ROOT, RAW, DERIVED, MANIFESTS, digest, get_json, download, save_json


def main():
    origin = json.loads((MANIFESTS / "world-origin.json").read_text())
    boundary = shape(json.loads((DERIVED / "park_boundary_utm.geojson").read_text())["features"][0]["geometry"])
    points = np.array([boundary.exterior.interpolate(i/20, normalized=True).coords[0] for i in range(20)])
    forward = Transformer.from_crs(3157,4326,always_xy=True)
    back = Transformer.from_crs(4326,3157,always_xy=True)
    lon, lat = forward.transform(points[:,0], points[:,1])
    east, north = back.transform(lon,lat)
    residual = np.hypot(points[:,0]-east,points[:,1]-north)
    report = {"kind": "data numerical validation; not independent survey or application testing",
              "origin": {k:origin[k] for k in ("easting","northing","height","horizontal_crs")},
              "geographic_projected_roundtrip_max_m":float(residual.max()), "roundtrip_sample_count":20,
              "controls": [{"easting":float(p[0]),"northing":float(p[1]),"lon":float(lo),"lat":float(la),"roundtrip_error_m":float(r)} for p,lo,la,r in zip(points,lon,lat,residual)],
              "boundary_valid":boundary.is_valid, "park_area_m2":boundary.area, "products": {}}
    for product in ("terrain_park","terrain_surroundings"):
        with np.load(DERIVED / f"{product}.npz") as data:
            x,y,z,valid,park = [data[k] for k in ("x","y","z","valid","inside_park")]
            assert z.shape == (len(y),len(x))
            assert np.all(np.diff(x)>0) and np.all(np.diff(y)>0)
            assert np.array_equal(valid,np.isfinite(z))
            assert not np.any(park & ~valid)
            heights = z[valid & park]
            entry = {"array_shape_correct":True,"x_y_ascending":True,"validity_mask_matches":True,
                     "park_has_complete_valid_coverage":True,"park_height_min_m":float(heights.min()),"park_height_max_m":float(heights.max()),
                     "grid_spacing_m":[float(np.diff(x).min()),float(np.diff(y).min())]}
            report["products"][product]=entry
    report["independent_accuracy"] = "NOT VALIDATED. Geographic round-trip precision is not real-world survey accuracy."
    report["route_surface_accuracy"] = "NOT VALIDATED. 2 m historic DTM must not replace measured path cross sections."
    report["city_download_failure"] = {"status":403,"affected":["https://webtransfer.vancouver.ca/opendata/TIF/DEM_2013_TIF.zip","https://webtransfer.vancouver.ca/opendata/2022LiDAR/489000_5462000.zip"],"fallback":"Public NRCan 2013 Vancouver LiDAR-derived DTM; CGVD2013"}
    report["raw_cache_bytes"] = sum(p.stat().st_size for p in RAW.rglob("*") if p.is_file())
    assert report["geographic_projected_roundtrip_max_m"] < 0.01
    assert report["raw_cache_bytes"] < 6_000_000_000
    save_json(MANIFESTS / "geospatial-validation.json",report)
    print(json.dumps({k:v for k,v in report.items() if k != "controls"},indent=2))


if __name__ == "__main__":
    main()
