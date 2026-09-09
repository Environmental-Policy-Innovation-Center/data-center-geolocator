#!/usr/bin/env python3
"""Resolve selected taxonomy records into preliminary campus analysis units."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SEEDS = ROOT / "data/illinois_land_use_change/inventory/taxonomy_seed_sites.geojson"
HARMONIZED = ROOT / "processed-data/harmonized-data-center-reference-sites-illinois.geojson"
PNNL_BUILDINGS = ROOT / "raw-data/data-center-locations/PNNL/PNNL_2026.02.09_building.geojson"
PNNL_CAMPUSES = ROOT / "raw-data/data-center-locations/PNNL/PNNL_2026.02.09_campus.geojson"
OUT = ROOT / "data/illinois_land_use_change/inventory"


RESOLUTION_RULES = {
    "aurora_cyrusone_chi1_chi2": {
        "seed_ids": ["site_01911", "site_02530"],
        "related_ids": [],
        "canonical_name": "CyrusOne Aurora CHI1-CHI2",
        "operator": "CyrusOne",
        "resolution_status": "resolved_in_aurora_poc",
        "identity_confidence": "high",
        "evidence": ["reports/aurora_land_use_change/aurora_data_center_land_use_change_report.pdf"],
    },
    "aligned_northlake_ord01_ord02": {
        "seed_ids": ["site_00627"],
        "related_ids": ["site_00628"],
        "canonical_name": "Aligned Northlake ORD-01/ORD-02 campus",
        "operator": "Aligned Data Centers",
        "resolution_status": "resolved_operator_campus",
        "identity_confidence": "high",
        "evidence": [
            "https://aligneddc.com/chicago-data-centers/",
            "https://aligneddc.com/press-release/aligned-breaks-ground-on-chicago-hyperscale-data-center-campus/",
        ],
    },
    "element_critical_wood_dale_ch1_ch2": {
        "seed_ids": ["site_01834", "site_02008"],
        "related_ids": [],
        "canonical_name": "Element Critical Wood Dale CH1-CH2 campus",
        "operator": "Element Critical",
        "resolution_status": "resolved_operator_campus",
        "identity_confidence": "high",
        "evidence": [
            "https://elementcritical.com/data-centers/chicago-one/",
            "https://elementcritical.com/private-colocation-suite-solutions-for-wood-dale-businesses/",
        ],
    },
    "edgeconnex_elk_grove_chi01_chi02": {
        "seed_ids": ["site_01897", "site_02007"],
        "related_ids": [],
        "canonical_name": "EdgeConneX Elk Grove CHI01-CHI02 campus",
        "operator": "EdgeConneX",
        "resolution_status": "resolved_operator_campus",
        "identity_confidence": "high",
        "evidence": [
            "https://www.edgeconnex.com/wp-content/uploads/2024/09/Chicago-Data-Sheet.pdf"
        ],
    },
    "ntt_itasca_chicago_campus": {
        "seed_ids": ["site_02375"],
        "related_ids": ["site_02435", "site_02554", "site_02555"],
        "canonical_name": "NTT Itasca Chicago campus",
        "operator": "NTT",
        "resolution_status": "resolved_operator_campus",
        "identity_confidence": "high",
        "evidence": [
            "https://services.global.ntt/en-us/services-and-products/global-data-centers/global-locations/americas/chicago-data-centers"
        ],
    },
    "meta_dekalb_campus": {
        "seed_ids": ["site_02615"],
        "related_ids": ["site_02465", "site_02466", "site_02467"],
        "canonical_name": "Meta DeKalb Data Center campus",
        "operator": "Meta Platforms",
        "resolution_status": "resolved_reference_campus",
        "identity_confidence": "high",
        "evidence": ["visual-taxonomy/data_center_site_report.pdf"],
    },
    "microsoft_elk_grove_campus": {
        "seed_ids": ["site_02399"],
        "related_ids": [],
        "canonical_name": "Microsoft Elk Grove CHI10-CHI12 campus",
        "operator": "Microsoft",
        "resolution_status": "resolved_documentary_campus_seed",
        "identity_confidence": "high",
        "evidence": [
            "https://www.elkgrove.org/home/showpublisheddocument/14156/638339203873670000",
            "https://epa.illinois.gov/content/dam/soi/en/web/epa/topics/environmental-justice/documents/notification-letters/Elk%20Grove%20Village%20%28CHI10-11-12%29%20Data%20Center%20031440AUK%20Construction%2024070017.pdf",
        ],
    },
    "site_02613": {
        "seed_ids": ["site_02613"],
        "related_ids": [],
        "canonical_name": "Microsoft Hoffman Estates data-center campus",
        "operator": "Microsoft",
        "resolution_status": "resolved_reference_campus",
        "identity_confidence": "high",
        "evidence": [
            "visual-taxonomy/data_center_site_report.pdf",
            "https://dceo.illinois.gov/content/dam/soi/en/web/dceo/aboutdceo/reportsrequiredbystatute/2024-data-centers-annual-report-submission.pdf",
        ],
    },
}


def _safe_join(values) -> str:
    return "|".join(str(value) for value in values if pd.notna(value) and str(value))


def _load_pnnl_geometry_lookup() -> dict[str, object]:
    lookup = {}
    for layer, path in (("building", PNNL_BUILDINGS), ("campus", PNNL_CAMPUSES)):
        source = gpd.read_file(path).to_crs(4326)
        for row in source.itertuples():
            lookup[f"PNNL:{layer}_{row.id}"] = row.geometry
    return lookup


def main() -> None:
    seeds = gpd.read_file(SEEDS).to_crs(4326)
    reference = gpd.read_file(HARMONIZED).to_crs(4326).set_index("site_group_id")
    pnnl_geometries = _load_pnnl_geometry_lookup()
    assigned = set()
    rows = []
    crosswalk = []

    for analysis_unit_id, rule in RESOLUTION_RULES.items():
        seed_rows = seeds[seeds["site_group_id"].isin(rule["seed_ids"])]
        missing = set(rule["seed_ids"]) - set(seed_rows["site_group_id"])
        if missing:
            raise ValueError(f"Resolution rule {analysis_unit_id} has missing seeds: {sorted(missing)}")
        assigned.update(rule["seed_ids"])

        reference_ids = list(dict.fromkeys(rule["seed_ids"] + rule["related_ids"]))
        missing_related = set(reference_ids) - set(reference.index)
        if missing_related:
            raise ValueError(f"Resolution rule {analysis_unit_id} has missing references: {sorted(missing_related)}")
        geometries = []
        for site_id in reference_ids:
            source_row = reference.loc[site_id]
            geometry = pnnl_geometries.get(source_row.primary_record_uid, source_row.geometry)
            geometries.append(geometry)
        geometry = gpd.GeoSeries(geometries, crs=4326).union_all()

        rows.append(
            {
                "analysis_unit_id": analysis_unit_id,
                "canonical_name": rule["canonical_name"],
                "operator": rule["operator"],
                "taxonomy_group_id": _safe_join(sorted(seed_rows["taxonomy_group_id"].unique())),
                "seed_record_ids": _safe_join(rule["seed_ids"]),
                "related_record_ids": _safe_join(rule["related_ids"]),
                "seed_record_count": len(rule["seed_ids"]),
                "reference_record_count": len(reference_ids),
                "resolution_status": rule["resolution_status"],
                "identity_confidence": rule["identity_confidence"],
                "poc_status": "complete" if analysis_unit_id == "aurora_cyrusone_chi1_chi2" else "not_started",
                "entity_evidence": _safe_join(rule["evidence"]),
                "geometry_role": "source_geometry_union_not_project_boundary",
                "geometry": geometry,
            }
        )
        for site_id in reference_ids:
            crosswalk.append(
                {
                    "analysis_unit_id": analysis_unit_id,
                    "source_site_group_id": site_id,
                    "relationship": "taxonomy_seed" if site_id in rule["seed_ids"] else "related_campus_record",
                    "included": True,
                    "resolution_status": rule["resolution_status"],
                }
            )

    for seed in seeds[~seeds["site_group_id"].isin(assigned)].itertuples():
        analysis_unit_id = seed.site_group_id
        rows.append(
            {
                "analysis_unit_id": analysis_unit_id,
                "canonical_name": seed.canonical_name or seed.site_group_id,
                "operator": seed.operator_summary or "",
                "taxonomy_group_id": seed.taxonomy_group_id,
                "seed_record_ids": seed.site_group_id,
                "related_record_ids": "",
                "seed_record_count": 1,
                "reference_record_count": 1,
                "resolution_status": "provisional_single_record",
                "identity_confidence": "medium",
                "poc_status": "not_started",
                "entity_evidence": "visual-taxonomy/data_center_site_report.pdf",
                "geometry_role": "source_geometry_not_project_boundary",
                "geometry": pnnl_geometries.get(seed.primary_record_uid, seed.geometry),
            }
        )
        crosswalk.append(
            {
                "analysis_unit_id": analysis_unit_id,
                "source_site_group_id": seed.site_group_id,
                "relationship": "taxonomy_seed",
                "included": True,
                "resolution_status": "provisional_single_record",
            }
        )

    units = gpd.GeoDataFrame(rows, geometry="geometry", crs=4326).sort_values("analysis_unit_id")
    crosswalk = sorted(crosswalk, key=lambda item: (item["analysis_unit_id"], item["source_site_group_id"]))

    OUT.mkdir(parents=True, exist_ok=True)
    units.to_file(OUT / "analysis_units_preliminary.geojson", driver="GeoJSON")
    (OUT / "source_crosswalk_preliminary.json").write_text(
        json.dumps(crosswalk, indent=2) + "\n", encoding="utf-8"
    )

    summary = {
        "seed_record_count": int(len(seeds)),
        "analysis_unit_count": int(len(units)),
        "completed_analysis_unit_count": int((units["poc_status"] == "complete").sum()),
        "pending_analysis_unit_count": int((units["poc_status"] != "complete").sum()),
        "resolved_or_documented_count": int((units["resolution_status"] != "provisional_single_record").sum()),
        "provisional_single_record_count": int((units["resolution_status"] == "provisional_single_record").sum()),
        "crosswalk_record_count": int(len(crosswalk)),
        "notes": [
            "Reference geometry is not a parcel, fence, disturbance, or final campus boundary.",
            "Related non-seed buildings are included only when operator or campus evidence supports the relationship.",
            "Microsoft Elk Grove requires current-footprint expansion beyond the single PNNL seed building.",
        ],
    }
    (OUT / "entity_resolution_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
