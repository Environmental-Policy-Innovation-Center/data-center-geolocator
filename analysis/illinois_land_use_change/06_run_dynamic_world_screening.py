#!/usr/bin/env python3
"""Run annual Dynamic World breakpoint screening for all analysis units."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import ee
import geopandas as gpd
import pandas as pd
from google.oauth2.credentials import Credentials


ROOT = Path(__file__).resolve().parents[2]
ENVELOPES = ROOT / "data/illinois_land_use_change/interim/screening_envelopes.geojson"
OUT = ROOT / "data/illinois_land_use_change/interim"
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


def initialize() -> None:
    token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
    ee.Initialize(credentials=Credentials(token), project="earthindex")


def feature_collection(envelopes: gpd.GeoDataFrame) -> ee.FeatureCollection:
    features = []
    for row in envelopes.itertuples():
        geometry = json.loads(gpd.GeoSeries([row.geometry], crs=4326).to_json())["features"][0]["geometry"]
        features.append(
            ee.Feature(
                ee.Geometry(geometry),
                {"analysis_unit_id": row.analysis_unit_id, "taxonomy_group_id": row.taxonomy_group_id},
            )
        )
    return ee.FeatureCollection(features)


def summarize_year(features: ee.FeatureCollection, bounds: ee.Geometry, year: int) -> list[dict]:
    start = f"{year}-01-01"
    end = f"{year + 1}-01-01"
    collection = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(bounds).filterDate(start, end)
    scene_count = int(collection.size().getInfo())
    if not scene_count:
        return []

    probabilities = collection.select(CLASSES).median()
    labels = probabilities.toArray().arrayArgmax().arrayGet([0]).rename("label")
    area_bands = ee.Image.cat(
        [ee.Image.pixelArea().multiply(labels.eq(index)).rename(f"{name}_area_m2") for index, name in enumerate(CLASSES)]
    )
    observation_count = collection.select("built").count().rename("observation_count")
    stack = probabilities.addBands(area_bands).addBands(observation_count)
    reducer = ee.Reducer.mean().combine(ee.Reducer.sum(), sharedInputs=True)
    result = stack.reduceRegions(collection=features, reducer=reducer, scale=10, tileScale=4).getInfo()

    rows = []
    for feature in result.get("features", []):
        props = feature.get("properties", {})
        area_values = {name: float(props.get(f"{name}_area_m2_sum", 0) or 0) for name in CLASSES}
        classified_area = sum(area_values.values())
        for name in CLASSES:
            rows.append(
                {
                    "analysis_unit_id": props["analysis_unit_id"],
                    "taxonomy_group_id": props["taxonomy_group_id"],
                    "year": year,
                    "class_name": name,
                    "probability_median_composite_mean": props.get(f"{name}_mean"),
                    "argmax_area_m2": area_values[name],
                    "argmax_area_pct": 100 * area_values[name] / classified_area if classified_area else None,
                    "mean_pixel_observation_count": props.get("observation_count_mean"),
                    "regional_scene_count": scene_count,
                    "dataset": "GOOGLE/DYNAMICWORLD/V1",
                    "scale_m": 10,
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=2016)
    parser.add_argument("--end-year", type=int, default=2026)
    args = parser.parse_args()

    initialize()
    envelopes = gpd.read_file(ENVELOPES).to_crs(4326)
    features = feature_collection(envelopes)
    bounds = features.geometry().bounds()
    rows = []
    for year in range(args.start_year, args.end_year + 1):
        annual = summarize_year(features, bounds, year)
        rows.extend(annual)
        print(year, len(annual))

    result = pd.DataFrame(rows).sort_values(["analysis_unit_id", "year", "class_name"])
    result.to_parquet(OUT / "dynamic_world_screening_annual.parquet", index=False)
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "earth_engine_project": "earthindex",
        "dataset": "GOOGLE/DYNAMICWORLD/V1",
        "period": [args.start_year, args.end_year],
        "analysis_unit_count": int(result["analysis_unit_id"].nunique()),
        "row_count": int(len(result)),
        "method": "Annual median class-probability composite; 10 m argmax areas inside provisional screening masks",
        "warning": "Screening masks are not project boundaries; review neighbor-contamination flags before interpreting breakpoints.",
    }
    (OUT / "dynamic_world_screening_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
