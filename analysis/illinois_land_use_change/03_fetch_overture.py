#!/usr/bin/env python3
"""Download one current Overture Buildings extract per shared query zone."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd


ROOT = Path(__file__).resolve().parents[2]
ZONES = ROOT / "data/illinois_land_use_change/inventory/query_zones.geojson"
OUT = ROOT / "data/illinois_land_use_change/raw/overture"
RELEASE = "2026-08-19.0"


def main() -> None:
    zones = gpd.read_file(ZONES)
    OUT.mkdir(parents=True, exist_ok=True)
    expected_names = {f"{zone_id}_buildings.parquet" for zone_id in zones["query_zone_id"]}
    for existing in OUT.glob("zone_*_buildings.parquet"):
        if existing.name not in expected_names:
            existing.unlink()
            existing.with_suffix(existing.suffix + ".state").unlink(missing_ok=True)
    results = []
    for zone in zones.itertuples():
        destination = OUT / f"{zone.query_zone_id}_buildings.parquet"
        command = [
            str(ROOT / ".venv/bin/overturemaps"),
            "download",
            "--bbox",
            zone.bbox_wgs84,
            "-f",
            "geoparquet",
            "-o",
            str(destination),
            "-t",
            "building",
            "-r",
            RELEASE,
        ]
        state_path = destination.with_suffix(destination.suffix + ".state")
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        state_bbox = state.get("bbox") or {}
        state_bbox_string = (
            f'{state_bbox.get("xmin"):.7f},{state_bbox.get("ymin"):.7f},'
            f'{state_bbox.get("xmax"):.7f},{state_bbox.get("ymax"):.7f}'
            if all(key in state_bbox for key in ("xmin", "ymin", "xmax", "ymax"))
            else None
        )
        if destination.exists() and (
            state_bbox_string != zone.bbox_wgs84 or state.get("last_release") != RELEASE
        ):
            destination.unlink()
            state_path.unlink(missing_ok=True)
        if not destination.exists():
            subprocess.run(command, check=True)
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["output"] = str(destination.relative_to(ROOT))
            state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        buildings = gpd.read_parquet(destination)
        results.append(
            {
                "query_zone_id": zone.query_zone_id,
                "release": RELEASE,
                "building_count": int(len(buildings)),
                "path": str(destination.relative_to(ROOT)),
                "bbox_wgs84": zone.bbox_wgs84,
            }
        )
        print(zone.query_zone_id, len(buildings))

    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release": RELEASE,
        "theme": "buildings",
        "type": "building",
        "zones": results,
    }
    (OUT / "download_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
