#!/usr/bin/env python3
"""Summarize independent NLCD and USDA CDL land-cover evidence by analysis unit.

These products corroborate, but do not replace, dated-image interpretation. Results
are calculated inside provisional screening envelopes and therefore inherit their
boundary and neighbor-contamination limitations.
"""

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
ENVELOPES = ROOT / "data/illinois_land_use_change/interim/screening_envelopes.geojson"
OUT = ROOT / "data/illinois_land_use_change/interim"
NLCD_YEARS = [2001, 2004, 2006, 2008, 2011, 2013, 2016, 2019, 2021]
CDL_YEARS = [2008, 2011, 2015, 2017, 2019, 2021, 2023, 2024]


def initialize() -> None:
    token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
    ee.Initialize(credentials=Credentials(token), project="earthindex")


def feature_collection(envelopes: gpd.GeoDataFrame) -> ee.FeatureCollection:
    features = []
    for row in envelopes.itertuples():
        geometry = json.loads(gpd.GeoSeries([row.geometry], crs=4326).to_json())["features"][0]["geometry"]
        features.append(ee.Feature(ee.Geometry(geometry), {"analysis_unit_id": row.analysis_unit_id}))
    return ee.FeatureCollection(features)


def broad_class_stack(image: ee.Image, dataset: str) -> ee.Image:
    value = image.select(0)
    if dataset == "nlcd":
        masks = {
            "developed": value.gte(21).And(value.lte(24)),
            "agriculture": value.eq(81).Or(value.eq(82)),
            "forest": value.gte(41).And(value.lte(43)),
            "grass_shrub": value.eq(51).Or(value.eq(52)).Or(value.gte(71).And(value.lte(74))),
            "wetland": value.eq(90).Or(value.eq(95)),
            "barren": value.eq(31),
            "water": value.eq(11),
        }
    else:
        # CDL codes 1-60 and 66-80 are annual/specialty crops; 204-254 are
        # predominantly double-crop and specialty-crop classes. Pasture/hay is
        # retained separately because it is not direct evidence of row cropping.
        crop = value.gte(1).And(value.lte(60)).Or(value.gte(66).And(value.lte(80))).Or(
            value.gte(204).And(value.lte(254))
        )
        masks = {
            "crops": crop,
            "pasture_hay": value.eq(61).Or(value.eq(176)),
            "developed": value.gte(121).And(value.lte(124)),
            "forest": value.eq(63).Or(value.gte(141).And(value.lte(143))),
            "grass_shrub": value.eq(64).Or(value.eq(152)),
            "wetland": value.eq(190).Or(value.eq(195)),
            "barren": value.eq(65).Or(value.eq(131)),
            "water": value.eq(83).Or(value.eq(87).Or(value.eq(111))),
        }
    return ee.Image.cat(
        [ee.Image.pixelArea().multiply(mask).rename(f"{name}_area_m2") for name, mask in masks.items()]
    )


def summarize(features: ee.FeatureCollection, image: ee.Image, dataset: str, year: int, scale: int) -> list[dict]:
    stack = broad_class_stack(image, dataset)
    result = stack.reduceRegions(
        collection=features, reducer=ee.Reducer.sum(), scale=scale, tileScale=4
    ).getInfo()
    rows = []
    for feature in result.get("features", []):
        props = feature["properties"]
        areas = {}
        for key, value in props.items():
            if key.endswith("_area_m2_sum"):
                areas[key.removesuffix("_area_m2_sum")] = float(value or 0)
            elif key.endswith("_area_m2"):
                areas[key.removesuffix("_area_m2")] = float(value or 0)
        total = sum(areas.values())
        for class_name, area in areas.items():
            rows.append(
                {
                    "analysis_unit_id": props["analysis_unit_id"],
                    "dataset": dataset,
                    "year": year,
                    "class_name": class_name,
                    "area_m2": area,
                    "area_pct": 100 * area / total if total else None,
                    "scale_m": scale,
                }
            )
    return rows


def main() -> None:
    initialize()
    envelopes = gpd.read_file(ENVELOPES).to_crs(4326)
    features = feature_collection(envelopes)
    rows = []

    historical_nlcd = ee.ImageCollection("USGS/NLCD_RELEASES/2019_REL/NLCD")
    for year in NLCD_YEARS:
        if year == 2021:
            image = ee.ImageCollection("USGS/NLCD_RELEASES/2021_REL/NLCD").first().select("landcover")
        else:
            image = historical_nlcd.filter(ee.Filter.eq("system:index", str(year))).first().select("landcover")
        annual = summarize(features, image, "nlcd", year, 30)
        rows.extend(annual)
        print("nlcd", year, len(annual))

    for year in CDL_YEARS:
        image = ee.ImageCollection("USDA/NASS/CDL").filterDate(f"{year}-01-01", f"{year + 1}-01-01").first().select("cropland")
        annual = summarize(features, image, "cdl", year, 30)
        rows.extend(annual)
        print("cdl", year, len(annual))

    table = pd.DataFrame(rows).sort_values(["analysis_unit_id", "dataset", "year", "class_name"])
    table.to_parquet(OUT / "independent_landcover_annual.parquet", index=False)
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "earth_engine_project": "earthindex",
        "datasets": {
            "nlcd": "USGS/NLCD_RELEASES/2019_REL/NLCD plus USGS/NLCD_RELEASES/2021_REL/NLCD",
            "cdl": "USDA/NASS/CDL",
        },
        "years": {"nlcd": NLCD_YEARS, "cdl": CDL_YEARS},
        "analysis_unit_count": int(table.analysis_unit_id.nunique()),
        "row_count": int(len(table)),
        "warning": "Independent categorical screening inside provisional envelopes; final prior-use labels require direct imagery and documentary review.",
    }
    (OUT / "independent_landcover_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
