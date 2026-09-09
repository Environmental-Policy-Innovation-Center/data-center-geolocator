#!/usr/bin/env python3
"""Extract provisional 2026 built-surface polygons from Dynamic World.

These polygons are screening products, not authoritative building footprints.
Dynamic World operates at 10 m and may merge roofs with pavement, equipment
pads, or other impervious surfaces. Two products are written:

* core: built is the median-composite argmax class and P(built) >= 0.50
* inclusive: built is the argmax class and P(built) >= 0.30

Only connected patches of at least 500 m2 are retained. Attributes quantify
overlap with the existing Overture/plan-derived roof layer.
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
FINAL = ROOT / "data/aurora_land_use_change/final"
CRS_AREA = "EPSG:26916"
DATE_START = "2026-01-01"
DATE_END = "2026-09-01"
MIN_PATCH_M2 = 500.0


def initialize():
    token = subprocess.check_output(
        ["gcloud", "auth", "print-access-token"], text=True
    ).strip()
    ee.Initialize(credentials=Credentials(token), project="earthindex")


def to_ee_geometry(geometry):
    feature = json.loads(gpd.GeoSeries([geometry], crs=4326).to_json())["features"][0]
    return ee.Geometry(feature["geometry"])


def extract_site(site_id, geometry, threshold):
    ee_geom = to_ee_geometry(geometry)
    collection = (
        ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
        .filterBounds(ee_geom)
        .filterDate(DATE_START, DATE_END)
    )
    scene_count = int(collection.size().getInfo())
    probabilities = collection.select(
        ["water", "trees", "grass", "flooded_vegetation", "crops", "shrub_and_scrub", "built", "bare", "snow_and_ice"]
    ).median()
    built_probability = probabilities.select("built")
    argmax = probabilities.toArray().arrayArgmax().arrayGet([0])
    built_vote = collection.map(lambda image: image.select("label").eq(6)).mean()
    mask = argmax.eq(6).And(built_probability.gte(threshold))
    vectors = (
        mask.selfMask()
        .toInt()
        .rename("class")
        .reduceToVectors(
            geometry=ee_geom,
            scale=10,
            geometryType="polygon",
            eightConnected=True,
            labelProperty="dw_class",
            reducer=ee.Reducer.countEvery(),
            maxPixels=10_000_000,
            tileScale=2,
        )
    )
    stats = built_probability.rename("built_probability").addBands(
        built_vote.rename("built_vote_fraction")
    )
    vectors = stats.reduceRegions(vectors, ee.Reducer.mean(), 10)
    info = vectors.getInfo()
    rows = []
    for feature in info.get("features", []):
        props = feature.get("properties", {})
        rows.append(
            {
                "site_id": site_id,
                "threshold": threshold,
                "scene_count": scene_count,
                "built_probability_mean": props.get("built_probability"),
                "built_vote_fraction_mean": props.get("built_vote_fraction"),
                "geometry": feature["geometry"],
            }
        )
    if not rows:
        return gpd.GeoDataFrame(columns=["site_id", "geometry"], geometry="geometry", crs=4326)
    return gpd.GeoDataFrame.from_features(
        [
            {
                "type": "Feature",
                "properties": {k: v for k, v in row.items() if k != "geometry"},
                "geometry": row["geometry"],
            }
            for row in rows
        ],
        crs=4326,
    )


def annotate(gdf, roofs, product):
    if gdf.empty:
        return gdf
    result = gdf.to_crs(CRS_AREA)
    result.geometry = result.geometry.buffer(0)
    result["area_m2"] = result.geometry.area
    result = result[result.area_m2 >= MIN_PATCH_M2].copy()
    result["product"] = product
    result["observation_start"] = DATE_START
    result["observation_end"] = "2026-08-31"
    result["dataset"] = "GOOGLE/DYNAMICWORLD/V1"
    result["nominal_resolution_m"] = 10
    result["geometry_confidence"] = "low"
    result["interpretation"] = "provisional built surface; not a roof boundary"
    result["known_roof_overlap_m2"] = 0.0
    result["known_roof_overlap_pct"] = 0.0
    result["screening_class"] = "unmatched built-surface candidate"
    for idx, row in result.iterrows():
        candidates = roofs[roofs.site_id.eq(row.site_id)]
        overlap = candidates.geometry.intersection(row.geometry).area.sum()
        result.at[idx, "known_roof_overlap_m2"] = overlap
        result.at[idx, "known_roof_overlap_pct"] = 100 * overlap / row.area_m2
        if overlap / row.area_m2 >= 0.25:
            result.at[idx, "screening_class"] = "supports existing roof footprint"
        elif row.area_m2 >= 2_000:
            result.at[idx, "screening_class"] = "large unmatched built-surface candidate"
    result = result.sort_values(["site_id", "area_m2"], ascending=[True, False]).reset_index(drop=True)
    result.insert(0, "dw_polygon_id", [f"dw26_{product}_{i+1:03d}" for i in range(len(result))])
    return result.to_crs(4326)


def main():
    initialize()
    sites = gpd.read_file(FINAL / "sites.geojson").to_crs(4326)
    roofs = gpd.read_file(FINAL / "buildings.geojson").to_crs(CRS_AREA)
    outputs = {}
    for product, threshold in (("core", 0.50), ("inclusive", 0.30)):
        pieces = []
        for row in sites.itertuples():
            print(product, row.site_id)
            pieces.append(extract_site(row.site_id, row.geometry, threshold))
        merged = pd.concat(pieces, ignore_index=True)
        merged = gpd.GeoDataFrame(merged, geometry="geometry", crs=4326)
        outputs[product] = annotate(merged, roofs, product)

    gpkg = FINAL / "aurora_data_center_land_use_change.gpkg"
    for product, gdf in outputs.items():
        stem = f"dynamic_world_built_{product}_2026"
        gdf.to_file(FINAL / f"{stem}.geojson", driver="GeoJSON")
        gdf.to_parquet(FINAL / f"{stem}.parquet", index=False)
        pd.DataFrame(gdf.drop(columns="geometry")).to_csv(FINAL / f"{stem}.csv", index=False)
        gdf.to_file(gpkg, layer=stem, driver="GPKG")

    summary_rows = []
    for product, gdf in outputs.items():
        projected = gdf.to_crs(CRS_AREA)
        for site_id, group in projected.groupby("site_id"):
            summary_rows.append(
                {
                    "product": product,
                    "site_id": site_id,
                    "polygon_count": len(group),
                    "total_area_m2": group.geometry.area.sum(),
                    "total_area_acres": group.geometry.area.sum() / 4046.8564224,
                    "large_unmatched_count": int(group.screening_class.str.startswith("large unmatched").sum()),
                }
            )
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(FINAL / "dynamic_world_built_2026_summary.csv", index=False)
    summary.to_parquet(FINAL / "dynamic_world_built_2026_summary.parquet", index=False)
    metadata = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "earth_engine_project": "earthindex",
        "dataset": "GOOGLE/DYNAMICWORLD/V1",
        "period": [DATE_START, DATE_END],
        "core_rule": "median-composite argmax built and median built probability >= 0.50",
        "inclusive_rule": "median-composite argmax built and median built probability >= 0.30",
        "minimum_patch_m2": MIN_PATCH_M2,
        "warning": "Built-surface screening polygons are not building footprints; 10 m pixels may include pavement and equipment pads.",
    }
    (FINAL / "dynamic_world_built_2026_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
