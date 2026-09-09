# Aurora Data Center Land-Use Change Study Plan

## 1. Objective

Produce an auditable, site-level dataset and illustrated report for data centers within the supplied Aurora, Illinois area of interest (AOI). For each resolved data-center site, determine:

1. when construction occurred, expressed as an evidence-bounded interval and a sequence of milestones;
2. the land use immediately before construction;
3. the maximum area disturbed by construction;
4. the current roof/building footprint and broader developed campus area; and
5. the development timeline, including phased expansion where visible.

The analysis should remain reproducible from repository data, Google Earth Engine (GEE), Overture Maps, and openly accessible satellite or aerial imagery. Claims must retain source, image acquisition date, method, confidence, and reviewer notes.

## 2. Study Area and Preliminary Inventory

The AOI is approximately 21.42 square kilometers and spans the Bilter Road/Diehl Road industrial area in Aurora and eastern Kane/western DuPage County surroundings.

Repository screening identifies three harmonized records, but they likely represent two facility-level sites:

| Working site | Repository evidence in AOI | Preliminary interpretation | Required resolution |
| --- | --- | --- | --- |
| Edged Data Center, 2835 Bilter Road | FracTracker site `site_00603`; NAICS record `EDGED CHICAGO LLC`; Illinois EPA facility `IL_1` | Approved/permitted/under construction; expected online 2027; no current PNNL building polygon | Delineate the project/disturbance boundary and any completed structures from recent imagery and Overture; verify construction milestones against permits and dated imagery |
| CyrusOne Chicago Aurora CME / CyrusOne Data Center | PNNL building `00199252950`; Illinois EPA facility `IL_17`; harmonized site `site_01911` | Existing data center; PNNL roof footprint 483,103 square feet | Establish original construction and later expansion dates; determine whether the nearby unnamed PNNL building is part of the same campus |
| Unnamed PNNL building `01426146790` | Harmonized site `site_02530`; PNNL roof footprint 169,253 square feet | Adjacent large building, about 333 meters from the EPA CyrusOne point | Resolve identity and campus membership with Overture attributes, imagery, parcel/address context, and physical campus connectivity before treating it as a separate data center |

The final inventory must be facility/campus based rather than record based. Source records will be retained in a crosswalk so that merging the two CyrusOne-area PNNL polygons, if justified, does not erase provenance.

## 3. Measurement Definitions

These definitions must be fixed before digitizing.

### Construction timing

- `construction_start_lower`: date of the last clear image showing no construction activity.
- `construction_start_upper`: date of the first clear image showing clearing, demolition, grading, excavation, or site mobilization.
- `first_structure_visible`: first clear image with an identifiable foundation, frame, or roof.
- `substantially_complete`: first clear image showing the principal phase roofed, paved, and no longer dominated by active grading.
- `operational_or_online_date`: documentary date when available; it is not inferred from imagery alone.
- Each phase receives its own interval. A site-level date is a summary of phase records, not a replacement for them.

### Pre-development land use

Classify the disturbance envelope using the last reliable pre-construction observation. Store fractional area and a dominant class rather than forcing mixed sites into one label.

- `greenfield_nonag`: undeveloped grass, shrub, wetland, vacant/open land, or other nonagricultural greenfield;
- `agricultural`: active cropland, pasture, hay, orchard, or managed agricultural field;
- `forested`: tree-covered land, with forest fraction recorded separately;
- `previously_developed`: impervious, building, parking, industrial, commercial, or transportation land;
- `brownfield_industrial`: previously developed land with independent evidence of prior industrial use, demolition, contamination, or formal brownfield status;
- `mixed` or `unknown`: used when no class exceeds 60 percent or the evidence is insufficient.

“Brownfield” must not be assigned from satellite appearance alone. It requires parcel/history, permit, planning, or other documentary evidence.

### Areas

- `disturbance_area_max`: union of all land visibly cleared, graded, excavated, demolished, used for laydown, or newly occupied by project roads, drainage ponds, utility/substation works, parking, and buildings during the observed construction period.
- `current_building_footprint`: roof/building polygons only, clipped to structures confirmed as part of the data center.
- `current_developed_area`: buildings plus internal paved roads, parking, yards, utility plant, stormwater facilities, and other permanently converted surfaces.
- `campus_or_project_area`: parcel, fence, or documented project boundary; reported separately and never substituted for disturbance.
- Areas will be calculated geodesically and in a suitable local projected CRS, reported in square meters, hectares, acres, and square feet where appropriate.

## 4. Source Strategy

