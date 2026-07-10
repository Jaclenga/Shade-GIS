import io
import ipaddress
import json
import math
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pydeck as pdk
import streamlit as st

import published_app
from builder_about_page import render_builder_about_page
from public_voting import normalize_voting_config
from platform_store import (
    add_review_event,
    add_shade_label,
    create_project,
    database_status,
    init_database,
    list_review_history,
    list_shade_labels,
    list_projects,
    load_project_bundle,
    save_project_bundle,
)
from shade_gis.builder_imports import (
    REQUIRED_STOP_FIELDS,
    OPTIONAL_FIELDS,
    apply_field_mapping,
    calculate_priority_scores,
    clean_import_key,
    detect_zip_import_format,
    fetch_api_bytes,
    format_bytes,
    hex_to_rgb,
    import_stop_dataset,
    max_api_bytes,
    max_upload_bytes,
    max_zip_members,
    max_zip_uncompressed_bytes,
    normalize_category,
    normalize_hex_color,
    normalize_review_status,
    parse_api_response,
    parse_geojson_bytes,
    parse_geojson_overlay_bytes,
    parse_gtfs_zip,
    parse_shapefile_overlay_zip,
    parse_shapefile_zip,
    prepare_stop_dataset,
    read_csv_bytes,
    render_mapped_import_controls,
    suggest_source_column,
    timestamp_with_timezone,
    validate_api_url,
    validate_zip_bytes,
)
from shade_gis.builder_labels import (
    agreement_metric_summary,
    average_pairwise_cohen_kappa,
    category_count_matrix,
    clean_label_values,
    cohen_kappa_for_pair,
    fleiss_kappa,
    format_metric_value,
    krippendorff_alpha_nominal,
    label_rater_key,
    label_source_code,
    latest_labels_by_rater,
    majority_label_table,
    raw_label_summary,
    render_agreement_metrics,
    review_queue_label,
    review_queue_table,
    split_list_field,
    stop_picker_label,
    stop_review_snapshot,
    taxonomy_names,
)
from shade_gis.builder_visuals import (
    CATEGORICAL_MAP_FILTERS,
    CHART_AGGREGATIONS,
    CHART_TYPES,
    COLOR_MODE_FIELDS,
    COLOR_PALETTE,
    DEFAULT_CUSTOM_CHART,
    DEFAULT_DISPLAY_COLUMNS,
    DEFAULT_VISUALIZATION,
    DESTINATION_FILTER_COLUMNS,
    FIELD_LABELS,
    GIS_OVERLAY_CATEGORIES,
    MAP_STYLES,
    MARKER_SHAPES,
    MAX_CUSTOM_CHARTS,
    METRIC_REQUIREMENTS,
    NUMERIC_MAP_FILTERS,
    OVERLAY_REQUIREMENTS,
    PRIORITY_FACTOR_DETAILS,
    RECORD_COUNT_FIELD,
    SHADE_PALETTES,
    add_marker_icons,
    build_custom_chart_data,
    build_deck_chart,
    build_gis_overlay_layers,
    build_tooltip_text,
    calculate_view_state,
    clean_gis_overlays,
    clean_selected_options,
    color_dataset,
    color_for_priority,
    display_label,
    ensure_custom_chart_defaults,
    ensure_field_color_map,
    field_values_for_colors,
    get_active_data_columns,
    get_available_metric_cards,
    get_available_overlays,
    get_chart_column_options,
    get_color_options,
    get_custom_charts,
    get_display_column_options,
    get_selected_display_columns,
    get_taxonomy_color_map,
    has_all_column_data,
    has_any_column_data,
    has_column_data,
    marker_icon_svg,
    priority_formula_for_about,
    priority_score_used_in_visualization,
    render_custom_chart,
    render_custom_charts,
    rgba_from_hex,
    selected_dashboard_sections,
)
from shade_gis.shade_dimensions import (
    DEFAULT_COVERAGE_TAXONOMY,
    SHADE_COVERAGE_OPTIONS as CORE_SHADE_COVERAGE_OPTIONS,
    SHADE_COVERAGE_TAXONOMY as CORE_SHADE_COVERAGE_TAXONOMY,
    SHADE_SOURCE_OPTIONS as CORE_SHADE_SOURCE_OPTIONS,
    SHADE_SOURCE_TAXONOMY as CORE_SHADE_SOURCE_TAXONOMY,
    normalize_coverage_taxonomy,
)


APP_DIR = Path(__file__).parent
DATA_PATH = APP_DIR / "stops.txt"
SHADE_DATA_PATH = APP_DIR / "shading_data.csv"
APP_TITLE = "Shade Study Builder"
VISUAL_MAP_HEIGHT = 500
METHODS_PREVIEW_HEIGHT = 1220
DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_API_BYTES = 15 * 1024 * 1024
DEFAULT_MAX_ZIP_MEMBERS = 256
DEFAULT_MAX_ZIP_MEMBER_BYTES = 80 * 1024 * 1024
DEFAULT_MAX_ZIP_UNCOMPRESSED_BYTES = 150 * 1024 * 1024
API_FETCH_TIMEOUT_SECONDS = 30



