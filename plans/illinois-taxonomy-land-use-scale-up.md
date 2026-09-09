# Illinois Data-Center Land-Use Change Scale-Up

## Decision and scope

The Aurora study remains the reference proof of concept. The next production scope is every Illinois record assigned to these visual-taxonomy groups:

- `hyperscale_greenfield_campus`;
- `large_purpose_built_data_center`; and
- `industrial_park_warehouse_style_colo`.

The taxonomy contains 27 seed records: 2 hyperscale, 6 large purpose-built, and 19 warehouse-style colocation records. The first documented entity-resolution pass consolidates the seed records and related reference records into 24 analysis units, of which the Aurora CyrusOne CHI1-CHI2 unit is complete. This count remains provisional until parcel- and imagery-level review confirms every campus boundary.

The unit of analysis will be the physical campus or independently developed parcel, not the source record. Every taxonomy record will remain traceable through a source crosswalk, including records merged into a campus.

## Outputs

The statewide deliverable will preserve the Aurora schema and add scale-management fields:

1. A canonical GeoPackage with campus, building, development-phase, disturbance, current-developed-area, authoritative mapped roof, approved-plan, and provisional satellite-built-envelope layers.
2. GeoJSON exports for spatial layers and Parquet/CSV exports for tabular layers.
3. A site/phase evidence catalog recording imagery acquisition dates, documentary event dates, source versions, and the fields each item supports.
4. A statewide illustrated report with a comparison chapter, category summaries, regional maps, and concise site profiles.
5. Per-site image panels and QA records so individual findings can be revised without rebuilding unrelated sites.

## Required changes from the Aurora proof of concept

### Separate seed records from analysis units

Create three identifiers:

- `seed_record_id`: the taxonomy/harmonized record entering the workflow;
- `analysis_unit_id`: the resolved campus or independently developed parcel; and
- `building_id`: each confirmed current data-center building.

Entity resolution must consider operator, address, parcel ownership, shared access/security, contiguous disturbance, utility infrastructure, and documentary campus naming. Proximity alone is insufficient. This prevents both double-counting adjacent buildings and incorrectly merging neighboring operators in dense industrial parks.

### Make site processing configuration-driven

Move site-specific dates, buffers, imagery choices, and documentary URLs out of plotting/report code and into versioned configuration tables. Each pipeline stage should read the same inventory and write outputs keyed by `analysis_unit_id` and `phase_id`.

### Preserve three geometry provenance classes

Maintain separate layers for:

1. authoritative/current mapped roofs from Overture/OSM or another documented map source;
2. approved-plan footprints, with georeferencing precision recorded; and
3. approximate satellite-interpreted built or construction envelopes.

No aggregate footprint field may silently combine these classes. Statewide comparisons will use authoritative/current mapped roofs by default and expose plan-inclusive totals separately.

### Add review state

Every analysis unit will move through `inventory`, `imagery_ready`, `automated_screened`, `human_reviewed`, `document_checked`, `qa_complete`, and `published`. Low-resolution classification may nominate dates or envelopes, but it cannot advance a site to `qa_complete` without visual review.

## Category-specific method

### Wave 1: hyperscale greenfield campuses

Process DeKalb Meta and Microsoft Hoffman Estates first. Their large, phased campuses have high Sentinel-2 findability and strong crop-to-bare-to-built signals. Use campus-scale Dynamic World/Sentinel time series to identify phases, then NAIP or newer open high-resolution imagery for roofs, grading limits, substations, ponds, and roads. This wave is the best test of automated phase segmentation beyond Aurora.

### Wave 2: large purpose-built wholesale/colocation

Process the four unresolved seed records after excluding the two Aurora records already consolidated into the completed CHI1-CHI2 analysis unit. Sentinel-2 is suitable for broad construction timing but not for distinguishing these roofs from large warehouses. Current roof geometry and facility identity require Overture plus high-resolution review of cooling equipment, generator/fuel yards, transformer yards, access control, and the absence of logistics-scale dock courts. Older sites will require Landsat, historical NAIP, and documentary records because construction may predate Dynamic World.

### Wave 3: industrial-park, warehouse-style colocation

Process the 19 seed records only after entity resolution and imagery-availability review. Sentinel-2 has low class-discrimination value here and should be used for temporal screening, not facility confirmation or roof delineation. Parcel-scale high-resolution imagery and documentary evidence carry the most weight. Reviewers must explicitly compare each candidate with neighboring warehouses and record the presence or absence of rooftop cooling, generator enclosures, truck docks, trailer parking, and secure utility yards.

## Standard site workflow

