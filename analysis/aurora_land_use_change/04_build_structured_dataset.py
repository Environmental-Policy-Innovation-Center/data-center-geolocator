#!/usr/bin/env python3
"""Build the final Aurora data-center land-use change dataset.

The output intentionally separates measured roof footprint, gross floor area,
parcel/campus area, and remotely sensed disturbed area.  All area calculations
are performed in NAD83 / UTM zone 16N (EPSG:26916).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import affinity
from shapely.geometry import box


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/aurora_land_use_change/raw"
INTERIM = ROOT / "data/aurora_land_use_change/interim"
FINAL = ROOT / "data/aurora_land_use_change/final"
CRS_AREA = "EPSG:26916"
CRS_WEB = "EPSG:4326"
M2_PER_ACRE = 4046.8564224
M2_PER_SQFT = 0.09290304

OVERTURE_IDS = {
    "edged_ord01_1": "2bb5f41d-b1d2-4ca2-855e-4d93af62a66f",
    "cyrus_chi1": "539ab7e6-603a-406a-b98e-05c2b52a59a0",
    "cyrus_chi2": "8f138e06-fc92-442f-a4a5-7d6968d82dc3",
    "cyrus_chi3": "e1769c58-a74b-4991-bc03-5ce1ffd3c73e",
}


def rotated_rectangle(cx: float, cy: float, width: float, height: float, angle: float):
    geom = box(cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)
    return affinity.rotate(geom, angle, origin=(cx, cy), use_radians=False)


def write_table(df: pd.DataFrame, name: str):
    df.to_csv(FINAL / f"{name}.csv", index=False)
    df.to_parquet(FINAL / f"{name}.parquet", index=False)


def main():
    FINAL.mkdir(parents=True, exist_ok=True)

    edged_parcels = gpd.read_file(RAW / "edged_parcels.geojson").to_crs(CRS_AREA)
    cyrus_parcels = gpd.read_file(RAW / "cyrus_parcels.geojson").to_crs(CRS_AREA)
    overture = gpd.read_parquet(RAW / "overture/buildings.parquet").to_crs(CRS_AREA)
    selected = overture[overture["id"].isin(OVERTURE_IDS.values())].set_index("id")

    site_geoms = {
        "edged_chicago": edged_parcels.geometry.union_all(),
        "cyrusone_aurora_chi1_chi2": cyrus_parcels.loc[
            cyrus_parcels["ADDRESS"].eq("2905 DIEHL RD"), "geometry"
        ].iloc[0],
        "cyrusone_aurora_iii": cyrus_parcels.loc[
            cyrus_parcels["ADDRESS"].eq("2725 BILTER RD"), "geometry"
        ].iloc[0],
    }

    # Approved Edged plan dimensions: 417.2 x 612.1 ft.  The plan's 415,934
    # square feet is gross floor area, not roof footprint. Center and bearing
    # provide an approximate analytical placement informed by the approved plan
    # and 2026-08-22 Sentinel-2 imagery; this is not an as-built boundary.
    ord2_width = 417.2 * 0.3048
    ord2_height = 612.1 * 0.3048
    ord2_geom = rotated_rectangle(396708.0, 4628790.0, ord2_width, ord2_height, 42.6093)

    building_specs = [
        ("edged_ord01_1", "edged_chicago", "Edged ORD01-1", OVERTURE_IDS["edged_ord01_1"], selected.loc[OVERTURE_IDS["edged_ord01_1"], "geometry"], "operating", "Overture building polygon sourced from OpenStreetMap", "current_mapped_footprint", "high", 207967.0, "2026-02-21"),
        ("edged_ord01_2", "edged_chicago", "Edged ORD01-2", None, ord2_geom, "under_construction", "Approved plan dimensions; approximate georeferencing against Sentinel-2", "approved_plan_footprint_approximate_position", "low-medium", 415934.0, "2023-01-12"),
        ("cyrus_chi1", "cyrusone_aurora_chi1_chi2", "CyrusOne CHI1 / Aurora CME", OVERTURE_IDS["cyrus_chi1"], selected.loc[OVERTURE_IDS["cyrus_chi1"], "geometry"], "operating", "Overture building polygon sourced from OpenStreetMap", "current_mapped_footprint", "high", 428000.0, "2025-10-13"),
        ("cyrus_chi2", "cyrusone_aurora_chi1_chi2", "CyrusOne CHI2", OVERTURE_IDS["cyrus_chi2"], selected.loc[OVERTURE_IDS["cyrus_chi2"], "geometry"], "operating", "Overture building polygon sourced from OpenStreetMap", "current_mapped_footprint", "high", 316000.0, "2025-12-01"),
        ("cyrus_chi3", "cyrusone_aurora_iii", "CyrusOne CHI3 building 1", OVERTURE_IDS["cyrus_chi3"], selected.loc[OVERTURE_IDS["cyrus_chi3"], "geometry"], "substantially_complete", "Overture building polygon sourced from OpenStreetMap", "current_mapped_footprint", "high", 223000.0, "2026-02-21"),
    ]
    buildings = gpd.GeoDataFrame(
        [
            {
                "building_id": bid,
                "site_id": sid,
                "building_name": name,
                "overture_id": oid,
                "status_as_of": status,
                "status_date": "2026-09-08",
                "geometry_source": source,
                "geometry_class": geometry_class,
                "geometry_confidence": conf,
                "source_geometry_update": source_update,
                "source_release": "Overture 2026-08-19.0" if oid else "Aurora approved plan dated 2023-01-12",
                "roof_footprint_m2": geom.area,
                "roof_footprint_sqft": geom.area / M2_PER_SQFT,
                "reported_gross_floor_area_sqft": gfa,
                "geometry": geom,
            }
            for bid, sid, name, oid, geom, status, source, geometry_class, conf, gfa, source_update in building_specs
        ],
        crs=CRS_AREA,
    )

    dw = pd.read_csv(INTERIM / "dynamic_world_annual.csv")
    dw_bb = (
        dw[dw["class_name"].isin(["built", "bare"])]
        .groupby(["site_id", "year"], as_index=False)["argmax_area_m2"]
        .sum()
    )
    primary_year = {
        "edged_chicago": 2026,
        "cyrusone_aurora_chi1_chi2": 2023,
        "cyrusone_aurora_iii": 2025,
    }
    disturbed = {
        sid: float(dw_bb[(dw_bb.site_id == sid) & (dw_bb.year == year)].argmax_area_m2.iloc[0])
        for sid, year in primary_year.items()
    }
    lower_ac = {
        "edged_chicago": disturbed["edged_chicago"] / M2_PER_ACRE,
        "cyrusone_aurora_chi1_chi2": 32.0,
        "cyrusone_aurora_iii": disturbed["cyrusone_aurora_iii"] / M2_PER_ACRE,
    }
    upper_ac = {
        sid: geom.area / M2_PER_ACRE for sid, geom in site_geoms.items()
    }

    mapped_footprint_by_site = (
        buildings[buildings.geometry_class.eq("current_mapped_footprint")]
        .groupby("site_id")["roof_footprint_m2"]
        .sum()
        .to_dict()
    )
    plan_footprint_by_site = (
        buildings[buildings.geometry_class.str.startswith("approved_plan")]
        .groupby("site_id")["roof_footprint_m2"]
        .sum()
        .to_dict()
    )
    footprint_by_site = buildings.groupby("site_id")["roof_footprint_m2"].sum().to_dict()
    site_rows = [
        {
            "site_id": "edged_chicago",
            "campus_name": "Edged Chicago Campus",
            "operator": "Edged Energy",
            "address": "2815–2845 Bilter Road, Aurora, IL 60502",
            "status_as_of": "Operating plus active construction",
            "first_construction_start": "2023-05-22",
            "first_operational_date": "2025-02-27",
            "predevelopment_land_use": "agricultural",
            "predevelopment_summary": "Row-crop agriculture; Dynamic World classified 95.4% crops in 2022.",
            "land_use_confidence": "high",
            "campus_area_m2": site_geoms["edged_chicago"].area,
            "campus_area_acres": site_geoms["edged_chicago"].area / M2_PER_ACRE,
            "current_roof_footprint_m2": footprint_by_site["edged_chicago"],
            "current_roof_footprint_acres": footprint_by_site["edged_chicago"] / M2_PER_ACRE,
            "mapped_roof_footprint_m2": mapped_footprint_by_site["edged_chicago"],
            "approved_plan_active_roof_m2": plan_footprint_by_site["edged_chicago"],
            "current_roof_metric_status": "provisional total: mapped ORD01-1 plus plan-dimension ORD01-2",
            "disturbed_area_estimate_m2": disturbed["edged_chicago"],
            "disturbed_area_estimate_acres": disturbed["edged_chicago"] / M2_PER_ACRE,
            "disturbed_area_lower_acres": lower_ac["edged_chicago"],
            "disturbed_area_upper_acres": upper_ac["edged_chicago"],
            "disturbance_method": "2026 Dynamic World built+bare lower bound; parcel union upper bound",
            "disturbance_confidence": "medium",
            "geometry": site_geoms["edged_chicago"],
        },
        {
            "site_id": "cyrusone_aurora_chi1_chi2",
            "campus_name": "CyrusOne Aurora CHI1–CHI2 Campus",
            "operator": "CyrusOne",
            "address": "2705–2905 Diehl Road, Aurora, IL 60502",
            "status_as_of": "Operating",
            "first_construction_start": "2006/2007",
            "first_operational_date": "2009 (reported year built)",
            "predevelopment_land_use": "mixed agricultural / previously developed / forested",
            "predevelopment_summary": "CHI1 footprint was mostly pasture/cropland in 2006 with some developed land; CHI2 was a wooded/open/developed mix before its 2016 start.",
            "land_use_confidence": "medium",
            "campus_area_m2": site_geoms["cyrusone_aurora_chi1_chi2"].area,
            "campus_area_acres": site_geoms["cyrusone_aurora_chi1_chi2"].area / M2_PER_ACRE,
            "current_roof_footprint_m2": footprint_by_site["cyrusone_aurora_chi1_chi2"],
            "current_roof_footprint_acres": footprint_by_site["cyrusone_aurora_chi1_chi2"] / M2_PER_ACRE,
            "mapped_roof_footprint_m2": mapped_footprint_by_site["cyrusone_aurora_chi1_chi2"],
            "approved_plan_active_roof_m2": 0.0,
            "current_roof_metric_status": "mapped Overture/OSM total",
            "disturbed_area_estimate_m2": disturbed["cyrusone_aurora_chi1_chi2"],
            "disturbed_area_estimate_acres": disturbed["cyrusone_aurora_chi1_chi2"] / M2_PER_ACRE,
            "disturbed_area_lower_acres": lower_ac["cyrusone_aurora_chi1_chi2"],
            "disturbed_area_upper_acres": upper_ac["cyrusone_aurora_chi1_chi2"],
            "disturbance_method": "2023 Dynamic World built proxy; documentary 32-acre core lower bound and parcel upper bound",
            "disturbance_confidence": "low-medium",
            "geometry": site_geoms["cyrusone_aurora_chi1_chi2"],
        },
        {
            "site_id": "cyrusone_aurora_iii",
            "campus_name": "CyrusOne Aurora III / CHI3 Campus",
            "operator": "CyrusOne",
            "address": "2725 Bilter Road, Aurora, IL 60502",
            "status_as_of": "First building substantially complete; second building planned",
            "first_construction_start": "2024-09-13",
            "first_operational_date": None,
            "predevelopment_land_use": "agricultural",
            "predevelopment_summary": "Row-crop agriculture; Dynamic World classified 98.7% crops in 2023.",
            "land_use_confidence": "high",
            "campus_area_m2": site_geoms["cyrusone_aurora_iii"].area,
            "campus_area_acres": site_geoms["cyrusone_aurora_iii"].area / M2_PER_ACRE,
            "current_roof_footprint_m2": footprint_by_site["cyrusone_aurora_iii"],
            "current_roof_footprint_acres": footprint_by_site["cyrusone_aurora_iii"] / M2_PER_ACRE,
            "mapped_roof_footprint_m2": mapped_footprint_by_site["cyrusone_aurora_iii"],
            "approved_plan_active_roof_m2": 0.0,
            "current_roof_metric_status": "mapped Overture/OSM total; later site work may be omitted",
            "disturbed_area_estimate_m2": disturbed["cyrusone_aurora_iii"],
            "disturbed_area_estimate_acres": disturbed["cyrusone_aurora_iii"] / M2_PER_ACRE,
            "disturbed_area_lower_acres": lower_ac["cyrusone_aurora_iii"],
            "disturbed_area_upper_acres": upper_ac["cyrusone_aurora_iii"],
            "disturbance_method": "2025 Dynamic World built+bare lower bound; parcel boundary upper bound",
            "disturbance_confidence": "medium",
            "geometry": site_geoms["cyrusone_aurora_iii"],
        },
    ]
    sites = gpd.GeoDataFrame(site_rows, crs=CRS_AREA)

    phases = pd.DataFrame(
        [
            ("cyrus_chi1", "cyrusone_aurora_chi1_chi2", "CHI1 / CME", "2006-09-25", "2006-01-01", "2007-12-31", "2009-12-31", "2009", "operating", "Landsat/CDL transition brackets initial site work; third-party year-built record", "medium"),
            ("cyrus_chi2", "cyrusone_aurora_chi1_chi2", "CHI2", "2015-09-16", "2016-12-01", "2016-12-31", "2017-07-02", "2018", "operating", "NAIP 2015 pre-site; reported December 2016 construction start; roof visible in NAIP 2017", "high"),
            ("edged_ord01_1", "edged_chicago", "ORD01-1", "2022-06-14", "2023-05-22", "2023-05-22", "2023-08-18", "2025-02-27", "operating", "Official groundbreaking and opening; NAIP confirms 2023 construction", "high"),
            ("cyrus_chi3", "cyrusone_aurora_iii", "CHI3 building 1", "2023-08-18", "2024-09-13", "2024-09-13", "2024-10-06", "2026-06-25", "substantially_complete", "Official groundbreaking; Sentinel-2 construction sequence; completion source uses campus building naming", "medium-high"),
            ("edged_ord01_2", "edged_chicago", "ORD01-2", "2025-10-26", "2025-11-13", "2025-11-13", "2026-05-04", "2027-Q2 planned", "under_construction", "Official groundbreaking and top-out; Sentinel-2 roof visible in 2026", "high"),
            ("edged_ord01_3", "edged_chicago", "Future building 3", None, None, None, None, None, "planned", "Shown on approved preliminary plan; no construction visible as of 2026-08-22", "high"),
            ("cyrus_chi3_b2", "cyrusone_aurora_iii", "CHI3 building 2", None, None, None, None, None, "planned", "Two-building 446,000-square-foot campus announced; only one current roof mapped", "medium"),
        ],
        columns=["phase_id", "site_id", "phase_name", "last_preconstruction_observation", "construction_start_lower", "construction_start_upper", "first_structure_observation", "completion_or_operation", "current_status", "basis", "confidence"],
    )

    phase_land_use = pd.DataFrame(
        [
            ("cyrus_chi1", 2006, "agricultural/pasture", 74.3, "USDA CDL 30 m normalized weighted histogram", "medium"),
            ("cyrus_chi1", 2006, "previously developed", 18.1, "USDA CDL 30 m normalized weighted histogram", "medium"),
            ("cyrus_chi1", 2006, "forested", 3.2, "USDA CDL 30 m normalized weighted histogram", "low-medium"),
            ("cyrus_chi1", 2006, "other", 4.4, "USDA CDL 30 m normalized weighted histogram", "low"),
            ("cyrus_chi2", 2015, "forested", 42.0, "USDA CDL footprint-buffer approximation, checked against NAIP", "medium"),
            ("cyrus_chi2", 2015, "previously developed/open", 34.0, "USDA CDL footprint-buffer approximation, checked against NAIP", "medium"),
            ("cyrus_chi2", 2015, "agricultural", 24.0, "USDA CDL footprint-buffer approximation, checked against NAIP", "medium"),
            ("edged_ord01_1", 2022, "agricultural", 95.4, "Dynamic World parcel-wide argmax area", "high"),
            ("edged_ord01_2", 2022, "agricultural", 95.4, "Dynamic World parcel-wide argmax area", "high"),
            ("cyrus_chi3", 2023, "agricultural", 98.7, "Dynamic World parcel-wide argmax area", "high"),
        ],
        columns=["phase_id", "baseline_year", "land_use_class", "approximate_percent", "method", "confidence"],
    )

    evidence = pd.DataFrame(
        [
            ("repo_harmonized", "Local harmonized reference sites", "processed-data/harmonized-data-center-reference-sites-illinois.geojson", "Candidate IDs site_00603, site_01911 and site_02530", "local"),
            ("repo_regulatory", "Local Illinois regulatory inventory", "processed-data/illinois-data-center-regulatory-facilities.geojson", "Edged and CyrusOne facility/generator records", "local"),
            ("aurora_parcels", "City of Aurora Parcels MapServer", "https://gis.aurora.il.us/arcgis/rest/services/Parcels/Parcels/MapServer/0", "Ownership, parcel boundaries and acreage", "primary"),
            ("aurora_edged_plan", "Aurora File 23-0044", "https://aurora-il.legistar.com/LegislationDetail.aspx?GUID=6D64A5E2-09B6-4786-B142-69F7F0AC4938&ID=6013833", "Approved three-building plan and dimensions", "primary"),
            ("aurora_chi2_plan", "Aurora File 17-01180", "https://aurora-il.legistar.com/LegislationDetail.aspx?GUID=8558F28D-3318-4388-A645-32A726B9409D&ID=6657046", "CHI2 plan and 316,000 square feet", "primary"),
            ("edged_groundbreak", "Edged groundbreaking release", "https://edged.us/news/edged-breaks-ground-on-new-ultra-efficient-waterless-data-center-campus-in-aurora", "May 22, 2023 groundbreaking; 65 acres; three phases", "primary"),
            ("edged_open", "Edged opening release", "https://edged.us/news/edged-opens-new-data-center-to-power-chicagos-ai-boom", "February 27, 2025 opening", "primary"),
            ("edged_ord2_start", "Edged expansion release", "https://edged.us/news/edged-us-expands-chicagoland-campus", "November 13, 2025 ORD01-2 groundbreaking; Q2 2027 target", "primary"),
            ("edged_ord2_topout", "Edged top-out release", "https://edged.us/news/edged-us-tops-out-second-sustainable-data-center-on-edged-chicago-campus", "June 4, 2026 top-out", "primary"),
            ("cyrus_chi3_start", "CyrusOne Aurora campus groundbreaking release", "https://www.cyrusone.com/media-coverage-press-releases/cyrusone-breaks-ground-on-new-data-center-in-aurora", "September 2024 groundbreaking; two buildings, 446,000 square feet", "primary"),
            ("cyrus_chi3_update", "CyrusOne Aurora campus construction update", "https://www.cyrusone.com/data-centers/north-america/aurora-il-back-up-generator-schedule", "June 2026 substantial-completion statement; public naming is potentially ambiguous", "primary"),
            ("cme_sale", "CME Group sale announcement", "https://investor.cmegroup.com/news-releases/news-release-details/cme-group-announces-agreement-sell-aurora-ill-data-center", "2016 sale; existing 428,000-square-foot data center", "primary"),
            ("overture", "Overture Maps Buildings", "https://docs.overturemaps.org/guides/buildings/", "Current roof polygons; release 2026-08-19.0", "open_data"),
            ("dynamic_world", "Google Dynamic World V1", "https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1", "2016–2026 annual land-cover probabilities and class areas", "open_data"),
            ("naip", "USDA NAIP", "https://planetarycomputer.microsoft.com/dataset/naip", "1 m dated aerial imagery, 2011–2023", "open_data"),
            ("sentinel2", "Copernicus Sentinel-2 L2A", "https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a", "10 m dated optical imagery, 2016–2026", "open_data"),
            ("landsat", "USGS Landsat Collection 2 Level-2", "https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2", "30 m imagery, 2005–2015", "open_data"),
            ("cdl", "USDA Cropland Data Layer", "https://developers.google.com/earth-engine/datasets/catalog/USDA_NASS_CDL", "30 m land-cover evidence for pre-Dynamic World years", "open_data"),
        ],
        columns=["evidence_id", "source_name", "uri_or_path", "use", "source_tier"],
    )

    crosswalk = pd.DataFrame(
        [
            ("site_00603", "FracTracker:frac_row_259", "edged_chicago", "edged_ord01_1; edged_ord01_2; edged_ord01_3", "Expanded point record to parcel-defined three-phase campus"),
            ("site_01911", "PNNL:building_00199252950", "cyrusone_aurora_chi1_chi2", "cyrus_chi1", "CME building retained as CHI1"),
            ("site_02530", "PNNL:building_01426146790", "cyrusone_aurora_chi1_chi2", "cyrus_chi2", "Previously unnamed PNNL building identified as CHI2"),
            (None, None, "cyrusone_aurora_iii", "cyrus_chi3; cyrus_chi3_b2", "Additional campus found from parcel ownership, Overture and imagery"),
        ],
        columns=["repo_site_group_id", "repo_record_uid", "final_site_id", "phase_ids", "reconciliation_note"],
    )

    # Spatial exports.
    sites_web = sites.to_crs(CRS_WEB)
    buildings_web = buildings.to_crs(CRS_WEB)
    # A parcel-union vertex collapses at GeoJSON coordinate precision after
    # reprojection; zero-width cleaning removes the degenerate ring component.
    sites_web.geometry = sites_web.geometry.buffer(0)
    sites_web.to_file(FINAL / "sites.geojson", driver="GeoJSON")
    buildings_web.to_file(FINAL / "buildings.geojson", driver="GeoJSON")
    sites_web.to_parquet(FINAL / "sites.parquet", index=False)
    buildings_web.to_parquet(FINAL / "buildings.parquet", index=False)
    mapped_web = buildings_web[buildings_web.geometry_class.eq("current_mapped_footprint")].copy()
    plan_web = buildings_web[buildings_web.geometry_class.str.startswith("approved_plan")].copy()
    mapped_web.to_file(FINAL / "mapped_building_footprints.geojson", driver="GeoJSON")
    mapped_web.to_parquet(FINAL / "mapped_building_footprints.parquet", index=False)
    plan_web.to_file(FINAL / "approved_plan_footprints.geojson", driver="GeoJSON")
    plan_web.to_parquet(FINAL / "approved_plan_footprints.parquet", index=False)
    gpkg = FINAL / "aurora_data_center_land_use_change.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    sites_web.to_file(gpkg, layer="sites", driver="GPKG")
    buildings_web.to_file(gpkg, layer="buildings", driver="GPKG")
    mapped_web.to_file(gpkg, layer="mapped_building_footprints", driver="GPKG")
    plan_web.to_file(gpkg, layer="approved_plan_footprints", driver="GPKG")

    write_table(pd.DataFrame(sites.drop(columns="geometry")), "sites")
    write_table(pd.DataFrame(buildings.drop(columns="geometry")), "buildings")
    write_table(phases, "development_phases")
    write_table(phase_land_use, "predevelopment_land_use")
    write_table(dw, "dynamic_world_annual")
    write_table(evidence, "evidence_catalog")
    write_table(crosswalk, "source_crosswalk")

    readme = f"""# Aurora data-center land-use change dataset

