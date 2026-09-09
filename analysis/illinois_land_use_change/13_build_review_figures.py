#!/usr/bin/env python3
"""Build auditable three-panel imagery figures and a statewide location map."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/illinois_land_use_change"
FIGURES = ROOT / "figures/illinois_land_use_change"
M2_PER_ACRE = 4046.8564224


def land_origin(value: str) -> str:
    """Collapse detailed, evidence-preserving land-use labels for summaries."""
    if value.startswith("previously_developed") or value.startswith("brownfield_"):
        return "Previously developed / brownfield"
    if value.startswith("agricultural") or value.startswith("greenfield_"):
        return "Greenfield / agricultural / natural"
    if value.startswith("former_agricultural"):
        return "Transitional industrial park"
    return "Other"


def construction_period(value) -> str:
    if value is None:
        return "Unknown"
    try:
        year = int(str(value)[:4])
    except (TypeError, ValueError):
        return "Unknown"
    if year <= 2016:
        return "2008-2016"
    if year <= 2018:
        return "2017-2018"
    return "2019-2022"


def build_summary_findings(units: gpd.GeoDataFrame) -> None:
    included = units[units.scope_disposition == "included"].copy()
    included["land_origin"] = included.predevelopment_land_use.map(land_origin)
    included["construction_period"] = included.construction_start.map(construction_period)

    group_order = [
        "hyperscale_greenfield_campus",
        "large_purpose_built_data_center",
        "industrial_park_warehouse_style_colo",
    ]
    group_labels = ["Hyperscale\ngreenfield", "Large purpose-\nbuilt", "Industrial-park\ncolo"]
    origins = [
        "Previously developed / brownfield",
        "Greenfield / agricultural / natural",
        "Transitional industrial park",
    ]
    origin_colors = ["#536878", "#59a14f", "#edc948"]

    fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.25))
    fig.patch.set_facecolor("white")

    # A. Predevelopment land origin by taxonomy category.
    ax = axes[0]
    left = np.zeros(len(group_order))
    for origin, color in zip(origins, origin_colors):
        values = np.array([
            int(((included.taxonomy_group_id == group) & (included.land_origin == origin)).sum())
            for group in group_order
        ])
        bars = ax.barh(group_labels, values, left=left, color=color, label=origin, height=0.62)
        for bar, value in zip(bars, values):
            if value:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_y() + bar.get_height() / 2,
                        str(value), ha="center", va="center", color="white" if color != "#edc948" else "#24333b",
                        fontsize=9, fontweight="bold")
        left += values
    ax.set_title("A. What occupied the site before development?", loc="left", fontsize=11, fontweight="bold")
    ax.set_xlabel("Included analysis units")
    ax.set_xlim(0, max(left) + 1)
    ax.grid(axis="x", color="#d8dee2", linewidth=0.7, zorder=0)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), frameon=False, fontsize=7, ncol=1)

    # B. Documentary construction-start coverage and timing.
    ax = axes[1]
    periods = ["2008-2016", "2017-2018", "2019-2022", "Unknown"]
    period_colors = ["#8da0ae", "#4e89a8", "#247ba0", "#d2d7da"]
    counts = [int((included.construction_period == period).sum()) for period in periods]
    bars = ax.bar(periods, counts, color=period_colors, width=0.68)
    for bar, count in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, count + 0.2, str(count), ha="center", fontsize=10, fontweight="bold")
    ax.set_title("B. When did construction start?", loc="left", fontsize=11, fontweight="bold")
    ax.set_ylabel("Included analysis units")
    ax.set_ylim(0, max(counts) + 1.5)
    ax.tick_params(axis="x", labelrotation=25, labelsize=8)
    ax.grid(axis="y", color="#d8dee2", linewidth=0.7, zorder=0)
    ax.text(0.5, -0.25, "8 of 16 resolved starts occurred in 2019-2022; 7 remain unresolved.",
            transform=ax.transAxes, ha="center", fontsize=7.5, color="#58636b")

    # C. Demonstrate why the Dynamic World envelope is not a roof footprint.
    ax = axes[2]
    measurable = included[included.mapped_roof_area_m2.notna()].copy()
    categories = ["Large purpose-\nbuilt", "Industrial-park\ncolo"]
    ratios = []
    areas = []
    for group in group_order[1:]:
        subset = measurable[measurable.taxonomy_group_id == group]
        roof = subset.mapped_roof_area_m2.sum()
        built = subset.dynamic_world_2026_built_surface_area_m2.sum()
        ratios.append(built / roof)
        areas.append((roof / M2_PER_ACRE, built / M2_PER_ACRE))
    bars = ax.bar(categories, ratios, color=["#f28e2b", "#6a4c93"], width=0.6)
    for bar, ratio, (roof_acres, built_acres) in zip(bars, ratios, areas):
        ax.text(bar.get_x() + bar.get_width() / 2, ratio + 0.18, f"{ratio:.1f}x",
                ha="center", fontsize=11, fontweight="bold")
        ax.text(bar.get_x() + bar.get_width() / 2, 0.25,
                f"{roof_acres:.1f} roof ac\n{built_acres:.1f} DW ac",
                ha="center", va="bottom", fontsize=7.2, color="white", fontweight="bold")
    ax.set_title("C. Satellite built surface exceeds mapped roof", loc="left", fontsize=11, fontweight="bold")
    ax.set_ylabel("Dynamic World area / mapped roof area")
    ax.set_ylim(0, max(ratios) + 1.3)
    ax.grid(axis="y", color="#d8dee2", linewidth=0.7, zorder=0)
    ax.text(0.5, -0.25, "Same 21 units. DW includes pavement/equipment and sometimes neighboring development.",
            transform=ax.transAxes, ha="center", fontsize=7.5, color="#58636b")

    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_axisbelow(True)
    fig.suptitle("Statewide screening findings: land origin, timing, and measurement scale",
                 fontsize=15, fontweight="bold", color="#153b50", y=1.02)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.84, bottom=0.28, wspace=0.34)
    fig.savefig(FIGURES / "statewide_summary_findings.png", dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def build_hyperscale_dynamic_world_figure(units: gpd.GeoDataFrame) -> None:
    """Compare the two hyperscale land-cover transitions using annual DW argmax shares."""
    annual = pd.read_parquet(DATA / "interim/dynamic_world_screening_annual.parquet")
    sites = [
        ("meta_dekalb_campus", "Meta DeKalb", 2020),
        ("site_02613", "Microsoft Hoffman Estates", 2021),
    ]
    classes = ["crops", "trees", "other vegetation", "bare", "built", "water / other"]
    colors = {
        "crops": "#E9C46A",
        "trees": "#2A9D8F",
        "other vegetation": "#76B7B2",
        "bare": "#E76F51",
        "built": "#355070",
        "water / other": "#4E79A7",
    }

    tables = {}
    for uid, _, _ in sites:
        q = annual[annual.analysis_unit_id == uid].pivot(
            index="year", columns="class_name", values="argmax_area_pct"
        ).fillna(0)
        q["other vegetation"] = q.get("grass", 0) + q.get("shrub_and_scrub", 0) + q.get("flooded_vegetation", 0)
        q["water / other"] = q.get("water", 0) + q.get("snow_and_ice", 0)
        tables[uid] = q

    fig, axes = plt.subplots(2, 2, figsize=(14.8, 8.2), gridspec_kw={"height_ratios": [1.45, 1]})
    fig.patch.set_facecolor("white")

    for column, (uid, title, start_year) in enumerate(sites):
        q = tables[uid]
        ax = axes[0, column]
        for cls in classes:
            ax.plot(q.index, q[cls], marker="o", markersize=3.4, linewidth=2.0,
                    color=colors[cls], label=cls.title())
        ax.axvline(start_year, color="#7b8790", linestyle="--", linewidth=1.2)
        ax.text(start_year + 0.12, 98, f"documented start: {start_year}", rotation=90,
                va="top", fontsize=7.5, color="#58636b")
        source_area = float(units.loc[units.analysis_unit_id == uid, "source_geometry_area_acres"].iloc[0])
        ax.set_title(f"{title} ({source_area:.1f}-acre screening geometry)",
                     fontsize=11, fontweight="bold", color="#153b50")
        ax.set_xlim(2016, 2026)
        ax.set_xticks(range(2016, 2027, 2))
        ax.set_ylim(0, 103)
        ax.grid(axis="y", color="#d8dee2", linewidth=0.7)
        ax.set_xlabel("Year")
        if column == 0:
            ax.set_ylabel("Screening geometry assigned to class (%)")

        ax = axes[1, column]
        baseline = q.loc[2019, classes]
        current = q.loc[2026, classes]
        change = current - baseline
        y = np.arange(len(classes))
        bar_colors = [colors[cls] for cls in classes]
        bars = ax.barh(y, change.values, color=bar_colors, height=0.68)
        ax.axvline(0, color="#59666e", linewidth=0.8)
        for bar, delta in zip(bars, change.values):
            offset = 2.0 if delta >= 0 else -2.0
            ax.text(delta + offset, bar.get_y() + bar.get_height() / 2, f"{delta:+.1f}",
                    va="center", ha="left" if delta >= 0 else "right", fontsize=8, fontweight="bold")
        ax.set_yticks(y, [cls.title() for cls in classes])
        ax.invert_yaxis()
        ax.set_xlim(-105, 105)
        ax.set_xlabel("Change in class share, 2019 to 2026 (percentage points)")
        ax.set_title(f"{title}: net land-cover change", fontsize=10, fontweight="bold", color="#153b50")
        ax.grid(axis="x", color="#d8dee2", linewidth=0.7)

    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.94),
               ncol=6, frameon=False, fontsize=8)
    for ax in axes.ravel():
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_axisbelow(True)
    fig.suptitle("Dynamic World traces two different hyperscale greenfield conversions",
                 fontsize=15, fontweight="bold", color="#153b50", y=0.995)
    fig.text(
        0.5, 0.01,
        "Annual median probability composite; 10 m argmax class shares inside provisional screening geometries. "
        "The 2026 observation is partial through August. Mixed pixels and seasonal conditions create year-to-year noise.",
        ha="center", fontsize=8, color="#58636b",
    )
    fig.subplots_adjust(left=0.09, right=0.98, top=0.86, bottom=0.11, hspace=0.42, wspace=0.24)
    fig.savefig(FIGURES / "hyperscale_dynamic_world_buildout.png", dpi=230, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def date_label(record: dict) -> str:
    dates = record.get("acquisition_dates", [])
    if not dates:
        return str(record["year"])
    return dates[0] if len(dates) == 1 else f"{dates[0]} to {dates[-1]}"


def plot_geometry(ax, frame, color, linewidth=1.5, linestyle="-"):
    if frame.empty:
        return
    frame.boundary.plot(ax=ax, color=color, linewidth=linewidth, linestyle=linestyle, zorder=5)


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    units = gpd.read_file(DATA / "final/analysis_units_screening.geojson").to_crs(4326)
    overture = gpd.read_file(DATA / "interim/overture_building_candidates.geojson").to_crs(4326)
    manifest = json.loads((DATA / "review/imagery_manifest.json").read_text())
    by_unit = {}
    for item in manifest:
        by_unit.setdefault(item["analysis_unit_id"], {})[item["role"]] = item

    for row in units.itertuples():
        items = by_unit[row.analysis_unit_id]
        roles = ["baseline", "naip_current", "sentinel2_current"]
        fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.6))
        for ax, role in zip(axes, roles):
            item = items[role]
            image = Image.open(ROOT / item["path"])
            xmin, ymin, xmax, ymax = item["bbox_wgs84"]
            ax.imshow(image, extent=[xmin, xmax, ymin, ymax], origin="upper")
            unit_frame = gpd.GeoDataFrame(geometry=[row.geometry], crs=4326)
            plot_geometry(ax, unit_frame, "#00a6b2", 1.8)
            if role != "baseline":
                plot_geometry(
                    ax,
                    overture[overture.analysis_unit_id == row.analysis_unit_id],
                    "#f2aa1f",
                    1.1,
                    "--",
                )
            source = "NAIP" if role != "sentinel2_current" else "Sentinel-2 SR median"
            ax.set_title(f"{source}\n{date_label(item)}", fontsize=9)
            ax.set_xlim(xmin, xmax)
            ax.set_ylim(ymin, ymax)
            ax.set_xticks([])
            ax.set_yticks([])
        disposition = "EXCLUDED FALSE POSITIVE" if row.scope_disposition != "included" else row.taxonomy_group_id.replace("_", " ")
        fig.suptitle(
            textwrap.fill(f"{row.canonical_name} · {disposition}", 95),
            fontsize=13,
            fontweight="bold",
        )
        fig.subplots_adjust(left=0.02, right=0.98, bottom=0.11, top=0.79, wspace=0.08)
        fig.text(
            0.5,
            0.035,
            "Cyan: PNNL/OSM source geometry  •  Orange dashed: Overture building candidates",
            ha="center",
            fontsize=8,
        )
        fig.savefig(FIGURES / f"{row.analysis_unit_id}_imagery_review.png", dpi=180, bbox_inches="tight")
        plt.close(fig)

    points = units.to_crs(26916)
    points.geometry = points.geometry.centroid
    points = points.to_crs(4326)
    fig, ax = plt.subplots(figsize=(8.5, 8.5))
    ax.set_facecolor("#eef1f3")
    colors = {
        "hyperscale_greenfield_campus": "#247ba0",
        "large_purpose_built_data_center": "#f28e2b",
        "industrial_park_warehouse_style_colo": "#6a4c93",
    }
    for group_id, group in points.groupby("taxonomy_group_id"):
        group.plot(ax=ax, color=colors[group_id], markersize=38, label=group_id.replace("_", " "))
    for row in points.itertuples():
        ax.annotate(row.analysis_unit_id.replace("site_", ""), (row.geometry.x, row.geometry.y), xytext=(3, 3), textcoords="offset points", fontsize=6)
    ax.legend(loc="lower left", fontsize=8)
    ax.set_title("Illinois taxonomy analysis units (resolved campus count: 24)", fontweight="bold")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    fig.savefig(FIGURES / "statewide_analysis_units.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    build_summary_findings(units)
    build_hyperscale_dynamic_world_figure(units)


if __name__ == "__main__":
    main()
