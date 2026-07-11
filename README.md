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
- [Bundled Example Dataset](#bundled-example-dataset)
- [Configuration](#configuration)
- [Testing](#testing)
- [Deployment](#deployment)
- [License and Citation](#license-and-citation)
- [Contact and Support](#contact-and-support)

## Why use it?

Shade studies often combine transit feeds, local imagery review, community observations, review decisions, GIS context, public-facing maps, and methodology documentation. Without a shared platform, each project tends to recreate the same glue code for imports, labeling, quality review, exports, and publication.

Shade-GIS addresses those recurring needs by providing:

- A reusable Streamlit builder for configuring study metadata, source data, shade source and coverage taxonomies, methodology copy, visualizations, optional public crowd voting, and exports.
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
- **Public app template** - The tested `published_app.py` experience plus the `public_voting.py` runtime copied into generated study bundles.
- **Schema and docs** - A Postgres-ready schema plus platform documentation for teams that want to move beyond local SQLite.

### Builder App

The builder starts with the bundled Tampa/HART starter dataset, or with a new imported dataset. Project teams can configure metadata, import logs, source licensing, shade source and coverage taxonomies, review workflow, map styling, dashboard sections, custom charts, public voting, public table columns, map hover fields, GIS overlays, and methodology content.

The main app entrypoint is intentionally small:

```bash
streamlit run app.py
```

The builder implementation lives in `builder_app.py`, with supporting modules under `shade_gis/`.

At the bottom of the Data page, `Dataset Status` summarizes total, labeled, reviewed, and
needs-review stops. Label coverage and review-completion progress bars make project completeness
visible without scanning the underlying table. A filtered, paginated work queue defaults to stops
that need review or remain unlabeled and shows only stop ID, workflow status, raw-label count, final
label, and agreement. The collapsed `Dataset Preview` renders only the selected 25-, 50-, or
100-row page while retaining paginated access to every record and the import-validation checks.

The Preview's `Analytics` tab includes an Agreement section when `Agreement metrics` is selected in
the Visuals dashboard controls. Its compact overview shows labeled stops, unresolved disagreements,
mean agreement, Krippendorff's alpha, and Fleiss' kappa. The primary action opens a
disagreement-only queue sorted by lowest agreement, with minimum-label, agreement-threshold, and
label-category filters plus pagination. A reviewer can open one stop, compare every submitted label
and reviewer ID, inspect embedded Street View, the project map, and registered photos, then save a
canonical coverage/source decision. That decision marks the stop `Accepted` and appends an auditable
`Resolve disagreement` event to `review_history`; a newer raw label automatically reopens the stop.
Generated public apps show the compact summary and filtered disagreement queue without admin write
controls.

The Preview `Exports` tab and generated app downloads use a compact Export Files catalog instead of
stacked buttons. Every file row includes its purpose, record count, generated file size, relevant
data date, and download action. Import sources and timestamps appear separately below the catalog in
`Dataset Provenance`.

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
- `public_voting.py`: public voting interface and SQLite/PostgreSQL vote storage.
- `shade_study_stops.csv`: exported stop dataset with current priority scores.
- `shade_study_raw_labels.csv`: raw labels when labels have been collected.
- `shade_study_config.json`: project metadata, taxonomy, methodology, visualization settings, and import log.
- `requirements.txt`, `.streamlit/config.toml`, generated `README.md`, and `deploy_to_github.ps1`.

The dedicated `Voting` page includes the Public Voting editor. An admin can enable or hide voting, choose the
coverage categories visitors may submit, edit all visible voting copy including the separate shade-source
checkbox prompt, control whether repeat votes
from the same browser session may be changed, show or hide totals, and set the minimum vote count
before a unique leading status is reported. Community results stay separate from the reviewed stop
dataset so public input does not silently overwrite an admin-approved classification.

Generated apps use a local `.shade_gis_votes.sqlite3` file by default. That is useful for local
testing, but hosted deployments should set the Streamlit secret
`SHADE_GIS_VOTE_DATABASE_URL = "postgresql://..."` because Streamlit Community Cloud local files
are ephemeral. The generated bundle README contains the complete setup note, and the app creates its
`shade_votes` table automatically. Voter identifiers are random browser-session IDs rather than
names or email addresses; this is lightweight crowdsourcing, not authenticated identity verification.

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

## Bundled Example Dataset

The repository includes a small Tampa/HART starter study to demonstrate the builder workflow with real stop records. The example is not meant to be a complete published shade inventory. It is a handcrafted sample dataset: 34 bus stop datapoints were manually reviewed using Google Maps imagery, accepted by project admin Jack Lenga, and coded for visible shade conditions at the passenger waiting area.

The reviewed example records focus on three shade fields:

| Field | Meaning in the example dataset |
| --- | --- |
| `shade_coverage` | The amount of visible shade reaching the waiting area: `No Shade`, `Limited Shade`, or `Significant Shade`. |
| `shade_sources` | The visible source of shade reaching the waiting area, such as `Natural`, `Constructed`, `Manmade`, or combined labels when multiple sources are present. |
| `shading` | The derived coverage category used for coloring, filtering, summaries, and public display. |

Manual coding used the visible waiting area as the unit of analysis. Reviewers should code what appears to shade the place where a rider would reasonably stand or sit while waiting, rather than nearby objects that do not visibly shade that space.

The example labels distinguish source and coverage as separate dimensions. Use `shade_sources` for
what creates the shade and `shade_coverage` for how much of the waiting area is shaded. The derived
`shading` field mirrors the coverage code, and source values never appear as coverage choices or map
coverage labels.

Shade source definitions:

| Shade source | Operational definition |
| --- | --- |
| `Natural` | Trees, palms, hedges, or other vegetation visibly shade the waiting area. |
| `Constructed` | A designated, purpose-built bus shelter, awning, canopy, overhang, or similar passenger shelter visibly shades the waiting area. |
| `Manmade` | A nearby building or other non-shelter built feature visibly shades the waiting area. |

Shade coverage definitions:

| Shade coverage | Operational definition |
| --- | --- |
| `No Shade` | No shade visibly reaches the waiting area. |
| `Limited Shade` | Shade visibly reaches part of the waiting area, but does not cover most of it. |
| `Significant Shade` | Shade visibly covers most of the waiting area or seating area. |

Because the example was created from Google Maps imagery, it should be treated as a demonstration dataset with known limitations. Image dates, camera angle, season, time of day, temporary obstructions, and incomplete street-level coverage can all affect what shade is visible. The sample is useful for testing the platform workflow, previewing maps and review tools, and illustrating a reproducible coding approach; project teams should perform their own review before publishing a local study.

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

To publish a rendered study app, use the builder's `Deploy` page. The generated bundle can create a new GitHub repository or publish into a pre-existing private repository that your GitHub account can access.

After downloading the bundle, the browser should save it to your Downloads folder. The default commands assume that location:

```powershell
$BundleName = "your-shade-study.zip"
$ZipPath = Join-Path (Join-Path $env:USERPROFILE "Downloads") $BundleName
$ExtractTo = Join-Path (Join-Path $env:USERPROFILE "Documents") "your-shade-study"
if (-not (Test-Path $ZipPath)) {
    throw "Expected the deploy bundle at $ZipPath. If your browser saved it somewhere else, move it to Downloads or update `$ZipPath."
}
Expand-Archive -Path $ZipPath -DestinationPath $ExtractTo -Force
Set-Location $ExtractTo
if (-not (Test-Path ".\deploy_to_github.ps1")) {
    throw "deploy_to_github.ps1 was not found. Check that `$ExtractTo points to the extracted deploy bundle folder, then run Set-Location `$ExtractTo."
}
git --version
gh auth status
gh repo view OWNER/REPO
```

Only change `$BundleName` if the downloaded zip has a different filename. `$ExtractTo` is the folder PowerShell will create for the extracted app files.
Run `.\deploy_to_github.ps1` only after `Set-Location $ExtractTo`; the helper is generated inside the extracted deploy bundle, not inside the builder source folder.

If GitHub CLI is not authenticated, run `gh auth login`. If Windows blocks the downloaded script, run `Unblock-File .\deploy_to_github.ps1` once from the extracted bundle folder.
Before publishing into an existing private repository, verify the exact repository owner/name and account access:

```powershell
gh auth status
gh repo view Jaclenga/sunbelt-shade-project
```

If that verification works, deploy with the same owner/name:

```powershell
.\deploy_to_github.ps1 -Mode existing -RepositoryName "Jaclenga/sunbelt-shade-project" -Branch "main"
```

If GitHub reports that it "Could not resolve to a Repository", the signed-in account does not have access to that private repo, or the repo owner/name is different.

For a new repository:

```powershell
.\deploy_to_github.ps1 -Mode create -RepositoryName "your-shade-study" -Branch "main" -Visibility private
```

For an existing private repository:

```powershell
.\deploy_to_github.ps1 -Mode existing -RepositoryName "OWNER/REPO" -Branch "main"
```

Before committing, the helper prints `git status`, `git diff --stat`, and a staged diff summary, then asks you to type `PUBLISH`. Add `-Yes` only when you intentionally want non-interactive publishing.

In existing-repository mode, the helper verifies private repo visibility when it can, clones the target repo into a temporary `_shade_gis_publish_*` folder under PowerShell's temp path, checks out the selected branch, copies only generated app/runtime files into that checkout, commits changes, pushes back to GitHub, and cleans up the temporary folder. It does not copy protected files such as `.git/`, `.github/`, `README.md`, `LICENSE`, `.env*`, or `secrets.toml`. In new-repository mode, it initializes Git in the extracted bundle, stages only generated app files, creates the GitHub repository, and pushes the branch. Public publishing requires the explicit `-AllowPublicTarget` flag.

The generated repository can then be connected to Streamlit Community Cloud or another Streamlit host with `app.py` as the main file. Private repositories require the deployment host to have access to the repository. When public voting is enabled, add a PostgreSQL connection URL as the `SHADE_GIS_VOTE_DATABASE_URL` deployment secret before relying on vote persistence.

## License and Citation

The code in this repository is licensed under the MIT License. See [LICENSE](LICENSE) for rights and obligations.

Use [CITATION.cff](CITATION.cff) when citing this repository or a derived study release.

## Contact and Support

For questions, bug reports, and project support expectations, see [SUPPORT.md](SUPPORT.md). For contribution workflow and governance expectations, see [CONTRIBUTING.md](CONTRIBUTING.md) and [GOVERNANCE.md](GOVERNANCE.md).