DEFAULT_PROJECT = {
    "name": "Tampa Bus Stop Shade Study",
    "agency": "Hillsborough Area Regional Transit (HART)",
    "region": "Tampa, Florida",
    "description": (
        "A reusable shade inventory project seeded with Tampa-area GTFS stops, "
        "shade classifications, and optional dataset attributes."
    ),
    "owners": "Open transit and climate research contributors",
    "visibility": "Public",
    "dataset_version": "0.1.0",
    "methodology_version": "0.1.0",
    "source_name": "HART GTFS feed",
    "source_license": "Agency GTFS terms",
    "source_url": "",
}

DEFAULT_TAXONOMY = [dict(item) for item in DEFAULT_COVERAGE_TAXONOMY]
SHADE_SOURCE_TAXONOMY = [dict(item) for item in CORE_SHADE_SOURCE_TAXONOMY]
SHADE_COVERAGE_TAXONOMY = [dict(item) for item in CORE_SHADE_COVERAGE_TAXONOMY]

DEFAULT_METHODOLOGY = {
    "title": "Bus Stop Shade Study",
    "summary": "Visualizing bus stop shade for a more comfortable and resilient transit system.",
    "purpose": (
        "Tampa's hot and humid climate can make waiting for transit uncomfortable, particularly at bus stops "
        "with limited protection from direct sunlight. Inspired by research examining the relationship between "
        "bus stop shade, heat exposure, and transit use, this project explores how shade is distributed across "
        "a transit network and provides a platform for community-driven data collection.\n\n"
        "The bundled Tampa/HART starter study combines official bus stop locations from HART's GTFS feed with "
        "a small handcrafted example: 34 bus stop datapoints were manually analyzed using Google Maps imagery, "
        "accepted by project admin Jack Lenga, and coded for visible shade conditions at the passenger waiting area. The goal is to support "
        "transportation planning, accessibility research, resilience initiatives, and public understanding of "
        "the rider experience.\n\n"
        "By identifying which stops provide meaningful shade and which do not, a shade study can help highlight "
        "opportunities for shelter installation, vegetation, maintenance, and other improvements that make "
        "transit more comfortable and accessible for riders. Research on thermal comfort at bus stops has shown "
        "that the waiting environment plays an important role in how riders perceive public transportation."
    ),
    "shade_method": (
        "Classifications should describe visible shade reaching the passenger waiting area, not merely nearby "
        "trees or structures. The waiting area is the place where a passenger would reasonably stand or sit "
        "while waiting for transit, including benches when present. Code what visibly shades the waiting area, "
        "not what might shade it at another time.\n\n"
        "Manual review records separate fields for `shade_coverage` and `shade_sources`. The derived "
        "`shading` field mirrors the coverage code for coloring, filtering, summaries, and public display.\n\n"
        "Shade coverage definitions: `No Shade` means no shade visibly reaches the waiting area; `Limited Shade` "
        "means shade visibly reaches part of the waiting area, but does not cover most of it; `Significant Shade` "
        "means shade visibly covers most of the waiting area or seating area.\n\n"
        "Shade source definitions: `Natural` means trees, palms, hedges, or other vegetation visibly shade "
        "the waiting area; `Constructed` means a designated, purpose-built bus shelter, awning, canopy, "
        "overhang, or similar passenger shelter visibly shades the waiting area; `Manmade` means a nearby "
        "building or other non-shelter built feature visibly shades the waiting area.\n\n"
        "Trees, utility poles, signs, and nearby buildings should not be classified as `Constructed` unless "
        "they are clearly intended to provide passenger shade or weather protection. Nearby buildings that "
        "visibly shade the waiting area should be coded as `Manmade`. Store raw labels and consensus labels "
        "so future reviewers can reproduce decisions."
    ),
    "data_sources": (
        "- Hillsborough Area Regional Transit (HART) GTFS stops and routes\n"
        "- Tampa/HART starter shade review sample: 34 manually analyzed and admin-accepted bus stop datapoints\n"
        "- Google Maps imagery used for manual waiting-area shade review\n"
        "- Expert, field-audit, imported, or community-submitted shade labels\n"
        "- Optional project-specific attributes and GIS overlays"
    ),
    "contributors": "Project team, reviewers, and community contributors",
    "citation": (
        "Dataset release:\n"
        "    Shade Study Builder contributors. (2026). Tampa/HART starter shade review sample (Version 0.1.0) [Data set]. Shade-GIS.\n"
        "    Author or Organization. (Year). Title of local shade study release (Version number) [Data set]. Publisher. URL"
    ),
    "bibliography": (
        "Works referenced:\n"
        "    Google. (n.d.). Google Maps imagery [Map and street-level imagery]. Retrieved July 2, 2026, from https://www.google.com/maps\n"
        "    Hillsborough Area Regional Transit. (Year). General Transit Feed Specification (GTFS) data feed [Data set]. Retrieved June 17, 2026, from the HART GTFS feed.\n"
        "    Lanza, K., & Durand, C. P. (2021). Heat-moderating effects of bus stop shelters and tree shade on public transport ridership. International Journal of Environmental Research and Public Health, 18(2), 463. https://doi.org/10.3390/ijerph18020463\n"
        "    Briant, S., Cushing, D. F., Washington, T., Pham, K., Pemasiri Hewa Thondilege, A. S., White, K. M., ... & Fookes, C. (2026). Thermal comfort at bus stops in a subtropical context: Investigating perceptions and satisfaction levels while waiting for the bus. In Human-Building Interaction: The Nexus of Architecture, Building Science and Interaction Design (pp. 119-145). Springer Nature Switzerland.\n"
        "    Author, A. A., & Author, B. B. (Year). Title of article. Title of Journal, volume(issue), page range. https://doi.org/xxxxx"
    ),
    "limitations": (
        "The bundled starter data is a demonstration sample, not a complete published shade inventory. "
        "Google Maps image dates, camera angle, season, time of day, temporary obstructions, incomplete "
        "street-level coverage, and reviewer uncertainty can all affect visible shade labels. Published "
        "releases should document these limitations and perform a project-specific review before use."
    ),
    "release_history": "- 0.1.0: Draft project configuration with Tampa/HART starter dataset and 34 manually reviewed, admin-accepted example datapoints",
}

