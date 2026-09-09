#!/usr/bin/env python3
"""Fetch dated open imagery chips for the Aurora data-center study.

Sources are queried through the Microsoft Planetary Computer STAC API. The
script writes cropped GeoTIFFs plus a CSV evidence manifest. It does not depend
on Earth Engine credentials, but uses the same public source collections used
by the companion Earth Engine workflow.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import planetary_computer
import rasterio
from pyproj import Transformer
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.vrt import WarpedVRT


CATALOG_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
AOI_CRS = "EPSG:26916"
CORE_BBOX_WGS84 = (-88.258, 41.790, -88.232, 41.813)
BAD_SCL = {0, 1, 3, 8, 9, 10, 11}


def target_grid(bbox_wgs84, resolution):
    project = Transformer.from_crs("EPSG:4326", AOI_CRS, always_xy=True)
    x1, y1 = project.transform(bbox_wgs84[0], bbox_wgs84[1])
    x2, y2 = project.transform(bbox_wgs84[2], bbox_wgs84[3])
    left, right = sorted((x1, x2))
    bottom, top = sorted((y1, y2))
    width = int(np.ceil((right - left) / resolution))
    height = int(np.ceil((top - bottom) / resolution))
    transform = from_bounds(left, bottom, right, top, width, height)
    return (left, bottom, right, top), width, height, transform


def read_to_grid(href, bands, resolution, resampling=Resampling.bilinear):
    _, width, height, transform = target_grid(CORE_BBOX_WGS84, resolution)
    with rasterio.open(href) as src:
        with WarpedVRT(
            src,
            crs=AOI_CRS,
            transform=transform,
            width=width,
            height=height,
            resampling=resampling,
        ) as vrt:
            arr = vrt.read(bands, masked=True)
            profile = vrt.profile.copy()
    profile.update(
        driver="GTiff",
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
        count=len(bands),
        dtype=str(arr.dtype),
        nodata=0,
    )
    return arr, profile


def write_array(path, arr, profile, descriptions=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = arr.filled(0) if np.ma.isMaskedArray(arr) else arr
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data)
        if descriptions:
            for i, description in enumerate(descriptions, 1):
                dst.set_band_description(i, description)


def local_clear_fraction(item):
    signed = planetary_computer.sign(item)
    try:
        arr, _ = read_to_grid(
            signed.assets["SCL"].href,
            [1],
            20,
            resampling=Resampling.nearest,
        )
    except Exception:
        return -1.0
    data = arr[0]
    valid = ~np.ma.getmaskarray(data)
    if not valid.any():
        return -1.0
    good = valid & ~np.isin(data.filled(0), list(BAD_SCL))
    return float(good.sum() / valid.sum())


def choose_best(items, year, quarter=None):
    candidates = []
    for item in items:
        if item.datetime.year != year:
            continue
        month = item.datetime.month
        if quarter is None and month not in range(5, 11):
            continue
        if quarter is not None and ((month - 1) // 3 + 1) != quarter:
            continue
        candidates.append(item)
    candidates.sort(key=lambda x: x.properties.get("eo:cloud_cover", 100))
    # Three low-cloud candidates are sufficient for this small AOI and avoid
    # opening dozens of remote COGs when the catalog is rerun.
    scored = [(local_clear_fraction(item), item) for item in candidates[:3]]
    scored.sort(key=lambda x: (x[0], -x[1].properties.get("eo:cloud_cover", 100)), reverse=True)
    return scored[0] if scored else (None, None)


def fetch_sentinel(catalog, out_dir, evidence):
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=list(CORE_BBOX_WGS84),
        datetime="2015-01-01/2026-09-06",
        query={"eo:cloud_cover": {"lt": 45}},
        max_items=5000,
    )
    items = list(search.items())
    periods = [(year, None) for year in range(2016, 2023)]
    periods += [(year, q) for year in range(2023, 2027) for q in range(1, 5)]
    for year, quarter in periods:
        period = f"{year}_q{quarter}" if quarter else f"{year}_annual"
        existing = sorted((out_dir / "sentinel2").glob(f"sentinel2_{period}_*.tif"))
        if existing:
            evidence.append(
                {
                    "evidence_type": "satellite_imagery",
                    "provider": "ESA Copernicus via Microsoft Planetary Computer",
                    "collection": "sentinel-2-l2a",
                    "item_id": "existing_local_chip",
                    "acquisition_date": existing[0].stem.rsplit("_", 1)[-1],
                    "resolution_m": 10,
                    "local_clear_fraction": None,
                    "path": str(existing[0]),
                }
            )
            continue
        clear, item = choose_best(items, year, quarter)
        if item is None or clear is None or clear < 0:
            continue
        signed = planetary_computer.sign(item)
        arr, profile = read_to_grid(
            signed.assets["visual"].href,
            [1, 2, 3],
            10,
            resampling=Resampling.bilinear,
        )
        path = out_dir / "sentinel2" / f"sentinel2_{period}_{item.datetime.date()}.tif"
        write_array(path, arr, profile, ["red", "green", "blue"])
        evidence.append(
            {
                "evidence_type": "satellite_imagery",
                "provider": "ESA Copernicus via Microsoft Planetary Computer",
                "collection": "sentinel-2-l2a",
                "item_id": item.id,
                "acquisition_date": item.datetime.date().isoformat(),
                "resolution_m": 10,
                "local_clear_fraction": round(clear, 4),
                "path": str(path),
            }
        )


def fetch_naip(catalog, out_dir, evidence):
    items = list(
        catalog.search(
            collections=["naip"], bbox=list(CORE_BBOX_WGS84), max_items=500
        ).items()
    )
    by_year = defaultdict(list)
    for item in items:
        by_year[int(item.properties["naip:year"])].append(item)

    _, width, height, transform = target_grid(CORE_BBOX_WGS84, 1.0)
    for year, year_items in sorted(by_year.items()):
        date_label = sorted({i.datetime.date().isoformat() for i in year_items})[0]
        path = out_dir / "naip" / f"naip_{year}_{date_label}_1m.tif"
        if path.exists():
            evidence.append(
                {
                    "evidence_type": "aerial_imagery",
                    "provider": "USDA NAIP via Microsoft Planetary Computer",
                    "collection": "naip",
                    "item_id": "|".join(sorted(i.id for i in year_items)),
                    "acquisition_date": date_label,
                    "resolution_m": 1.0,
                    "local_clear_fraction": 1.0,
                    "path": str(path),
                }
            )
            continue
        mosaic = np.zeros((4, height, width), dtype=np.uint8)
        covered = np.zeros((height, width), dtype=bool)
        item_ids = []
        acquisition_dates = []
        for item in year_items:
            signed = planetary_computer.sign(item)
            arr, profile = read_to_grid(
                signed.assets["image"].href,
                [1, 2, 3, 4],
                1.0,
                resampling=Resampling.bilinear,
            )
            valid = ~np.ma.getmaskarray(arr).all(axis=0)
            data = arr.filled(0).astype(np.uint8)
            mosaic[:, valid & ~covered] = data[:, valid & ~covered]
            covered |= valid
            item_ids.append(item.id)
            acquisition_dates.append(item.datetime.date().isoformat())
        profile.update(
            crs=AOI_CRS,
            transform=transform,
            width=width,
            height=height,
            count=4,
            dtype="uint8",
        )
        date_label = sorted(set(acquisition_dates))[0]
        write_array(path, mosaic, profile, ["red", "green", "blue", "nir"])
        evidence.append(
            {
                "evidence_type": "aerial_imagery",
                "provider": "USDA NAIP via Microsoft Planetary Computer",
                "collection": "naip",
                "item_id": "|".join(sorted(item_ids)),
                "acquisition_date": date_label,
                "resolution_m": 1.0,
                "local_clear_fraction": 1.0,
                "path": str(path),
            }
        )


def fetch_cdl(catalog, out_dir, evidence):
    items = list(
        catalog.search(
            collections=["usda-cdl"], bbox=list(CORE_BBOX_WGS84), max_items=500
        ).items()
    )
    for year in (2008, 2009, 2015, 2021):
        match = next((i for i in items if i.id.startswith(f"cropland_{year}_")), None)
        if not match:
            continue
        signed = planetary_computer.sign(match)
        arr, profile = read_to_grid(
            signed.assets["cropland"].href,
            [1],
            30,
            resampling=Resampling.nearest,
        )
        path = out_dir / "cdl" / f"cdl_{year}_30m.tif"
        write_array(path, arr, profile, ["cropland_class"])
        evidence.append(
            {
                "evidence_type": "land_cover",
                "provider": "USDA NASS via Microsoft Planetary Computer",
                "collection": "usda-cdl",
                "item_id": match.id,
                "acquisition_date": str(year),
                "resolution_m": 30,
                "local_clear_fraction": None,
                "path": str(path),
            }
        )


def fetch_landsat(catalog, out_dir, evidence):
    items = list(
        catalog.search(
            collections=["landsat-c2-l2"],
            bbox=list(CORE_BBOX_WGS84),
            datetime="2005-01-01/2016-01-01",
            query={"eo:cloud_cover": {"lt": 35}},
            max_items=2000,
        ).items()
    )
    for year in range(2005, 2016):
        candidates = [
            i for i in items if i.datetime.year == year and 5 <= i.datetime.month <= 10
        ]
        candidates.sort(key=lambda i: i.properties.get("eo:cloud_cover", 100))
        if not candidates:
            continue
        item = candidates[0]
        path = out_dir / "landsat" / f"landsat_{year}_{item.datetime.date()}_30m.tif"
        if not path.exists():
            signed = planetary_computer.sign(item)
            channels = []
            profile = None
            for asset_name in ("red", "green", "blue"):
                band, profile = read_to_grid(
                    signed.assets[asset_name].href,
                    [1],
                    30,
                    resampling=Resampling.bilinear,
                )
                reflectance = band.filled(0).astype("float32") * 0.0000275 - 0.2
                channels.append(np.clip(reflectance / 0.30 * 255, 0, 255).astype("uint8")[0])
            arr = np.stack(channels)
            profile.update(dtype="uint8", count=3)
            write_array(path, arr, profile, ["red", "green", "blue"])
        evidence.append(
            {
                "evidence_type": "satellite_imagery",
                "provider": "USGS Landsat via Microsoft Planetary Computer",
                "collection": "landsat-c2-l2",
                "item_id": item.id,
                "acquisition_date": item.datetime.date().isoformat(),
                "resolution_m": 30,
                "local_clear_fraction": None,
                "path": str(path),
            }
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/aurora_land_use_change/raw/imagery"),
    )
    args = parser.parse_args()
    catalog = Client.open(CATALOG_URL)
    evidence = []
    fetch_naip(catalog, args.output, evidence)
    fetch_sentinel(catalog, args.output, evidence)
    fetch_cdl(catalog, args.output, evidence)
    fetch_landsat(catalog, args.output, evidence)
    manifest = pd.DataFrame(evidence).sort_values(["collection", "acquisition_date"])
    manifest_path = args.output / "imagery_manifest.csv"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(manifest_path, index=False)
    metadata = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "catalog": CATALOG_URL,
        "bbox_wgs84": CORE_BBOX_WGS84,
        "analysis_crs": AOI_CRS,
        "notes": "Sentinel scenes selected by local SCL clear fraction; chips are analysis subsets.",
    }
    (args.output / "manifest_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )
    print(manifest.to_string(index=False))


if __name__ == "__main__":
    main()
