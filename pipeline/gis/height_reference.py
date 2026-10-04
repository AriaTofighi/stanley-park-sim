"""Explicit regional geoid conversion; never treat a height datum as sea level.

The local CSRS realization and epoch are retained as an uncertainty. This is a
geoid conversion, not a claimed centimetre-grade 4D datum transformation.
"""
from pathlib import Path

import numpy as np
from pyproj import Transformer
import rasterio
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).resolve().parents[2]


class GeoidGrid:
    def __init__(self, path):
        with rasterio.open(path) as ds:
            self.values = ds.read(1).astype(np.float64) * ds.scales[0] + ds.offsets[0]
            self.transform = ds.transform
            self.crs = ds.crs.to_string()

    def sample(self, lon, lat):
        col, row = (~self.transform) * (np.asarray(lon), np.asarray(lat))
        # GDAL transforms describe pixel corners, including Point source grids.
        return map_coordinates(self.values, [row - .5, col - .5], order=1,
                               mode="constant", cval=np.nan, prefilter=False)


class VancouverHeightConversion:
    def __init__(self):
        self.regional = GeoidGrid(ROOT / "data/raw/geoid/HTMVBC00_Abb.byn")
        self.national = GeoidGrid(ROOT / "data/raw/geoid/ca_nrc_CGG2013an83.tif")
        self.to_geographic = Transformer.from_crs(3157, 4617, always_xy=True)

    def correction(self, east, north):
        lon, lat = self.to_geographic.transform(east, north)
        return self.regional.sample(lon, lat) - self.national.sample(lon, lat)

    def to_cgvd2013(self, east, north, h28):
        # h = H28 + N28; H2013 = h - N2013.
        return np.asarray(h28) + self.correction(east, north)
