"""Build measured, local-metre terrain products from bounded NRCan COG reads."""
from __future__ import annotations
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import from_bounds

from acquire_sources import ROOT, RAW, DERIVED, MANIFESTS, digest, get_json, save_json
from remote_raster import RangeSource

NODATA = -32767.0


def export_obj(path, x, y, z, valid, stride=1, omit_bounds=None):
    x, y, z, valid = x[::stride], y[::stride], z[::stride, ::stride], valid[::stride, ::stride].copy()
    if omit_bounds:
        xx, yy = np.meshgrid(x, y)
        xmin, ymin, xmax, ymax = omit_bounds
        valid &= ~((xx > xmin) & (xx < xmax) & (yy > ymin) & (yy < ymax))
    indices = np.zeros(z.shape, dtype=np.int32)
    indices[valid] = np.arange(1, np.count_nonzero(valid)+1)
    face_count = 0
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("# Measured NRCan DTM; local metres; X east Y north Z up. CGVD2013 heights.\n")
        stream.write("# Missing source cells are omitted, never assigned invented elevations.\n")
        stream.write(f"o {path.stem}\n")
        for row, col in zip(*np.where(valid)):
            stream.write(f"v {x[col]:.3f} {y[row]:.3f} {z[row,col]:.3f}\n")
        for row in range(z.shape[0]-1):
            for col in range(z.shape[1]-1):
                a, b, c, d = indices[row,col], indices[row,col+1], indices[row+1,col+1], indices[row+1,col]
                if a and b and c and d:
                    stream.write(f"f {a} {b} {c}\nf {a} {c} {d}\n")
                    face_count += 2
    return {"vertices": int(valid.sum()), "triangles": face_count, "stride": stride,
            "path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": digest(path)}


