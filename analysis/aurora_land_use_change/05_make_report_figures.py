#!/usr/bin/env python3
"""Create publication-ready figures for the Aurora land-use change report."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd
import rasterio
from rasterio.plot import plotting_extent


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/aurora_land_use_change"
FIG = ROOT / "figures/aurora_land_use_change/report"
FIG.mkdir(parents=True, exist_ok=True)

NAVY = "#16324F"
CYAN = "#00A6A6"
GOLD = "#F2B134"
RED = "#D1495B"
PURPLE = "#7E57C2"
GRAY = "#64748B"


def read_rgb(path: Path):
    with rasterio.open(path) as src:
        arr = src.read([1, 2, 3])
        extent = plotting_extent(src)
        crs = src.crs
    arr = np.moveaxis(arr, 0, -1)
    if arr.dtype != np.uint8:
        lo, hi = np.percentile(arr[arr > 0], [2, 98])
        arr = np.clip((arr - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)
    return arr, extent, crs


def plot_chip(ax, path, bounds, title, site_geom, mapped_geoms, plan_geoms, resolution):
    arr, extent, crs = read_rgb(path)
    ax.imshow(arr, extent=extent)
    site = gpd.GeoSeries([site_geom], crs="EPSG:26916").to_crs(crs)
    mapped = gpd.GeoSeries(list(mapped_geoms), crs="EPSG:26916").to_crs(crs)
    plans = gpd.GeoSeries(list(plan_geoms), crs="EPSG:26916").to_crs(crs)
    site.boundary.plot(ax=ax, color=GOLD, linewidth=1.8)
    if len(mapped):
        mapped.boundary.plot(ax=ax, color=CYAN, linewidth=1.5)
    if len(plans):
        plans.boundary.plot(ax=ax, color=PURPLE, linewidth=1.5, linestyle="--")
    ax.set_xlim(bounds[0], bounds[2])
    ax.set_ylim(bounds[1], bounds[3])
    ax.set_title(title, fontsize=10, fontweight="bold", color=NAVY, pad=6)
    ax.text(
        0.02,
        0.02,
        resolution,
        transform=ax.transAxes,
        fontsize=7.5,
        color="white",
        bbox=dict(facecolor="black", alpha=0.6, pad=2, edgecolor="none"),
    )
    ax.set_xticks([])
    ax.set_yticks([])


def add_scale_note(fig):
    fig.text(
        0.5,
        0.015,
        "Gold = campus; cyan solid = mapped Overture/OSM roof; purple dashed = approved-plan geometry with approximate positioning.",
        ha="center",
        fontsize=8,
        color=GRAY,
    )


def site_montage(site_id, title, panels, filename, ncols=None):
    sites = gpd.read_file(DATA / "final/sites.geojson").to_crs(26916).set_index("site_id")
    buildings = gpd.read_file(DATA / "final/buildings.geojson").to_crs(26916)
    geom = sites.loc[site_id].geometry
    subset = buildings[buildings.site_id.eq(site_id)]
    mapped = subset.loc[subset.geometry_class.eq("current_mapped_footprint"), "geometry"].tolist()
    plans = subset.loc[subset.geometry_class.str.startswith("approved_plan"), "geometry"].tolist()
    bounds = geom.buffer(90).bounds
    n = len(panels)
    ncols = ncols or n
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.15 * ncols, 4.25 * nrows), dpi=180)
    axes = np.atleast_1d(axes).ravel()
    for ax, panel in zip(axes, panels):
        plot_chip(ax, Path(panel[0]), bounds, panel[1], geom, mapped, plans, panel[2])
    for ax in axes[n:]:
        ax.axis("off")
    fig.suptitle(title, fontsize=16, fontweight="bold", color=NAVY, y=0.98)
    add_scale_note(fig)
    fig.tight_layout(rect=(0.01, 0.04, 0.99, 0.94))
    fig.savefig(FIG / filename, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def overview():
    sites = gpd.read_file(DATA / "final/sites.geojson").to_crs(26916)
    buildings = gpd.read_file(DATA / "final/buildings.geojson").to_crs(26916)
    path = DATA / "raw/imagery/naip/naip_2023_2023-08-18_1m.tif"
    arr, extent, crs = read_rgb(path)
    fig, ax = plt.subplots(figsize=(9.2, 7), dpi=180)
    ax.imshow(arr, extent=extent)
    sites.to_crs(crs).boundary.plot(ax=ax, color=GOLD, linewidth=2.0)
    mapped = buildings[buildings.geometry_class.eq("current_mapped_footprint")]
    plans = buildings[buildings.geometry_class.str.startswith("approved_plan")]
    mapped.to_crs(crs).boundary.plot(ax=ax, color=CYAN, linewidth=1.5)
    plans.to_crs(crs).boundary.plot(ax=ax, color=PURPLE, linewidth=1.5, linestyle="--")
    labels = {
        "edged_chicago": ("Edged Chicago", 18, 18),
        "cyrusone_aurora_iii": ("CyrusOne Aurora III", -130, 30),
        "cyrusone_aurora_chi1_chi2": ("CyrusOne CHI1–CHI2", 20, -25),
    }
    for row in sites.itertuples():
        c = row.geometry.centroid
        name, dx, dy = labels[row.site_id]
        ax.annotate(
            name,
            (c.x, c.y),
            xytext=(c.x + dx, c.y + dy),
            color="white",
            fontsize=9,
            fontweight="bold",
            bbox=dict(facecolor=NAVY, alpha=0.82, edgecolor="none", pad=3),
        )
    minx, miny, maxx, maxy = sites.total_bounds
    ax.set_xlim(minx - 180, maxx + 220)
    ax.set_ylim(miny - 180, maxy + 160)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("Three data-center campuses identified in the study area", fontsize=16, fontweight="bold", color=NAVY)
    ax.text(0.01, 0.01, "USDA NAIP • 18 Aug 2023 • 1 m", transform=ax.transAxes, color="white", fontsize=8, bbox=dict(facecolor="black", alpha=.65, edgecolor="none", pad=3))
    fig.tight_layout()
    fig.savefig(FIG / "01_study_area_overview.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def dynamic_world_chart():
    dw = pd.read_csv(DATA / "final/dynamic_world_annual.csv")
    focus = dw[dw.class_name.isin(["crops", "trees", "built", "bare"])]
    sites = [
        ("edged_chicago", "Edged Chicago"),
        ("cyrusone_aurora_chi1_chi2", "CyrusOne CHI1–CHI2"),
        ("cyrusone_aurora_iii", "CyrusOne Aurora III"),
    ]
    colors = {"crops": "#E9C46A", "trees": "#2A9D8F", "built": "#355070", "bare": "#E76F51"}
    fig, axes = plt.subplots(1, 3, figsize=(12.6, 3.8), dpi=180, sharey=True)
    for ax, (sid, title) in zip(axes, sites):
        q = focus[focus.site_id.eq(sid)].pivot(index="year", columns="class_name", values="argmax_area_pct").fillna(0)
        for cls in ["crops", "trees", "built", "bare"]:
            ax.plot(q.index, q.get(cls, 0), marker="o", markersize=2.8, linewidth=1.7, color=colors[cls], label=cls.title())
        ax.set_title(title, fontsize=10, fontweight="bold", color=NAVY)
        ax.set_ylim(0, 103)
        ax.grid(axis="y", alpha=.2)
        ax.set_xlabel("Year")
        ax.tick_params(labelsize=8)
    axes[0].set_ylabel("Parcel area assigned to class (%)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 1.03), ncol=4, frameon=False)
    fig.suptitle("Dynamic World captures the agricultural-to-construction transition", y=1.15, fontsize=15, fontweight="bold", color=NAVY)
    fig.text(.5, -.02, "Annual median probability composite; 10 m argmax classification. Mixed pixels and landscaping create year-to-year noise.", ha="center", fontsize=8, color=GRAY)
    fig.tight_layout()
    fig.savefig(FIG / "05_dynamic_world_change.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def metric_chart():
    sites = pd.read_csv(DATA / "final/sites.csv")
    labels = ["Edged\nChicago", "CyrusOne\nCHI1–CHI2", "CyrusOne\nAurora III"]
    x = np.arange(3)
    fig, ax = plt.subplots(figsize=(8.4, 4.4), dpi=180)
    ax.bar(x - .19, sites.campus_area_acres, width=.38, label="Campus parcel", color="#C9D6DF")
    ax.bar(x + .19, sites.disturbed_area_estimate_acres, width=.38, label="Disturbed estimate", color=RED)
    mapped_roof = sites.mapped_roof_footprint_m2.to_numpy() / 4046.8564224
    provisional_total = sites.current_roof_footprint_acres.to_numpy()
    ax.scatter(x + .19, mapped_roof, marker="D", s=55, color=NAVY, zorder=4, label="Mapped roof footprint")
    has_plan = sites.approved_plan_active_roof_m2.to_numpy() > 0
    ax.scatter((x + .19)[has_plan], provisional_total[has_plan], marker="X", s=70, color=PURPLE, zorder=5, label="Mapped + active approved plan")
    for i, row in sites.iterrows():
        ax.text(i + .19, row.disturbed_area_estimate_acres + 1.3, f"{row.disturbed_area_estimate_acres:.1f} ac", ha="center", fontsize=8, color=RED, fontweight="bold")
        ax.text(i + .19, mapped_roof[i] + 1.0, f"{mapped_roof[i]:.1f}", ha="center", fontsize=7.5, color=NAVY)
        if has_plan[i]:
            ax.text(i + .19, provisional_total[i] + 1.0, f"{provisional_total[i]:.1f}", ha="center", fontsize=7.5, color=PURPLE)
    ax.set_xticks(x, labels)
    ax.set_ylabel("Acres")
    ax.set_ylim(0, 72)
    ax.grid(axis="y", alpha=.2)
    ax.legend(frameon=False, ncol=2, loc="upper center")
    ax.set_title("Disturbance extends well beyond the roof footprint", fontsize=15, fontweight="bold", color=NAVY, pad=16)
    fig.text(.5, .01, "Disturbance estimates are classifier-based proxies with site-specific uncertainty ranges in the dataset.", ha="center", fontsize=8, color=GRAY)
    fig.tight_layout(rect=(0, .04, 1, 1))
    fig.savefig(FIG / "06_area_comparison.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def dynamic_world_envelopes():
    sites = gpd.read_file(DATA / "final/sites.geojson").to_crs(26916).set_index("site_id")
    buildings = gpd.read_file(DATA / "final/buildings.geojson").to_crs(26916)
    core = gpd.read_file(DATA / "final/dynamic_world_built_core_2026.geojson").to_crs(26916)
    inclusive = gpd.read_file(DATA / "final/dynamic_world_built_inclusive_2026.geojson").to_crs(26916)
    image_path = DATA / "raw/imagery/sentinel2/sentinel2_2026_q3_2026-08-22.tif"
    arr, extent, crs = read_rgb(image_path)
    panels = [
        ("edged_chicago", "Edged Chicago"),
        ("cyrusone_aurora_iii", "CyrusOne Aurora III"),
        ("cyrusone_aurora_chi1_chi2", "CyrusOne CHI1-CHI2"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(12.7, 4.6), dpi=180)
    for ax, (sid, title) in zip(axes, panels):
        geom = sites.loc[sid].geometry
        bounds = geom.buffer(80).bounds
        ax.imshow(arr, extent=extent)
        inc = inclusive[inclusive.site_id.eq(sid)].to_crs(crs)
        cor = core[core.site_id.eq(sid)].to_crs(crs)
        mapped = buildings[(buildings.site_id.eq(sid)) & buildings.geometry_class.eq("current_mapped_footprint")].to_crs(crs)
        plans = buildings[(buildings.site_id.eq(sid)) & buildings.geometry_class.str.startswith("approved_plan")].to_crs(crs)
        if len(inc):
            inc.plot(ax=ax, facecolor=RED, edgecolor=RED, alpha=.22, linewidth=.8)
        if len(cor):
            cor.plot(ax=ax, facecolor="#D81B60", edgecolor="#D81B60", alpha=.42, linewidth=1.0)
        if len(mapped):
            mapped.boundary.plot(ax=ax, color=CYAN, linewidth=1.8)
        if len(plans):
            plans.boundary.plot(ax=ax, color=PURPLE, linewidth=1.8, linestyle="--")
        ax.set_xlim(bounds[0], bounds[2])
        ax.set_ylim(bounds[1], bounds[3])
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(title, fontsize=10, fontweight="bold", color=NAVY)
    handles = [
        Line2D([0], [0], color=CYAN, lw=2, label="Mapped Overture/OSM roof"),
        Line2D([0], [0], color=PURPLE, lw=2, ls="--", label="Approved-plan geometry"),
        Patch(facecolor="#D81B60", alpha=.42, label="Dynamic World core"),
        Patch(facecolor=RED, alpha=.22, label="Dynamic World inclusive"),
    ]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, .98), ncol=4, frameon=False, fontsize=8)
    fig.suptitle("Provisional Dynamic World built-surface envelopes", fontsize=15, fontweight="bold", color=NAVY, y=1.06)
    fig.text(.5, .01, "January-August 2026 median composite. Built surfaces are screening envelopes, not building footprints.", ha="center", fontsize=8, color=GRAY)
    fig.tight_layout(rect=(.01, .05, .99, .89))
    fig.savefig(FIG / "07_dynamic_world_built_envelopes.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    overview()
    img = DATA / "raw/imagery"
    site_montage(
        "edged_chicago",
        "Edged Chicago: row-crop fields to a two-building campus",
        [
            (img / "naip/naip_2021_2021-09-28_1m.tif", "Before • 28 Sep 2021", "USDA NAIP • 1 m"),
            (img / "naip/naip_2023_2023-08-18_1m.tif", "Construction • 18 Aug 2023", "USDA NAIP • 1 m"),
            (img / "sentinel2/sentinel2_2026_q3_2026-08-22.tif", "Current • 22 Aug 2026", "Sentinel-2 L2A • 10 m"),
        ],
        "02_edged_change.png",
    )
    site_montage(
        "cyrusone_aurora_chi1_chi2",
        "CyrusOne CHI1–CHI2: an older campus developed in two main waves",
        [
            (img / "landsat/landsat_2006_2006-09-25_30m.tif", "CHI1 baseline • 25 Sep 2006", "Landsat • 30 m"),
            (img / "naip/naip_2015_2015-09-16_1m.tif", "Before CHI2 • 16 Sep 2015", "USDA NAIP • 1 m"),
            (img / "naip/naip_2017_2017-07-02_1m.tif", "CHI2 roof present • 2 Jul 2017", "USDA NAIP • 1 m"),
            (img / "naip/naip_2023_2023-08-18_1m.tif", "Current high-resolution view • 18 Aug 2023", "USDA NAIP • 1 m"),
        ],
        "03_cyrus_original_change.png",
        ncols=2,
    )
    site_montage(
        "cyrusone_aurora_iii",
        "CyrusOne Aurora III: agricultural field to first completed roof",
        [
            (img / "naip/naip_2023_2023-08-18_1m.tif", "Before • 18 Aug 2023", "USDA NAIP • 1 m"),
            (img / "sentinel2/sentinel2_2024_q4_2024-10-06.tif", "Early works • 6 Oct 2024", "Sentinel-2 L2A • 10 m"),
            (img / "sentinel2/sentinel2_2026_q3_2026-08-22.tif", "Current • 22 Aug 2026", "Sentinel-2 L2A • 10 m"),
        ],
        "04_cyrus_iii_change.png",
    )
    dynamic_world_chart()
    metric_chart()
    dynamic_world_envelopes()
    print("\n".join(str(p) for p in sorted(FIG.glob("*.png"))))


if __name__ == "__main__":
    main()
