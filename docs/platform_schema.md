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

Import guardrails are enforced before parsing so open-source deployments have safe defaults without
removing local flexibility. File and overlay uploads default to 50 MB; API responses default to
15 MB; ZIP uploads default to 256 members, 80 MB per member, and 150 MB total uncompressed size.
API URLs must use `http` or `https`, cannot include embedded credentials, and cannot target
localhost/private-network addresses unless `SHADE_GIS_ALLOW_PRIVATE_API_URLS=1` is set. Operators
can set `SHADE_GIS_ALLOWED_API_HOSTS` to a comma-separated host allowlist and can tune byte/member
limits with the `SHADE_GIS_MAX_*` environment variables documented in `README.md`.

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
| `nearby_destinations` | Destination or nearby-place labels used for public map filtering. |

Columns outside the required and optional platform fields are preserved as dataset attributes in
`stops.extra_json`. They can be shown in tables, map hovers, color palettes, public filters, custom
charts, and exports when the active dataset contains usable values, but they are not promoted into
the core platform schema.

## Shade Taxonomy

The default reusable taxonomy is:

| Category | Intent |
| --- | --- |
| `No Shade` | No shade reaches the waiting area. |
| `Limited Natural Shade` | Vegetation shades part of the waiting area. |
| `Significant Natural Shade` | Vegetation shades most of the waiting area. |
| `Intentional Built Shade` | A shelter, awning, roof, or similar passenger facility shades riders. |
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

## Review Workflow

The `Labels` page includes an admin review queue built from current stop statuses, raw-label counts,
agreement percentages, disagreement flags, and priority scores. Project teams can filter the queue
to stops that are unlabeled, disputed, or need review; search by stop ID/name/route; and isolate
stops with conflicting raw labels.

For each queued stop, an admin can accept the current label, enter an expert override, mark a stop
as disputed, resolve a dispute, or archive the stop. The decision form writes the final shade
category, coverage, source list, confidence, and review status back to the stop dataset used by maps
and exports. It also appends a `review_history` audit event with the actor, role, action, previous
and final statuses, previous and final labels, decision notes, agreement context, and timestamp.
Applying a raw label directly to the map label also records an audit event, so map-facing label
changes remain traceable.

Visualization settings store the selected map color field, premade and editable palettes for shade
categories, review statuses, priority-score gradients, and other categorical columns, plus marker
shape, size, opacity, outline, base map style, uploaded GIS overlays, data-backed context field
selections, up to 10 custom X/Y chart settings, advanced dashboard sections, public data
table/map-hover columns, and priority weights. Dataset-specific attributes are discovered from the
active stop table and remain project data, not schema-level platform fields.

Uploaded GIS overlays live under `visualization.gis_overlays`. Each overlay stores a name,
category, source, license, original filename, format, style settings, import timestamp, summary
metadata, and a GeoJSON FeatureCollection. GeoJSON files are preserved as GeoJSON, while zipped
Shapefiles are converted to GeoJSON features for rendering and export. These overlays render as
PyDeck `GeoJsonLayer`s in the builder preview and generated public app.

When `priority_score` is used by any configured visualization, the public methodology page
automatically includes the active priority formula. If `priority_score` is excluded from map
coloring, custom charts, dashboard summaries, public tables, and map-hover fields, the formula is
left out.

The Analytics tab renders the dashboard sections described in the platform issue when supporting
fields are available: summary statistics, shade distribution, stops without shade, stops requiring
review, agreement statistics, shade by route, shade by neighborhood, shade vs. ridership, and
highest-priority stops. Custom charts remain available below the dashboard.

## Preview Exports

The `Preview` page exports:

- Stops CSV.
- Stops GeoJSON.
- Raw labels CSV, when raw labels have been submitted.
- Study configuration JSON containing project metadata, taxonomy, methodology copy, visualization settings, and import log.

The `Deploy` page also exports a GitHub-ready ZIP bundle for the rendered public app. The public
Streamlit source is maintained in `published_app.py`, which the builder preview imports and the
deploy bundle copies as its standalone `app.py`. The bundle includes:

- Standalone `app.py` for the public Streamlit experience.
- `shade_study_stops.csv` with the active stop dataset and current priority scores.
- `shade_study_raw_labels.csv` with raw label submissions, when labels have been collected.
- `shade_study_config.json` with project metadata, taxonomy, methodology copy, visualization settings, and import log.
- `requirements.txt`, `.streamlit/config.toml`, generated `README.md`, `.gitignore`, and optional `deploy_to_github.ps1` helper.

The deploy helper supports creating a new GitHub repository or publishing the generated files into
a pre-existing private repository that the authenticated GitHub CLI account can access.
After downloading the ZIP, the command examples assume the browser saved the bundle to the user's
standard Downloads folder, expand that expected path, enter the extracted folder, confirm Git and
GitHub CLI authentication, verify existing private repository access with `gh repo view OWNER/REPO`,
verify that `deploy_to_github.ps1` exists in that extracted folder, and then run the generated helper.
The helper is generated inside the deploy bundle and is not available
from the builder source tree. Existing private repositories are visibility-checked when possible, cloned into a temporary
`_shade_gis_publish_*` folder under PowerShell's temp path, updated with an allowlist of generated
app/runtime files, previewed with `git status` and `git diff --stat`, confirmed by the user, pushed
to the requested branch, and cleaned up. Protected repository files such as `.git/`, `.github/`,
`README.md`, `LICENSE`, `.env*`, and `secrets.toml` are not copied in existing-repository mode.

Import log `imported_at` values are stored as timezone-aware local timestamps with a UTC offset.
File imports also record the original filename when available; API imports record the source URL.

The public preview also includes user-facing map controls to search by stop name or stop ID, filter
routes, shade categories, review statuses, confidence, ridership, priority score, nearby
destinations, and eligible dataset-specific attributes when those fields exist, click markers to
select a stop, inspect a stop-detail panel, and show or hide stops whose shade label is still
`Needs Review` without changing the exported dataset.

## Review And Release Entities

`images` and `releases` remain durable schema foundations for richer evidence and publication
workflows. Raw label submission, admin review decisions, dispute resolution, expert overrides, and
review audit trails are exposed through the `Labels` page.
