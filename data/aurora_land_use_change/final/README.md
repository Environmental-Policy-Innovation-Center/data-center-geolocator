# Aurora data-center land-use change dataset

Generated 2026-09-08. Area CRS: EPSG:26916. Spatial interchange CRS: EPSG:4326.

The canonical package is `aurora_data_center_land_use_change.gpkg` with `sites`
and `buildings` layers. Equivalent GeoJSON and Parquet files are supplied, plus
CSV/Parquet tables for development phases, predevelopment land use, annual
Dynamic World results, evidence, and source crosswalks.

Important distinctions:

- `mapped_building_footprints` contains only Overture/OSM roof polygons and
  records the underlying OSM edit date; an Overture release date is not an
  imagery acquisition date.
- `approved_plan_footprints` keeps the active Edged ORD01-2 plan geometry
  separate. Its dimensions are plan-derived, but its georeferenced position is
  approximate.
- `dynamic_world_built_core_2026` and `dynamic_world_built_inclusive_2026`, when
  present, are 10 m satellite-interpreted built-surface envelopes. They are not
  roof boundaries and may include pavement and equipment pads.
- `roof_footprint_*` is plan-view roof area, not gross floor area. The Edged
  combined value is explicitly provisional because it mixes mapped and plan data.
- `campus_area_*` is the parcel-defined site envelope.
- `disturbed_area_estimate_*` is a remotely sensed proxy. Its stated bounds are
  more appropriate than false precision from a single 10 m classification.
- Edged ORD01-2 geometry is an analysis approximation derived from approved plan
  dimensions. Its position is approximate and it is not a survey boundary.
- Results reflect evidence available through 2026-09-08; imagery observations
  extend through 2026-08-22.
