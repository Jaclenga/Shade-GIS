# Shade Study Platform Schema

This document describes the durable project schema implemented by the Streamlit builder and the Postgres-ready relational schema in `sql/schema.sql`.

## Platform Backend

The builder uses a local SQLite database by default. On Windows, the database is created under
`%LOCALAPPDATA%\Shade-GIS\shade_study_builder.sqlite3` to avoid OneDrive file-locking issues; on
other systems it falls back to `platform_data/shade_study_builder.sqlite3`. Set `SHADE_GIS_DB_PATH`
to point the app at a different SQLite database file. The database stores multiple projects and
treats Streamlit session state as a live editing cache, not the durable source of record.

If the preferred SQLite file can be read but not written, the builder marks that path unusable for
the current process and retries against a writable user or temp fallback database. The active path is
shown in the `Data` page's Project Store controls.

The canonical relational shape is:

| Entity | Purpose |
| --- | --- |
| `projects` | One row per shade study, including publication metadata and source metadata. |
| `project_settings` | JSON methodology and visualization settings for each project. |
| `shade_taxonomy` | Editable shade category names, definitions, colors, and sort order. |
| `stops` | Per-project stop records, priority scores, review fields, and extra imported columns. |
| `images` | Uploaded or referenced imagery associated with projects and stops. |
| `shade_labels` | Raw expert, crowd, imported, or model-assisted label submissions. |
| `review_history` | Status transitions, reviewer actions, notes, and audit metadata. |
| `releases` | Published or draft dataset/app release records and artifact manifests. |
| `import_logs` | Source, format, row count, timestamp, and import metadata. |

## Project

Each study is configured as a project.

| Field | Purpose |
| --- | --- |
| `name` | Public project name. |
| `agency` | Transit agency or agencies represented in the dataset. |
| `region` | City, county, metro area, or study geography. |
| `description` | Short project description. |
| `owners` | People or organizations responsible for the project. |
| `visibility` | Public or private publication status. |
| `dataset_version` | Version of the current stop and shade dataset. |
| `methodology_version` | Version of the current assessment method. |
| `source_name` | Primary transit dataset or source label. |
| `source_license` | License or terms for the source data. |
| `source_url` | Source URL when available. |

Methodology citation and bibliography text support grouped hanging-indent formatting with APA-style
templates: unindented lines render as group labels, and indented lines render as citation or
bibliography entries.

## Bus Stops

The builder accepts GTFS-compatible stops, mapped tabular files, spatial files, API responses, and manually entered stop records.

Supported import paths:

| Source | Current behavior |
| --- | --- |
| GTFS ZIP | Requires `stops.txt`; optional `stop_times.txt`, `trips.txt`, and `routes.txt` enrich route labels. |
| CSV or `stops.txt` | Uses the field-mapping panel before import. |
| GeoJSON | Converts feature geometry into `stop_lon` and `stop_lat`, preserves feature properties as mappable fields, and records geometry metadata in the import log. |
| Zipped Shapefile | Reads `.shp`/`.dbf` bundles through `pyshp`, converts geometry into `stop_lon` and `stop_lat`, and preserves attributes as mappable fields. |
| API URL | Fetches CSV or GeoJSON from a URL, then uses the same field-mapping panel. |
| Manual entry | Provides an editable table for adding individual stop records. |

Required fields:

| Field | Purpose |
| --- | --- |
| `stop_id` | Unique stop identifier. |
| `stop_name` | Human-readable stop name. |
| `stop_lat` | Latitude in WGS84. |
| `stop_lon` | Longitude in WGS84. |

Optional fields:

| Field | Purpose |
| --- | --- |
| `agency` | Agency label for multi-agency studies. |
| `routes` | Semicolon-separated route labels serving the stop. |
| `municipality` | Local jurisdiction or neighborhood label. |
| `shading` | Current shade taxonomy category. |
| `shade_coverage` | Coverage dimension, if collected separately. |
| `shade_sources` | Source dimension, such as natural or built shade. |
| `review_status` | Workflow status such as unlabeled, accepted, or disputed. |
| `confidence` | Reviewer or model confidence. |
| `ridership` | Ridership measure used for prioritization. |
| `heat_vulnerability_index` | Heat exposure or vulnerability score. |
| `heat_vulnerability_label` | Human-readable heat vulnerability category. |
| `tree_canopy_pct` | Nearby tree canopy share from 0 to 1. |
| `lst_median` | Median land surface temperature or equivalent heat metric. |