REVIEW_STATUS_COLORS = {
    "Unlabeled": [148, 163, 184],
    "Needs Review": [234, 179, 8],
    "Crowd Reviewed": [45, 212, 191],
    "Expert Reviewed": [59, 130, 246],
    "Accepted": [34, 197, 94],
    "Disputed": [239, 68, 68],
    "Archived": [107, 114, 128],
}

REVIEW_QUEUE_DEFAULT_STATUSES = ["Needs Review", "Disputed", "Unlabeled"]
REVIEW_ACTION_OPTIONS = [
    "Accept current label",
    "Expert override",
    "Mark disputed",
    "Resolve dispute",
    "Archive",
]
REVIEW_ACTION_STATUS_DEFAULTS = {
    "Accept current label": "Accepted",
    "Expert override": "Expert Reviewed",
    "Mark disputed": "Disputed",
    "Resolve dispute": "Accepted",
    "Archive": "Archived",
}

MANUAL_ENTRY_COLUMNS = REQUIRED_STOP_FIELDS + [
    "agency",
    "routes",
    "municipality",
    "shading",
    "review_status",
    "confidence",
]

LABEL_SOURCE_OPTIONS = [
    "Expert review",
    "Crowdsourcing",
    "Field audit",
    "Imported dataset",
    "LLM-assisted suggestion",
    "Manual review",
]

LABELER_ROLE_OPTIONS = [
    "Reviewer",
    "Contributor",
    "Project Admin",
    "Expert",
    "Public",
    "Model",
]

SHADE_SOURCE_OPTIONS = list(CORE_SHADE_SOURCE_OPTIONS)

SHADE_COVERAGE_OPTIONS = list(CORE_SHADE_COVERAGE_OPTIONS)


def rgb_to_hex(value: list[int]) -> str:
    rgb = [max(0, min(255, int(channel))) for channel in value[:3]]
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def load_seed_dataset(taxonomy: list[dict[str, Any]], project: dict[str, Any]) -> pd.DataFrame:
    if not DATA_PATH.exists():
        return pd.DataFrame(columns=REQUIRED_STOP_FIELDS)
    stops = pd.read_csv(DATA_PATH, dtype={"stop_id": str})
    if SHADE_DATA_PATH.exists():
        shade = pd.read_csv(SHADE_DATA_PATH, dtype={"stop_id": str})
        keep_cols = [column for column in shade.columns if column != "stop_name"]
        stops = stops.merge(shade.loc[:, keep_cols], on="stop_id", how="left")
    return prepare_stop_dataset(stops, project, taxonomy)


def empty_stop_dataset() -> pd.DataFrame:
    return pd.DataFrame(columns=REQUIRED_STOP_FIELDS + OPTIONAL_FIELDS + ["priority_score"])


def with_default_project_values(project: dict[str, Any]) -> dict[str, Any]:
    merged = DEFAULT_PROJECT.copy()
    merged.update(project or {})
    return merged


def with_default_methodology_values(methodology: dict[str, Any]) -> dict[str, Any]:
    merged = DEFAULT_METHODOLOGY.copy()
    merged.update(methodology or {})
    return merged


def with_default_visualization_values(visualization: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(DEFAULT_VISUALIZATION))
    merged.update(visualization or {})
    return merged


def ensure_visualization_defaults() -> None:
    visualization = st.session_state["visualization"]
    if "custom_charts" not in visualization and isinstance(visualization.get("custom_chart"), dict):
        visualization["custom_charts"] = [visualization["custom_chart"]]
    for key, value in DEFAULT_VISUALIZATION.items():
        visualization.setdefault(key, json.loads(json.dumps(value)))
    metric_cards = visualization.setdefault("metric_cards", [])
    for label in DEFAULT_VISUALIZATION["metric_cards"]:
        if label not in metric_cards:
            metric_cards.append(label)

    review_colors = visualization.setdefault("review_status_colors", {})
    for status, color in REVIEW_STATUS_COLORS.items():
        review_colors.setdefault(status, rgb_to_hex(color))

    priority_colors = visualization.setdefault("priority_colors", {})
    for key, color in DEFAULT_VISUALIZATION["priority_colors"].items():
        priority_colors.setdefault(key, color)

    clean_gis_overlays(visualization)
    visualization["voting"] = normalize_voting_config(
        visualization.get("voting"),
        st.session_state.get("taxonomy", []),
    )