### Repository sources

Use these first because they provide the candidate inventory, geometry, status, and regulatory cross-checks:

- `processed-data/harmonized-data-center-reference-sites-illinois.geojson`
- `processed-data/harmonized-data-center-reference-members-illinois.csv`
- `processed-data/illinois-data-center-regulatory-facilities.geojson`
- PNNL point, building, and campus layers under `raw-data/data-center-locations/PNNL/`
- FracTracker GeoJSON/CSV for project status, expected online date, and source URLs
- NAICS points as corroboration, not authoritative geometry
- Illinois EPA documents and the scraping pipeline under `pdf-scraping/`
- imagery source notes in `raw-data/imagery-sources/README.md`

### GEE sources

| Source | Role | Important limitation |
| --- | --- | --- |
| Sentinel-2 surface reflectance/harmonized imagery | Seasonal and annual cloud-free composites; 2015-present construction screening; NDVI/NDBI/bare-soil signals | 10-20 m pixels cannot define roof edges precisely |
| Dynamic World V1 | 10 m class probabilities for crops, trees, built, bare, grass, and other classes; breakpoint screening from 2015 onward | Single-image predictions are noisy; use probability composites and temporal persistence, not one label image |
| Landsat Collection 2 Level 2 | Annual/seasonal history back to the 1980s for older construction and broad conversion | 30 m resolution supports timing/context, not detailed area delineation |
| USDA NASS Cropland Data Layer | Annual crop and cultivated-land evidence from 1997 onward | 30 m; validate field edges and nonagricultural classes against imagery |
| NLCD land cover and imperviousness | Long-run developed/forest/agriculture context and impervious change | Coarse and episodic; not a construction-date source by itself |
| USDA NAIP | High-resolution pre/post validation and manual digitizing where acquisition years bracket construction | GEE catalog recency and Illinois acquisition cadence may leave multi-year gaps |

### Overture and open imagery

- Query the current Overture `buildings` theme for every candidate plus a 500-meter context buffer. Retain Overture ID, geometry, source lineage, class/subtype where available, release version, and extraction date.
- Compare Overture polygons to PNNL/OSM-derived polygons. Do not union them blindly: inspect offsets, duplicate buildings, multipart roofs, and changes between source vintages.
- Use current Overture geometry as a candidate footprint. Manually edit against the newest legally redistributable high-resolution image when roof boundaries are incomplete or stale.
- Use open NAIP, Earth Genome annual Sentinel-2 composites, Landsat, and any applicable county/state orthophotos. The repository’s 2011 IDOT source does not cover DuPage or Kane Counties, so it cannot serve as the AOI baseline.
- Record imagery provider, collection/item ID, acquisition date, processing level, resolution, license/attribution, cloud score, and URL for every image used in a finding or figure.

## 5. Workflow

### Phase A — Inventory and entity resolution

1. Save the AOI as canonical WGS84 GeoJSON and calculate its area.
2. Spatially subset every repository reference and regulatory layer to the AOI plus a 1-kilometer context buffer.
3. Create a source-record crosswalk keyed by `site_id` and `source_record_id`.
4. Query Overture buildings and compare geometry/name/address context with PNNL, FracTracker, NAICS, and EPA records.
5. Review each cluster visually. Assign one of `confirmed_data_center`, `probable_data_center`, `not_data_center`, or `unresolved`, with a confidence score and rationale.
6. Decide whether PNNL building `01426146790` is a CyrusOne phase/building or an unrelated industrial building before downstream measurement.

**Gate:** no change analysis begins for an unresolved candidate unless it remains explicitly labeled unresolved in all outputs.

### Phase B — Build the imagery stack

1. Generate annual leaf-on and leaf-off Sentinel-2 composites from 2015 to the current year using cloud/shadow masking and per-image provenance.
2. Generate Landsat annual or seasonal composites back to at least 1984, or to ten years before the earliest visible construction if later.
3. Pull annual Dynamic World probability composites and pixel-level observation counts.
4. Pull annual CDL and available NLCD land-cover/impervious products.
5. Inventory all NAIP acquisitions over the AOI and obtain original-resolution imagery for useful before/after years.
6. Search for other public high-resolution orthophotos covering DuPage/Kane Counties; use only products with clear acquisition dates and acceptable redistribution terms.
7. Co-register imagery to a high-resolution reference. Flag offsets larger than one high-resolution pixel or five meters, whichever is greater.

### Phase C — Detect and bracket construction

