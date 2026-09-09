#!/usr/bin/env python3
"""Compute annual Dynamic World land-cover summaries for study campuses.

Authentication uses the active gcloud user token and the Earth Engine-enabled
`earthindex` Cloud project. No refresh token is written to the repository.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import ee
import geopandas as gpd
import pandas as pd
from google.oauth2.credentials import Credentials


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/aurora_land_use_change/interim"
CLASSES = [
    "water",
    "trees",
    "grass",
    "flooded_vegetation",
    "crops",
    "shrub_and_scrub",
    "built",
    "bare",
    "snow_and_ice",
]


def initialize():
    token = subprocess.check_output(
        ["gcloud", "auth", "print-access-token"], text=True
    ).strip()
    ee.Initialize(credentials=Credentials(token), project="earthindex")


def ee_geometry(geometry):
    return ee.Geometry(json.loads(gpd.GeoSeries([geometry], crs=4326).to_json())["features"][0]["geometry"])


def site_geometries():
    edged = gpd.read_file(
        ROOT / "data/aurora_land_use_change/raw/edged_parcels.geojson"
    ).to_crs(4326)
    cyrus = gpd.read_file(
        ROOT / "data/aurora_land_use_change/raw/cyrus_parcels.geojson"
    ).to_crs(4326)
    return {
        "edged_chicago": edged.union_all(),
        "cyrusone_aurora_chi1_chi2": cyrus[cyrus.ADDRESS == "2905 DIEHL RD"].union_all(),
        "cyrusone_aurora_iii": cyrus[cyrus.ADDRESS == "2725 BILTER RD"].union_all(),
    }


def summarize_year(site_id, geometry, year):
    start = f"{year}-01-01"
    end = f"{year + 1}-01-01"
    collection = (
        ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
        .filterBounds(geometry)
        .filterDate(start, end)
    )
    count = int(collection.size().getInfo())
    if not count:
        return []
    probabilities = collection.select(CLASSES).median()
    means = probabilities.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geometry,
        scale=10,
        maxPixels=1_000_000,
        tileScale=2,
    ).getInfo()
    labels = probabilities.toArray().arrayArgmax().arrayGet([0]).rename("label")
    grouped = (
        ee.Image.pixelArea()
        .rename("area")
        .addBands(labels)
        .reduceRegion(
            reducer=ee.Reducer.sum().group(groupField=1, groupName="label"),
            geometry=geometry,
            scale=10,
            maxPixels=1_000_000,
            tileScale=2,
        )
        .get("groups")
        .getInfo()
        or []
    )
    areas = {int(g["label"]): float(g["sum"]) for g in grouped}
    total = sum(areas.values())
    rows = []
    for label, class_name in enumerate(CLASSES):
        rows.append(
            {
                "site_id": site_id,
                "year": year,
                "class_name": class_name,
                "probability_median_composite_mean": means.get(class_name),
                "argmax_area_m2": areas.get(label, 0.0),
                "argmax_area_pct": 100 * areas.get(label, 0.0) / total if total else None,
                "scene_count": count,
                "dataset": "GOOGLE/DYNAMICWORLD/V1",
                "scale_m": 10,
            }
        )
    return rows


def main():
    initialize()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    geometries = site_geometries()
    for site_id, shape in geometries.items():
        geom = ee_geometry(shape)
        for year in range(2016, 2027):
            rows.extend(summarize_year(site_id, geom, year))
            print(site_id, year)
    result = pd.DataFrame(rows)
    result.to_csv(OUT / "dynamic_world_annual.csv", index=False)
    metadata = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "earth_engine_project": "earthindex",
        "dataset": "GOOGLE/DYNAMICWORLD/V1",
        "method": "Annual median class-probability composite; argmax class area at 10 m",
        "classes": CLASSES,
    }
    (OUT / "dynamic_world_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