def create_seed_project() -> str:
    project = DEFAULT_PROJECT.copy()
    taxonomy = [item.copy() for item in DEFAULT_TAXONOMY]
    methodology = DEFAULT_METHODOLOGY.copy()
    visualization = json.loads(json.dumps(DEFAULT_VISUALIZATION))
    stops = load_seed_dataset(taxonomy, project)
    import_log = [
        {
            "source": "Seed Tampa GTFS and shade CSV",
            "format": "CSV",
            "rows": len(stops),
            "imported_at": timestamp_with_timezone(),
        }
    ]
    return create_project(project, taxonomy, methodology, visualization, stops, import_log)


def load_project_into_session(project_id: str) -> None:
    bundle = load_project_bundle(project_id)
    project = with_default_project_values(bundle["project"])
    taxonomy = normalize_coverage_taxonomy(bundle["taxonomy"] or DEFAULT_TAXONOMY)
    methodology = with_default_methodology_values(bundle["methodology"])
    visualization = with_default_visualization_values(bundle["visualization"])
    stops = bundle["stops"]
    if stops.empty:
        stops = empty_stop_dataset()
    else:
        stops = prepare_stop_dataset(stops, project, taxonomy)

    st.session_state["active_project_id"] = project_id
    st.session_state["loaded_project_id"] = project_id
    st.session_state["project"] = project
    st.session_state["taxonomy"] = taxonomy
    st.session_state["methodology"] = methodology
    st.session_state["visualization"] = visualization
    st.session_state["stops"] = stops
    st.session_state["import_log"] = bundle["import_log"]
    ensure_visualization_defaults()


def save_active_project_to_store() -> None:
    project_id = st.session_state.get("active_project_id")
    if not project_id:
        return
    save_project_bundle(
        project_id,
        st.session_state.get("project", DEFAULT_PROJECT.copy()),
        st.session_state.get("taxonomy", [item.copy() for item in DEFAULT_TAXONOMY]),
        st.session_state.get("methodology", DEFAULT_METHODOLOGY.copy()),
        st.session_state.get("visualization", json.loads(json.dumps(DEFAULT_VISUALIZATION))),
        st.session_state.get("stops", empty_stop_dataset()),
        st.session_state.get("import_log", []),
    )


def create_blank_project(name: str) -> str:
    project = DEFAULT_PROJECT.copy()
    project.update(
        {
            "name": name.strip() or "Untitled Shade Study",
            "agency": "",
            "region": "",
            "description": "A reusable bus stop shade study project.",
            "dataset_version": "draft",
            "methodology_version": "draft",
            "source_name": "",
            "source_license": "",
            "source_url": "",
        }
    )
    return create_project(
        project,
        [item.copy() for item in DEFAULT_TAXONOMY],
        DEFAULT_METHODOLOGY.copy(),
        json.loads(json.dumps(DEFAULT_VISUALIZATION)),
        empty_stop_dataset(),
        [],
    )


def ensure_state() -> None:
    init_database()
    projects = list_projects()
    if not projects:
        create_seed_project()
        projects = list_projects()

    active_project_id = st.session_state.get("active_project_id") or projects[0]["id"]
    known_ids = {project["id"] for project in projects}
    if active_project_id not in known_ids:
        active_project_id = projects[0]["id"]

    if st.session_state.get("loaded_project_id") != active_project_id:
        load_project_into_session(active_project_id)
        return

    current_taxonomy = st.session_state.get("taxonomy", DEFAULT_TAXONOMY)
    normalized_taxonomy = normalize_coverage_taxonomy(current_taxonomy)
    if current_taxonomy != normalized_taxonomy:
        st.session_state["taxonomy"] = normalized_taxonomy
        stops = st.session_state.get("stops", empty_stop_dataset())
        if not stops.empty:
            st.session_state["stops"] = prepare_stop_dataset(
                stops,
                st.session_state.get("project", DEFAULT_PROJECT),
                normalized_taxonomy,
            )
    ensure_visualization_defaults()


def dataframe_to_geojson(df: pd.DataFrame) -> str:
    features = []
    for _, row in df.iterrows():
        properties = row.drop(labels=["stop_lat", "stop_lon"], errors="ignore").to_dict()
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(row["stop_lon"]), float(row["stop_lat"])]},
                "properties": {key: (None if pd.isna(value) else value) for key, value in properties.items()},
            }
        )
    return json.dumps({"type": "FeatureCollection", "features": features}, indent=2)


def study_config_json() -> str:
    return json.dumps(study_config_payload(), indent=2, default=str)


