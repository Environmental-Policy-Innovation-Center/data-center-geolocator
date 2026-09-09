#!/usr/bin/env python3
"""Compile the documented statewide screening dataset and evidence catalog."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "data/illinois_land_use_change/inventory"
INTERIM = ROOT / "data/illinois_land_use_change/interim"
FINAL = ROOT / "data/illinois_land_use_change/final"
CRS_AREA = 26916
SQFT_PER_M2 = 10.7639104167


COMMON = {
    "taxonomy": "visual-taxonomy/data_center_site_report.pdf",
    "pnnl_readme": "raw-data/data-center-locations/PNNL/README.pdf",
    "dceo": "https://dceo.illinois.gov/content/dam/soi/en/web/dceo/aboutdceo/reportsrequiredbystatute/2024-data-centers-annual-report-submission.pdf",
}


PROFILES = {
    "aligned_northlake_ord01_ord02": {
        "prior_land_use": "previously_developed_site",
        "prior_confidence": "medium",
        "construction_start": "2021-04-28",
        "construction_start_precision": "day",
        "operational_or_completion": "2022-04-19",
        "timeline_summary": "ORD01 broke ground 28 Apr 2021; ORD01 launched and adjacent ORD02 broke ground 19 Apr 2022.",
        "sources": [
            "https://aligneddc.com/press-release/aligned-breaks-ground-on-chicago-hyperscale-data-center-campus/",
            "https://aligneddc.com/es/press-release/aligned-launches-chicago-hyperscale-data-center-campus-and-breaks-ground-on-second-adjacent-facility/",
            "https://aligneddc.com/chicago-data-centers/",
        ],
    },
    "aurora_cyrusone_chi1_chi2": {
        "prior_land_use": "agricultural",
        "prior_confidence": "high",
        "construction_start": "2016",
        "construction_start_precision": "year",
        "operational_or_completion": None,
        "timeline_summary": "Aurora proof-of-concept timeline and phase metrics retained as the reviewed regression fixture.",
        "sources": ["reports/aurora_land_use_change/aurora_data_center_land_use_change_report.pdf"],
    },
    "edgeconnex_elk_grove_chi01_chi02": {
        "prior_land_use": "previously_developed_industrial_area",
        "prior_confidence": "medium",
        "construction_start": None,
        "construction_start_precision": None,
        "operational_or_completion": None,
        "timeline_summary": "CHI01 and CHI02 are documented as one operating Chicago campus; exact conversion/construction dates remain unresolved.",
        "sources": ["https://www.edgeconnex.com/wp-content/uploads/2024/09/Chicago-Data-Sheet.pdf"],
    },
    "element_critical_wood_dale_ch1_ch2": {
        "prior_land_use": "previously_developed_data_center_industrial",
        "prior_confidence": "high",
        "construction_start": "2014",
        "construction_start_precision": "year_acquisition_modernization",
        "operational_or_completion": None,
        "timeline_summary": "Former ComDisco/SunGard facilities were purchased in 2014 and modernized; this is reuse, not greenfield construction.",
        "sources": [
            "https://elementcritical.com/data-centers/chicago-one/",
            "https://elementcritical.com/private-colocation-suite-solutions-for-wood-dale-businesses/",
        ],
    },
    "meta_dekalb_campus": {
        "prior_land_use": "agricultural_row_crop",
        "prior_confidence": "high",
        "construction_start": "2020",
        "construction_start_precision": "year",
        "operational_or_completion": "2023-11-29",
        "timeline_summary": "Meta broke ground in 2020; Building 2 received final occupancy in summer 2023; the campus began serving traffic in Nov 2023 while later buildings remained under construction.",
        "sources": [
            "https://datacenters.atmeta.com/2023/11/dekalb-we-are-online/",
            "https://www.cityofdekalb.com/DocumentCenter/View/16872/FY2024-Budget-DRAFT",
        ],
    },
    "microsoft_elk_grove_campus": {
        "prior_land_use": "former_agricultural_then_serviced_industrial_park",
        "prior_confidence": "high",
        "construction_start": "2020",
        "construction_start_precision": "year_site_development",
        "operational_or_completion": None,
        "timeline_summary": "Village reporting says Microsoft began site development in 2020 on a 38-acre former Busse Farm tract; a second of three buildings was reported in 2024.",
        "sources": [
            "https://fliphtml5.com/inylu/vgas/2020_Compendium/",
            "https://fliphtml5.com/inylu/sqtn/2024_Compendium/",
            "https://epa.illinois.gov/content/dam/soi/en/web/epa/topics/environmental-justice/documents/notification-letters/Elk%20Grove%20Village%20%28CHI10-11-12%29%20Data%20Center%20031440AUK%20Construction%2024070017.pdf",
        ],
    },
    "ntt_itasca_chicago_campus": {
        "prior_land_use": "previously_developed_site",
        "prior_confidence": "medium",
        "construction_start": "2019",
        "construction_start_precision": "imagery_interval_lower_bound",
        "operational_or_completion": "2021-02-25",
        "timeline_summary": "Dynamic World nominates 2019–2020 site change; NTT announced the first building open in Feb 2021 and documents a multi-building 19-acre campus.",
        "sources": [
            "https://services.global.ntt/en-us/newsroom/ntt-opens-two-new-data-centers-in-illinois-and-oregon",
            "https://services.global.ntt/en-us/services-and-products/global-data-centers/global-locations/americas/chicago-data-centers",
        ],
    },
    "site_00614": {
        "prior_land_use": "previously_developed_industrial_building",
        "prior_confidence": "high",
        "construction_start": "2017-12",
        "construction_start_precision": "month_acquisition_reconstruction",
        "operational_or_completion": "2020",
        "timeline_summary": "Stream acquired Chicago I in Dec 2017, reconstructed it, and reported full lease-up/expansion by the end of 2020; another expansion followed in 2024.",
        "sources": ["https://www.streamdatacenters.com/locations/chicago-data-centers/"],
    },
    "site_00616": {
        "prior_land_use": "previously_developed_industrial_building",
        "prior_confidence": "high",
        "construction_start": "2021-02",
        "construction_start_precision": "month",
        "operational_or_completion": "2022-Q3",
        "timeline_summary": "Stream acquired a 215,000-square-foot industrial property in 2020, planned construction for Feb 2021, and commissioned phase one in Q3 2022.",
        "sources": [
            "https://www.streamdatacenters.com/news/stream-expands-chicago-presence-with-second-data-center/",
            "https://www.streamdatacenters.com/locations/chicago-data-centers/",
        ],
    },
    "site_00617": {
        "prior_land_use": "previously_developed_warehouse",
        "prior_confidence": "high",
        "construction_start": "2022",
        "construction_start_precision": "year_phase_announcement",
        "operational_or_completion": None,
        "timeline_summary": "T5 documents conversion of an existing 164,000-square-foot warehouse and announced the final phase in Nov 2022; the automated 2017–2018 signal is neighbor-contaminated.",
        "sources": [
            "https://t5datacenters.com/resources/t5-chicagoii-final-phase/",
            "https://t5datacenters.com/resources/powering-hyperscale-growth-how-t5-data-centers-met-a-30mw-demand-without-missing-a-beat/",
        ],
    },
    "site_01560": {
        "prior_land_use": "brownfield_former_printing_plant",
        "prior_confidence": "high",
        "construction_start": "2014",
        "construction_start_precision": "year_acquisition_redevelopment",
        "operational_or_completion": None,
        "timeline_summary": "QTS acquired the vacant former Chicago Sun-Times printing plant in 2014 and converted the 990,000-square-foot structure into a data center.",
        "sources": ["https://qtsdatacenters.com/wp-content/uploads/2024/07/Sustainability-Report_FINAL_42319.pdf"],
    },
    "site_01842": {
        "prior_land_use": "previously_developed_site",
        "prior_confidence": "medium",
        "construction_start": None,
        "construction_start_precision": None,
        "operational_or_completion": None,
        "timeline_summary": "Current Equinix documentation confirms CH3 at 1905 Lunt; the site is developed in every NLCD/CDL checkpoint, but its original conversion date remains unresolved.",
        "sources": ["https://www.equinix.com/data-centers/americas-colocation/united-states-colocation/chicago-data-centers/ch3"],
    },
    "site_01881": {
        "prior_land_use": "previously_developed_industrial_warehouse",
        "prior_confidence": "high",
        "construction_start": "2008",
        "construction_start_precision": "year_phase_1_conversion",
        "operational_or_completion": "2013",
        "timeline_summary": "The 1972 industrial warehouse was converted to data-center use in 2008, with a second phase in 2013.",
        "sources": [
            "https://www.spglobal.com/ratings/en/regulatory/article/230622-presale-data-2023-cntr-mortgage-trust-s12758184",
            "https://www.digitalrealty.com/data-centers/americas/chicago/ch1",
        ],
    },
    "site_01928": {
        "prior_land_use": "not_applicable",
        "prior_confidence": "high",
        "construction_start": None,
        "construction_start_precision": None,
        "operational_or_completion": None,
        "timeline_summary": "Excluded after identity review: the mapped feature is a South Halsted records-storage warehouse, while Iron Mountain's Chicago data center is CHI-1 at 1680 Touhy Avenue in Des Plaines.",
        "scope_disposition": "excluded_false_positive_not_data_center",
        "sources": [
            "https://www.ironmountain.com/data-centers/locations/na/chicago-data-center",
            "https://mapcarta.com/W210222970",
        ],
    },
    "site_01940": {
        "prior_land_use": "previously_developed_data_center",
        "prior_confidence": "high",
        "construction_start": None,
        "construction_start_precision": None,
        "operational_or_completion": "2017-05",
        "timeline_summary": "The Westmont facility predates Equinix ownership and became CH7 through Equinix's May 2017 Verizon data-center acquisition.",
        "sources": ["https://investor.equinix.com/news-events/press-releases/detail/288/equinix-completes-acquisition-of-29-data-centers-from"],
    },
    "site_02009": {
        "prior_land_use": "previously_developed_site",
        "prior_confidence": "medium",
        "construction_start": None,
        "construction_start_precision": None,
        "operational_or_completion": None,
        "timeline_summary": "Current operator documentation confirms a purpose-built, two-story ORD2 facility; exact construction dates remain unresolved and historical imagery is required.",
        "sources": ["https://centersquaredc.com/hubfs/CenterSquare/docs/Centersquare-ORD-SpecSheet.pdf"],
    },
    "site_02019": {
        "prior_land_use": "previously_developed_warehouse_complex",
        "prior_confidence": "high",
        "construction_start": "2020",
        "construction_start_precision": "approximate_year",
        "operational_or_completion": "2021",
        "timeline_summary": "Skybox/Prologis developed Chicago I on a former warehouse-complex site; contemporary reporting described the 190,000-square-foot facility as open in 2021.",
        "sources": [
            "https://www.skyboxdatacenters.com/locations/skybox-chicago",
            "https://skyboxdatacenters.com/news/industrial-sites-start-flipping-to-data-centers-amid-fears-of-logistics-slowdown",
        ],
    },
    "site_02031": {
        "prior_land_use": "previously_developed_industrial_building",
        "prior_confidence": "high",
        "construction_start": "2012-08",
        "construction_start_precision": "month_redevelopment",
        "operational_or_completion": "2014",
        "timeline_summary": "Digital Realty acquired the three-building Grand Avenue campus in May 2012 and began redeveloping 9333 Grand (ORD12) in Aug 2012; ENERGY STAR records 2014 as year built.",
        "sources": [
            "https://investor.digitalrealty.com/static-files/18487391-d78b-41c5-a4d9-51d59d6483ba",
            "https://www.digitalrealty.com/data-centers/americas/chicago/ord12",
        ],
    },
    "site_02109": {
        "prior_land_use": "previously_developed_site",
        "prior_confidence": "medium",
        "construction_start": None,
        "construction_start_precision": None,
        "operational_or_completion": None,
        "timeline_summary": "ORD4 is confirmed at 4513 Western Avenue; the site is developed throughout available categorical history, while the original data-center conversion date remains unresolved.",
        "sources": ["https://centersquaredc.com/hubfs/CenterSquare/docs/Centersquare-ORD-SpecSheet.pdf"],
    },
    "site_02132": {
        "prior_land_use": "previously_developed_site",
        "prior_confidence": "medium",
        "construction_start": "2016",
        "construction_start_precision": "year_phase_2_document",
        "operational_or_completion": None,
        "timeline_summary": "A construction labor agreement records Microsoft Data Center Phase 2 at 601 Northwest Avenue in 2016; the Illinois incentive program records Microsoft Northlake in 2021.",
        "sources": [
            "https://chicagobuildingtrades.org/wp-content/uploads/2024/08/PLA-with-Detail-August-14-2024.pdf",
            COMMON["dceo"],
        ],
    },
    "site_02186": {
        "prior_land_use": "previously_developed_industrial_site",
        "prior_confidence": "medium",
        "construction_start": "2017",
        "construction_start_precision": "year",
        "operational_or_completion": "2018-Q1",
        "timeline_summary": "Work on CH3 began in 2017 and phase one was completed in Q1 2018; NLCD maps the site as developed before construction.",
        "sources": [
            "https://www.digitalrealty.com/data-centers/americas/chicago",
            "https://www.spglobal.com/ratings/en/regulatory/article/230622-presale-data-2023-cntr-mortgage-trust-s12758184",
        ],
    },
    "site_02187": {
        "prior_land_use": "previously_developed_site",
        "prior_confidence": "medium",
        "construction_start": None,
        "construction_start_precision": None,
        "operational_or_completion": "2015",
        "timeline_summary": "Digital Realty records CH2 at 2299 Busse as a distinct facility; market documentation places opening in 2015, but a primary construction record remains to be located.",
        "sources": [
            "https://www.digitalrealty.com/data-centers/americas/chicago",
            "https://investor.digitalrealty.com/static-files/3ebb6f07-8955-45c2-96fa-1c9d14bdb8b7",
        ],
    },
    "site_02253": {
        "prior_land_use": "previously_developed_site",
        "prior_confidence": "medium",
        "construction_start": None,
        "construction_start_precision": None,
        "operational_or_completion": "2020_or_earlier",
        "timeline_summary": "STACK documents CHI01A and CHI01B as a two-building, 14-acre campus; a Dec 2020 operator video confirms the campus by that date.",
        "sources": [
            "https://www.stackinfra.com/locations/americas/chicago/chi01/",
            "https://www.stackinfra.com/resources/video/stack-chicago/",
        ],
    },
    "site_02613": {
        "prior_land_use": "greenfield_mixed_pasture_woodland_wetland",
        "prior_confidence": "high",
        "construction_start": "2021-06",
        "construction_start_precision": "month",
        "operational_or_completion": None,
        "timeline_summary": "Village records state construction began in June 2021; the first building continued build-out and a second building was permitted in 2024. Direct 2019 NAIP review shows a mixed pasture/old-field, woodland, and wetland site—not uniform cropland—consistent with Dynamic World's 61.9% trees and 32.9% crops in 2019 but inconsistent with coarse NLCD/CDL labels.",
        "sources": [
            "https://www.hoffmanestates.org/Documents/Government/Departments/Finance/Financial%20Documents/2024-2028-Capital-Improvements-Program.pdf?t=202509191049100",
            "https://www.hoffmanestates.org/Documents/Government/Departments/Finance/Financial%20Documents/2025-Operating-and-Capital-Budget.pdf?t=202512111326230",
        ],
    },
}


def class_pct(table: pd.DataFrame, unit_id: str, dataset: str, year: int, class_name: str):
    row = table[(table.analysis_unit_id == unit_id) & (table.dataset == dataset) & (table.year == year) & (table.class_name == class_name)]
    return round(float(row.iloc[0].area_pct), 1) if len(row) else None


def main() -> None:
    units = gpd.read_file(INVENTORY / "analysis_units_preliminary.geojson").to_crs(CRS_AREA)
    breakpoints = pd.read_parquet(INTERIM / "breakpoint_screening.parquet").set_index("analysis_unit_id")
    landcover = pd.read_parquet(INTERIM / "independent_landcover_annual.parquet")
    overture = gpd.read_file(INTERIM / "overture_building_candidates.geojson").to_crs(CRS_AREA)
    dw_summary = pd.DataFrame(json.loads((INTERIM / "dynamic_world_built_core_2026_summary.json").read_text())).set_index("analysis_unit_id")
    imagery_manifest_path = ROOT / "data/illinois_land_use_change/review/imagery_manifest.json"
    imagery_manifest = json.loads(imagery_manifest_path.read_text()) if imagery_manifest_path.exists() else []
    aurora_sites = gpd.read_file(ROOT / "data/aurora_land_use_change/final/sites.geojson")
    aurora_row = aurora_sites[aurora_sites.site_id == "cyrusone_aurora_chi1_chi2"].iloc[0]
    records = []
    evidence = []

    for row in units.itertuples():
        unit_id = row.analysis_unit_id
        profile = PROFILES[unit_id]
        bp = breakpoints.loc[unit_id]
        candidates = overture[overture.analysis_unit_id == unit_id]
        geometry_is_campus = unit_id in {"meta_dekalb_campus", "site_02613"}
        reference_area = float(row.geometry.area)
        record = {
            "analysis_unit_id": unit_id,
            "canonical_name": row.canonical_name,
            "operator": row.operator,
            "taxonomy_group_id": row.taxonomy_group_id,
            "scope_disposition": profile.get("scope_disposition", "included"),
            "review_state": "qa_complete_reference" if unit_id == "aurora_cyrusone_chi1_chi2" else "automated_screened_document_checked",
            "identity_confidence": row.identity_confidence,
            "construction_start": profile["construction_start"],
            "construction_start_precision": profile["construction_start_precision"],
            "operational_or_completion": profile["operational_or_completion"],
            "timeline_summary": profile["timeline_summary"],
            "predevelopment_land_use": profile["prior_land_use"],
            "predevelopment_confidence": profile["prior_confidence"],
            "nlcd_2001_agriculture_pct": class_pct(landcover, unit_id, "nlcd", 2001, "agriculture"),
            "nlcd_2001_developed_pct": class_pct(landcover, unit_id, "nlcd", 2001, "developed"),
            "cdl_2008_crops_pct": class_pct(landcover, unit_id, "cdl", 2008, "crops"),
            "cdl_2008_pasture_hay_pct": class_pct(landcover, unit_id, "cdl", 2008, "pasture_hay"),
            "dynamic_world_screening_result": bp.dynamic_world_screening_result,
            "dynamic_world_candidate_start_lower_year": bp.candidate_start_lower_year,
            "dynamic_world_candidate_start_upper_year": bp.candidate_start_upper_year,
            "neighbor_contamination_flag": bool(bp.neighbor_contamination_flag),
            "source_geometry_class": "mapped_campus_boundary" if geometry_is_campus else "mapped_roof_or_roof_union",
            "source_geometry_area_m2": round(reference_area, 1),
            "source_geometry_area_acres": round(reference_area / 4046.8564224, 2),
            "mapped_roof_area_m2": None if geometry_is_campus else round(reference_area, 1),
            "mapped_roof_area_sqft": None if geometry_is_campus else round(reference_area * SQFT_PER_M2),
            "overture_candidate_count": int(len(candidates)),
            "overture_candidate_area_m2": round(float(candidates.geometry.area.sum()), 1),
            "dynamic_world_2026_built_surface_area_m2": float(dw_summary.loc[unit_id].built_surface_area_m2),
            "dynamic_world_2026_built_surface_area_acres": float(dw_summary.loc[unit_id].built_surface_area_acres),
            "approved_plan_roof_area_m2": None,
            "disturbed_area_m2": None,
            "disturbed_area_acres": None,
            "disturbance_status": "pending_site_scale_delineation",
            "geometry": row.geometry,
        }
        if unit_id == "aurora_cyrusone_chi1_chi2":
            record.update(
                {
                    "mapped_roof_area_m2": float(aurora_row.mapped_roof_footprint_m2),
                    "mapped_roof_area_sqft": round(float(aurora_row.mapped_roof_footprint_m2) * SQFT_PER_M2),
                    "disturbed_area_m2": float(aurora_row.disturbed_area_estimate_m2),
                    "disturbed_area_acres": float(aurora_row.disturbed_area_estimate_acres),
                    "disturbance_status": "reviewed_aurora_poc_estimate",
                }
            )
        records.append(record)
        for index, source in enumerate(profile["sources"], 1):
            evidence.append(
                {
                    "evidence_id": f"{unit_id}_doc_{index:02d}",
                    "analysis_unit_id": unit_id,
                    "source": source,
                    "evidence_type": "documentary",
                    "supports": "identity|timeline|prior_land_use",
                    "note": profile["timeline_summary"],
                }
            )
        evidence.extend(
            [
                {
                    "evidence_id": f"{unit_id}_pnnl_osm",
                    "analysis_unit_id": unit_id,
                    "source": "PNNL IM3 Open Source Data Center Atlas 2026-02-09 (derived from OpenStreetMap)",
                    "evidence_type": "mapped_geometry",
                    "supports": "identity|mapped_roof_or_campus_geometry",
                    "note": "Source geometry can be incomplete or stale; geometry role is recorded in the analysis-unit table.",
                },
                {
                    "evidence_id": f"{unit_id}_overture",
                    "analysis_unit_id": unit_id,
                    "source": "Overture Maps Buildings release 2026-08-19.0",
                    "evidence_type": "mapped_geometry_candidates",
                    "supports": "current_roof_review",
                    "note": "Candidate search results only; candidate area is not an accepted footprint total.",
                },
                {
                    "evidence_id": f"{unit_id}_nlcd",
                    "analysis_unit_id": unit_id,
                    "source": "USGS/NLCD_RELEASES/2019_REL/NLCD and 2021_REL/NLCD via Earth Engine",
                    "evidence_type": "categorical_land_cover",
                    "supports": "prior_land_use_corroboration",
                    "note": "Broad-class proportions are stored in the statewide record and annual Parquet table.",
                },
                {
                    "evidence_id": f"{unit_id}_cdl",
                    "analysis_unit_id": unit_id,
                    "source": "USDA/NASS/CDL via Earth Engine",
                    "evidence_type": "categorical_land_cover",
                    "supports": "crop_or_pasture_corroboration",
                    "note": "CDL is independent of Dynamic World but remains a 30 m categorical screening product.",
                },
            ]
        )

    for item in imagery_manifest:
        evidence.append(
            {
                "evidence_id": f"{item['analysis_unit_id']}_img_{item['role']}",
                "analysis_unit_id": item["analysis_unit_id"],
                "source": item["dataset"],
                "evidence_type": "dated_open_imagery",
                "supports": "visual_land_use_and_development_review",
                "note": f"{item['role']}; dates {', '.join(item.get('acquisition_dates', []))}; local file {item['path']}",
            }
        )

    FINAL.mkdir(parents=True, exist_ok=True)
    result = gpd.GeoDataFrame(records, geometry="geometry", crs=CRS_AREA).to_crs(4326)
    result.to_file(FINAL / "analysis_units_screening.geojson", driver="GeoJSON")
    result.to_parquet(FINAL / "analysis_units_screening.parquet", index=False)
    (FINAL / "documentary_evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    summary = {
        "analysis_unit_count": int(len(result)),
        "included_count": int((result.scope_disposition == "included").sum()),
        "excluded_false_positive_count": int((result.scope_disposition != "included").sum()),
        "qa_complete_count": int((result.review_state == "qa_complete_reference").sum()),
        "screened_not_qa_complete_count": int((result.review_state != "qa_complete_reference").sum()),
        "prior_land_use_counts": result.predevelopment_land_use.value_counts().to_dict(),
        "known_disturbance_count": int(result.disturbed_area_m2.notna().sum()),
        "warnings": [
            "Only Aurora is QA-complete; statewide values are a documented screening deliverable.",
            "Mapped roof areas are OSM-derived PNNL source geometries and can be incomplete or stale.",
            "Overture areas are candidate totals, not accepted roof totals.",
            "Dynamic World built areas are 10 m built-surface envelopes, not roof footprints.",
        ],
    }
    (FINAL / "screening_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
