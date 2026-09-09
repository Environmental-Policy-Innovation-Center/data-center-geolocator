#!/usr/bin/env python3
"""Create shared spatial query zones around preliminary analysis units."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd


ROOT = Path(__file__).resolve().parents[2]
UNITS = ROOT / "data/illinois_land_use_change/inventory/analysis_units_preliminary.geojson"
OUT = ROOT / "data/illinois_land_use_change/inventory"
ANALYSIS_CRS = 26916
BUFFER_M = 500


def main() -> None:
    units = gpd.read_file(UNITS).to_crs(ANALYSIS_CRS)
    buffered_union = units.geometry.buffer(BUFFER_M).union_all()
    parts = list(buffered_union.geoms) if buffered_union.geom_type == "MultiPolygon" else [buffered_union]

    zones = []
    assignments = []
    for part in parts:
        member_mask = units.geometry.intersects(part)
        members = sorted(units.loc[member_mask, "analysis_unit_id"].tolist())
        center = part.centroid
        zones.append({"members": members, "member_count": len(members), "sort_x": center.x, "sort_y": center.y, "geometry": part})

    zones.sort(key=lambda item: (-item["sort_y"], item["sort_x"]))
    rows = []
    for index, zone in enumerate(zones, 1):
        zone_id = f"zone_{index:02d}"
        wgs_geometry = gpd.GeoSeries([zone["geometry"]], crs=ANALYSIS_CRS).to_crs(4326).iloc[0]
        xmin, ymin, xmax, ymax = wgs_geometry.bounds
        rows.append(
            {
                "query_zone_id": zone_id,
                "analysis_unit_count": zone["member_count"],
                "analysis_unit_ids": "|".join(zone["members"]),
                "bbox_wgs84": f"{xmin:.7f},{ymin:.7f},{xmax:.7f},{ymax:.7f}",
                "buffer_m": BUFFER_M,
                "geometry": wgs_geometry,
            }
        )
        assignments.extend(
            {"analysis_unit_id": member, "query_zone_id": zone_id} for member in zone["members"]
        )

    output = gpd.GeoDataFrame(rows, geometry="geometry", crs=4326)
    output.to_file(OUT / "query_zones.geojson", driver="GeoJSON")
    (OUT / "query_zone_assignments.json").write_text(
        json.dumps(sorted(assignments, key=lambda item: item["analysis_unit_id"]), indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Created {len(output)} query zones for {len(units)} analysis units")


if __name__ == "__main__":
    main()
