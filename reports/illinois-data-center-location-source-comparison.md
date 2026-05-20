# Illinois Data Center Location Source Comparison

## Purpose

This note compares the raw data center location sources stored in `raw-data/data-center-locations`, restricted to Illinois. The goal is to understand what each source contains, where the sources spatially overlap, and how each source is best used in downstream data center geolocation work.

## Sources Reviewed

Three source families are present in the raw data directory:

| Source | Raw file | Illinois records | Main character |
| --- | ---: | ---: | --- |
| FracTracker | `raw-data/data-center-locations/FracTracker/FracTracker_01_29_26.csv` | 31 | Human-curated inventory with project status, advocacy context, source links, and development details |
| PNNL / IM3 Atlas | `raw-data/data-center-locations/PNNL/PNNL_2026.02.09.gpkg` | 50 | OpenStreetMap-derived geospatial atlas with points, building polygons, campus polygons, counties, operators, and footprint area |
| NAICS | `raw-data/data-center-locations/NAICS/NAICS_518210_05_07_26.csv` | 17 | Registry-style point dataset for facilities tagged with NAICS `518210` |

FracTracker and PNNL include state fields, so Illinois records were selected using `state == IL` and `state_abb == IL`, respectively. NAICS has no state or county field, so Illinois records were inferred spatially with a rough Illinois bounding box: longitude `-91.6` to `-87.0`, latitude `36.9` to `42.6`.

## Schema Comparison

FracTracker is the richest descriptive source. Its Illinois records include facility name, address, city, state, ZIP, county, latitude, longitude, project status, location confidence, size rank, operator, MW capacity where available, square footage, acreage, expected online date, power/cooling fields, community pushback, advocacy information, petition/community links, media/source URLs, and created/updated dates.

PNNL has a compact geospatial schema repeated across `point`, `building`, and `campus` layers. Key fields are `id`, `state`, `state_abb`, `county`, `operator`, `ref`, `name`, `sqft`, `lon`, `lat`, `type`, and `geometry`. In Illinois, PNNL contains 42 building records, 6 point records, and 2 campus records. It is the only source among the three with actual polygon geometries and footprint area.

NAICS is much thinner. It contains `ejam_uniq_id`, `lat`, `lon`, `REGISTRY_ID`, `PRIMARY_NAME`, `NAICS`, `valid`, and `invalid_msg`. All 17 Illinois candidate records are marked valid, and `invalid_msg` is empty. The source has no address, state, county, project status, footprint, operator normalization, or source URL fields.

## Illinois Source Profiles

FracTracker's Illinois subset is mostly a development pipeline and public-interest dataset. The 31 records break down as follows:

| Status | Count |
| --- | ---: |
| Proposed | 15 |
| Approved/Permitted/Under construction | 8 |
| Operating | 4 |
| Cancelled | 3 |
| Suspended | 1 |

FracTracker's Illinois records are concentrated around Chicagoland and nearby development zones. Elk Grove Village has the largest number of records, with 8. Aurora, Northlake, and Yorkville each have 2. Other records appear in Chicago, DeKalb, Effingham, Joliet, Lisle, Lombard, Minooka, Morris, Naperville, New Lenox, Troy, and several township-level locations.

PNNL's Illinois subset is more clearly an existing-facility and footprint layer. County concentration is strong:

| County | PNNL records |
| --- | ---: |
| Cook County | 29 |
| DuPage County | 14 |
| DeKalb County | 4 |
| Champaign County | 1 |
| Lake County | 1 |
| Madison County | 1 |

PNNL has complete Illinois coverage for location and administrative fields. In the Illinois subset, `sqft` is present for 44 of 50 records, `name` for 43, `operator` for 41, and `ref` for 28. The median Illinois PNNL building footprint is about 117,873 square feet. The two campus polygons are much larger, with a median area of about 7.45 million square feet.

The NAICS Illinois candidates include recognizable data center or data-center-adjacent records such as `EQUINIX LLC`, `STREAM DATA CENTERS`, `T5@CHICAGO II LP`, `EDGED CHICAGO LLC`, `CYRUSONE CHI6 FACILITY`, `QUALITY TECHNOLOGY SERVICES LLC`, `ALTEREDSCALE`, and `ENSONO DATA CENTER`. They also include broader enterprise records such as `DEERE & CO`, `ADP`, `ALLSTATE DATA CENTER`, and `THE NORTHERN TRUST CO`.

## Spatial Overlap

Spatial overlap was measured by converting source coordinates to point geometries and running nearest-neighbor comparisons in `EPSG:5070`. For PNNL buildings and campuses, the provided centroid latitude and longitude fields were used for the point comparison. These are proximity matches, not confirmed entity matches.

