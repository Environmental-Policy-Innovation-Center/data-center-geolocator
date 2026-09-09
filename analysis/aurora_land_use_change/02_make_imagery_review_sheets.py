#!/usr/bin/env python3
"""Create annotated contact sheets for manual phase and identity review."""

from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.plot import plotting_extent


ROOT = Path(__file__).resolve().parents[2]
IMAGERY = ROOT / "data/aurora_land_use_change/raw/imagery"
FIGURES = ROOT / "figures/aurora_land_use_change"
OVERTURE = ROOT / "data/aurora_land_use_change/raw/overture/buildings.parquet"

SELECTED = {
    "2bb5f41d-b1d2-4ca2-855e-4d93af62a66f": "Edged ORD01-1",
    "539ab7e6-603a-406a-b98e-05c2b52a59a0": "CyrusOne CHI1 CME",
    "8f138e06-fc92-442f-a4a5-7d6968d82dc3": "CyrusOne CHI2 candidate",
    "e1769c58-a74b-4991-bc03-5ce1ffd3c73e": "CyrusOne CHI3",
}


def read_rgb(path):
    with rasterio.open(path) as src:
        arr = src.read([1, 2, 3])
        extent = plotting_extent(src)
    rgb = np.moveaxis(arr, 0, -1)
    if rgb.dtype != np.uint8:
        lo, hi = np.nanpercentile(rgb[rgb > 0], [2, 98])
        rgb = np.clip((rgb - lo) / max(hi - lo, 1), 0, 1)
    return rgb, extent


def overlay(ax, buildings, labels=False):
    buildings.boundary.plot(ax=ax, color="#ff2a2a", linewidth=1.4)
    if labels:
        for _, row in buildings.iterrows():
            p = row.geometry.centroid
            ax.text(
                p.x,
                p.y,
                SELECTED[row.id],
                fontsize=6.5,
                color="white",
                ha="center",
                va="center",
                bbox={"facecolor": "#111111", "alpha": 0.7, "pad": 1.5, "edgecolor": "none"},
            )


def contact_sheet(paths, output, title, buildings, columns=4):
    rows = int(np.ceil(len(paths) / columns))
    fig, axes = plt.subplots(rows, columns, figsize=(4.4 * columns, 4.6 * rows))
    axes = np.atleast_1d(axes).ravel()
    for ax, path in zip(axes, paths):
        rgb, extent = read_rgb(path)
        ax.imshow(rgb, extent=extent)
        overlay(ax, buildings, labels=True)
        ax.set_title(path.stem.replace("_", " "), fontsize=9)
        ax.set_axis_off()
    for ax in axes[len(paths) :]:
        ax.set_axis_off()
    fig.suptitle(title, fontsize=16, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(output, dpi=180, facecolor="white")
    plt.close(fig)


def main():
    FIGURES.mkdir(parents=True, exist_ok=True)
    buildings = gpd.read_parquet(OVERTURE).to_crs(26916)
    buildings = buildings[buildings.id.isin(SELECTED)].copy()

    naip = sorted((IMAGERY / "naip").glob("*.tif"))
    contact_sheet(
        naip,
        FIGURES / "review_naip_2011_2023.png",
        "NAIP chronology 2011 to 2023",
        buildings,
    )

    sentinel = sorted((IMAGERY / "sentinel2").glob("*.tif"))
    contact_sheet(
        sentinel,
        FIGURES / "review_sentinel_2016_2026.png",
        "Sentinel-2 chronology 2016 to 2026",
        buildings,
        columns=4,
    )

    # Detailed recent views for manual interpretation of the two northern sites.
    edged = gpd.read_file(ROOT / "data/aurora_land_use_change/raw/edged_parcels.geojson").to_crs(26916)
    cyrus = gpd.read_file(ROOT / "data/aurora_land_use_change/raw/cyrus_parcels.geojson").to_crs(26916)
    detail_paths = [
        IMAGERY / "naip/naip_2021_2021-09-28_1m.tif",
        IMAGERY / "naip/naip_2023_2023-08-18_1m.tif",
        IMAGERY / "sentinel2/sentinel2_2024_q4_2024-10-06.tif",
        IMAGERY / "sentinel2/sentinel2_2025_q4_2025-10-26.tif",
        IMAGERY / "sentinel2/sentinel2_2026_q2_2026-05-04.tif",
        IMAGERY / "sentinel2/sentinel2_2026_q3_2026-08-22.tif",
    ]
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    north = edged.union_all().union(cyrus[cyrus.ADDRESS == "2725 BILTER RD"].union_all()).buffer(120).bounds
    for ax, path in zip(axes.ravel(), detail_paths):
        rgb, extent = read_rgb(path)
        ax.imshow(rgb, extent=extent)
        edged.boundary.plot(ax=ax, color="#ffcc00", linewidth=1.2)
        cyrus[cyrus.ADDRESS == "2725 BILTER RD"].boundary.plot(ax=ax, color="#00d4ff", linewidth=1.2)
        buildings[buildings.id.isin(SELECTED)].boundary.plot(ax=ax, color="#ff3344", linewidth=1.2)
        ax.set_xlim(north[0], north[2])
        ax.set_ylim(north[1], north[3])
        ax.set_title(path.stem.replace("_", " "), fontsize=10)
        ax.set_axis_off()
    fig.suptitle("Northern campus detail  yellow Edged parcels  blue CyrusOne parcel  red current Overture roofs", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(FIGURES / "review_northern_campuses_detail.png", dpi=220, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
