#!/usr/bin/env python3
"""Extract conservative 2026 Dynamic World built-surface screening polygons."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import ee
import geopandas as gpd
import pandas as pd
from google.oauth2.credentials import Credentials


ROOT = Path(__file__).resolve().parents[2]
INTERIM = ROOT / "data/illinois_land_use_change/interim"
ENVELOPES = INTERIM / "screening_envelopes.geojson"
UNITS = ROOT / "data/illinois_land_use_change/inventory/analysis_units_preliminary.geojson"
CRS_AREA = 26916
DATE_START = "2026-01-01"
DATE_END = "2026-09-01"
THRESHOLD = 0.50
MIN_PATCH_M2 = 500.0
CLASSES = [
    "water", "trees", "grass", "flooded_vegetation", "crops",
    "shrub_and_scrub", "built", "bare", "snow_and_ice",
]


def initialize() -> None:
    token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
    ee.Initialize(credentials=Credentials(token), project="earthindex")


def ee_geometry(geometry) -> ee.Geometry:
    item = json.loads(gpd.GeoSeries([geometry], crs=4326).to_json())["features"][0]
    return ee.Geometry(item["geometry"])


def extract(unit_id: str, geometry) -> gpd.GeoDataFrame:
    region = ee_geometry(geometry)
    collection = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(region).filterDate(DATE_START, DATE_END)
    scene_count = int(collection.size().getInfo())
    probabilities = collection.select(CLASSES).median()
    built_probability = probabilities.select("built")
    argmax = probabilities.toArray().arrayArgmax().arrayGet([0])
    mask = argmax.eq(6).And(built_probability.gte(THRESHOLD))
    vectors = mask.selfMask().toInt().rename("class").reduceToVectors(
        geometry=region,
        scale=10,
        geometryType="polygon",
        eightConnected=True,
        labelProperty="dw_class",
        reducer=ee.Reducer.countEvery(),
        maxPixels=25_000_000,
        tileScale=4,
    )
    vectors = built_probability.rename("built_probability").reduceRegions(vectors, ee.Reducer.mean(), 10)
    records = []
    for feature in vectors.getInfo().get("features", []):
        records.append(
            {
                "type": "Feature",
                "properties": {
                    "analysis_unit_id": unit_id,
                    "scene_count": scene_count,
                    "built_probability_mean": feature["properties"].get("built_probability"),
                },
                "geometry": feature["geometry"],
            }
        )
    if not records:
        return gpd.GeoDataFrame(columns=["analysis_unit_id", "geometry"], geometry="geometry", crs=4326)
    return gpd.GeoDataFrame.from_features(records, crs=4326)


def main() -> None:
    initialize()
    envelopes = gpd.read_file(ENVELOPES).to_crs(4326)
    units = gpd.read_file(UNITS).to_crs(CRS_AREA).set_index("analysis_unit_id")
    pieces = []
    for row in envelopes.itertuples():
        print(row.analysis_unit_id)
        pieces.append(extract(row.analysis_unit_id, row.geometry))
    polygons = gpd.GeoDataFrame(pd.concat(pieces, ignore_index=True), geometry="geometry", crs=4326).to_crs(CRS_AREA)
    polygons.geometry = polygons.geometry.buffer(0)
    polygons["area_m2"] = polygons.geometry.area
    polygons = polygons[polygons.area_m2 >= MIN_PATCH_M2].copy()
    polygons["reference_geometry_overlap_m2"] = 0.0
    for index, row in polygons.iterrows():
        reference = units.loc[row.analysis_unit_id].geometry
        polygons.at[index, "reference_geometry_overlap_m2"] = row.geometry.intersection(reference).area
    polygons["reference_geometry_overlap_pct"] = (
        100 * polygons.reference_geometry_overlap_m2 / polygons.area_m2
    )
    polygons["observation_start"] = DATE_START
    polygons["observation_end"] = "2026-08-31"
    polygons["dataset"] = "GOOGLE/DYNAMICWORLD/V1"
    polygons["nominal_resolution_m"] = 10
    polygons["geometry_class"] = "provisional_satellite_built_surface_envelope"
    polygons["geometry_confidence"] = "low"
    polygons["interpretation"] = "built-surface screening; not a building footprint"
    polygons = polygons.sort_values(["analysis_unit_id", "area_m2"], ascending=[True, False]).reset_index(drop=True)
    polygons.insert(0, "dw_polygon_id", [f"ildw26_{index + 1:04d}" for index in range(len(polygons))])
    output = polygons.to_crs(4326)
    output.to_file(INTERIM / "dynamic_world_built_core_2026.geojson", driver="GeoJSON")
    output.to_parquet(INTERIM / "dynamic_world_built_core_2026.parquet", index=False)

    summary_rows = []
    for unit_id in envelopes.analysis_unit_id:
        group = polygons[polygons.analysis_unit_id == unit_id]
        summary_rows.append(
            {
                "analysis_unit_id": unit_id,
                "polygon_count": int(len(group)),
                "built_surface_area_m2": round(float(group.area_m2.sum()), 1),
                "built_surface_area_acres": round(float(group.area_m2.sum() / 4046.8564224), 2),
            }
        )
    (INTERIM / "dynamic_world_built_core_2026_summary.json").write_text(
        json.dumps(summary_rows, indent=2) + "\n"
    )
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": "GOOGLE/DYNAMICWORLD/V1",
        "period": [DATE_START, DATE_END],
        "rule": "median-composite argmax built and median built probability >= 0.50",
        "minimum_patch_m2": MIN_PATCH_M2,
        "warning": "Provisional built-surface envelopes are not roofs and may include pavement or equipment pads.",
    }
    (INTERIM / "dynamic_world_built_core_2026_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )
    print(json.dumps({"polygon_count": len(polygons), "analysis_unit_count": 24}, indent=2))


if __name__ == "__main__":
    main()
