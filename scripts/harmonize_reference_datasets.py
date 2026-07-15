#!/usr/bin/env python3
"""Build a harmonized data center reference dataset from raw sources."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "raw-data" / "data-center-locations"
OUT_DIR = REPO_ROOT / "processed-data"

FRAC_PATH = RAW_DIR / "FracTracker" / "FracTracker_01_29_26.csv"
NAICS_PATH = RAW_DIR / "NAICS" / "NAICS_518210_05_07_26.csv"
PNNL_LAYERS = {
    "point": RAW_DIR / "PNNL" / "PNNL_2026.02.09_point.geojson",
    "building": RAW_DIR / "PNNL" / "PNNL_2026.02.09_building.geojson",
    "campus": RAW_DIR / "PNNL" / "PNNL_2026.02.09_campus.geojson",
}

COMMON_TOKENS = {
    "a",
    "and",
    "center",
    "centers",
    "centre",
    "company",
    "co",
    "corp",
    "corporation",
    "c",
    "d",
    "data",
    "datacenter",
    "datacenters",
    "dc",
    "dba",
    "facility",
    "facilities",
    "inc",
    "incorporated",
    "llc",
    "lp",
    "ltd",
    "na",
    "of",
    "park",
    "partners",
    "property",
    "properties",
    "realty",
    "site",
    "the",
}


def clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def clean_number(value: object) -> float | None:
    text = clean_text(value)
    if not text:
        return None
    text = re.sub(r"[$,]", "", text)
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def normalize_name(value: object) -> str:
    text = clean_text(value).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = [token for token in text.split() if token and token not in COMMON_TOKENS]
    return " ".join(tokens)


def token_set(value: object) -> set[str]:
    normalized = normalize_name(value)
    return set(normalized.split()) if normalized else set()


def facility_codes(value: object) -> set[str]:
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    roman = {
        "i": "1",
        "ii": "2",
        "iii": "3",
        "iv": "4",
        "v": "5",
        "vi": "6",
        "vii": "7",
        "viii": "8",
        "ix": "9",
        "x": "10",
    }
    codes: set[str] = set()
    tokens = text.split()
    for idx, token in enumerate(tokens):
        compact = re.fullmatch(r"([a-z]{2,})(\d{1,3})", token)
        if compact:
            codes.add(f"{compact.group(1)}{int(compact.group(2))}")
        if idx + 1 >= len(tokens):
            continue
        prefix = token
        suffix = tokens[idx + 1]
        if prefix in COMMON_TOKENS or len(prefix) < 2:
            continue
        number = None
        if re.fullmatch(r"\d{1,3}", suffix):
            number = str(int(suffix))
        elif suffix in roman:
            number = roman[suffix]
        if number:
            codes.add(f"{prefix}{number}")
    return codes


def facility_code_conflict(left: object, right: object) -> bool:
    left_codes = facility_codes(left)
    right_codes = facility_codes(right)
    return bool(left_codes and right_codes and left_codes.isdisjoint(right_codes))


def low_specificity_bridge(left: pd.Series, right: pd.Series, distance_m: float) -> bool:
    if distance_m <= 100:
        return False
    if left["source"] != "NAICS" and right["source"] != "NAICS":
        return False
    left_tokens = token_set(left["source_name"])
    right_tokens = token_set(right["source_name"])
    left_codes = facility_codes(left["source_name"])
    right_codes = facility_codes(right["source_name"])
    if left["source"] == "NAICS" and len(left_tokens) <= 2 and not left_codes:
        return True
    if right["source"] == "NAICS" and len(right_tokens) <= 2 and not right_codes:
        return True
    return False


def name_score(left: object, right: object) -> float:
    left_tokens = token_set(left)
    right_tokens = token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    union = left_tokens | right_tokens
    score = len(intersection) / len(union)
    left_norm = " ".join(sorted(left_tokens))
    right_norm = " ".join(sorted(right_tokens))
    if left_norm and right_norm and (left_norm in right_norm or right_norm in left_norm):
        score = max(score, min(len(intersection), len(left_tokens), len(right_tokens)) / max(1, min(len(left_tokens), len(right_tokens))))
    return score


def coordinate_valid(lat: object, lon: object) -> bool:
    try:
        lat_float = float(lat)
        lon_float = float(lon)
    except (TypeError, ValueError):
        return False
    return 18 <= lat_float <= 72 and -180 <= lon_float <= -60


class DisjointSet:
    def __init__(self, values: list[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def source_currently_built(source: str, status: str) -> bool:
    if source in {"PNNL", "NAICS"}:
        return True
    return status.strip().lower() == "operating"


def load_frac() -> gpd.GeoDataFrame:
    df = pd.read_csv(FRAC_PATH)
    df["source"] = "FracTracker"
    df["source_layer"] = ""
    df["source_file"] = str(FRAC_PATH.relative_to(REPO_ROOT))
    df["source_record_id"] = df.index.map(lambda idx: f"frac_row_{idx}")
    df["record_uid"] = "FracTracker:" + df["source_record_id"]
    df["source_name"] = df["facility_name"].map(clean_text)
    df["operator"] = df["operator_name"].map(clean_text)
    df["status"] = df["status"].map(clean_text)
    df["source_latitude"] = pd.to_numeric(df["lat"], errors="coerce")
    df["source_longitude"] = pd.to_numeric(df["long"], errors="coerce")
    df["coordinate_valid"] = [coordinate_valid(lat, lon) for lat, lon in zip(df["source_latitude"], df["source_longitude"])]
    df["geometry_type"] = "Point"
    df["facility_size_sqft"] = df["facility_size_sqft"].map(clean_number)
    df["campus_area_sqft"] = None
    df["mw"] = df["mw"].map(clean_text)
    df["canonical_state_source"] = df["state"].map(clean_text)
    df["canonical_county_source"] = df["county"].map(clean_text)
    df["city"] = df["city"].map(clean_text)
    df["address"] = df["address"].map(clean_text)
    df["zip"] = df["zip"].map(clean_text)
    df["location_confidence"] = df["location_confidence"].map(clean_text)
    df["source_detail_json"] = df.apply(
        lambda row: json.dumps(
            {
                "sizerank": clean_text(row.get("sizerank")),
                "information_source": clean_text(row.get("information_source")),
                "info_source_1": clean_text(row.get("info_source_1")),
                "date_created": clean_text(row.get("date_created")),
                "date_updated": clean_text(row.get("date_updated")),
                "community_pushback": clean_text(row.get("community_pushback")),
            },
            sort_keys=True,
        ),
        axis=1,
    )
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["source_longitude"], df["source_latitude"]), crs="EPSG:4326")
    return standardize_columns(gdf)


def load_naics() -> gpd.GeoDataFrame:
    df = pd.read_csv(NAICS_PATH)
    df["source"] = "NAICS"
    df["source_layer"] = ""
    df["source_file"] = str(NAICS_PATH.relative_to(REPO_ROOT))
    df["source_record_id"] = df["ejam_uniq_id"].map(lambda value: f"naics_{value}")
    df["record_uid"] = "NAICS:" + df["source_record_id"]
    df["source_name"] = df["PRIMARY_NAME"].map(clean_text)
    df["operator"] = ""
    df["status"] = "Operating/inferred"
    df["source_latitude"] = pd.to_numeric(df["lat"], errors="coerce")
    df["source_longitude"] = pd.to_numeric(df["lon"], errors="coerce")
    df["coordinate_valid"] = [coordinate_valid(lat, lon) for lat, lon in zip(df["source_latitude"], df["source_longitude"])]
    df["geometry_type"] = "Point"
    df["facility_size_sqft"] = None
    df["campus_area_sqft"] = None
    df["mw"] = ""
    df["canonical_state_source"] = ""
    df["canonical_county_source"] = ""
    df["city"] = ""
    df["address"] = ""
    df["zip"] = ""
    df["location_confidence"] = ""
    df["source_detail_json"] = df.apply(
        lambda row: json.dumps(
            {
                "registry_id": clean_text(row.get("REGISTRY_ID")),
                "naics": clean_text(row.get("NAICS")),
                "valid": bool(row.get("valid")),
            },
            sort_keys=True,
        ),
        axis=1,
    )
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["source_longitude"], df["source_latitude"]), crs="EPSG:4326")
    return standardize_columns(gdf)


def load_pnnl() -> gpd.GeoDataFrame:
    frames = []
    for layer, path in PNNL_LAYERS.items():
        gdf = gpd.read_file(path)
        gdf["source"] = "PNNL"
        gdf["source_layer"] = layer
        gdf["source_file"] = str(path.relative_to(REPO_ROOT))
        gdf["source_record_id"] = layer + "_" + gdf["id"].astype(str)
        gdf["record_uid"] = "PNNL:" + gdf["source_record_id"]
        gdf["source_name"] = gdf["name"].map(clean_text)
        gdf["operator"] = gdf["operator"].map(clean_text)
        gdf["status"] = "Operating/inferred"
        gdf["source_latitude"] = pd.to_numeric(gdf["lat"], errors="coerce")
        gdf["source_longitude"] = pd.to_numeric(gdf["lon"], errors="coerce")
        gdf["coordinate_valid"] = [coordinate_valid(lat, lon) for lat, lon in zip(gdf["source_latitude"], gdf["source_longitude"])]
        gdf["geometry_type"] = gdf.geometry.geom_type
        sqft = gdf["sqft"].map(clean_number)
        gdf["facility_size_sqft"] = sqft if layer == "building" else None
        gdf["campus_area_sqft"] = sqft if layer == "campus" else None
        gdf["mw"] = ""
        gdf["canonical_state_source"] = gdf["state_abb"].map(clean_text)
        gdf["canonical_county_source"] = gdf["county"].map(clean_text)
        gdf["city"] = ""
        gdf["address"] = ""
        gdf["zip"] = ""
        gdf["location_confidence"] = ""
        gdf["source_detail_json"] = gdf.apply(
            lambda row: json.dumps(
                {
                    "osm_id": clean_text(row.get("id")),
                    "ref": clean_text(row.get("ref")),
                    "state": clean_text(row.get("state")),
                    "county_id": clean_text(row.get("county_id")),
                    "sqft": clean_text(row.get("sqft")),
                },
                sort_keys=True,
            ),
            axis=1,
        )
        frames.append(standardize_columns(gdf))
    return pd.concat(frames, ignore_index=True)


def standardize_columns(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    columns = [
        "record_uid",
        "source",
        "source_layer",
        "source_file",
        "source_record_id",
        "source_name",
        "operator",
        "status",
        "source_latitude",
        "source_longitude",
        "coordinate_valid",
        "geometry_type",
        "facility_size_sqft",
        "campus_area_sqft",
        "mw",
        "canonical_state_source",
        "canonical_county_source",
        "city",
        "address",
        "zip",
        "location_confidence",
        "source_detail_json",
        "geometry",
    ]
    out = gdf[columns].copy()
    out["normalized_name"] = out["source_name"].map(normalize_name)
    out["normalized_operator"] = out["operator"].map(normalize_name)
    out["source_is_currently_built"] = [
        source_currently_built(source, status) for source, status in zip(out["source"], out["status"])
    ]
    return gpd.GeoDataFrame(out, geometry="geometry", crs=gdf.crs)


def representative_points(records: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    point_df = records.copy()
    point_df["geometry"] = gpd.points_from_xy(point_df["source_longitude"], point_df["source_latitude"])
    return gpd.GeoDataFrame(point_df, geometry="geometry", crs="EPSG:4326")


def candidate_rule(left: pd.Series, right: pd.Series, distance_m: float) -> tuple[bool, str, float]:
    score = max(
        name_score(left["source_name"], right["source_name"]),
        name_score(left["operator"], right["operator"]),
        name_score(left["operator"], right["source_name"]),
        name_score(left["source_name"], right["operator"]),
    )
    involves_frac = left["source"] == "FracTracker" or right["source"] == "FracTracker"
    frac_non_operating = False
    if left["source"] == "FracTracker" and left["status"].strip().lower() != "operating":
        frac_non_operating = True
    if right["source"] == "FracTracker" and right["status"].strip().lower() != "operating":
        frac_non_operating = True

    if facility_code_conflict(left["source_name"], right["source_name"]):
        return False, "candidate_only_code_conflict", score
    if low_specificity_bridge(left, right, distance_m):
        return False, "candidate_only_low_specificity", score
    if distance_m <= 100 and not (involves_frac and frac_non_operating and score < 0.30):
        return True, "spatial_100m", score
    if distance_m <= 500 and score >= 0.30:
        return True, "name_supported_500m", score
    if distance_m <= 1000 and score >= 0.45:
        return True, "strong_name_supported_1km", score
    return False, "candidate_only", score


def build_candidates(records: gpd.GeoDataFrame) -> pd.DataFrame:
    valid = records[records["coordinate_valid"]].copy()
    points = representative_points(valid).to_crs("EPSG:5070")
    rows = []
    for left_source in ["FracTracker", "NAICS", "PNNL"]:
        for right_source in ["FracTracker", "NAICS", "PNNL"]:
            if left_source >= right_source:
                continue
            left = points[points["source"] == left_source]
            right = points[points["source"] == right_source]
            if left.empty or right.empty:
                continue
            buffered = left.copy()
            buffered["geometry"] = buffered.geometry.buffer(1000)
            joined = gpd.sjoin(buffered, right, how="inner", predicate="intersects", lsuffix="left", rsuffix="right")
            for left_index, row in joined.iterrows():
                right_index = row["index_right"]
                left_record = points.loc[left_index]
                right_record = points.loc[right_index]
                distance_m = float(left_record.geometry.distance(right_record.geometry))
                should_group, rule, score = candidate_rule(left_record, right_record, distance_m)
                rows.append(
                    {
                        "left_record_uid": left_record["record_uid"],
                        "right_record_uid": right_record["record_uid"],
                        "left_source": left_record["source"],
                        "right_source": right_record["source"],
                        "left_name": left_record["source_name"],
                        "right_name": right_record["source_name"],
                        "left_status": left_record["status"],
                        "right_status": right_record["status"],
                        "distance_m": round(distance_m, 3),
                        "name_score": round(score, 3),
                        "match_rule": rule,
                        "is_grouped_match": should_group,
                    }
                )
    candidates = pd.DataFrame(rows).drop_duplicates(subset=["left_record_uid", "right_record_uid"])
    return candidates.sort_values(["is_grouped_match", "distance_m"], ascending=[False, True]).reset_index(drop=True)


def assign_groups(records: gpd.GeoDataFrame, candidates: pd.DataFrame) -> pd.Series:
    dsu = DisjointSet(records["record_uid"].tolist())
    for _, row in candidates[candidates["is_grouped_match"]].iterrows():
        dsu.union(row["left_record_uid"], row["right_record_uid"])

    # PNNL duplicates across county boundaries share the same source id after layer prefix.
    for _, same_id in records[records["source"] == "PNNL"].groupby("source_record_id"):
        ids = same_id["record_uid"].tolist()
        for record_uid in ids[1:]:
            dsu.union(ids[0], record_uid)

    roots = records["record_uid"].map(dsu.find)
    root_to_id = {root: f"site_{idx + 1:05d}" for idx, root in enumerate(sorted(roots.unique()))}
    return roots.map(root_to_id)


def choose_primary(group: pd.DataFrame) -> pd.Series:
    priority = {
        ("PNNL", "campus"): 0,
        ("PNNL", "building"): 1,
        ("PNNL", "point"): 2,
        ("FracTracker", ""): 3,
        ("NAICS", ""): 4,
    }
    scored = group.copy()
    scored["_priority"] = [
        priority.get((row.source, row.source_layer), 9) for row in scored.itertuples(index=False)
    ]
    scored["_has_name"] = scored["source_name"].astype(bool).map(lambda value: 0 if value else 1)
    return scored.sort_values(["_priority", "_has_name"]).iloc[0]


def first_nonempty(values: list[object]) -> str:
    for value in values:
        text = clean_text(value)
        if text:
            return text
    return ""


def summarize_sites(records: gpd.GeoDataFrame, candidates: pd.DataFrame) -> gpd.GeoDataFrame:
    site_rows = []
    grouped_matches = candidates[candidates["is_grouped_match"]]
    match_notes_by_uid: dict[str, list[str]] = {}
    for _, row in grouped_matches.iterrows():
        note = f"{row.left_record_uid}<->{row.right_record_uid}:{row.match_rule}:{row.distance_m}m"
        match_notes_by_uid.setdefault(row.left_record_uid, []).append(note)
        match_notes_by_uid.setdefault(row.right_record_uid, []).append(note)

    for site_id, group in records.groupby("site_group_id", sort=True):
        primary = choose_primary(group)
        sources = sorted(group["source"].unique())
        frac_statuses = sorted(status for status in group.loc[group["source"] == "FracTracker", "status"].unique() if status)
        names = sorted(name for name in group["source_name"].unique() if name)
        operators = sorted(operator for operator in group["operator"].unique() if operator)
        has_built_source = bool(group["source_is_currently_built"].any())
        has_pipeline_status = any(status.lower() != "operating" for status in frac_statuses)
        match_notes = sorted({note for uid in group["record_uid"] for note in match_notes_by_uid.get(uid, [])})
        if len(sources) > 1:
            confidence = "multi_source"
        elif primary["source"] == "PNNL":
            confidence = "single_source_geometry"
        elif primary["source"] == "FracTracker":
            confidence = "single_source_curated"
        else:
            confidence = "single_source_registry"

        state = first_nonempty(
            [
                primary["canonical_state_source"],
                *group["canonical_state_source"].tolist(),
            ]
        )
        county = first_nonempty(
            [
                primary["canonical_county_source"],
                *group["canonical_county_source"].tolist(),
            ]
        )
        city = first_nonempty([primary["city"], *group["city"].tolist()])
        site_rows.append(
            {
                "site_group_id": site_id,
                "canonical_name": first_nonempty([primary["source_name"], *names]),
                "sources": "|".join(sources),
                "source_count": len(sources),
                "member_count": len(group),
                "primary_source": primary["source"],
                "primary_source_layer": primary["source_layer"],
                "primary_record_uid": primary["record_uid"],
                "status_summary": "|".join(frac_statuses) if frac_statuses else "Operating/inferred",
                "is_currently_built": has_built_source,
                "has_pipeline_status": has_pipeline_status,
                "state": state,
                "county": county,
                "city": city,
                "latitude": primary["source_latitude"],
                "longitude": primary["source_longitude"],
                "coordinate_valid": bool(primary["coordinate_valid"]),
                "geometry_type": primary["geometry_type"],
                "operator_summary": "|".join(operators),
                "name_aliases": "|".join(names),
                "facility_size_sqft": first_nonempty(group["facility_size_sqft"].tolist()),
                "campus_area_sqft": first_nonempty(group["campus_area_sqft"].tolist()),
                "mw_summary": "|".join(sorted(mw for mw in group["mw"].unique() if mw)),
                "reference_confidence": confidence,
                "match_notes": " ; ".join(match_notes),
            }
        )
    sites = pd.DataFrame(site_rows)
    gdf = gpd.GeoDataFrame(
        sites,
        geometry=gpd.points_from_xy(sites["longitude"], sites["latitude"]),
        crs="EPSG:4326",
    )
    return gdf


def write_outputs(records: gpd.GeoDataFrame, candidates: pd.DataFrame, sites: gpd.GeoDataFrame) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    site_csv = OUT_DIR / "harmonized-data-center-reference-sites.csv"
    member_csv = OUT_DIR / "harmonized-data-center-reference-members.csv"
    candidate_csv = OUT_DIR / "harmonized-data-center-reference-candidate-matches.csv"
    site_geojson = OUT_DIR / "harmonized-data-center-reference-sites.geojson"

    sites.drop(columns="geometry").to_csv(site_csv, index=False)
    records.drop(columns="geometry").sort_values(["site_group_id", "source", "source_record_id"]).to_csv(member_csv, index=False)
    candidates.to_csv(candidate_csv, index=False)
    sites[sites["coordinate_valid"]].to_file(site_geojson, driver="GeoJSON")

    print(f"Wrote {len(sites):,} harmonized sites to {site_csv.relative_to(REPO_ROOT)}")
    print(f"Wrote {len(records):,} source members to {member_csv.relative_to(REPO_ROOT)}")
    print(f"Wrote {len(candidates):,} candidate matches to {candidate_csv.relative_to(REPO_ROOT)}")
    print(f"Wrote point GeoJSON to {site_geojson.relative_to(REPO_ROOT)}")


def main() -> None:
    records = pd.concat([load_frac(), load_naics(), load_pnnl()], ignore_index=True)
    records = gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
    candidates = build_candidates(records)
    records["site_group_id"] = assign_groups(records, candidates)
    sites = summarize_sites(records, candidates)
    write_outputs(records, candidates, sites)

    invalid = records[~records["coordinate_valid"]]
    if not invalid.empty:
        print("Coordinate warnings:")
        for _, row in invalid.iterrows():
            print(f"  {row.record_uid}: {row.source_name} ({row.source_latitude}, {row.source_longitude})")


if __name__ == "__main__":
    main()
