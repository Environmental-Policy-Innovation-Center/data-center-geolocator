# Illinois taxonomy land-use-change scale-up

This directory contains the statewide screening pass for the Illinois data-center records assigned to three visual-taxonomy categories: hyperscale greenfield campus, large purpose-built wholesale/colocation, and industrial-park warehouse-style colocation.

The 27 seed records resolve to 24 analysis units. Twenty-three remain in scope and one (`site_01928`) is excluded as a false-positive records-storage warehouse. Aurora CHI1–CHI2 remains the only QA-complete disturbance case; the other units are documented and imagery-ready screening records.

## Principal outputs

- `final/analysis_units_screening.geojson` and `.parquet`: one record per resolved analysis unit.
- `final/documentary_evidence.json`: documentary, geometry, categorical land-cover, and dated-imagery evidence catalog.
- `final/qa_summary.json`: reproducibility and completeness checks.
- `interim/dynamic_world_built_core_2026.geojson` and `.parquet`: conservative 10 m built-surface screening polygons, explicitly not roof footprints.
- `interim/overture_building_candidates.geojson`: current mapped-building candidates requiring acceptance/rejection.
- `interim/dynamic_world_screening_annual.parquet`: annual Dynamic World class summaries for 2016–2026.
- `interim/independent_landcover_annual.parquet`: NLCD and USDA CDL corroboration.
- `review/imagery_manifest.json`: exact dates, datasets, extents, and paths for 72 image chips.

The illustrated report is at `reports/illinois_land_use_change/illinois_data_center_land_use_change_screening_report.pdf` relative to the repository root. Per-unit review figures are under `figures/illinois_land_use_change/`.

## Geometry semantics

PNNL source polygons are derived from OpenStreetMap and may be incomplete or stale. Overture totals are candidate totals, not accepted roof totals. Dynamic World polygons are built-surface envelopes that can contain pavement and equipment pads. Approved-plan geometry is a separate class and is null unless a plan has actually been georeferenced. Construction disturbance is intentionally null outside the reviewed Aurora proof of concept until site-scale dated-image delineation is complete.
