#!/usr/bin/env python3
"""Build the illustrated statewide screening report as a landscape PDF."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/illinois_land_use_change"
FIGURES = ROOT / "figures/illinois_land_use_change"
OUT = ROOT / "reports/illinois_land_use_change"
REPORT = OUT / "illinois_data_center_land_use_change_screening_report.pdf"


def value(record, key, suffix=""):
    item = record.get(key)
    if item is None or item == "":
        return "Not yet resolved"
    if isinstance(item, float):
        return f"{item:,.1f}{suffix}"
    return f"{item}{suffix}"


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#58636b"))
    canvas.drawString(0.42 * inch, 0.22 * inch, "Illinois data-center land-use change · statewide screening deliverable")
    canvas.drawRightString(10.58 * inch, 0.22 * inch, f"Page {doc.page}")
    canvas.restoreState()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    geojson = json.loads((DATA / "final/analysis_units_screening.geojson").read_text())
    records = [feature["properties"] for feature in geojson["features"]]
    evidence = json.loads((DATA / "final/documentary_evidence.json").read_text())
    evidence_by_unit = {}
    for item in evidence:
        evidence_by_unit.setdefault(item["analysis_unit_id"], []).append(item)

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleWhite", parent=styles["Title"], textColor=colors.white, fontSize=25, leading=29, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="H1Blue", parent=styles["Heading1"], textColor=colors.HexColor("#153b50"), fontSize=18, leading=21, spaceAfter=8))
    styles.add(ParagraphStyle(name="H2Blue", parent=styles["Heading2"], textColor=colors.HexColor("#247ba0"), fontSize=12, leading=14, spaceAfter=5))
    styles.add(ParagraphStyle(name="BodySmall", parent=styles["BodyText"], fontSize=8.3, leading=10.5))
    styles.add(ParagraphStyle(name="Tiny", parent=styles["BodyText"], fontSize=6.5, leading=8))
    styles.add(ParagraphStyle(name="Callout", parent=styles["BodyText"], fontSize=10, leading=13, textColor=colors.HexColor("#153b50"), backColor=colors.HexColor("#e8f3f5"), borderPadding=8))

    doc = SimpleDocTemplate(
        str(REPORT), pagesize=landscape(letter), leftMargin=0.42 * inch,
        rightMargin=0.42 * inch, topMargin=0.38 * inch, bottomMargin=0.38 * inch,
        title="Illinois Data-Center Land-Use Change: Statewide Screening",
        author="Earth Genome / Codex",
    )
    story = []
    title_box = Table(
        [[Paragraph("Illinois Data-Center Land-Use Change", styles["TitleWhite"])],
         [Paragraph("Statewide taxonomy scale-up · documented screening deliverable · revised 9 September 2026", ParagraphStyle(name="SubWhite", parent=styles["BodyText"], textColor=colors.white, fontSize=11, alignment=TA_CENTER))]],
        colWidths=[10.15 * inch], rowHeights=[1.05 * inch, 0.42 * inch],
    )
    title_box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#153b50")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.extend([Spacer(1, 0.35 * inch), title_box, Spacer(1, 0.28 * inch)])
    story.append(Paragraph(
        "This report scales the Aurora proof of concept to every Illinois seed record in the selected visual-taxonomy categories. It separates mapped roof geometry, approved-plan geometry, and provisional satellite built surfaces. It is a screening and evidence-resolution deliverable: Aurora remains the only QA-complete disturbance measurement.",
        styles["Callout"],
    ))
    story.append(Spacer(1, 0.18 * inch))
    story.append(Image(str(FIGURES / "statewide_analysis_units.png"), width=4.2 * inch, height=4.2 * inch))
    story.append(PageBreak())

    story.append(Paragraph("Executive findings", styles["H1Blue"]))
    bullets = [
        "The 27 taxonomy seed records resolve to 24 campus/parcel analysis units. Twenty-three remain in scope; one South Halsted Iron Mountain records warehouse is excluded as a false-positive data center.",
        "The two unreviewed hyperscale examples are not equivalent: Meta DeKalb was row-crop agriculture, while 2019 NAIP shows Microsoft Hoffman Estates as a mixed pasture/old-field, woodland, and wetland site. Dynamic World captures the tree component; coarse NLCD/CDL summaries do not.",
        "Most warehouse-style sites were already developed before the available Dynamic World record. Documentary evidence confirms reuse at QTS Chicago, Stream Chicago I/II, T5 Chicago II, Element Critical Wood Dale, Digital Realty CH1, and Digital Realty ORD12.",
        "Automated Dynamic World breakpoints are accepted only as review dates. Six units show a candidate 2016–2026 change, and two of those are contaminated by overlapping neighboring-site masks.",
        "The OSM-derived PNNL and Overture roof layers are useful mapped evidence but can lag 2026 imagery or include neighboring buildings. Dynamic World polygons are built-surface envelopes at 10 m and are never reported as roof footprints.",
    ]
    for item in bullets:
        story.append(Paragraph(f"• {item}", styles["BodyText"]))
        story.append(Spacer(1, 4))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Geometry and measurement status", styles["H2Blue"]))
    status_data = [
        ["Measure", "Statewide status", "Interpretation"],
        ["Mapped roof", "PNNL/OSM source polygons; Overture candidates", "Lower-bound or candidate geometry; may be stale/incomplete"],
        ["Approved-plan roof", "No new statewide plan geometries yet", "Kept null rather than merged with mapped roofs"],
        ["Satellite built surface", "2026 Dynamic World core polygons", "Low-confidence roof/pavement/equipment envelope"],
        ["Construction disturbance", "Reviewed for Aurora only", "Null elsewhere pending dated-image delineation"],
    ]
    table = Table(status_data, colWidths=[1.55 * inch, 3.0 * inch, 5.35 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#247ba0")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b8c3c9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f7")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    story.append(PageBreak())

    story.append(Paragraph("What the statewide screening reveals", styles["H1Blue"]))
    story.append(Image(str(FIGURES / "statewide_summary_findings.png"), width=10.0 * inch, height=3.42 * inch))
    story.append(Paragraph(
        "Source: statewide screening dataset, 23 included analysis units. Roof comparison uses the 21 units with mapped PNNL/OSM roof area.",
        styles["Tiny"],
    ))
    story.append(Spacer(1, 5))
    findings = [
        ("Redevelopment dominates overall", "Nineteen of 23 included analysis units (83%) occupied previously developed or brownfield sites. The industrial-park colo category is especially reuse-oriented: 15 of 16 units are previously developed or brownfield, while one transitioned from agriculture into a serviced industrial park before data-center construction."),
        ("Hyperscale greenfield is not one land-cover story", "Both hyperscale campuses are greenfield, but Meta DeKalb replaced row-crop agriculture whereas Microsoft Hoffman Estates replaced a mixed pasture/old-field, woodland, and wetland landscape. The large purpose-built group is mostly redevelopment (four of five units), with Aurora CHI1-CHI2 as the agricultural exception."),
        ("The documented development wave is recent", "Eight of the 16 units with a resolved construction start began during 2019-2022. Seven included units still lack a defensible start date, so this distribution describes documentary coverage as well as development timing."),
        ("Satellite built surface is a campus-scale proxy", "Across the 21 included units with mapped PNNL/OSM roof area, those roofs total 121.7 acres while 2026 Dynamic World built-surface envelopes total 742.8 acres - 6.1 times as much. Even units without a neighbor-contamination flag show a roughly 5.0-fold aggregate gap. Dynamic World therefore captures pavement, equipment pads, and surrounding development and cannot substitute for roof geometry."),
        ("Change detection is useful but selective", "Six of 23 included units show a candidate 2016-2026 Dynamic World construction or major-redevelopment interval; two of the six are affected by overlapping neighboring-site masks. The remaining 17 were already mature by 2016 or predate Dynamic World's record."),
    ]
    findings_table = Table(
        [[Paragraph(f"<b>{heading}</b>", styles["BodySmall"]), Paragraph(text, styles["BodySmall"])] for heading, text in findings],
        colWidths=[2.35 * inch, 7.55 * inch],
    )
    findings_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c8d0d4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f3f5")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(findings_table)
    story.append(PageBreak())

    story.append(Paragraph("Special focus: hyperscale buildout", styles["H1Blue"]))
    story.append(Paragraph(
        "The two hyperscale analysis units are both greenfield conversions, but the annual Dynamic World trajectories show materially different starting landscapes and construction signatures. The curves below report 10 m argmax class shares within provisional screening geometries; they describe land-cover transition, not accepted roof or disturbance boundaries. The stricter 2026 built-core outputs are separate and measure 22.4 acres at Meta and 28.5 acres at Hoffman Estates.",
        styles["BodySmall"],
    ))
    story.append(Spacer(1, 5))
    story.append(Image(str(FIGURES / "hyperscale_dynamic_world_buildout.png"), width=9.65 * inch, height=5.31 * inch))
    hyperscale_rows = [
        [Paragraph("<b>Meta DeKalb</b>", styles["BodySmall"]), Paragraph("The screening geometry was effectively all crops in 2017-2019. In 2020, crops fell to 45.3% while bare ground rose to 48.6%, matching the documented groundbreaking year. Built-class share then rose from 14.0% in 2021 to 48.7% in 2022 and 62.7% in 2024. The 2026 mix - 52.3% built, 15.2% bare, and 22.4% crops or other vegetation - is consistent with a large campus still undergoing phased buildout or landscaping after beginning service in November 2023.", styles["BodySmall"])],
        [Paragraph("<b>Microsoft Hoffman Estates</b>", styles["BodySmall"]), Paragraph("The 2019 baseline was heterogeneous: 61.9% trees, 32.9% crops, and 5.0% other vegetation. During the documented 2021 construction start, trees fell to 5.0% while other vegetation and bare ground reached 69.5% and 16.7%. Built-class share then jumped to 84.1% in 2022 and reached 93.5% in 2026, indicating a faster and more spatially complete conversion than the multi-phase Meta trajectory.", styles["BodySmall"])],
    ]
    hyperscale_table = Table(hyperscale_rows, colWidths=[2.0 * inch, 7.9 * inch])
    hyperscale_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c8d0d4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f3f5")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(hyperscale_table)
    story.append(PageBreak())

    story.append(Paragraph("Methods and confidence rules", styles["H1Blue"]))
    methods = [
        ("Scope and entity resolution", "Taxonomy records are crosswalked to physical campuses using operator naming, addresses, related PNNL records, and documentary campus evidence. Proximity alone is insufficient."),
        ("Construction timing", "Annual Dynamic World built/bare change nominates review intervals. Exact dates come only from dated imagery or phase-specific documentary records."),
        ("Prior land use", "Dynamic World is corroborated with USGS NLCD, USDA Cropland Data Layer, documentary history, and direct NAIP interpretation. Coarse categorical disagreement is retained rather than averaged away."),
        ("Current footprint", "The dataset exposes PNNL/OSM geometry, Overture candidates, and 2026 Dynamic World built surfaces separately. Candidate totals are not silently promoted to accepted roof area."),
        ("Disturbance", "Maximum grading/construction disturbance requires site-scale dated-image delineation. It is intentionally null for the 23 unreviewed units."),
    ]
    method_table = Table([[Paragraph(f"<b>{a}</b>", styles["BodySmall"]), Paragraph(b, styles["BodySmall"])] for a, b in methods], colWidths=[2.1 * inch, 7.8 * inch])
    method_table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c8d0d4")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f3f5")), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(method_table)
    story.append(PageBreak())
    story.append(Paragraph("Scope summary", styles["H2Blue"]))
    rows = [["Unit", "Category", "Prior use", "Start", "Mapped roof acres", "DW surface acres", "Disturbance acres"]]
    for record in records:
        rows.append([
            record["analysis_unit_id"], record["taxonomy_group_id"].replace("_", " "), record["predevelopment_land_use"].replace("_", " "),
            value(record, "construction_start"),
            "—" if record.get("mapped_roof_area_m2") is None else f'{record["mapped_roof_area_m2"] / 4046.8564224:.1f}',
            f'{record["dynamic_world_2026_built_surface_area_acres"]:.1f}',
            "—" if record.get("disturbed_area_acres") is None else f'{record["disturbed_area_acres"]:.1f}',
        ])
    summary_table = Table(rows, repeatRows=1, colWidths=[1.5 * inch, 1.65 * inch, 2.3 * inch, 0.8 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#153b50")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 6.2),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b8c3c9")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f7")]),
    ]))
    story.append(summary_table)
    story.append(PageBreak())

    for record in records:
        disposition = "Excluded false positive" if record["scope_disposition"] != "included" else record["taxonomy_group_id"].replace("_", " ")
        story.append(Paragraph(record["canonical_name"], styles["H1Blue"]))
        story.append(Paragraph(f"{record['analysis_unit_id']} · {disposition} · review state: {record['review_state']}", styles["BodySmall"]))
        story.append(Spacer(1, 4))
        figure = FIGURES / f"{record['analysis_unit_id']}_imagery_review.png"
        story.append(Image(str(figure), width=10.05 * inch, height=3.65 * inch))
        metric_rows = [
            ["Prior land use", record["predevelopment_land_use"].replace("_", " "), "Confidence", record["predevelopment_confidence"]],
            ["Construction start", value(record, "construction_start"), "Completion/operation", value(record, "operational_or_completion")],
            ["Mapped roof", "—" if record.get("mapped_roof_area_m2") is None else f'{record["mapped_roof_area_m2"]:,.0f} m²', "Overture candidates", f'{record["overture_candidate_count"]} / {record["overture_candidate_area_m2"]:,.0f} m²'],
            ["DW 2026 built surface", f'{record["dynamic_world_2026_built_surface_area_m2"]:,.0f} m²', "Disturbance", "Not delineated" if record.get("disturbed_area_m2") is None else f'{record["disturbed_area_m2"]:,.0f} m²'],
        ]
        metrics = Table(metric_rows, colWidths=[1.35 * inch, 3.15 * inch, 1.35 * inch, 4.05 * inch])
        metrics.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c8d0d4")), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f3f5")), ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#e8f3f5")), ("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7.3), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(metrics)
        story.append(Spacer(1, 5))
        story.append(Paragraph(f"<b>Timeline and interpretation.</b> {record['timeline_summary']}", styles["BodySmall"]))
        ids = [item["evidence_id"] for item in evidence_by_unit.get(record["analysis_unit_id"], []) if item["evidence_type"] == "documentary"]
        story.append(Paragraph(f"Documentary evidence IDs: {', '.join(ids) if ids else 'none'}", styles["Tiny"]))
        story.append(PageBreak())

    story.append(Paragraph("Source register", styles["H1Blue"]))
    documentary = [item for item in evidence if item["evidence_type"] == "documentary"]
    for item in documentary:
        source = item["source"]
        if source.startswith("http"):
            domain = urlparse(source).netloc
            source_text = f'<link href="{source}" color="#247ba0">{domain}</link>'
        else:
            source_text = source
        story.append(Paragraph(f"<b>{item['evidence_id']}</b> · {source_text}<br/>{item['note']}", styles["Tiny"]))
        story.append(Spacer(1, 4))

    story.append(Spacer(1, 8))
    story.append(Paragraph("Data package", styles["H2Blue"]))
    story.append(Paragraph(
        "Primary outputs: analysis_units_screening.geojson/parquet; documentary_evidence.json; dynamic_world_built_core_2026.geojson/parquet; annual Dynamic World, NLCD, and CDL Parquet tables; Overture candidate GeoJSON; imagery_manifest.json; and per-unit review figures.",
        styles["BodySmall"],
    ))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(REPORT)


if __name__ == "__main__":
    main()
