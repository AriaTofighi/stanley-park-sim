"""Read the supplied City LAS without changing the user's downloaded archive."""
from collections import Counter
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import zipfile

import laspy
import numpy as np

from acquire_sources import ROOT, save_json, digest
from height_reference import VancouverHeightConversion


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tile", default="488000_5462000")
    args = parser.parse_args()
    tile = args.tile
    if not tile.replace("_", "").isdigit() or len(tile) != 14:
        raise ValueError("Expected easting_northing tile name")
    origin = json.loads((ROOT / "manifests/world-origin.json").read_text())
    archive = ROOT / f"data/raw/city/lidar2022/{tile}.zip"
    conversion = VancouverHeightConversion()
    counts = Counter()
    ground, water, ground_rgb, buildings = [], [], [], []
    tile_e, tile_n = map(int,tile.split("_"))
    canopy_max = np.full((200,200), -np.inf, dtype=np.float32)
    canopy_count = np.zeros((200,200), dtype=np.uint32)
    with zipfile.ZipFile(archive) as source:
        names = [n for n in source.namelist() if n.lower().endswith(".las")]
        if names != [f"{tile}.las"]:
            raise ValueError(f"Unexpected LAS entries: {names}")
        with source.open(names[0]) as stream, laspy.open(stream) as las:
            header = dict(version=str(las.header.version), format=las.header.point_format.id,
                          points=las.header.point_count, minima=las.header.mins.tolist(),
                          maxima=las.header.maxs.tolist(), crs=las.header.parse_crs().to_wkt())
            for chunk in las.chunk_iterator(500_000):
                classes = np.asarray(chunk.classification)
                keys, values = np.unique(classes, return_counts=True)
                counts.update(dict(zip(map(int, keys), map(int, values))))
                vegetation = classes == 5
                vx,vy = np.asarray(chunk.x)[vegetation], np.asarray(chunk.y)[vegetation]
                ci=np.clip(((vx-tile_e)/5).astype(int),0,199)
                cj=np.clip(((vy-tile_n)/5).astype(int),0,199)
                np.maximum.at(canopy_max,(cj,ci),np.asarray(chunk.z)[vegetation])
                np.add.at(canopy_count,(cj,ci),1)
                # The catalogue's HTML ordered list is descriptive, not LAS codes.
                # LAS 1.4 class 9 is water; class 5 is high vegetation.
                for code, destination in ((2, ground), (9, water), (6, buildings)):
                    take = classes == code
                    if code == 2:
                        ground_rgb.append(np.column_stack((np.asarray(chunk.red)[take],
                            np.asarray(chunk.green)[take], np.asarray(chunk.blue)[take])).astype(np.uint16))
                    east, north, native = np.asarray(chunk.x)[take], np.asarray(chunk.y)[take], np.asarray(chunk.z)[take]
                    if code == 9:
                        east, north, native = east[::50], north[::50], native[::50]
                    if code == 6:
                        east, north, native = east[::10], north[::10], native[::10]
                    if not len(east):
                        continue
                    height = conversion.to_cgvd2013(east, north, native)
                    destination.append(np.column_stack((east-origin["easting"], north-origin["northing"], height, native)))
    output = ROOT / f"data/derived/lidar2022_{tile}.npz"
    g = np.concatenate(ground).astype(np.float32)
    w = np.concatenate(water).astype(np.float32) if water else np.empty((0, 4), np.float32)
    b = np.concatenate(buildings).astype(np.float32) if buildings else np.empty((0,4),np.float32)
    cx,cy=np.meshgrid(np.arange(200)*5+tile_e+2.5,np.arange(200)*5+tile_n+2.5)
    canopy_max += conversion.correction(cx.ravel(),cy.ravel()).reshape(200,200)
    canopy_max[~np.isfinite(canopy_max)]=np.nan
    np.savez_compressed(output, ground=g, water=w, ground_rgb=np.concatenate(ground_rgb),buildings=b,
                        canopy_x=cx[0]-origin["easting"],canopy_y=cy[:,0]-origin["northing"],
                        canopy_max=canopy_max,canopy_count=canopy_count)
    delta = g[:, 2] - g[:, 3]
    record = dict(created_utc=datetime.now(timezone.utc).isoformat(), input_path=archive.relative_to(ROOT).as_posix(),
        source_url=f"https://webtransfer.vancouver.ca/opendata/2022LiDAR/{tile}.zip",
        delivery="Public download from City portal; original retained", input_sha256=digest(archive),
        metadata_url="https://opendata.vancouver.ca/explore/dataset/lidar-2022/information/",
        capture_dates=["2022-09-07", "2022-09-09"], licence="Open Government Licence - Vancouver",
        distribution="Derived geometry allowed with attribution; archive retained as source, not shipped in game",
        header=header, class_counts=dict(counts), water_sampling="Each fiftieth LAS class-9 return per read chunk; not a tide datum",
        canopy_sampling="5m cells, maximum height and count of class-5 returns; not individual tree identities",
        building_sampling="Each tenth class-6 return; blockout height/footprint reference",
        horizontal_reference="Catalogue: NAD83(CSRS) 4.0.0.BC.1.GVRD / UTM 10; LAS generic EPSG26910 is less specific",
        horizontal_treatment="Keep source UTM coordinates; realization/epoch residual not independently established",
        vertical_reference_input="CGVD28GVRD, HTMVBC00_Abb geoid",
        vertical_reference_output="CGVD2013(CGG2013a); regional realization residual remains open",
        formula="H2013 = H28 + N_HTMVBC00_Abb - N_CGG2013an83; bilinear grid-centre interpolation in metres",
        correction_range_m=[float(delta.min()), float(delta.max())],
        geoid_sources=[dict(path=p.relative_to(ROOT).as_posix(), sha256=digest(p)) for p in
                      [ROOT/"data/raw/geoid/HTMVBC00_Abb.byn", ROOT/"data/raw/geoid/ca_nrc_CGG2013an83.tif"]],
        geoid_documentation=["https://www2.gov.bc.ca/gov/content/data/geographic-data-services/geo-spatial-referencing/height-transformations",
            "https://cdn.proj.org/ca_nrc_README.txt", "https://gdal.org/en/stable/drivers/raster/byn.html"],
        output=dict(path=output.relative_to(ROOT).as_posix(),sha256=digest(output),columns=["local_east_m","local_north_m","H_CGVD2013_m","H_native_m"]),
        source_reported_vertical_accuracy_95_m=.081,
        acceptance="Source ingested, not accepted as independent centimetre survey control; check on flat pavement")
    save_json(ROOT/f"manifests/lidar2022-{tile}.json", record)
    print(json.dumps({k:record[k] for k in ["class_counts","correction_range_m","source_reported_vertical_accuracy_95_m"]},indent=2))
    report = ROOT/"data/raw/corridor/maze-gates-2025.pdf"
    refs = json.loads((ROOT/"manifests/corridor-references.json").read_text())
    refs["records"][0].update(status="user_supplied_download", path=report.relative_to(ROOT).as_posix(),
        bytes=report.stat().st_size,sha256=digest(report),document_date="2025-02-27",meeting_date="2025-03-10",
        observations_dates=["2024-08-14","2024-08-17","2024-08-29"],
        baseline_note="Existing-condition pages 21-23 apply as historical references. Proposed 2027 construction is not 2026 as-built geometry.")
    refs["records"][0].pop("error",None)
    save_json(ROOT/"manifests/corridor-references.json",refs)


if __name__ == "__main__":
    main()