def study_config_payload() -> dict[str, Any]:
    return {
        "study_id": st.session_state.get("active_project_id")
        or slugify_repo_name(st.session_state["project"].get("name", "shade-study")),
        "project": st.session_state["project"],
        "taxonomy": st.session_state["taxonomy"],
        "methodology": st.session_state["methodology"],
        "visualization": st.session_state["visualization"],
        "import_log": st.session_state["import_log"],
    }


def active_raw_labels() -> pd.DataFrame:
    project_id = st.session_state.get("active_project_id")
    if not project_id:
        return pd.DataFrame()
    return list_shade_labels(project_id)


def slugify_repo_name(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", str(value or "").strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip(".-_")
    return slug or "shade-study-app"


def github_new_repo_url(project: dict[str, Any], repo_name: str) -> str:
    params = {
        "name": slugify_repo_name(repo_name),
        "description": f"{project.get('name', 'Shade study')} Streamlit app",
        "visibility": "public" if project.get("visibility") == "Public" else "private",
    }
    return "https://github.com/new?" + urllib.parse.urlencode(params)


PUBLISHED_APP_SOURCE_PATH = APP_DIR / "published_app.py"
PUBLIC_VOTING_SOURCE_PATH = APP_DIR / "public_voting.py"


def published_app_source() -> str:
    return PUBLISHED_APP_SOURCE_PATH.read_text(encoding="utf-8")


def public_voting_source() -> str:
    return PUBLIC_VOTING_SOURCE_PATH.read_text(encoding="utf-8")


def deploy_readme(repo_name: str, project: dict[str, Any], deploy_mode: str = "existing") -> str:
    app_name = project.get("name", "Shade Study")
    folder_name = slugify_repo_name(repo_name.rstrip("/").split("/")[-1].replace(".git", ""))
    if deploy_mode == "create":
        publish_intro = "create the target repository used for this bundle"
        verification_line = ""
        publish_command = f'./deploy_to_github.ps1 -Mode create -RepositoryName "{repo_name}" -Branch "main" -Visibility private'
    else:
        publish_intro = "publish into the target repository used for this bundle"
        verification_line = f'gh repo view "{repo_name}"\n'
        publish_command = f'./deploy_to_github.ps1 -Mode existing -RepositoryName "{repo_name}" -Branch "main"'
    return f"""# {app_name}

This repository was generated by Shade Study Builder. It contains a published Streamlit app rendered from the builder state at export time.

## Files

- `app.py`: public Streamlit app.
- `public_voting.py`: voting interface and SQLite/PostgreSQL vote storage.
- `shade_study_stops.csv`: published stop dataset.
- `shade_study_raw_labels.csv`: raw submitted labels, included when labels have been collected.
- `shade_study_config.json`: project metadata, methodology, taxonomy, visualization settings, uploaded GIS overlays, and import log.
- `requirements.txt`: Python dependencies for Streamlit deployment.

## Crowd Voting Storage

If voting is enabled in the builder, visitors can submit one coverage assessment plus zero or more
shade-source checkboxes per browser session and stop. The app keeps the community result separate
from the admin-reviewed stop dataset, and the configured threshold controls when a unique leading
coverage status is reported.

The app works locally with a generated `.shade_gis_votes.sqlite3` database. A hosted app should use
a shared PostgreSQL database so votes survive app restarts and remain consistent across instances.
Add this secret in the Streamlit deployment settings; do not commit it to Git:

```toml
SHADE_GIS_VOTE_DATABASE_URL = "postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require"
```

The `shade_votes` table is created automatically. Without that secret, Streamlit Community Cloud
uses the local SQLite fallback, whose files are ephemeral and may be lost when the app restarts.

## After Downloading The Zip

1. Click the download button. By default, your browser should save the bundle to your Downloads folder as `{folder_name}.zip`.
2. Open PowerShell and run this one copy-paste block to {publish_intro}:

```powershell
$BundleName = "{folder_name}.zip"
$ZipPath = Join-Path (Join-Path $env:USERPROFILE "Downloads") $BundleName
$ExtractTo = Join-Path (Join-Path $env:USERPROFILE "Documents") "{folder_name}"
if (-not (Test-Path $ZipPath)) {{
    throw "Expected the deploy bundle at $ZipPath. If your browser saved it somewhere else, move it to Downloads or update `$ZipPath."
}}
Expand-Archive -Path $ZipPath -DestinationPath $ExtractTo -Force
Set-Location $ExtractTo
if (-not (Test-Path ".\\deploy_to_github.ps1")) {{
    throw "deploy_to_github.ps1 was not found. Check that `$ExtractTo points to the extracted deploy bundle folder, then run Set-Location `$ExtractTo."
}}
git --version
gh auth status
{verification_line}{publish_command}
```

If GitHub CLI is not authenticated, run:

```powershell
gh auth login
```

Then rerun the one copy-paste block above.
If GitHub reports that it "Could not resolve to a Repository", check the exact `OWNER/REPO` value and run `gh auth status` plus `gh repo view OWNER/REPO` to confirm the signed-in account has access to that private repository.

## Publish To GitHub

Create a new GitHub repository named `{repo_name}` and push these files:

```powershell
./deploy_to_github.ps1 -Mode create -RepositoryName "{repo_name}" -Branch "main" -Visibility private
```

Or publish into a pre-existing private repository:

```powershell
./deploy_to_github.ps1 -Mode existing -RepositoryName "{repo_name}" -Branch "main"
```

The script requires Git and the GitHub CLI (`gh`) with an authenticated account.
For existing private repositories, the authenticated account must already have access to the target repository.
If Windows blocks the downloaded script, run `Unblock-File .\\deploy_to_github.ps1` once and retry.
Before committing, the script prints `git status`, `git diff --stat`, and a staged diff summary, then asks you to type `PUBLISH`. Add `-Yes` only when you intentionally want non-interactive publishing.

## What The Publish Script Does

For a new repository, the helper initializes Git in the extracted bundle, stages only generated app files, commits those files, creates the GitHub repository, and pushes the branch. Public repository creation is blocked unless you explicitly add `-AllowPublicTarget`.

For an existing private repository, the helper verifies repository visibility when it can, clones the target repository into a temporary `_shade_gis_publish_*` folder under PowerShell's temp path, checks out the requested branch, copies only generated app/runtime files into that checkout, commits any changes, pushes back to GitHub, and cleans up the temporary folder. Your existing repository history is preserved. Protected files such as `.git/`, `.github/`, `README.md`, `LICENSE`, `.env*`, and `secrets.toml` are not copied in existing-repository mode.

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud

After the repository is on GitHub, create a Streamlit Community Cloud app with:

- repository: `{repo_name}`
- branch: `main`
- main file path: `app.py`
"""


def deploy_script(repo_name: str) -> str:
    return f"""param(
    [Alias("TargetRepo")]
    [string]$RepositoryName = "{repo_name}",
    [ValidateSet("public", "private")]
    [string]$Visibility = "private",
    [ValidateSet("create", "existing")]
    [string]$Mode = "create",
    [string]$RepositoryUrl = "",
    [string]$Branch = "main",
    [switch]$Yes,
    [switch]$AllowPublicTarget
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {{
    throw "Git is not installed or not on PATH."
}}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {{
    throw "GitHub CLI is not installed or not on PATH."
}}

if ($Visibility -eq "public" -and -not $AllowPublicTarget) {{
    throw "Refusing to create a public repository without -AllowPublicTarget. Re-run with -Visibility private or add -AllowPublicTarget."
}}

function Invoke-Native {{
    param(
        [string]$Command,
        [string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {{
        throw "$Command $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }}
}}

function Invoke-NativeOutput {{
    param(
        [string]$Command,
        [string[]]$Arguments
    )
    $output = & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {{
        throw "$Command $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }}
    return $output
}}

function Get-RemoteUrl {{
    if ($RepositoryUrl.Trim()) {{
        return $RepositoryUrl.Trim()
    }}
    if ($RepositoryName -match "^https?://") {{
        return $RepositoryName
    }}
    return "https://github.com/$RepositoryName.git"
}}

function Get-RepositorySlug {{
    $candidate = $RepositoryName
    if ($RepositoryUrl.Trim()) {{
        $candidate = $RepositoryUrl.Trim()
    }}
    if ($candidate -match "github\\.com[:/](?<owner>[^/]+)/(?<repo>[^/]+?)(\\.git)?$") {{
        return "$($Matches.owner)/$($Matches.repo)"
    }}
    if ($candidate -match "^[^/]+/[^/]+$") {{
        return $candidate
    }}
    return ""
}}

function Assert-PrivateExistingRepository {{
    $repoSlug = Get-RepositorySlug
    if (-not $repoSlug) {{
        Write-Warning "Could not verify repository visibility from '$RepositoryName'. Repository visibility controls who can see the published app files."
        return
    }}
    try {{
        $repoVisibility = (Invoke-NativeOutput "gh" @("repo", "view", $repoSlug, "--json", "visibility", "--jq", ".visibility") | Out-String).Trim().ToLowerInvariant()
    }} catch {{
        throw "Could not access GitHub repository '$repoSlug'. Confirm the OWNER/REPO spelling, that the repository exists, and that 'gh auth status' is authenticated to an account with access. Original error: $($_.Exception.Message)"
    }}
    if ($repoVisibility -ne "private" -and -not $AllowPublicTarget) {{
        throw "Target repository $repoSlug is '$repoVisibility'. Re-run with a private repository or add -AllowPublicTarget to publish there intentionally."
    }}
    Write-Host "Verified target repository visibility: $repoVisibility"
}}

function Confirm-Publish {{
    param([string]$Message)
    if ($Yes) {{
        return
    }}
    $answer = Read-Host "$Message Type PUBLISH to continue"
    if ($answer -ne "PUBLISH") {{
        throw "Publishing cancelled."
    }}
}}

function Show-ProtectedFileWarnings {{
    $protectedPaths = @(
        ".git",
        ".github",
        "README.md",
        "LICENSE",
        ".env",
        "secrets.toml",
        ".streamlit/secrets.toml"
    )
    foreach ($path in $protectedPaths) {{
        if (Test-Path $path) {{
            Write-Host "Protected file will not be copied in existing-repository mode: $path"
        }}
    }}
    Get-ChildItem -Path . -Force -File -Filter ".env.*" | ForEach-Object {{
        Write-Host "Protected file will not be copied in existing-repository mode: $($_.Name)"
    }}
}}

function Copy-SafeBundleFiles {{
    param([string]$Destination)
    $items = @(
        "app.py",
        "public_voting.py",
        "shade_study_stops.csv",
        "shade_study_raw_labels.csv",
        "shade_study_config.json",
        "requirements.txt",
        ".streamlit/config.toml"
    )
    Show-ProtectedFileWarnings
    foreach ($item in $items) {{
        if (Test-Path $item -PathType Leaf) {{
            $destinationPath = Join-Path $Destination $item
            $destinationParent = Split-Path -Parent $destinationPath
            if ($destinationParent -and -not (Test-Path $destinationParent)) {{
                New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
            }}
            if (Test-Path $destinationPath) {{
                Write-Host "Updating generated file: $item"
            }} else {{
                Write-Host "Adding generated file: $item"
            }}
            Copy-Item -LiteralPath $item -Destination $destinationPath -Force
        }}
    }}
}}

function Stage-PublishFiles {{
    param([string[]]$Paths)
    foreach ($path in $Paths) {{
        if (Test-Path $path) {{
            Invoke-Native "git" @("add", "--", $path)
        }}
    }}
}}

function Commit-And-Push {{
    param(
        [string]$TargetBranch,
        [string[]]$Paths,
        [switch]$SkipPush
    )
    Write-Host "Repository status before commit:"
    Invoke-Native "git" @("status")
    Write-Host "Working tree diff summary:"
    Invoke-Native "git" @("diff", "--stat")
    Stage-PublishFiles -Paths $Paths
    Write-Host "Staged diff summary:"
    Invoke-Native "git" @("diff", "--cached", "--stat")
    $stagedChanges = Invoke-NativeOutput "git" @("diff", "--cached", "--name-only")
    if (-not $stagedChanges) {{
        Write-Host "No changes to publish."
        return
    }}
    Confirm-Publish "Review the status and diff summary for branch '$TargetBranch'."
    Invoke-Native "git" @("commit", "-m", "Publish shade study app")
    if (-not $SkipPush) {{
        Invoke-Native "git" @("push", "origin", $TargetBranch)
    }}
}}

if ($Mode -eq "existing") {{
    Assert-PrivateExistingRepository
    $remoteUrl = Get-RemoteUrl
    $publishDir = Join-Path $env:TEMP ("_shade_gis_publish_" + [guid]::NewGuid().ToString("N"))
    $existingPublishFiles = @(
        "app.py",
        "public_voting.py",
        "shade_study_stops.csv",
        "shade_study_raw_labels.csv",
        "shade_study_config.json",
        "requirements.txt",
        ".streamlit/config.toml"
    )
    try {{
        if ($RepositoryUrl.Trim() -or $RepositoryName -match "^https?://") {{
            Invoke-Native "git" @("clone", $remoteUrl, $publishDir)
        }} else {{
            Invoke-Native "gh" @("repo", "clone", $RepositoryName, $publishDir)
        }}
        if (-not (Test-Path $publishDir)) {{
            throw "Clone command completed but publish directory was not created: $publishDir"
        }}
        Push-Location $publishDir
        try {{
            try {{
                Invoke-Native "git" @("checkout", $Branch)
            }} catch {{
                Invoke-Native "git" @("checkout", "-b", $Branch)
            }}
        }} finally {{
            Pop-Location
        }}
        Copy-SafeBundleFiles -Destination $publishDir
        Push-Location $publishDir
        try {{
            Commit-And-Push -TargetBranch $Branch -Paths $existingPublishFiles
        }} finally {{
            Pop-Location
        }}
        Write-Host "Published to existing repository $RepositoryName on branch $Branch."
    }} finally {{
        if ($publishDir -and (Test-Path $publishDir)) {{
            Remove-Item -LiteralPath $publishDir -Recurse -Force
        }}
    }}
    exit 0
}}

if (-not (Test-Path ".git")) {{
    Invoke-Native "git" @("init")
    Invoke-Native "git" @("branch", "-M", $Branch)
}}

$newRepoFiles = @(
    "app.py",
    "public_voting.py",
    "shade_study_stops.csv",
    "shade_study_raw_labels.csv",
    "shade_study_config.json",
    "requirements.txt",
    "README.md",
    "deploy_to_github.ps1",
    ".gitignore",
    ".streamlit/config.toml"
)
Commit-And-Push -TargetBranch $Branch -Paths $newRepoFiles -SkipPush
Invoke-Native "gh" @("repo", "create", $RepositoryName, "--$Visibility", "--source=.", "--remote=origin", "--push")
"""


def build_github_deploy_bundle(repo_name: str, deploy_mode: str = "existing") -> bytes:
    stops = st.session_state["stops"].copy()
    stops["priority_score"] = calculate_priority_scores(stops, st.session_state["visualization"]["priority_weights"])
    config_json = study_config_json()
    raw_labels = active_raw_labels()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("app.py", published_app_source())
        bundle.writestr("public_voting.py", public_voting_source())
        bundle.writestr("shade_study_stops.csv", stops.to_csv(index=False))
        bundle.writestr("shade_study_config.json", config_json)
        if not raw_labels.empty:
            bundle.writestr("shade_study_raw_labels.csv", raw_labels.to_csv(index=False))
        bundle.writestr(
            "requirements.txt",
            "streamlit>=1.57,<2\npandas>=2,<4\npydeck>=0.8,<1\npsycopg[binary]>=3.2,<4\n",
        )
        bundle.writestr(".streamlit/config.toml", "[server]\nheadless = true\n\n[browser]\ngatherUsageStats = false\n")
        bundle.writestr(
            ".gitignore",
            "__pycache__/\n*.pyc\n*.sqlite3\n.streamlit/secrets.toml\n_shade_gis_publish_*/\n",
        )
        bundle.writestr("README.md", deploy_readme(repo_name, st.session_state["project"], deploy_mode))
        bundle.writestr("deploy_to_github.ps1", deploy_script(repo_name))
    return buffer.getvalue()


def validation_summary(df: pd.DataFrame) -> pd.DataFrame:
    checks = [
        ("Stops ready for mapping", len(df)),
        ("Duplicate stop IDs removed", int(df["stop_id"].duplicated().sum()) if "stop_id" in df else 0),
        ("Missing coordinates", int(df[["stop_lat", "stop_lon"]].isna().any(axis=1).sum()) if not df.empty else 0),
        ("Stops needing review", int((df.get("shading") == "Needs Review").sum()) if not df.empty else 0),
        ("Stops with route metadata", int((df.get("routes", "") != "").sum()) if not df.empty else 0),
    ]
    return pd.DataFrame(checks, columns=["Check", "Value"])


def set_page(page: str) -> None:
    st.session_state["page"] = page


def render_header() -> str:
    pages = ["Data", "Labels", "Visuals", "Voting", "Docs", "Preview", "Deploy"]
    if st.session_state.get("page") not in pages:
        st.session_state["page"] = "Data"
    st.markdown(
        """
        <style>
        .builder-topbar {
            border-bottom: 1px solid #e5e7eb;
            margin: -1rem -1rem 1.2rem;
            padding: 0.9rem 1.4rem 1.1rem;
        }
        .builder-brand {
            color: #14532d;
            font-size: 2.85rem;
            font-weight: 800;
            letter-spacing: 0;
            line-height: 1.08;
            white-space: nowrap;
        }
        .builder-topbar .stButton button {
            border-radius: 999px;
            font-size: 1.2rem;
            min-height: 3.05rem;
            font-weight: 680;
            padding: 0.5rem 1rem;
            white-space: nowrap;
            width: 100%;
        }
        .builder-topbar .stButton button p {
            white-space: nowrap;
        }
        .builder-topbar .stButton button[kind="primary"] {
            background: #ff4b4b;
            border-color: #ff4b4b;
            color: white;
        }
        .builder-topbar .stButton button[kind="secondary"] {
            background: white;
            border-color: #d1d5db;
            color: #31333f;
        }
        h1 {
            font-size: 1.85rem;
            line-height: 1.15;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div class='builder-topbar'>", unsafe_allow_html=True)
    cols = st.columns([3.1, 0.35, 0.9, 0.9, 1, 0.9, 0.9, 0.9, 0.9], gap="small", vertical_alignment="center")
    with cols[0]:
        st.markdown("<div class='builder-brand'>Shade-GIS</div>", unsafe_allow_html=True)
    for index, page in enumerate(pages, start=2):
        with cols[index]:
            st.button(
                page,
                key=f"nav_{page}",
                type="primary" if st.session_state["page"] == page else "secondary",
                width="stretch",
                on_click=set_page,
                args=(page,),
            )
    st.markdown("</div>", unsafe_allow_html=True)
    return st.session_state["page"]


def main() -> None:
    from shade_gis.pages.data_page import render_data_page
    from shade_gis.pages.deploy_page import render_deploy_page
    from shade_gis.pages.docs_page import render_methodology_page
    from shade_gis.pages.labels_page import render_labels_page
    from shade_gis.pages.preview_page import render_preview_page
    from shade_gis.pages.visuals_page import render_visuals_page
    from shade_gis.pages.voting_page import render_voting_page

    st.set_page_config(page_title=APP_TITLE, layout="wide")
    ensure_state()
    if st.session_state.get("page") in {"Methodology", "Methods"}:
        st.session_state["page"] = "Docs"
    page = render_header()
    if page == "Labels":
        render_labels_page()
    elif page == "Visuals":
        render_visuals_page()
    elif page == "Voting":
        render_voting_page()
    elif page == "Docs":
        render_methodology_page()
    elif page == "Preview":
        render_preview_page()
    elif page == "Deploy":
        render_deploy_page()
    else:
        render_data_page()
    save_active_project_to_store()