1. Extract time series for Dynamic World `built`, `bare`, `crops`, `trees`, and `grass` probabilities, plus NDVI, NDBI, and bare-soil indices within candidate parcels and 50-meter rings.
2. Use temporal change metrics to identify candidate breakpoints: persistent decline in vegetation/crop probability, spike in bare ground, then increase in built probability.
3. Inspect every candidate breakpoint in individual cloud-free Sentinel-2 scenes and the nearest high-resolution images.
4. Digitize phase polygons and assign the five milestone fields defined above.
5. Add documentary milestones from Illinois EPA permits, planning records already linked by repository sources, and reliable operator/project documentation. Preserve the distinction among permit, groundbreaking, visible work, completion, and operation.
6. Express uncertain dates as intervals. Do not use image publication date in place of acquisition date.

### Phase D — Determine prior land use

1. Use the final disturbance envelope as the analysis mask.
2. Select the last pre-construction high-resolution image and the corresponding pre-construction CDL, Dynamic World, NLCD, and Landsat/Sentinel composite.
3. Calculate fractional cover for agriculture, forest, nonagricultural greenfield, and previously developed land.
4. Manually inspect prior buildings, parking, road access, field boundaries, tree canopy, and demolition evidence.
5. Apply the dominant-class rule, with a separate `brownfield_industrial` flag only when documentary evidence supports it.
6. Store both automated class fractions and the reviewed final interpretation so disagreements are auditable.

### Phase E — Delineate disturbance and current footprint

1. Digitize disturbance by phase from the highest-resolution imagery available during construction. Include temporary impacts only when visibly attributable to the project.
2. Union phase disturbance polygons to obtain `disturbance_area_max`; retain phase polygons so the timeline remains recoverable.
3. Build current roof polygons from the best of PNNL, Overture, and manual interpretation. Split distinct structures and attach a `building_id`.
4. Delineate the permanent developed campus separately from the maximum construction disturbance.
5. Calculate areas in EPSG:26916 (UTM zone 16N) and cross-check with geodesic area. Investigate differences over 1 percent.
6. Report source geometry area and reviewed geometry area separately; never overwrite source measurements.

### Phase F — Quality assurance

1. Require two independent evidence types for facility identity and construction timing when possible: for example imagery plus EPA/permit evidence, or PNNL geometry plus Overture/source attribution.
2. Have a second reviewer check site identity, date bounds, pre-use class, and all digitized polygons.
3. Compute agreement metrics: boundary intersection-over-union, absolute/percent area difference, and date-bound agreement.
4. Use confidence levels:
   - `high`: high-resolution before/during/after imagery and corroborating records;
   - `medium`: clear medium-resolution sequence plus one strong geometry/document source;
   - `low`: sparse imagery, unresolved identity, or date interval wider than two years.
5. Run automated validations for valid geometry, non-overlapping phase IDs, date order, area-unit consistency, required provenance, and controlled vocabularies.

## 6. Structured Data Deliverables

Deliver one GeoPackage as the canonical spatial package, GeoJSON exports for web use, and CSV/Parquet tables for analysis.

### `sites`

One row per resolved campus/facility:

`site_id`, `canonical_name`, `operator`, `address`, `city`, `county`, `state`, `facility_status`, `identity_confidence`, `construction_start_lower`, `construction_start_upper`, `first_structure_visible`, `substantially_complete`, `operational_or_online_date`, `construction_date_confidence`, `pre_land_use_primary`, `pre_land_use_confidence`, `agriculture_pct`, `forest_pct`, `greenfield_nonag_pct`, `previously_developed_pct`, `brownfield_industrial_flag`, `disturbance_area_max_m2`, `disturbance_area_max_acres`, `current_building_footprint_m2`, `current_building_footprint_sqft`, `current_developed_area_m2`, `campus_or_project_area_m2`, `area_method`, `review_status`, `notes`, and campus geometry.

### `buildings`

One row per confirmed current data-center building:

`building_id`, `site_id`, `name`, `operator`, `construction_phase_id`, `first_visible_date`, `footprint_m2`, `source_geometry`, `source_release`, `manual_edit_flag`, `confidence`, and building geometry.

### `development_phases`

One row per visible construction/expansion phase:

`phase_id`, `site_id`, `phase_name`, `last_preconstruction_date`, `first_disturbance_date`, `first_structure_date`, `substantially_complete_date`, `phase_disturbance_m2`, `phase_building_footprint_m2`, `event_type`, `confidence`, `reviewer_notes`, and phase geometry.

### `land_use_composition`

One row per site, observation date, dataset, and class:

