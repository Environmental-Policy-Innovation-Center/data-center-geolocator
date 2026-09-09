#!/usr/bin/env python3
"""Build provisional masks for automated land-cover change screening."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd


ROOT = Path(__file__).resolve().parents[2]
UNITS = ROOT / "data/illinois_land_use_change/inventory/analysis_units_preliminary.geojson"
AURORA_SITES = ROOT / "data/aurora_land_use_change/final/sites.geojson"
OUT = ROOT / "data/illinois_land_use_change/interim"
ANALYSIS_CRS = 26916

CAMPUS_BOUNDARY_UNITS = {"meta_dekalb_campus", "site_02613"}
CUSTOM_BUFFERS_M = {"microsoft_elk_grove_campus": 300}
DEFAULT_BUFFER_M = 120


def main() -> None:
    units = gpd.read_file(UNITS).to_crs(ANALYSIS_CRS)
    aurora = gpd.read_file(AURORA_SITES).to_crs(ANALYSIS_CRS)
    aurora_shape = aurora[aurora["site_id"] == "cyrusone_aurora_chi1_chi2"].geometry.union_all()
    rows = []

    for unit in units.itertuples():
        if unit.analysis_unit_id == "aurora_cyrusone_chi1_chi2":
            geometry = aurora_shape
            basis = "reviewed_aurora_campus_boundary"
            buffer_m = 0
            confidence = "high"
        elif unit.analysis_unit_id in CAMPUS_BOUNDARY_UNITS:
            geometry = unit.geometry
            basis = "reference_campus_geometry"
            buffer_m = 0
            confidence = "medium"
        else:
            buffer_m = CUSTOM_BUFFERS_M.get(unit.analysis_unit_id, DEFAULT_BUFFER_M)
            geometry = unit.geometry.buffer(buffer_m)
            basis = "reference_building_union_buffer"
            confidence = "low"
        rows.append(
            {
                "analysis_unit_id": unit.analysis_unit_id,
                "taxonomy_group_id": unit.taxonomy_group_id,
                "screening_geometry_basis": basis,
                "buffer_m": buffer_m,
                "screening_geometry_confidence": confidence,
                "geometry": geometry,
            }
        )

    envelopes = gpd.GeoDataFrame(rows, geometry="geometry", crs=ANALYSIS_CRS)
    envelopes["screening_area_m2"] = envelopes.geometry.area.round(1)
    envelopes["overlap_with_other_screening_masks_m2"] = 0.0
    for index, row in envelopes.iterrows():
        others = envelopes.drop(index=index)
        overlap = others.geometry.intersection(row.geometry).area.sum()
        envelopes.at[index, "overlap_with_other_screening_masks_m2"] = round(float(overlap), 1)
    envelopes["neighbor_contamination_flag"] = envelopes[
        "overlap_with_other_screening_masks_m2"
    ].gt(0)

    OUT.mkdir(parents=True, exist_ok=True)
    envelopes.to_crs(4326).to_file(OUT / "screening_envelopes.geojson", driver="GeoJSON")
    summary = {
        "analysis_unit_count": int(len(envelopes)),
        "basis_counts": envelopes["screening_geometry_basis"].value_counts().to_dict(),
        "neighbor_contamination_flag_count": int(envelopes["neighbor_contamination_flag"].sum()),
        "warning": "These masks support breakpoint screening only and are not project, parcel, disturbance, or campus boundaries.",
    }
    (OUT / "screening_envelope_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