def crop_raster(feature, product, bounds, resolution, origin, collection_metadata,
                *, write_mesh=True, cache_product=None):
    url = feature["assets"]["dtm"]["href"]
    cache = RAW / "nrcan" / f"{cache_product or product}-ranges"
    source = RangeSource(url, cache)
    xmin, ymin, xmax, ymax = bounds
    width, height = math.ceil((xmax-xmin)/resolution), math.ceil((ymax-ymin)/resolution)
    target_transform = from_origin(xmin, ymax, resolution, resolution)
    output = np.full((height, width), NODATA, dtype=np.float32)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(url, opener=source.opener) as dataset:
            src_bounds = transform_bounds(3157, dataset.crs, xmin, ymin, xmax, ymax, densify_pts=41)
            padding = 3 * abs(dataset.transform.a)
            window = from_bounds(src_bounds[0]-padding, src_bounds[1]-padding,
                                 src_bounds[2]+padding, src_bounds[3]+padding, dataset.transform)
            window = window.round_offsets().round_lengths()
            scale = max(1, int(resolution / abs(dataset.transform.a)))
            source_height = max(1, math.ceil(window.height / scale))
            source_width = max(1, math.ceil(window.width / scale))
            print(f"Reading {product} source crop: {source_width}x{source_height} at reduced scale {scale}", flush=True)
            data = dataset.read(1, window=window, out_shape=(source_height, source_width),
                                boundless=True, fill_value=NODATA, resampling=Resampling.average)
            source_transform = dataset.window_transform(window) * dataset.transform.scale(window.width/source_width, window.height/source_height)
            reproject(data, output, src_transform=source_transform, src_crs=dataset.crs,
                      src_nodata=dataset.nodata, dst_transform=target_transform, dst_crs="EPSG:3157",
                      dst_nodata=NODATA, resampling=Resampling.bilinear, num_threads=2)
            source_header = {"crs": dataset.crs.to_string(), "crs_wkt": dataset.crs.to_wkt(),
                             "transform": list(dataset.transform), "width": dataset.width, "height": dataset.height,
                             "nodata": dataset.nodata, "dtype": dataset.dtypes[0], "tags": dataset.tags(),
                             "source_window": list(window.flatten()), "decimation_before_reproject": scale}
    source.flush()
    valid = np.isfinite(output) & (output != NODATA)
    tif_path = DERIVED / f"{product}_utm.tif"
    with rasterio.open(tif_path, "w", driver="GTiff", width=width, height=height, count=1, dtype="float32",
                       crs="EPSG:3157", transform=target_transform, nodata=NODATA, tiled=True, compress="deflate") as dst:
        dst.write(output, 1)
        dst.update_tags(SOURCE_ID=feature["id"], VERTICAL_DATUM="CGVD2013", SOURCE_URL=url)
    x = (xmin + (np.arange(width)+0.5)*resolution - origin["easting"]).astype(np.float64)
    y = (ymax - (np.arange(height)+0.5)*resolution - origin["northing"])[::-1].astype(np.float64)
    z = output[::-1].copy()
    valid = valid[::-1].copy()
    z[~valid] = np.nan
    boundary = json.loads((DERIVED / "park_boundary_utm.geojson").read_text())
    park_mask = geometry_mask([f["geometry"] for f in boundary["features"]], out_shape=(height,width),
                              transform=target_transform, invert=True)[::-1].copy()
    npz_path = DERIVED / f"{product}.npz"
    np.savez_compressed(npz_path, x=x, y=y, z=z, valid=valid, inside_park=park_mask,
                        source_code=np.where(valid, 1, 0).astype(np.uint8), resolution_m=np.array(resolution),
                        easting_origin=np.array(origin["easting"]), northing_origin=np.array(origin["northing"]),
                        vertical_datum=np.array("CGVD2013"), horizontal_crs=np.array("EPSG:3157"))
    mesh = None
    if write_mesh:
        mesh = export_obj(DERIVED / f"{product}.obj", x, y, z, valid,
                          stride=4 if product == "terrain_park" else 1,
                          omit_bounds=(-1400, -1700, 2200, 1500) if product == "terrain_surroundings" else None)
    if mesh and product == "terrain_surroundings":
        mesh["overlap_note"] = "Near crop extends 100 m beyond omitted far-mesh interior. Reconcile edge heights before final art."
    values = z[valid]
    stats = {"grid_shape": [height,width], "resolution_m": resolution, "valid_cells": int(valid.sum()),
             "valid_fraction": float(valid.mean()), "height_min_m": float(values.min()), "height_max_m": float(values.max()),
             "height_percentiles_m": [float(v) for v in np.percentile(values,[1,25,50,75,99])],
             "park_cells": int(park_mask.sum()), "park_valid_fraction": float(valid[park_mask].mean()) if park_mask.any() else None}
    metadata = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
                "product": product, "source_id": feature["id"], "source_url": url,
                "source_datetime": feature.get("properties",{}).get("datetime"), "source_header": source_header,
                "origin_file": "manifests/world-origin.json", "coordinate_contract": "x east, y north, z up; metres; x/y ascending; z[row_y,col_x]",
                "horizontal_crs": "EPSG:3157", "vertical_datum": "CGVD2013",
                "missing_values": "NaN in NPZ; -32767 in GeoTIFF; absent faces in OBJ",
                "licence": collection_metadata.get("license"), "licence_links": [v for v in collection_metadata.get("links",[]) if v.get("rel") in ("license","about")],
                "attribution": "Contains information licensed under the Open Government Licence – Canada. See source collection for additional source notices.",
                "source_range_cache": str(cache.relative_to(ROOT)), "stats": stats, "mesh": mesh,
                "files": [{"path":str(p.relative_to(ROOT)),"sha256":digest(p),"bytes":p.stat().st_size} for p in [tif_path,npz_path]],
                "limitations": ["Measured source predates September 2026; this is a geographic blockout input, not a current survey.",
                                "No independent ground-control accuracy check has been completed.",
                                "Cliffs/overhangs and narrow path details need separate authored geometry.",
                                "No ocean or inland water elevation is assigned by this terrain product."]}
    save_json(MANIFESTS / f"geospatial-{product}.json", metadata)
    print(json.dumps({"product": product, "stats": stats, "mesh": mesh}), flush=True)
    return metadata


def main():
    origin_path = MANIFESTS / "world-origin.json"
    origin = json.loads(origin_path.read_text())
    search = json.loads((RAW / "nrcan/hrdem-search.json").read_text())
    selected = next(f for f in search["features"] if f["id"] == "VILLE_VANCOUVER-VILLE_VANCOUVER-1m")
    collection, _ = get_json("https://datacube.services.geo.ca/stac/api/collections/hrdem-lidar", RAW / "nrcan/hrdem-collection.json")
    origin["vertical_datum"] = "CGVD2013 for current NRCan terrain products; City 2022 CGVD28GVRD must be transformed before combination"
    origin["height_origin_note"] = "H0=0 is a subtractive coordinate offset in CGVD2013; not an assigned ocean level."
    save_json(origin_path, origin)
    bounds = (488100, 5459300, 491900, 5462700)
    crop_raster(selected,"terrain_park",bounds,2,origin,collection)
    far_search = json.loads((RAW / "nrcan/mrdem-search.json").read_text())
    collection, _ = get_json("https://datacube.services.geo.ca/stac/api/collections/mrdem-30", RAW / "nrcan/mrdem-collection.json")
    crop_raster(far_search["features"][0],"terrain_surroundings",(462000,5447000,514000,5507000),80,origin,collection)


if __name__ == "__main__":
    main()
