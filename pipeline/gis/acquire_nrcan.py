"""Snapshot exact public STAC queries and source licence evidence."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from acquire_sources import RAW, MANIFESTS, get_json, download, save_json, digest


def main():
    records = []
    for collection,bbox,name in [
        ("hrdem-lidar","-123.17,49.285,-123.105,49.32","hrdem"),
        ("mrdem-30","-123.6,49.15,-122.8,49.6","mrdem"),
    ]:
        url = "https://datacube.services.geo.ca/stac/api/search?" + urlencode({"collections":collection,"bbox":bbox,"limit":100})
        _, rec = get_json(url, RAW / "nrcan" / f"{name}-search.json")
        records.append(rec)
        _,rec=get_json(f"https://datacube.services.geo.ca/stac/api/collections/{collection}",RAW/"nrcan"/f"{name}-collection.json")
        records.append(rec)
    for url,name in [
        ("https://open.canada.ca/en/open-government-licence-canada","ogl-canada"),
        ("https://opendata.vancouver.ca/pages/licence/","ogl-vancouver"),
    ]:
        records.append(download(url,RAW/"licences"/f"{name}.html",max_bytes=5_000_000))
    save_json(MANIFESTS/"geospatial-nrcan-sources.json",{
        "retrieved_utc":datetime.now(timezone.utc).isoformat(),"records":records,
        "hrdem_catalogue":"https://open.canada.ca/data/en/dataset/957782bf-847c-4644-a757-e383c0057995",
        "mrdem_catalogue":"https://open.canada.ca/data/en/dataset/18752265-bda3-498c-a4ba-9dfe68cb98da",
        "licence":"OGL-Canada-2.0 as declared in both STAC collections",
        "attribution":"Contains information licensed under the Open Government Licence – Canada.",
        "additional_mrdem_notice":"MRDEM includes Copernicus GLO-30 and HRDEM sources. Review the product usage guide for required source notices before public distribution.",
        "release_rights_status":"Public OGL collection verified; final combined credits and source notices not signed off.",
        "vertical_datum_authority":"NRCan HRDEM and MRDEM product catalogue states CGVD2013. GeoTIFF horizontal CRS alone does not encode the height datum.",
    })
    print("NRCan source and licence manifest saved")


if __name__ == "__main__":
    main()
