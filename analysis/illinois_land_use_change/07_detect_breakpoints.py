#!/usr/bin/env python3
"""Convert annual Dynamic World summaries into reviewable breakpoint candidates."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
INTERIM = ROOT / "data/illinois_land_use_change/interim"
INVENTORY = ROOT / "data/illinois_land_use_change/inventory"


def main() -> None:
    annual = pd.read_parquet(INTERIM / "dynamic_world_screening_annual.parquet")
    envelopes = gpd.read_file(INTERIM / "screening_envelopes.geojson")[
        ["analysis_unit_id", "neighbor_contamination_flag", "screening_geometry_confidence"]
    ]
    units = gpd.read_file(INVENTORY / "analysis_units_preliminary.geojson")[
        ["analysis_unit_id", "canonical_name", "taxonomy_group_id", "poc_status"]
    ]

    wide = annual.pivot_table(
        index=["analysis_unit_id", "year"], columns="class_name", values="argmax_area_pct", aggfunc="first"
    ).reset_index()
    for name in ["built", "bare", "crops", "trees", "grass", "shrub_and_scrub"]:
        if name not in wide:
            wide[name] = 0.0
    wide["development_signal_pct"] = wide["built"] + wide["bare"]
    wide["vegetated_signal_pct"] = wide["crops"] + wide["trees"] + wide["grass"] + wide["shrub_and_scrub"]
    wide["development_signal_change_pct_points"] = wide.groupby("analysis_unit_id")["development_signal_pct"].diff()
    wide["built_change_pct_points"] = wide.groupby("analysis_unit_id")["built"].diff()
    wide["vegetated_change_pct_points"] = wide.groupby("analysis_unit_id")["vegetated_signal_pct"].diff()

    rows = []
    for site_id, group in wide.groupby("analysis_unit_id"):
        group = group.sort_values("year")
        first = group.iloc[0]
        strongest_index = group["development_signal_change_pct_points"].fillna(-999).idxmax()
        strongest = group.loc[strongest_index]
        max_change = float(strongest["development_signal_change_pct_points"])
        max_built_change = float(strongest["built_change_pct_points"])
        if first["built"] >= 40 and max_change < 15:
            screening_result = "predates_dynamic_world_or_mature_by_2016"
            lower_year = None
            upper_year = 2016
        elif max_change >= 15:
            screening_result = "candidate_construction_or_major_redevelopment"
            lower_year = int(strongest["year"] - 1)
            upper_year = int(strongest["year"])
        else:
            screening_result = "no_clear_dynamic_world_breakpoint"
            lower_year = None
            upper_year = None
        rows.append(
            {
                "analysis_unit_id": site_id,
                "dynamic_world_screening_result": screening_result,
                "candidate_start_lower_year": lower_year,
                "candidate_start_upper_year": upper_year,
                "strongest_change_year": int(strongest["year"]),
                "development_signal_change_pct_points": round(max_change, 2),
                "built_change_pct_points": round(max_built_change, 2),
                "vegetated_change_pct_points": round(float(strongest["vegetated_change_pct_points"]), 2),
                "built_pct_2016": round(float(first["built"]), 2),
                "development_signal_pct_2016": round(float(first["development_signal_pct"]), 2),
                "screening_only": True,
            }
        )

    breakpoints = pd.DataFrame(rows).merge(units, on="analysis_unit_id", how="left").merge(
        envelopes, on="analysis_unit_id", how="left"
    )
    breakpoints["review_priority"] = "standard"
    breakpoints.loc[breakpoints["neighbor_contamination_flag"], "review_priority"] = "high_neighbor_overlap"
    breakpoints.loc[
        breakpoints["dynamic_world_screening_result"].eq("predates_dynamic_world_or_mature_by_2016"),
        "review_priority",
    ] = "historical_imagery_required"
    breakpoints.loc[breakpoints["poc_status"].eq("complete"), "review_priority"] = "completed_reference"
    breakpoints = breakpoints.sort_values(["review_priority", "analysis_unit_id"])
    breakpoints.to_parquet(INTERIM / "breakpoint_screening.parquet", index=False)

    summary = {
        "analysis_unit_count": int(len(breakpoints)),
        "result_counts": breakpoints["dynamic_world_screening_result"].value_counts().to_dict(),
        "review_priority_counts": breakpoints["review_priority"].value_counts().to_dict(),
        "candidate_intervals": breakpoints[
            breakpoints["dynamic_world_screening_result"].eq(
                "candidate_construction_or_major_redevelopment"
            )
        ][
            [
                "analysis_unit_id",
                "canonical_name",
                "candidate_start_lower_year",
                "candidate_start_upper_year",
                "development_signal_change_pct_points",
                "neighbor_contamination_flag",
            ]
        ].to_dict(orient="records"),
        "warning": "Breakpoints nominate imagery-review dates only; they are not final construction dates.",
    }
    (INTERIM / "breakpoint_screening_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