Generated 2026-09-08. Area CRS: EPSG:26916. Spatial interchange CRS: EPSG:4326.

The canonical package is `aurora_data_center_land_use_change.gpkg` with `sites`
and `buildings` layers. Equivalent GeoJSON and Parquet files are supplied, plus
CSV/Parquet tables for development phases, predevelopment land use, annual
Dynamic World results, evidence, and source crosswalks.

Important distinctions:

- `mapped_building_footprints` contains only Overture/OSM roof polygons and
  records the underlying OSM edit date; an Overture release date is not an
  imagery acquisition date.
- `approved_plan_footprints` keeps the active Edged ORD01-2 plan geometry
  separate. Its dimensions are plan-derived, but its georeferenced position is
  approximate.
- `dynamic_world_built_core_2026` and `dynamic_world_built_inclusive_2026`, when
  present, are 10 m satellite-interpreted built-surface envelopes. They are not
  roof boundaries and may include pavement and equipment pads.
- `roof_footprint_*` is plan-view roof area, not gross floor area. The Edged
  combined value is explicitly provisional because it mixes mapped and plan data.
- `campus_area_*` is the parcel-defined site envelope.
- `disturbed_area_estimate_*` is a remotely sensed proxy. Its stated bounds are
  more appropriate than false precision from a single 10 m classification.
- Edged ORD01-2 geometry is an analysis approximation derived from approved plan
  dimensions. Its position is approximate and it is not a survey boundary.
- Results reflect evidence available through 2026-09-08; imagery observations
  extend through 2026-08-22.
"""
    (FINAL / "README.md").write_text(readme)

    checks = {
        "site_count": len(sites),
        "current_building_count": len(buildings),
        "phase_count_including_planned": len(phases),
        "all_buildings_within_site_or_boundary_tolerance": all(
            site_geoms[row.site_id].buffer(5).contains(row.geometry)
            for row in buildings.itertuples()
        ),
        "site_areas_acres": dict(zip(sites.site_id, sites.campus_area_acres.round(3))),
        "roof_footprint_m2": dict(zip(sites.site_id, sites.current_roof_footprint_m2.round(1))),
        "disturbed_area_acres": dict(zip(sites.site_id, sites.disturbed_area_estimate_acres.round(2))),
    }
    (FINAL / "qa_summary.json").write_text(json.dumps(checks, indent=2) + "\n")
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