`site_id`, `observation_date`, `dataset`, `dataset_version`, `class_name`, `area_m2`, `area_pct`, `probability_mean`, `observation_count`, `is_final_preconstruction_baseline`, and method fields.

### `evidence`

One row per image, document, or source assertion:

`evidence_id`, `site_id`, optional `phase_id`, `evidence_type`, `provider`, `collection_or_source`, `item_or_document_id`, `acquisition_or_event_date`, `access_date`, `resolution_m`, `url_or_repo_path`, `license`, `supports_field`, `supports_value`, `interpretation`, `quality_flags`, and `citation_text`.

### `source_crosswalk`

One row per original record associated with a resolved site:

`site_id`, `source_name`, `source_record_id`, `source_name_raw`, `match_method`, `distance_m`, `match_confidence`, `included`, and `exclusion_reason`.

## 7. Illustrated Report

Produce a PDF and source document with:

1. an executive summary and a site comparison table;
2. an AOI inventory map showing resolved campuses and excluded/unresolved candidates;
3. one section per site with:
   - a dated before/during/after image triptych at a consistent scale;
   - current high-resolution image with building, developed-area, and maximum-disturbance outlines;
   - a timeline of documentary and imagery-derived milestones;
   - pre-development land-use composition chart;
   - area results and uncertainty/confidence notes;
4. a methods section with operational definitions, source versions, and classification rules;
5. a limitations section covering imagery gaps, mixed pixels, source staleness, georegistration, and campus/entity ambiguity; and
6. an appendix containing the evidence register, detailed QA results, and per-image attribution.

Every report figure should show acquisition date, source/provider, scale bar, north arrow, AOI/site boundary, and figure-specific legend. Imagery should not be resampled in a way that implies finer native resolution.

## 8. Recommended Implementation Structure

```text
analysis/aurora_land_use_change/
  config.yaml
  01_inventory.py
  02_overture_extract.sql
  03_gee_export.js
  04_change_metrics.py
  05_area_and_qa.py
data/aurora_land_use_change/
  aoi.geojson
  interim/
  final/
figures/aurora_land_use_change/
reports/aurora-data-center-land-use-change.md
reports/aurora-data-center-land-use-change.pdf
```

`config.yaml` should hold the AOI path, analysis CRS, date range, seasonal windows, cloud thresholds, buffers, source release identifiers, and classification thresholds. Scripts should be rerunnable without manual path edits, while manual digitizing should be saved as versioned GeoPackage layers with editor and edit-date attributes.

## 9. Execution Sequence and Acceptance Criteria

### Stage 1 — Inventory and data access

- Resolve the candidate count and campus identities.
- Confirm GEE authentication/export destination and Overture release.
- Produce the source crosswalk and imagery availability matrix.

### Stage 2 — Pilot the two known sites

- Complete the full workflow for Edged and CyrusOne.
- Review classification thresholds and drawing rules after comparing automated results to high-resolution imagery.

### Stage 3 — Final production and QA

- Resolve or explicitly exclude the unnamed PNNL building.
- Complete all geometries, tables, evidence records, and figures.
- Conduct independent review and address discrepancies.

The work is complete when:

- every repository candidate in the AOI is included, merged, excluded, or marked unresolved with a reason;
- every reported value has at least one evidence record and confidence rating;
- every construction date is either documentary or bounded by dated imagery;
- disturbance, building footprint, developed area, and campus area remain distinct;
- all spatial outputs pass geometry and area checks;
- the dataset can regenerate the report’s tables and figures; and
- the final report contains readable, attributed before/during/after imagery for every confirmed site.

## 10. Known Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Edged construction is newer than public NAIP coverage | Use recent Sentinel-2 for timing and seek current openly licensed aerial imagery for boundary digitizing; state the footprint uncertainty if none is available |
| Dynamic World confuses bright roofs, bare soil, and seasonal fields | Analyze class probabilities and persistence; corroborate with spectral indices and manual imagery review |
| PNNL/Overture building data may be stale or duplicated | Retain release/version metadata, compare geometries, and manually reconcile against dated imagery |
| Industrial adjacency causes false campus grouping | Require physical campus continuity, address/operator evidence, or documentary support before merging buildings |
| A single “construction year” hides phased expansion | Store phase-level intervals and milestones, then derive a clearly labeled site-level summary |
| Parcel size is mistaken for disturbed area | Maintain separate geometries and fields for project parcel, disturbance, developed area, and roofs |
| Baseline date differs among sites | Use the last valid pre-construction observation per phase and record it explicitly |
