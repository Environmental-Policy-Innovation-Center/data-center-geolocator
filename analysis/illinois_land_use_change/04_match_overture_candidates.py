#!/usr/bin/env python3
"""Match Overture buildings to reference geometries for human footprint review."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "data/illinois_land_use_change/inventory"
OVERTURE = ROOT / "data/illinois_land_use_change/raw/overture"
OUT = ROOT / "data/illinois_land_use_change/interim"
ANALYSIS_CRS = 26916
MIN_BUILDING_M2 = 500

CAMPUS_BOUNDARY_UNITS = {"meta_dekalb_campus", "site_02613"}
EXPANSION_SEARCH_M = {
    "microsoft_elk_grove_campus": 400,
    "aligned_northlake_ord01_ord02": 150,
    "element_critical_wood_dale_ch1_ch2": 150,
    "edgeconnex_elk_grove_chi01_chi02": 150,
    "ntt_itasca_chicago_campus": 150,
    "aurora_cyrusone_chi1_chi2": 100,
}


def source_fields(value) -> tuple[str, str, str]:
    records = value if value is not None and not isinstance(value, (str, bytes)) else []
    datasets = []
    update_times = []
    record_ids = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("dataset"):
            datasets.append(str(record["dataset"]))
        if record.get("update_time"):
            update_times.append(str(record["update_time"]))
        if record.get("record_id"):
            record_ids.append(str(record["record_id"]))
    return "|".join(sorted(set(datasets))), max(update_times, default=""), "|".join(sorted(set(record_ids)))


def main() -> None:
    units = gpd.read_file(INVENTORY / "analysis_units_preliminary.geojson").to_crs(ANALYSIS_CRS)
    assignments = {
        item["analysis_unit_id"]: item["query_zone_id"]
        for item in json.loads((INVENTORY / "query_zone_assignments.json").read_text())
    }
    zone_cache = {}
    rows = []

    for unit in units.itertuples():
        zone_id = assignments[unit.analysis_unit_id]
        if zone_id not in zone_cache:
            zone_cache[zone_id] = gpd.read_parquet(
                OVERTURE / f"{zone_id}_buildings.parquet"
            ).to_crs(ANALYSIS_CRS)
        buildings = zone_cache[zone_id].copy()
        buildings["building_area_m2"] = buildings.geometry.area
        buildings = buildings[buildings["building_area_m2"] >= MIN_BUILDING_M2].copy()
        buildings["distance_to_reference_m"] = buildings.geometry.distance(unit.geometry)

        if unit.analysis_unit_id in CAMPUS_BOUNDARY_UNITS:
            mask = buildings.geometry.representative_point().within(unit.geometry.buffer(10))
            search_method = "representative_point_inside_reference_campus"
            search_distance_m = 10
        else:
            search_distance_m = EXPANSION_SEARCH_M.get(unit.analysis_unit_id, 35)
            mask = buildings["distance_to_reference_m"] <= search_distance_m
            search_method = "distance_to_reference_geometry"

        candidates = buildings[mask].copy()
        for building in candidates.itertuples():
            datasets, source_update_time, source_record_ids = source_fields(building.sources)
            intersection_m2 = building.geometry.intersection(unit.geometry).area
            rows.append(
                {
                    "analysis_unit_id": unit.analysis_unit_id,
                    "query_zone_id": zone_id,
                    "overture_id": building.id,
                    "building_area_m2": round(building.building_area_m2, 1),
                    "distance_to_reference_m": round(building.distance_to_reference_m, 1),
                    "reference_intersection_m2": round(intersection_m2, 1),
                    "search_method": search_method,
                    "search_distance_m": search_distance_m,
                    "overture_release": "2026-08-19.0",
                    "source_datasets": datasets,
                    "source_update_time": source_update_time,
                    "source_record_ids": source_record_ids,
                    "review_status": "accepted_from_aurora_poc" if unit.analysis_unit_id == "aurora_cyrusone_chi1_chi2" else "candidate_needs_visual_review",
                    "geometry": building.geometry,
                }
            )

    candidates = gpd.GeoDataFrame(rows, geometry="geometry", crs=ANALYSIS_CRS).to_crs(4326)
    candidates = candidates.sort_values(["analysis_unit_id", "building_area_m2"], ascending=[True, False])
    OUT.mkdir(parents=True, exist_ok=True)
    candidates.to_file(OUT / "overture_building_candidates.geojson", driver="GeoJSON")

    counts = candidates.groupby("analysis_unit_id").agg(
        candidate_building_count=("overture_id", "count"),
        candidate_area_m2=("building_area_m2", "sum"),
        latest_source_update=("source_update_time", "max"),
    )
    all_units = pd.DataFrame({"analysis_unit_id": units["analysis_unit_id"]}).set_index("analysis_unit_id")
    counts = all_units.join(counts).fillna(
        {"candidate_building_count": 0, "candidate_area_m2": 0, "latest_source_update": ""}
    )
    summary = {
        "overture_release": "2026-08-19.0",
        "analysis_unit_count": int(len(units)),
        "analysis_units_with_candidates": int((counts["candidate_building_count"] > 0).sum()),
        "analysis_units_without_candidates": counts.index[counts["candidate_building_count"] == 0].tolist(),
        "candidate_building_count": int(len(candidates)),
        "by_analysis_unit": counts.reset_index().to_dict(orient="records"),
        "warning": "Candidates are search results for visual review, not accepted data-center footprints.",
    }
    (OUT / "overture_candidate_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
