#!/usr/bin/env python3
"""Validate statewide screening outputs and write a machine-readable QA summary."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import geopandas as gpd
import pandas as pd
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/illinois_land_use_change"
FIGURES = ROOT / "figures/illinois_land_use_change"
REPORT = ROOT / "reports/illinois_land_use_change/illinois_data_center_land_use_change_screening_report.pdf"
PACKAGE = ROOT / "reports/illinois_land_use_change/illinois_data_center_land_use_change_screening_dataset.zip"


def check(name: str, condition: bool, detail: str) -> dict:
    return {"check": name, "passed": bool(condition), "detail": detail}


def main() -> None:
    seeds = gpd.read_file(DATA / "inventory/taxonomy_seed_sites.geojson")
    units = gpd.read_file(DATA / "inventory/analysis_units_preliminary.geojson")
    crosswalk = json.loads((DATA / "inventory/source_crosswalk_preliminary.json").read_text())
    final = gpd.read_file(DATA / "final/analysis_units_screening.geojson")
    dw = gpd.read_file(DATA / "interim/dynamic_world_built_core_2026.geojson")
    annual_dw = pd.read_parquet(DATA / "interim/dynamic_world_screening_annual.parquet")
    annual_lc = pd.read_parquet(DATA / "interim/independent_landcover_annual.parquet")
    manifest = json.loads((DATA / "review/imagery_manifest.json").read_text())
    evidence = json.loads((DATA / "final/documentary_evidence.json").read_text())
    mapped_seed_ids = {item["source_site_group_id"] for item in crosswalk if item["relationship"] == "taxonomy_seed"}
    checks = [
        check("seed_count", len(seeds) == 27, f"{len(seeds)} taxonomy seeds"),
        check("all_seeds_crosswalked", mapped_seed_ids == set(seeds.site_group_id), f"{len(mapped_seed_ids)} unique seed IDs"),
        check("analysis_unit_count", len(units) == 24 and units.analysis_unit_id.is_unique, f"{len(units)} unique units"),
        check("final_record_count", len(final) == 24 and final.analysis_unit_id.is_unique, f"{len(final)} final screening records"),
        check("scope_disposition", int((final.scope_disposition == "included").sum()) == 23 and int((final.scope_disposition != "included").sum()) == 1, "23 included; 1 excluded false positive"),
        check("valid_unit_geometry", bool(units.geometry.is_valid.all() and (~units.geometry.is_empty).all()), "all unit geometries valid and nonempty"),
        check("campus_not_roof", final[final.analysis_unit_id.isin(["meta_dekalb_campus", "site_02613"])].mapped_roof_area_m2.isna().all(), "hyperscale campus polygons not reported as roof area"),
        check("dynamic_world_rows", len(annual_dw) == 24 * 11 * 9, f"{len(annual_dw)} rows"),
        check("independent_landcover_rows", len(annual_lc) == 3048, f"{len(annual_lc)} rows"),
        check("dynamic_world_geometry", len(dw) > 0 and dw.geometry.is_valid.all(), f"{len(dw)} valid built-surface polygons"),
        check("imagery_manifest_count", len(manifest) == 72, f"{len(manifest)} imagery records"),
        check("evidence_coverage", set(final.analysis_unit_id).issubset({item["analysis_unit_id"] for item in evidence}), f"{len(evidence)} evidence records"),
        check("review_figure_count", len(list(FIGURES.glob("*_imagery_review.png"))) == 24, f"{len(list(FIGURES.glob('*_imagery_review.png')))} unit figures"),
        check("statewide_figure", (FIGURES / "statewide_analysis_units.png").exists(), "statewide map exists"),
        check("summary_findings_figure", (FIGURES / "statewide_summary_findings.png").exists(), "summary findings chart exists"),
        check("hyperscale_dynamic_world_figure", (FIGURES / "hyperscale_dynamic_world_buildout.png").exists(), "hyperscale Dynamic World chart exists"),
        check("report_exists", REPORT.exists() and REPORT.stat().st_size > 1_000_000, f"{REPORT.stat().st_size if REPORT.exists() else 0} bytes"),
        check("dataset_package", PACKAGE.exists() and PACKAGE.stat().st_size > 100_000, f"{PACKAGE.stat().st_size if PACKAGE.exists() else 0} bytes"),
    ]
    image_errors = []
    for item in manifest:
        path = ROOT / item["path"]
        if not path.exists():
            image_errors.append(f"missing:{path}")
            continue
        with Image.open(path) as image:
            if image.size != (640, 640):
                image_errors.append(f"size:{path}:{image.size}")
    checks.append(check("imagery_files", not image_errors, "all 72 chips exist at 640x640" if not image_errors else ";".join(image_errors[:5])))

    pdf_info = subprocess.check_output(["pdfinfo", str(REPORT)], text=True)
    pages = next(int(line.split(":", 1)[1]) for line in pdf_info.splitlines() if line.startswith("Pages:"))
    checks.append(check("report_page_count", pages == 33, f"{pages} pages"))
    extracted = subprocess.check_output(["pdftotext", str(REPORT), "-"], text=True)
    checks.append(check("report_key_findings", all(term in extracted for term in ["Excluded false positive", "mixed pasture/old-field", "Dynamic World", "Redevelopment dominates overall", "121.7 acres", "Special focus: hyperscale buildout", "48.6%", "93.5%"]), "key findings and caveats present in extracted report text"))

    summary = {
        "passed": all(item["passed"] for item in checks),
        "check_count": len(checks),
        "failed_count": sum(not item["passed"] for item in checks),
        "checks": checks,
    }
    (DATA / "final/qa_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    if not summary["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
