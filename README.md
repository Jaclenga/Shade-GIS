# Shade-GIS - Shade Study Builder

Shade-GIS provides a modular and easy-to-configure open-source platform for preparing, reviewing, visualizing, and publishing bus stop shade studies. It is designed to reduce the effort required to manage transit stop data, shade classifications, reviewer decisions, public methodology copy, and deployable Streamlit study apps.

Shade-GIS follows a project-based builder approach that keeps local prototyping simple while preserving a path toward shared database-backed deployments. The platform lets researchers, transit agencies, municipalities, and community contributors focus on shade analysis and public communication rather than rebuilding the same data workflow for every study area.

| Category | Badges and Links |
| --- | --- |
| Tests | [![Tests](https://github.com/Jaclenga/Shade-GIS/actions/workflows/tests.yml/badge.svg)](https://github.com/Jaclenga/Shade-GIS/actions/workflows/tests.yml) |
| License | [MIT License](LICENSE) |
| Documentation | [Platform schema](docs/platform_schema.md) - [Changelog](CHANGELOG.md) |
| Community | [Contributing](CONTRIBUTING.md) - [Support](SUPPORT.md) - [Governance](GOVERNANCE.md) |
| Citation | [CITATION.cff](CITATION.cff) |

## Table of Contents

- [Why use it?](#why-use-it)
- [How it works?](#how-it-works)
- [Getting Started](#getting-started)
- [Supported Data](#supported-data)
- [Configuration](#configuration)
- [Testing](#testing)
- [Deployment](#deployment)
- [License and Citation](#license-and-citation)
- [Contact and Support](#contact-and-support)

## Why use it?

Shade studies often combine transit feeds, local imagery review, community observations, review decisions, GIS context, public-facing maps, and methodology documentation. Without a shared platform, each project tends to recreate the same glue code for imports, labeling, quality review, exports, and publication.

Shade-GIS addresses those recurring needs by providing:

- A reusable Streamlit builder for configuring study metadata, source data, shade taxonomy, methodology copy, visualizations, and exports.
- Flexible import paths for GTFS, CSV, GeoJSON, zipped Shapefiles, API-hosted files, and manually entered records.
- A raw labeling and admin review workflow that preserves submissions, agreement metrics, final labels, and audit history.
- Project-scoped durable storage through SQLite by default, with a Postgres-ready relational schema for shared deployments.
- A generated public Streamlit app that can be bundled with current stops, raw labels, configuration, downloads, and methodology text.

Possible applications include:

- Citywide or corridor-level bus stop shade inventories.
- Community audit programs and reviewer quality workflows.
- Public maps for rider-facing shade information.
- Planning studies that combine shade conditions with ridership, routes, destinations, or other project-specific attributes.

## How it works?

Shade-GIS consists of the following layers:

- **Builder app** - The main Streamlit interface for importing data, editing project settings, reviewing labels, configuring visualizations, previewing the public app, and exporting deployment bundles.
- **Platform store** - A durable SQLite-backed project store that saves metadata, taxonomy, methodology, visualization settings, stops, import logs, raw labels, and review history.
- **Public app template** - The tested `published_app.py` module used by the builder preview and copied into generated study bundles.
- **Schema and docs** - A Postgres-ready schema plus platform documentation for teams that want to move beyond local SQLite.

### Builder App

The builder starts with the bundled Tampa/HART starter dataset, or with a new imported dataset. Project teams can configure metadata, import logs, source licensing, shade taxonomy, review workflow, map styling, dashboard sections, custom charts, public table columns, map hover fields, GIS overlays, and methodology content.

The main app entrypoint is intentionally small:

```bash
streamlit run app.py
```

The builder implementation lives in `builder_app.py`, with supporting modules under `shade_gis/`.

### Platform Store

The Streamlit builder uses SQLite by default. On Windows, the database is created under:

```text
%LOCALAPPDATA%\Shade-GIS\shade_study_builder.sqlite3
```

On other systems, the builder first tries:

```text
platform_data/shade_study_builder.sqlite3
```

Set `SHADE_GIS_DB_PATH` to point the builder at another writable SQLite database. If the configured or default database is readonly, the builder falls back to a writable user or temp database and shows the active path in the `Data` page.

### Public Study App

The `Preview` page renders the public-facing study experience for the active project. The `Deploy` page exports a GitHub-ready bundle containing:

- `app.py`: standalone public Streamlit app copied from `published_app.py`.
- `shade_study_stops.csv`: exported stop dataset with current priority scores.
- `shade_study_raw_labels.csv`: raw labels when labels have been collected.
- `shade_study_config.json`: project metadata, taxonomy, methodology, visualization settings, and import log.
- `requirements.txt`, `.streamlit/config.toml`, generated `README.md`, and `deploy_to_github.ps1`.

## Getting Started

Use the quick start below for a local builder run. For schema details, see [docs/platform_schema.md](docs/platform_schema.md).

### Prerequisites

- Python 3.11 or newer is recommended.
- A local shell capable of running Streamlit commands.
- Optional: Docker and Postgres if you want to test the shared database schema.

### Quick Start

Clone the repository and install runtime dependencies:

```bash
git clone https://github.com/Jaclenga/Shade-GIS.git
cd Shade-GIS
pip install -r requirements/requirements.txt
```

Start the builder:

```bash
streamlit run app.py
```

The app opens to the reusable builder. The bundled `stops.txt` and `shading_data.csv` seed the default starter project only; importing a GTFS zip, mapped file/API dataset, or manual entries in the `Data` page replaces the active in-session dataset.

### Local Folder Structure

The repository is organized around the reusable builder, generated public app template, tests, schemas, and documentation:

```text
Shade-GIS/
|-- app.py
|-- builder_app.py
|-- published_app.py
|-- shade_gis/
|-- docs/
|-- sql/
|-- scripts/
|-- tests/
|-- requirements/
`-- platform_data/
```

`platform_data/` is used only when the default database path falls back to the repository. On Windows, the preferred runtime database location is outside OneDrive under `%LOCALAPPDATA%`.

## Supported Data

Required stop fields:

| Field | Description |
| --- | --- |
| `stop_id` | Unique stop identifier, usually from GTFS. |
| `stop_name` | Public stop name. |
| `stop_lat` | Stop latitude in WGS84. |
| `stop_lon` | Stop longitude in WGS84. |

Optional platform fields include `agency`, `routes`, `municipality`, `shading`, `shade_coverage`, `shade_sources`, `review_status`, `confidence`, `ridership`, and `nearby_destinations`.

Additional uploaded columns are preserved as dataset attributes. When those fields contain usable values, the builder can expose them in displays, map hovers, public filters, custom charts, colors, exports, and GIS overlay metadata without promoting them into the core platform schema.

Supported import paths:

| Source | Notes |
| --- | --- |
| GTFS ZIP | Requires `stops.txt`; route labels are enriched when `stop_times.txt`, `trips.txt`, and `routes.txt` are present. |
| CSV or `stops.txt` | Uses the field-mapping panel so agency-specific column names can be mapped into the platform schema. |
| GeoJSON | Reads FeatureCollections, Features, and geometry objects; point coordinates are mapped into stop longitude/latitude. |
| Zipped Shapefile | Upload a `.zip` containing at least `.shp` and `.dbf`; records are mapped through the same field-mapping panel. |
| API URL | Fetches CSV or GeoJSON from a URL and stores the source URL in the import log. |
| Manual entry | Provides an editable table for adding individual stops without a source file. |

## Configuration

### Import Guardrails

Shade-GIS is intended for open-source use, so import safety is configurable rather than tied to one hosted environment.

Default limits:

```text
File and overlay uploads: 50 MB
API responses: 15 MB
ZIP members: 256
ZIP member size: 80 MB
ZIP total uncompressed size: 150 MB
```

Operators can adjust these defaults with:

```text
SHADE_GIS_MAX_UPLOAD_BYTES
SHADE_GIS_MAX_API_BYTES
SHADE_GIS_MAX_ZIP_MEMBERS
SHADE_GIS_MAX_ZIP_MEMBER_BYTES
SHADE_GIS_MAX_ZIP_UNCOMPRESSED_BYTES
```

API URLs must use `http` or `https`, cannot include embedded credentials, and cannot target localhost or private-network addresses by default. Use `SHADE_GIS_ALLOWED_API_HOSTS` for a host allowlist, or set `SHADE_GIS_ALLOW_PRIVATE_API_URLS=1` when intentionally running against private or local data services.

### Optional Postgres Schema

The Streamlit builder uses SQLite by default. `sql/schema.sql` mirrors the richer platform model for shared Postgres deployments with projects, stops, images, labels, releases, review history, taxonomy, settings, and import logs.

Start Postgres:

```bash
docker-compose up -d
```

Install optional database dependencies:

```bash
pip install -r requirements/requirements-db.txt
```

Initialize the schema and seed project stops:

```bash
python scripts/init_db.py
```

Default connection values are `localhost:5432`, database `tampa_shade`, user `postgres`, and password `postgres`. Override them with `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, and `PGPASSWORD`.

## Testing

Install the standard test dependencies:

```bash
pip install -r requirements/requirements-test.txt
```

Run the non-UI test suite:

```bash
pytest -q
```

The test suite uses temporary SQLite databases and small fixtures to verify project storage, imports, labels, review audit history, exports, priority scoring, and module syntax without touching the local builder database.

Browser UI tests are available as an opt-in Playwright suite:

```bash
pip install -r requirements/requirements-ui.txt
python -m playwright install chromium
pytest -q -m ui
```

Normal `pytest` runs exclude tests marked `ui`; GitHub Actions runs the UI suite in a separate job.

## Deployment

The builder itself can be deployed as a Streamlit app with:

- Main file: `app.py`
- Python dependencies: `requirements.txt` at the repository root, which delegates to `requirements/requirements.txt`

To publish a rendered study app, use the builder's `Deploy` page. Either create a GitHub repository and upload the generated bundle contents, or run the included PowerShell helper with the GitHub CLI:

```powershell
.\deploy_to_github.ps1 -RepositoryName "your-shade-study"
```

The generated repository can then be connected to Streamlit Community Cloud with `app.py` as the main file.

## License and Citation

The code in this repository is licensed under the MIT License. See [LICENSE](LICENSE) for rights and obligations.

Use [CITATION.cff](CITATION.cff) when citing this repository or a derived study release.

## Contact and Support

For questions, bug reports, and project support expectations, see [SUPPORT.md](SUPPORT.md). For contribution workflow and governance expectations, see [CONTRIBUTING.md](CONTRIBUTING.md) and [GOVERNANCE.md](GOVERNANCE.md).