Approximate Illinois row-level overlap counts:

| Pair | Within 100 m | Within 500 m | Within 1 km | Within 5 km | Within 10 km |
| --- | ---: | ---: | ---: | ---: | ---: |
| FracTracker to PNNL | 6 | 6 | 8 | 16 | 18 |
| FracTracker to NAICS | 2 | 8 | 9 | 15 | 16 |
| NAICS to PNNL | 5 | 9 | 9 | 14 | 14 |

Median nearest-neighbor distances:

| Pair | Median nearest distance |
| --- | ---: |
| FracTracker to PNNL | 3.217 km |
| FracTracker to NAICS | 8.058 km |
| NAICS to PNNL | 0.462 km |

The tightest overlap is between NAICS and PNNL. This is expected because both sources are more oriented toward existing or registry-visible facilities. FracTracker overlaps strongly around established Chicago-area data center clusters, but it also includes proposed, suspended, cancelled, and under-construction projects that do not necessarily appear in OSM or registry-derived data.

## Strongest Three-Way Illinois Matches

Five FracTracker Illinois records are within 1 km of both a PNNL record and a NAICS record:

| FracTracker record | PNNL nearest record | PNNL distance | NAICS nearest record | NAICS distance |
| --- | --- | ---: | --- | ---: |
| Stream Data Center: Chicago 1 | Stream Chicago I | 55.6 m | STREAM DATA CENTERS | 58.5 m |
| Stream Data Center: Chicago 2 | Stream Chicago II | 12.2 m | EQUINIX LLC | 316.6 m |
| T5 Data Center | T5 Chicago II | 12.5 m | T5@CHICAGO II LP | 16.2 m |
| ORD-01 Data Center | Aligned Data Center - Chicago ORD-01 | 19.8 m | ASCENT LLC | 474.5 m |
| ORD-02 Data Center | Aligned Data Center - Chicago ORD-02 | 35.4 m | ASCENT LLC | 549.6 m |

These represent the highest-confidence overlap zones because all three sources place a data center-related record in roughly the same location.

## Additional FracTracker to PNNL Matches Within 1 km

| FracTracker record | PNNL nearest record | PNNL layer | County | Distance |
| --- | --- | --- | --- | ---: |
| US Signal Data Center | Lincoln Rackhouse | building | DuPage | 8.4 m |
| Stream Data Center: Chicago 2 | Stream Chicago II | building | Cook | 12.2 m |
| T5 Data Center | T5 Chicago II | building | Cook | 12.5 m |
| ORD-01 Data Center | Aligned Data Center - Chicago ORD-01 | building | Cook | 19.8 m |
| ORD-02 Data Center | Aligned Data Center - Chicago ORD-02 | building | Cook | 35.4 m |
| Stream Data Center: Chicago 1 | Stream Chicago I | building | Cook | 55.6 m |
| Karis Critical Data Center | unnamed PNNL building | building | DeKalb | 539.3 m |
| HydraVault Data Center | Centersquare Chicago Data Center - ORD1 | point | Cook | 990.2 m |

## Interpretation

The three sources are complementary rather than interchangeable. PNNL is the strongest Illinois source for physical footprint and existing-site geometry, especially in Cook and DuPage counties. FracTracker is the strongest source for project pipeline, status, public controversy, and qualitative source trails. NAICS is useful as a corroborating registry signal around existing sites, but its sparse schema and broader `518210` inclusion mean it should not be treated as a clean data center inventory on its own.

Spatial overlap is strongest in the existing Chicago-area market. The most reliable merged candidates are those where FracTracker, PNNL, and NAICS all fall within roughly 1 km and names/operators are plausibly related. However, distance alone is not enough for final deduplication. Multiple records may represent different buildings within a campus, an operator versus a tenant, a registry entity versus a branded facility, or a proposed project near an existing data center cluster.

## Recommended Use

Use PNNL as the base geometry layer for existing Illinois data center footprints and campus/building polygons. Use FracTracker to add project status, development pipeline, capacity/size estimates, public opposition, and source citations. Use NAICS as a supplemental corroboration layer for established facilities, especially when it falls within 500 m to 1 km of a PNNL or FracTracker record.

For a merged Illinois data center location dataset, a practical first pass would be:

1. Start from PNNL building and campus geometries.
2. Attach FracTracker records within 500 m or 1 km where names/operators and city/county context agree.
3. Attach NAICS records as secondary evidence, not as the primary identity record.
4. Keep proposed/cancelled/suspended FracTracker records even when they do not match PNNL or NAICS, because they represent pipeline and advocacy-relevant locations that existing-facility sources may miss.
5. Review Chicago-area clusters manually, since several records are close together and may represent separate buildings, campuses, operators, tenants, or registry entities within the same market.