## Shade Taxonomy

The default reusable taxonomy is:

| Category | Intent |
| --- | --- |
| `No Shade` | No shade reaches the waiting area. |
| `Limited Natural Shade` | Vegetation shades part of the waiting area. |
| `Significant Natural Shade` | Vegetation shades most of the waiting area. |
| `Intentional Built Shade` | A shelter, canopy, awning, or similar passenger facility shades riders. |
| `Incidental Built Shade` | A nearby non-shelter built feature shades riders. |
| `Needs Review` | The stop needs imagery, review, or disagreement resolution. |

Project teams can edit names, descriptions, colors, and sort order in the `Data` page.

## Raw Shade Labels

The `Labels` page writes every submitted assessment to `shade_labels` instead of replacing earlier
labels. Each label records the stop ID, optional image reference, reviewer or contributor ID,
reviewer role, source type, shade category, coverage, shade sources, confidence, notes, and
timestamp. A reviewer can optionally apply a submitted label to the current stop fields used by the
map and exports, but the raw label row is still retained either way.

The page also exposes raw-label history, basic counts for labeled/unlabeled/conflicting stops, and
a raw-label CSV download. Agreement metrics are computed from `shade_category` labels:

- Per-stop majority label, label count, majority count, agreement percentage, disagreement flag, and tied-majority flag.
- Average pairwise Cohen's kappa using the latest label per stop per reviewer.
- Fleiss' kappa across stops with at least two raw labels.
- Nominal Krippendorff's alpha across stops with at least two raw labels.

Reviewer-based metrics use `labeler_id` when present; otherwise they fall back to the submitted
role/source combination. These metrics summarize reliability and do not overwrite raw labels or
current stop fields.

Visualization settings store the selected map color field, premade and editable palettes for shade
categories, review statuses, priority-score gradients, and other categorical columns, plus marker
shape, size, opacity, outline, base map style, data-backed overlay selections, up to 10 custom X/Y chart
settings, dashboard cards, public data table/map-hover columns, and priority weights. Optional
context layers such as heat vulnerability or tree canopy are exposed only when the active dataset
contains usable values for those fields. The builder presents those settings in an expandable,
scrollable panel beside the live map preview.

When `priority_score` is used by any configured visualization, the public methodology page
automatically includes the active priority formula. If `priority_score` is excluded from map
coloring, custom charts, dashboard summaries, public tables, and map-hover fields, the formula is
left out.

## Preview Exports

The `Preview` page exports:

- Stops CSV.
- Stops GeoJSON.
- Raw labels CSV, when raw labels have been submitted.
- Study configuration JSON containing project metadata, taxonomy, methodology copy, visualization settings, and import log.

The `Deploy` page also exports a GitHub-ready ZIP bundle for the rendered public app. The bundle includes:

- Standalone `app.py` for the public Streamlit experience.
- `shade_study_stops.csv` with the active stop dataset and current priority scores.
- `shade_study_raw_labels.csv` with raw label submissions, when labels have been collected.
- `shade_study_config.json` with project metadata, taxonomy, methodology copy, visualization settings, and import log.
- `requirements.txt`, `.streamlit/config.toml`, generated `README.md`, `.gitignore`, and optional `deploy_to_github.ps1` helper.

Import log `imported_at` values are stored as timezone-aware local timestamps with a UTC offset.
File imports also record the original filename when available; API imports record the source URL.

The public preview also includes user-facing map controls to search by stop name, stop ID, or route,
filter to one or more route labels, click markers to select a stop, inspect a stop-detail panel, and
show or hide stops whose shade label is still `Needs Review` without changing the exported dataset.

## Review And Release Entities

`images`, `review_history`, and `releases` are part of the durable schema even when the current
Streamlit screens do not expose every field yet. Raw label submission is now exposed through the
`Labels` page, while image evidence, review audit trails, and release metadata remain ready for
future workflow screens.
