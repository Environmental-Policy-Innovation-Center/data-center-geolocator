#!/usr/bin/env python3
"""Package the compact statewide dataset without duplicating raw image chips."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/illinois_land_use_change"
OUT = ROOT / "reports/illinois_land_use_change/illinois_data_center_land_use_change_screening_dataset.zip"

FILES = [
    "README.md",
    "inventory/taxonomy_seed_sites.geojson",
    "inventory/analysis_units_preliminary.geojson",
    "inventory/source_crosswalk_preliminary.json",
    "inventory/entity_resolution_summary.json",
    "final/analysis_units_screening.geojson",
    "final/analysis_units_screening.parquet",
    "final/documentary_evidence.json",
    "final/screening_summary.json",
    "final/qa_summary.json",
    "interim/breakpoint_screening.parquet",
    "interim/breakpoint_screening_summary.json",
    "interim/dynamic_world_screening_annual.parquet",
    "interim/dynamic_world_screening_metadata.json",
    "interim/independent_landcover_annual.parquet",
    "interim/independent_landcover_metadata.json",
    "interim/dynamic_world_built_core_2026.geojson",
    "interim/dynamic_world_built_core_2026.parquet",
    "interim/dynamic_world_built_core_2026_summary.json",
    "interim/dynamic_world_built_core_2026_metadata.json",
    "interim/overture_building_candidates.geojson",
    "interim/overture_candidate_summary.json",
    "interim/screening_envelopes.geojson",
    "interim/screening_envelope_summary.json",
    "interim/imagery_readiness_by_unit.parquet",
    "interim/imagery_availability_metadata.json",
    "review/imagery_manifest.json",
]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(OUT, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in FILES:
            path = DATA / relative
            if not path.exists():
                raise FileNotFoundError(path)
            archive.write(path, arcname=f"illinois_land_use_change/{relative}")
    print(f"{OUT} ({OUT.stat().st_size:,} bytes; {len(FILES)} files)")


if __name__ == "__main__":
    main()
