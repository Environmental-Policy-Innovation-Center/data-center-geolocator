# Harmonized Data Center Reference Dataset

The directory also contains
`illinois-data-center-regulatory-inventory.xlsx`, a screening workbook derived
from Illinois EPA Document Explorer records. Its pipeline and reproducibility
notes are documented in `pdf-scraping/README.md`.

This directory contains generated outputs from `scripts/harmonize_reference_datasets.py`. The script combines the raw reference datasets in `raw-data/data-center-locations` into auditable harmonized site groups.

## Outputs

| File | Grain | Description |
| --- | --- | --- |
| `harmonized-data-center-reference-sites.csv` | One row per harmonized site group | Canonical site table with source summary, status summary, representative coordinates, built/pipeline flags, and match notes |
| `harmonized-data-center-reference-members.csv` | One row per original source record | Source-member table showing which raw records belong to each `site_group_id` |
| `harmonized-data-center-reference-candidate-matches.csv` | One row per cross-source candidate pair within 1 km | Candidate match audit table, including distance, name score, rule, and whether the pair was grouped |
| `harmonized-data-center-reference-sites.geojson` | One point per harmonized site group with valid coordinates | Mapping-friendly point export of the harmonized site table |

Illinois-only extracts are also provided:

| File | Grain | Description |
| --- | --- | --- |
| `harmonized-data-center-reference-sites-illinois.csv` | One row per Illinois harmonized site group | Illinois subset of the harmonized site table, filtered to `state == IL` |
| `harmonized-data-center-reference-members-illinois.csv` | One row per source record attached to an Illinois site group | Source-member audit table for Illinois site groups |
| `harmonized-data-center-reference-candidate-matches-illinois.csv` | One row per Illinois cross-source candidate pair | Candidate match audit table where both records are attached to Illinois site groups |
| `harmonized-data-center-reference-sites-illinois.geojson` | One point per Illinois harmonized site group with valid coordinates | Mapping-friendly Illinois point export |

## Matching Approach

The harmonization uses spatial proximity plus name/operator evidence. Candidate pairs are generated across source families within 1 km using projected distances in `EPSG:5070`.

Records are grouped when they meet one of these rules:

1. `spatial_100m`: records are within 100 m. FracTracker non-operating records still need name/operator support before being grouped with built-source records.
2. `name_supported_500m`: records are within 500 m and have compatible name/operator tokens.
3. `strong_name_supported_1km`: records are within 1 km and have stronger name/operator compatibility.

The matcher also blocks two common over-grouping cases:

1. Facility-code conflicts, such as `ORD-01` versus `ORD-02`, are kept separate.
2. Low-specificity NAICS names, such as generic company names without site identifiers, do not bridge nearby sites beyond 100 m.

## Source Interpretation

PNNL is treated as the strongest geometry source because it includes points, building polygons, campus polygons, and footprint areas. FracTracker is treated as the strongest project-status and pipeline source. NAICS is treated as a supplemental registry signal, not a complete data center inventory.

`is_currently_built` is true when a group contains a PNNL record, a NAICS record, or a FracTracker record with `status == Operating`. FracTracker-only proposed, suspended, cancelled, or under-construction records remain in the dataset, but are marked as not currently built.

## Caveats

The harmonized site table is intended as a reference layer, not a final truth set. Dense data center markets may still require manual review. The candidate match table is included so ambiguous nearby records can be inspected without rerunning the script.

Two FracTracker records currently have invalid positive longitudes and are retained in the CSV outputs with `coordinate_valid == False`. They are excluded from the GeoJSON export so they do not plot in the wrong location.
