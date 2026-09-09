#!/usr/bin/env python3
"""Cross-check predevelopment land use with independent categorical products."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import ee
import geopandas as gpd
from google.oauth2.credentials import Credentials


ROOT = Path(__file__).resolve().parents[2]
SITES = ROOT / "data/aurora_land_use_change/final/sites.geojson"


def initialize():
    token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
    ee.Initialize(credentials=Credentials(token), project="earthindex")


def ee_geometry(geometry):
    feature = json.loads(gpd.GeoSeries([geometry], crs=4326).to_json())["features"][0]
    return ee.Geometry(feature["geometry"])


def area_histogram(image, band, geometry, scale):
    grouped = (
        ee.Image.pixelArea()
        .addBands(image.select(band))
        .reduceRegion(
            reducer=ee.Reducer.sum().group(groupField=1, groupName="class"),
            geometry=geometry,
            scale=scale,
            maxPixels=10_000_000,
        )
        .get("groups")
        .getInfo()
    )
    values = {int(item["class"]): float(item["sum"]) for item in grouped}
    total = sum(values.values())
    return {key: 100 * value / total for key, value in values.items()}


def mean_value(image, band, geometry, scale):
    return float(
        image.select(band)
        .reduceRegion(ee.Reducer.mean(), geometry=geometry, scale=scale, maxPixels=10_000_000)
        .get(band)
        .getInfo()
    )


def main():
    initialize()
    sites = gpd.read_file(SITES).to_crs(4326).set_index("site_id")
    targets = {
        "edged_chicago": 2022,
        "cyrusone_aurora_iii": 2023,
    }
    for site_id, year in targets.items():
        geometry = ee_geometry(sites.loc[site_id].geometry)
        cdl = ee.ImageCollection("USDA/NASS/CDL").filter(ee.Filter.calendarRange(year, year, "year")).first()
        nlcd = ee.ImageCollection("USGS/NLCD_RELEASES/2021_REL/NLCD").filter(ee.Filter.eq("system:index", "2021")).first()
        worldcover = ee.ImageCollection("ESA/WorldCover/v200").first()
        cdl_hist = area_histogram(cdl, "cropland", geometry, 30)
        cultivated_hist = area_histogram(cdl, "cultivated", geometry, 30)
        cdl_confidence = mean_value(cdl, "confidence", geometry, 30)
        nlcd_hist = area_histogram(nlcd, "landcover", geometry, 30)
        wc_hist = area_histogram(worldcover, "Map", geometry, 10)
        print(f"\n{site_id}")
        print("USDA CDL", year, sorted(cdl_hist.items(), key=lambda item: item[1], reverse=True))
        print("USDA CDL cultivated", year, cultivated_hist, "mean confidence", round(cdl_confidence, 1))
        print("USGS NLCD 2021", sorted(nlcd_hist.items(), key=lambda item: item[1], reverse=True))
        print("ESA WorldCover 2021", sorted(wc_hist.items(), key=lambda item: item[1], reverse=True))


if __name__ == "__main__":
    main()
