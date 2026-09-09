#!/usr/bin/env python3
"""Fetch standardized NAIP before/current and 2026 Sentinel-2 review chips."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import ee
import geopandas as gpd
import requests
from google.oauth2.credentials import Credentials


ROOT = Path(__file__).resolve().parents[2]
UNITS = ROOT / "data/illinois_land_use_change/final/analysis_units_screening.geojson"
OUT = ROOT / "data/illinois_land_use_change/review/imagery"
MANIFEST = ROOT / "data/illinois_land_use_change/review/imagery_manifest.json"
CRS_AREA = 26916
NAIP_YEARS = [2011, 2012, 2014, 2015, 2017, 2019, 2021, 2023]


def initialize() -> None:
    token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
    ee.Initialize(credentials=Credentials(token), project="earthindex")


def ee_geometry(bounds) -> ee.Geometry:
    xmin, ymin, xmax, ymax = bounds
    return ee.Geometry.Rectangle([xmin, ymin, xmax, ymax], proj="EPSG:4326", geodesic=False)


def square_bounds(geometry) -> list[float]:
    projected = gpd.GeoSeries([geometry], crs=4326).to_crs(CRS_AREA)
    shape = projected.iloc[0]
    center = shape.centroid
    span = max(shape.bounds[2] - shape.bounds[0], shape.bounds[3] - shape.bounds[1], 450)
    half = min(max(span * 0.68, 300), 1400)
    square = center.buffer(half, cap_style=3)
    return [float(value) for value in gpd.GeoSeries([square], crs=CRS_AREA).to_crs(4326).iloc[0].bounds]


def download(image: ee.Image, region: ee.Geometry, path: Path, vis: dict) -> None:
    url = image.visualize(**vis).getThumbURL(
        {"region": region, "dimensions": "640x640", "format": "png", "crs": "EPSG:3857"}
    )
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    path.write_bytes(response.content)


def nearest_baseline_year(start_value) -> int:
    try:
        year = int(str(start_value)[:4])
    except (TypeError, ValueError):
        return 2011
    eligible = [candidate for candidate in NAIP_YEARS if candidate < year]
    return max(eligible) if eligible else 2011


def main() -> None:
    initialize()
    OUT.mkdir(parents=True, exist_ok=True)
    units = gpd.read_file(UNITS).to_crs(4326)
    manifest = []
    for row in units.itertuples():
        bounds = square_bounds(row.geometry)
        region = ee_geometry(bounds)
        baseline_year = nearest_baseline_year(row.construction_start)
        for role, year in (("baseline", baseline_year), ("naip_current", 2023)):
            collection = ee.ImageCollection("USDA/NAIP/DOQQ").filterBounds(region).filterDate(
                f"{year}-01-01", f"{year + 1}-01-01"
            )
            count = int(collection.size().getInfo())
            dates = sorted(set(collection.aggregate_array("system:time_start").getInfo()))
            iso_dates = [ee.Date(value).format("YYYY-MM-dd").getInfo() for value in dates]
            image = collection.mosaic()
            path = OUT / f"{row.analysis_unit_id}_{role}_{year}.png"
            download(image, region, path, {"bands": ["R", "G", "B"], "min": 0, "max": 255})
            manifest.append(
                {
                    "analysis_unit_id": row.analysis_unit_id,
                    "role": role,
                    "dataset": "USDA/NAIP/DOQQ",
                    "year": year,
                    "item_count": count,
                    "acquisition_dates": iso_dates,
                    "bbox_wgs84": bounds,
                    "path": str(path.relative_to(ROOT)),
                }
            )

        def mask_s2(image):
            qa = image.select("QA60")
            return image.updateMask(qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0)))

        s2 = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(region)
            .filterDate("2026-05-01", "2026-09-01")
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40))
        )
        s2_count = int(s2.size().getInfo())
        s2_dates = sorted(set(s2.aggregate_array("system:time_start").getInfo()))
        s2_iso_dates = [ee.Date(value).format("YYYY-MM-dd").getInfo() for value in s2_dates]
        s2_path = OUT / f"{row.analysis_unit_id}_sentinel2_2026.png"
        download(s2.map(mask_s2).median(), region, s2_path, {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3200, "gamma": 1.15})
        manifest.append(
            {
                "analysis_unit_id": row.analysis_unit_id,
                "role": "sentinel2_current",
                "dataset": "COPERNICUS/S2_SR_HARMONIZED",
                "year": 2026,
                "item_count": s2_count,
                "acquisition_dates": s2_iso_dates,
                "composite_period": ["2026-05-01", "2026-08-31"],
                "bbox_wgs84": bounds,
                "path": str(s2_path.relative_to(ROOT)),
            }
        )
        print(row.analysis_unit_id, baseline_year, s2_count)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
