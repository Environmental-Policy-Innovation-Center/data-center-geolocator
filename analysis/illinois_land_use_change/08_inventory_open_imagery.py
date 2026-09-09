#!/usr/bin/env python3
"""Inventory open STAC imagery availability for each shared query zone."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pystac_client import Client


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "data/illinois_land_use_change/inventory"
OUT = ROOT / "data/illinois_land_use_change/interim"
CATALOG_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"

COLLECTIONS = {
    "naip": {"collection": "naip", "start": "2003-01-01", "end": "2026-09-09", "cloud_query": None},
    "sentinel2_l2a": {
        "collection": "sentinel-2-l2a",
        "start": "2015-01-01",
        "end": "2026-09-09",
        "cloud_query": {"eo:cloud_cover": {"lt": 60}},
    },
    "landsat_c2_l2": {
        "collection": "landsat-c2-l2",
        "start": "1984-01-01",
        "end": "2026-09-09",
        "cloud_query": {"eo:cloud_cover": {"lt": 60}},
    },
}


def main() -> None:
    catalog = Client.open(CATALOG_URL)
    zones = gpd.read_file(INVENTORY / "query_zones.geojson")
    assignments = pd.DataFrame(json.loads((INVENTORY / "query_zone_assignments.json").read_text()))
    rows = []

    for zone in zones.itertuples():
        bbox = [float(value) for value in zone.bbox_wgs84.split(",")]
        for source_name, config in COLLECTIONS.items():
            kwargs = {
                "collections": [config["collection"]],
                "bbox": bbox,
                "datetime": f'{config["start"]}/{config["end"]}',
            }
            if config["cloud_query"]:
                kwargs["query"] = config["cloud_query"]
            items = list(catalog.search(**kwargs).items())
            by_year = {}
            for item in items:
                year = item.datetime.year
                by_year.setdefault(year, []).append(item)
            for year, year_items in sorted(by_year.items()):
                dates = sorted({item.datetime.date().isoformat() for item in year_items})
                clouds = [item.properties.get("eo:cloud_cover") for item in year_items]
                clouds = [float(value) for value in clouds if value is not None]
                rows.append(
                    {
                        "query_zone_id": zone.query_zone_id,
                        "source_name": source_name,
                        "collection": config["collection"],
                        "year": year,
                        "item_count": len(year_items),
                        "distinct_acquisition_dates": len(dates),
                        "first_date": dates[0],
                        "last_date": dates[-1],
                        "minimum_item_cloud_cover_pct": min(clouds) if clouds else None,
                    }
                )
            print(zone.query_zone_id, source_name, len(items))

    availability = pd.DataFrame(rows).sort_values(["query_zone_id", "source_name", "year"])
    availability.to_parquet(OUT / "imagery_availability_by_zone.parquet", index=False)

    summaries = []
    for zone_id, group in availability.groupby("query_zone_id"):
        record = {"query_zone_id": zone_id}
        for source_name in COLLECTIONS:
            source = group[group["source_name"] == source_name]
            years = source["year"].astype(int).tolist()
            record[f"{source_name}_years"] = "|".join(map(str, years))
            record[f"{source_name}_first_year"] = min(years) if years else None
            record[f"{source_name}_last_year"] = max(years) if years else None
            record[f"{source_name}_item_count"] = int(source["item_count"].sum())
        summaries.append(record)
    readiness = assignments.merge(pd.DataFrame(summaries), on="query_zone_id", how="left")
    readiness.to_parquet(OUT / "imagery_readiness_by_unit.parquet", index=False)

    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalog": CATALOG_URL,
        "query_zone_count": int(zones.shape[0]),
        "analysis_unit_count": int(readiness["analysis_unit_id"].nunique()),
        "collections": COLLECTIONS,
        "note": "Availability is inventoried by shared spatial query zone; item cloud cover is scene-level and does not replace local clear-pixel review.",
    }
    (OUT / "imagery_availability_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
