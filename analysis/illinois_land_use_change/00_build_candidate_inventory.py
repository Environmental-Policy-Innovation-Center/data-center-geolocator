#!/usr/bin/env python3
"""Build the statewide seed inventory for the land-use change scale-up."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "visual-taxonomy/il_data_centers_taxonomy.geojson"
OUT = ROOT / "data/illinois_land_use_change/inventory"

TARGET_GROUPS = {
    "hyperscale_greenfield_campus": "wave_1_hyperscale",
    "large_purpose_built_data_center": "wave_2_large_purpose_built",
    "industrial_park_warehouse_style_colo": "wave_3_warehouse_style",
}

# The Aurora proof of concept established that these two taxonomy records are
# buildings/phases within one campus-level analysis unit.
AURORA_RECORDS = {"site_01911", "site_02530"}
AURORA_UNIT = "aurora_cyrusone_chi1_chi2"


def main() -> None:
    sites = gpd.read_file(SOURCE).to_crs(4326)
    selected = sites[sites["taxonomy_group_id"].isin(TARGET_GROUPS)].copy()
    selected["seed_record_id"] = selected["site_group_id"]
    selected["analysis_unit_id_candidate"] = selected["site_group_id"]
    selected["entity_resolution_status"] = "pending"
    selected["poc_status"] = "not_started"
    selected["processing_wave"] = selected["taxonomy_group_id"].map(TARGET_GROUPS)

    aurora = selected["site_group_id"].isin(AURORA_RECORDS)
    selected.loc[aurora, "analysis_unit_id_candidate"] = AURORA_UNIT
    selected.loc[aurora, "entity_resolution_status"] = "resolved_in_aurora_poc"
    selected.loc[aurora, "poc_status"] = "complete"
    selected.loc[aurora, "processing_wave"] = "wave_0_reference_poc"

    selected = selected.sort_values(
        ["processing_wave", "taxonomy_group_id", "site_group_id"]
    ).reset_index(drop=True)

    OUT.mkdir(parents=True, exist_ok=True)
    selected.to_file(OUT / "taxonomy_seed_sites.geojson", driver="GeoJSON")

    counts = selected.groupby("taxonomy_group_id").size().to_dict()
    summary = {
        "source": str(SOURCE.relative_to(ROOT)),
        "target_taxonomy_groups": list(TARGET_GROUPS),
        "seed_record_count": int(len(selected)),
        "initial_analysis_unit_count": int(selected["analysis_unit_id_candidate"].nunique()),
        "completed_aurora_seed_record_count": int(aurora.sum()),
        "completed_aurora_analysis_unit_count": 1,
        "counts_by_taxonomy_group": {key: int(value) for key, value in counts.items()},
        "entity_resolution_note": (
            "Analysis-unit count is provisional until parcel, operator, address, "
            "and physical-campus continuity checks are complete statewide."
        ),
    }
    payload = json.dumps(summary, indent=2) + "\n"
    (OUT / "inventory_summary.json").write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