1. Resolve the analysis unit and crosswalk all taxonomy, harmonized, PNNL, regulatory, Overture, and parcel records.
2. Determine the project/campus boundary without substituting a point buffer for a parcel or fence line.
3. Inventory imagery from Landsat, Sentinel-2, Dynamic World, CDL, NLCD, WorldCover, NAIP, and applicable county/state orthophotos.
4. Detect candidate construction breakpoints from vegetation/crop decline, bare-ground increase, and persistent built increase.
5. Inspect dated scenes and record last-preconstruction, first-disturbance, first-structure, substantial-completion, and operational/documentary milestones by phase.
6. Classify prior land cover inside the final disturbance envelope. Corroborate Dynamic World with at least one independent categorical source and direct high-resolution interpretation.
7. Distinguish observed agricultural cover from zoning, planned-development status, farmland-program enrollment, or permanent agricultural use.
8. Delineate maximum construction disturbance, permanent developed area, current mapped roofs, approved-plan roofs, and provisional built envelopes separately.
9. Calculate projected and geodesic areas and investigate differences greater than one percent.
10. Complete human review, documentary checks, geometry validation, and confidence scoring before publication.

## Confidence and evidence rules

- Construction timing requires dated imagery; exact dates require documentary evidence tied to the same phase.
- `brownfield_industrial` requires evidence of prior development plus industrial, demolition, contamination, or formal brownfield history. Bare ground alone is insufficient.
- Agricultural findings should, where available, combine direct aerial evidence with crop-specific CDL and regional parcel/land-use mapping. Dynamic World and WorldCover are not fully independent because both use Sentinel imagery.
- Current roofs must record source release and underlying edit/imagery date where available. A current Overture release does not prove current geometry.
- Dynamic World built polygons remain screening envelopes and are never labeled building footprints.
- Mixed sites retain fractional prior-cover fields; the dominant label does not replace composition.

## Pipeline structure

```text
analysis/illinois_land_use_change/
  00_build_candidate_inventory.py
  01_resolve_analysis_units.py
  02_inventory_imagery.py
  03_run_gee_timeseries.py
  04_extract_overture_buildings.py
  05_build_review_packets.py
  06_compile_documentary_evidence.py
  07_finalize_geometries_and_metrics.py
  08_run_qa.py
  09_build_statewide_report.py
data/illinois_land_use_change/
  inventory/
  raw/
  interim/
  review/
  final/
figures/illinois_land_use_change/
reports/illinois_land_use_change/
```

The Aurora code should be refactored into shared functions only after Wave 1 demonstrates which parameters vary by category. Aurora outputs remain immutable regression fixtures during the refactor.

## Quality gates

### Gate 1: resolved inventory

- Every one of the 27 seed records is mapped to an analysis unit, excluded with a reason, or explicitly unresolved.
- Campus merges include evidence beyond distance.
- Related buildings omitted from the taxonomy seed are attached when they are demonstrably part of a selected campus.

### Gate 2: imagery and automated screening

- Each phase has a dated preconstruction baseline and at least one post-change observation.
- Image/provider metadata and cloud/quality flags are complete.
- Dynamic World and spectral breakpoints are stored as candidates, not final determinations.

### Gate 3: reviewed measurements

- Prior land use has independent corroboration and a confidence rating.
- Disturbance, permanent developed area, campus area, and each footprint provenance class remain distinct.
- Every geometry is valid and every reported area can be regenerated.

### Gate 4: publication

- A second review checks all low- and medium-confidence findings and a sample of high-confidence findings.
- Dataset/report totals reconcile exactly.
- Each site profile contains dated imagery, source attribution, uncertainty, and a concise development timeline.

## Immediate execution sequence

1. Freeze the 27-record seed inventory from the taxonomy GeoJSON.
2. Run statewide entity resolution, beginning with known multi-building clusters in Aurora, DeKalb, NTT Wood Dale, and Elk Grove Village.
3. Build an imagery-availability matrix and current Overture snapshot for every provisional analysis unit.
4. Complete the two hyperscale sites end to end and compare their outputs against the Aurora regression fixtures.
5. Process large purpose-built sites, then warehouse-style sites in geographic batches to reuse imagery and parcel queries.
6. Publish interim datasets only after each category wave passes its quality gate; compile the statewide report after all three waves reconcile.

## Execution status — 9 September 2026

- Complete: frozen 27-record seed inventory and 24-unit campus/parcel crosswalk.
- Complete: restored original PNNL/OSM polygon geometry that the harmonized centroid layer had dropped.
- Complete: Overture Buildings 2026-08-19.0 candidate inventory, 2016–2026 Dynamic World screening, 2001–2021 NLCD corroboration, and 2008–2024 USDA CDL corroboration.
- Complete: 72 standardized dated-image chips and 24 three-panel review figures using NAIP and Sentinel-2.
- Complete: documentary screening profiles, an evidence catalog, a structured screening dataset, and a rendered statewide report.
- Complete: automated QA (18 checks, zero failures).
- Pending publication gate: site-scale human delineation of disturbance and acceptance/rejection of current roof candidates for the 23 non-Aurora units. These fields remain null or explicitly candidate-only in the screening dataset.
