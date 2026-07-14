import html
import hashlib
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

# Keep ordinary strings as Python objects. Streamlit serializes every dataframe
# through PyArrow; pandas extension-string arrays have caused process-fatal
# native crashes at that boundary in CI.
pd.options.future.infer_string = False

import published_app
from builder_about_page import render_builder_about_page
from public_voting import normalize_voting_config
from platform_store import (
    add_review_event,
    add_shade_label,
    create_project,
    database_status,
    init_database,
    list_images,
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
    agreement_overview_metrics,
    agreement_metric_summary,
    average_pairwise_cohen_kappa,
    category_count_matrix,
    clean_label_values,
    cohen_kappa_for_pair,
    disagreement_queue_table,
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
from shade_gis.deployment import (
    DEFAULT_DEPLOY_COMMIT_MESSAGE,
    normalize_deploy_commit_message,
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


def normalized_visualization_values(
    visualization: dict[str, Any], taxonomy: list[dict[str, Any]]
) -> dict[str, Any]:
    visualization = with_default_visualization_values(
        json.loads(json.dumps(visualization or {}, default=str))
    )
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
        taxonomy,
    )
    return visualization


def ensure_visualization_defaults() -> None:
    st.session_state["visualization"] = normalized_visualization_values(
        st.session_state["visualization"],
        st.session_state.get("taxonomy", []),
    )


def create_seed_project() -> str:
    project = DEFAULT_PROJECT.copy()
    taxonomy = [item.copy() for item in DEFAULT_TAXONOMY]
    methodology = DEFAULT_METHODOLOGY.copy()
    visualization = json.loads(json.dumps(DEFAULT_VISUALIZATION))
    stops = load_seed_dataset(taxonomy, project)
    test_seed_limit = os.environ.get("SHADE_GIS_TEST_MAX_SEED_ROWS", "").strip()
    if test_seed_limit:
        try:
            limit = max(int(test_seed_limit), 1)
        except ValueError:
            limit = len(stops)
        stops = stops.head(limit).copy()
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
    if os.environ.get("SHADE_GIS_TEST_DISABLE_AUTO_SAVE", "").strip() == "1":
        return
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


def _canonical_deployment_state(
    project_id: str,
    project: dict[str, Any],
    taxonomy: list[dict[str, Any]],
    methodology: dict[str, Any],
    visualization: dict[str, Any],
    stops: pd.DataFrame,
    import_log: list[dict[str, Any]],
) -> str:
    normalized_project = with_default_project_values(project)
    normalized_taxonomy = normalize_coverage_taxonomy(taxonomy)
    normalized_methodology = with_default_methodology_values(methodology)
    normalized_visualization = normalized_visualization_values(visualization, normalized_taxonomy)
    normalized_stops = stops.copy()
    if not normalized_stops.empty:
        normalized_stops = prepare_stop_dataset(normalized_stops, normalized_project, normalized_taxonomy)
    if not normalized_stops.empty:
        normalized_stops = normalized_stops.reindex(sorted(normalized_stops.columns), axis=1)
        if "stop_id" in normalized_stops.columns:
            normalized_stops = normalized_stops.sort_values("stop_id", kind="stable")
    payload = {
        "study_id": project_id,
        "project": normalized_project,
        "taxonomy": normalized_taxonomy,
        "methodology": normalized_methodology,
        "visualization": normalized_visualization,
        "import_log": import_log,
        "stops": normalized_stops.to_dict(orient="records"),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def deployment_session_freshness_issue() -> str:
    project_id = str(st.session_state.get("active_project_id") or "").strip()
    if not project_id:
        return "The active project is not saved yet. Save or reopen it before publishing."
    try:
        persisted = load_project_bundle(project_id)
    except KeyError:
        return "The saved project could not be found. Return to the project list and reopen it before publishing."

    current_state = _canonical_deployment_state(
        project_id,
        st.session_state.get("project", {}),
        st.session_state.get("taxonomy", []),
        st.session_state.get("methodology", {}),
        st.session_state.get("visualization", {}),
        st.session_state.get("stops", empty_stop_dataset()),
        st.session_state.get("import_log", []),
    )
    persisted_state = _canonical_deployment_state(
        project_id,
        persisted["project"],
        persisted["taxonomy"],
        persisted["methodology"],
        persisted["visualization"],
        persisted["stops"],
        persisted["import_log"],
    )
    if current_state != persisted_state:
        return (
            "This browser tab is not using the latest saved project state. Another tab or session changed the "
            "project. Reload the saved project before creating a deployment package."
        )
    return ""


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
EXISTING_REPO_PREVIEW_DIR = "preview_app"


def published_app_source() -> str:
    return PUBLISHED_APP_SOURCE_PATH.read_text(encoding="utf-8")


def public_voting_source() -> str:
    return PUBLIC_VOTING_SOURCE_PATH.read_text(encoding="utf-8")


def powershell_literal(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def streamlit_entrypoint_path(deploy_mode: str) -> str:
    if deploy_mode == "create":
        return "app.py"
    if deploy_mode == "existing":
        return f"{EXISTING_REPO_PREVIEW_DIR}/app.py"
    raise ValueError("deploy_mode must be 'create' or 'existing'")


def deploy_launcher_script(
    bundle_name: str,
    repo_name: str,
    branch: str = "main",
    deploy_mode: str = "existing",
    visibility: str = "private",
    commit_message: str = DEFAULT_DEPLOY_COMMIT_MESSAGE,
) -> str:
    if deploy_mode not in {"create", "existing"}:
        raise ValueError("deploy_mode must be 'create' or 'existing'")
    if visibility not in {"public", "private"}:
        raise ValueError("visibility must be 'public' or 'private'")
    commit_message = normalize_deploy_commit_message(commit_message)

    if deploy_mode == "existing":
        repository_verification = """        gh repo view $RepositoryName --json nameWithOwner
        if ($LASTEXITCODE -ne 0) {
            throw "GitHub repository '$RepositoryName' was not found or is not accessible."
        }
"""
        publish_command = """        & $DeployScript.FullName `
            -Mode existing `
            -RepositoryName $RepositoryName `
            -Branch $Branch `
            -CommitMessage $CommitMessage
"""
    else:
        repository_verification = ""
        allow_public = " -AllowPublicTarget" if visibility == "public" else ""
        publish_command = f"""        & $DeployScript.FullName `
            -Mode create `
            -RepositoryName $RepositoryName `
            -Branch $Branch `
            -CommitMessage $CommitMessage `
            -Visibility $Visibility{allow_public}
"""

    return f"""& {{
    Set-StrictMode -Version Latest
    $ErrorActionPreference = "Stop"

    $BundleName = {powershell_literal(bundle_name)}
    $BundlePath = ""  # Optional: paste the full ZIP path here when it is not in a standard folder.
    $RepositoryName = {powershell_literal(repo_name)}
    $Branch = {powershell_literal(branch)}
    $CommitMessage = {powershell_literal(commit_message)}
    $Visibility = {powershell_literal(visibility)}

    if ([string]::IsNullOrWhiteSpace($RepositoryName)) {{
        throw "Enter a GitHub repository before running this deployment block."
    }}

    foreach ($CommandName in @("git", "gh")) {{
        if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {{
            throw "Required command '$CommandName' was not found in PATH."
        }}
    }}

    $DownloadsDirectory = Join-Path $env:USERPROFILE "Downloads"
    $DocumentsDirectory = [Environment]::GetFolderPath("MyDocuments")
    if ([string]::IsNullOrWhiteSpace($DocumentsDirectory)) {{
        $DocumentsDirectory = Join-Path $env:USERPROFILE "Documents"
    }}
    $BundleStem = [System.IO.Path]::GetFileNameWithoutExtension($BundleName)
    $BundleNamePattern = "^" + [Regex]::Escape($BundleStem) + "( \\([0-9]+\\))?\\.zip$"

    $SearchDirectories = @(
        $DownloadsDirectory
        if ($env:OneDrive) {{ Join-Path $env:OneDrive "Downloads" }}
        $DocumentsDirectory
        (Get-Location).Path
    ) | Where-Object {{ $_ -and (Test-Path -LiteralPath $_ -PathType Container) }} | Select-Object -Unique

    $ZipCandidate = $null
    if (-not [string]::IsNullOrWhiteSpace($BundlePath)) {{
        $ExpandedBundlePath = [Environment]::ExpandEnvironmentVariables($BundlePath)
        if (-not (Test-Path -LiteralPath $ExpandedBundlePath -PathType Leaf)) {{
            throw "The deployment bundle path does not exist: $ExpandedBundlePath"
        }}
        $ZipCandidate = Get-Item -LiteralPath $ExpandedBundlePath
        if ($ZipCandidate.Extension -ne ".zip") {{
            throw "The deployment bundle must be a ZIP file: $ExpandedBundlePath"
        }}
    }} else {{
        $ZipCandidate = @($SearchDirectories | ForEach-Object {{
            Get-ChildItem -LiteralPath $_ -Filter "$BundleStem*.zip" -File -ErrorAction SilentlyContinue
        }}) |
            Where-Object {{ $_.Name -match $BundleNamePattern }} |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
    }}

    if (-not $ZipCandidate) {{
        $ShadeBundles = @($SearchDirectories | ForEach-Object {{
            Get-ChildItem -LiteralPath $_ -Filter "*shade*.zip" -File -ErrorAction SilentlyContinue
        }} | Sort-Object LastWriteTime -Descending)
        $Available = if ($ShadeBundles.Count) {{
            ($ShadeBundles.FullName -join ", ")
        }} else {{
            "none"
        }}
        $Searched = $SearchDirectories -join ", "
        throw "Could not find '$BundleName' or a numbered browser copy. Click 'Download website package' first. Searched: $Searched. Available shade ZIP files: $Available. To use another folder, set `$BundlePath at the top of this block."
    }}

    $ZipPath = $ZipCandidate.FullName
    Write-Host "Using newest deployment bundle: $($ZipCandidate.Name)"

    $BundleBaseName = [System.IO.Path]::GetFileNameWithoutExtension($ZipPath)
    $ExtractTo = Join-Path $DocumentsDirectory $BundleBaseName
    if (Test-Path -LiteralPath $ExtractTo) {{
        $ExtractTo = Join-Path $DocumentsDirectory ($BundleBaseName + "-deploy-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
    }}

    Expand-Archive -LiteralPath $ZipPath -DestinationPath $ExtractTo -Force
    $DeployScript = Get-ChildItem -LiteralPath $ExtractTo -Filter "deploy_to_github.ps1" -File -Recurse |
        Select-Object -First 1
    if (-not $DeployScript) {{
        throw "The ZIP was extracted to '$ExtractTo', but deploy_to_github.ps1 was not found anywhere inside it."
    }}

    Push-Location -LiteralPath $DeployScript.Directory.FullName
    try {{
        gh auth status
        if ($LASTEXITCODE -ne 0) {{
            throw "GitHub CLI authentication failed. Run 'gh auth login' and retry."
        }}
{repository_verification}{publish_command}        if ($LASTEXITCODE -ne 0) {{
            throw "deploy_to_github.ps1 exited with code $LASTEXITCODE."
        }}
    }} finally {{
        Pop-Location
    }}
}}"""


def deploy_readme(
    repo_name: str,
    project: dict[str, Any],
    deploy_mode: str = "existing",
    bundle_name: str = "",
    commit_message: str = DEFAULT_DEPLOY_COMMIT_MESSAGE,
) -> str:
    app_name = project.get("name", "Shade Study")
    folder_name = slugify_repo_name(repo_name.rstrip("/").split("/")[-1].replace(".git", ""))
    resolved_bundle_name = bundle_name or f"{folder_name}.zip"
    commit_message = normalize_deploy_commit_message(commit_message)
    launcher_script = deploy_launcher_script(
        resolved_bundle_name,
        repo_name,
        deploy_mode=deploy_mode,
        commit_message=commit_message,
    )
    main_file_path = streamlit_entrypoint_path(deploy_mode)
    if deploy_mode == "create":
        publish_intro = "create the target repository used for this bundle"
        published_layout = (
            "The new repository contains only this public preview app and its runtime files. "
            "It does not contain the Shade-GIS builder."
        )
    else:
        publish_intro = "publish into the target repository used for this bundle"
        published_layout = (
            f"The helper installs the public preview under `{EXISTING_REPO_PREVIEW_DIR}/` and leaves the "
            "repository's root app and Shade-GIS builder files untouched."
        )
    return f"""# {app_name}

This bundle was generated by Shade Study Builder. It contains only the public preview rendered from the builder state at export time, not the Shade-GIS builder interface.

{published_layout}

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

1. Click the download button. By default, your browser should save the content-addressed bundle as `{resolved_bundle_name}`.
   Browser-numbered copies of that exact bundle are supported automatically. Older project states have different bundle IDs and cannot be selected accidentally.
2. Open PowerShell and run this one copy-paste block to {publish_intro}:

```powershell
{launcher_script}
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
./deploy_to_github.ps1 -Mode create -RepositoryName "{repo_name}" -Branch "main" -CommitMessage {powershell_literal(commit_message)} -Visibility private
```

Or publish into a pre-existing private repository:

```powershell
./deploy_to_github.ps1 -Mode existing -RepositoryName "{repo_name}" -Branch "main" -CommitMessage {powershell_literal(commit_message)}
```

The script requires Git and the GitHub CLI (`gh`) with an authenticated account.
For existing private repositories, the authenticated account must already have access to the target repository.
If Windows blocks the downloaded script, run `Unblock-File .\\deploy_to_github.ps1` once and retry.
Before committing, the script prints `git status`, `git diff --stat`, and a staged diff summary, then asks you to type `PUBLISH`. Add `-Yes` only when you intentionally want non-interactive publishing.

## What The Publish Script Does

For a new repository, the helper initializes Git in the extracted bundle, stages only generated app files, commits those files, creates the GitHub repository, and pushes the branch. Public repository creation is blocked unless you explicitly add `-AllowPublicTarget`.

For an existing private repository, the helper verifies repository visibility when it can, clones the target repository into a temporary `_shade_gis_publish_*` folder under PowerShell's temp path, checks out the requested branch, copies only generated app/runtime files into `{EXISTING_REPO_PREVIEW_DIR}/`, commits any changes, pushes back to GitHub, and cleans up the temporary folder. Your existing repository history and root app are preserved. Protected files such as `.git/`, `.github/`, `.streamlit/`, `README.md`, `LICENSE`, `.env*`, and `secrets.toml` are not copied in existing-repository mode.

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud

After the repository is on GitHub, create a Streamlit Community Cloud app with:

- repository: `{repo_name}`
- branch: `main`
- main file path: `{main_file_path}`
"""


def deploy_script(
    repo_name: str,
    commit_message: str = DEFAULT_DEPLOY_COMMIT_MESSAGE,
) -> str:
    commit_message = normalize_deploy_commit_message(commit_message)
    return f"""param(
    [Alias("TargetRepo")]
    [string]$RepositoryName = "{repo_name}",
    [string]$Visibility = "private",
    [ValidateSet("create", "existing")]
    [string]$Mode = "create",
    [string]$RepositoryUrl = "",
    [string]$Branch = "main",
    [string]$CommitMessage = {powershell_literal(commit_message)},
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

function Invoke-Native {{
    param(
        [string]$Command,
        [string[]]$Arguments
    )
    & $Command @Arguments | Out-Host
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

function Assert-DeploymentBundle {{
    $manifestPath = Join-Path (Get-Location) "deployment_manifest.json"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {{
        throw "deployment_manifest.json is missing. Download a fresh deployment package from Shade-GIS."
    }}
    try {{
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    }} catch {{
        throw "deployment_manifest.json is invalid: $($_.Exception.Message)"
    }}
    if ([int]$manifest.schema_version -ne 1) {{
        throw "Unsupported deployment manifest version '$($manifest.schema_version)'. Download a fresh package."
    }}
    $expectedRepository = ($RepositoryName.Trim() -replace "\\.git$", "")
    if ([string]$manifest.repository -ne $expectedRepository) {{
        throw "This bundle targets '$($manifest.repository)', not '$expectedRepository'. Download a package for the selected repository."
    }}
    if ([string]$manifest.deploy_mode -ne $Mode) {{
        throw "This bundle was created for '$($manifest.deploy_mode)' mode, not '$Mode'. Download a matching package."
    }}
    if ([string]$manifest.commit_message -ne $CommitMessage) {{
        throw "This bundle was created with a different commit message. Download a package using the current deployment settings."
    }}
    foreach ($fileProperty in $manifest.files.PSObject.Properties) {{
        $relativePath = [string]$fileProperty.Name
        if ([IO.Path]::IsPathRooted($relativePath) -or $relativePath -match '(^|[\\/])\\.\\.([\\/]|$)') {{
            throw "Unsafe file path in deployment manifest: $relativePath"
        }}
        if (-not (Test-Path -LiteralPath $relativePath -PathType Leaf)) {{
            throw "The deployment package is incomplete; '$relativePath' is missing."
        }}
        $actualHash = (Get-FileHash -LiteralPath $relativePath -Algorithm SHA256).Hash.ToLowerInvariant()
        $expectedHash = ([string]$fileProperty.Value).ToLowerInvariant()
        if ($actualHash -ne $expectedHash) {{
            throw "The deployment package is stale or damaged; '$relativePath' does not match its manifest hash."
        }}
    }}
    Write-Host "Validated deployment bundle $($manifest.bundle_id) for $($manifest.repository)."
    Write-Host "Project snapshot: $($manifest.project_name) [$($manifest.study_id)]"
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
        ".streamlit",
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
    $previewDirectory = Join-Path $Destination "{EXISTING_REPO_PREVIEW_DIR}"
    $items = @(
        "app.py",
        "public_voting.py",
        "shade_study_stops.csv",
        "shade_study_raw_labels.csv",
        "shade_study_config.json",
        "deployment_manifest.json",
        "requirements.txt"
    )
    Show-ProtectedFileWarnings
    if (-not (Test-Path $previewDirectory)) {{
        New-Item -ItemType Directory -Path $previewDirectory -Force | Out-Null
    }}
    foreach ($item in $items) {{
        if (Test-Path $item -PathType Leaf) {{
            $destinationPath = Join-Path $previewDirectory $item
            if (Test-Path $destinationPath) {{
                Write-Host "Updating generated preview file: {EXISTING_REPO_PREVIEW_DIR}/$item"
            }} else {{
                Write-Host "Adding generated preview file: {EXISTING_REPO_PREVIEW_DIR}/$item"
            }}
            Copy-Item -LiteralPath $item -Destination $destinationPath -Force
        }}
    }}
    $optionalRawLabels = Join-Path $previewDirectory "shade_study_raw_labels.csv"
    if (-not (Test-Path "shade_study_raw_labels.csv" -PathType Leaf) -and (Test-Path $optionalRawLabels)) {{
        Remove-Item -LiteralPath $optionalRawLabels -Force
        Write-Host "Removed stale generated preview file: {EXISTING_REPO_PREVIEW_DIR}/shade_study_raw_labels.csv"
    }}
}}

function Stage-PublishFiles {{
    param([string[]]$Paths)
    $existingPaths = @($Paths | Where-Object {{ Test-Path $_ }})
    if (-not $existingPaths.Count) {{
        return
    }}
    & git add -- $existingPaths
    if ($LASTEXITCODE -ne 0) {{
        throw "Failed to stage generated deployment files."
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
    Write-Host "Repository status after staging:"
    Invoke-Native "git" @("status")
    Write-Host "Staged diff summary:"
    Invoke-Native "git" @("diff", "--cached", "--stat")
    & git diff --cached --quiet
    $diffExitCode = $LASTEXITCODE
    if ($diffExitCode -eq 0) {{
        Write-Host "No changes to publish."
        return $false
    }}
    if ($diffExitCode -ne 1) {{
        throw "git diff failed with exit code $diffExitCode."
    }}
    Confirm-Publish "Review the status and diff summary for branch '$TargetBranch'."
    Invoke-Native "git" @("commit", "-m", $CommitMessage)
    if (-not $SkipPush) {{
        Invoke-Native "git" @("push", "origin", $TargetBranch)
    }}
    Write-Host "Repository status after commit/push:"
    Invoke-Native "git" @("status", "--short", "--branch")
    return $true
}}

Assert-DeploymentBundle

if ($Mode -eq "existing") {{
    Assert-PrivateExistingRepository
    $remoteUrl = Get-RemoteUrl
    $publishDir = Join-Path $env:TEMP ("_shade_gis_publish_" + [guid]::NewGuid().ToString("N"))
    $existingPublishFiles = @(
        "{EXISTING_REPO_PREVIEW_DIR}"
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
            $publishedChanges = Commit-And-Push -TargetBranch $Branch -Paths $existingPublishFiles
        }} finally {{
            Pop-Location
        }}
        if ($publishedChanges) {{
            Write-Host "Published changes to $RepositoryName on branch $Branch."
        }} else {{
            Write-Host "Existing repository already matches the generated deployment; nothing was pushed."
        }}
    }} finally {{
        if ($publishDir -and (Test-Path $publishDir)) {{
            Remove-Item -LiteralPath $publishDir -Recurse -Force
        }}
    }}
    exit 0
}}

# Visibility is a create-only option. Validate it after the existing workflow
# exits so PowerShell does not reject an irrelevant value during parameter binding.
if ($Visibility -notin @("public", "private")) {{
    throw "Visibility must be 'public' or 'private' when creating a repository."
}}

if ($Visibility -eq "public" -and -not $AllowPublicTarget) {{
    throw "Refusing to create a public repository without -AllowPublicTarget. Re-run with -Visibility private or add -AllowPublicTarget."
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
    "deployment_manifest.json",
    "requirements.txt",
    "README.md",
    "deploy_to_github.ps1",
    ".gitignore",
    ".streamlit/config.toml"
)
$createdCommit = Commit-And-Push -TargetBranch $Branch -Paths $newRepoFiles -SkipPush
if (-not $createdCommit) {{
    throw "No generated deployment changes were staged for the new repository."
}}
Invoke-Native "gh" @("repo", "create", $RepositoryName, "--$Visibility", "--source=.", "--remote=origin", "--push")
Write-Host "Created and published repository $RepositoryName on branch $Branch."
"""


def build_github_deploy_bundle(
    repo_name: str,
    deploy_mode: str = "existing",
    commit_message: str = DEFAULT_DEPLOY_COMMIT_MESSAGE,
) -> bytes:
    if deploy_mode not in {"create", "existing"}:
        raise ValueError("deploy_mode must be 'create' or 'existing'")
    commit_message = normalize_deploy_commit_message(commit_message)
    stops = st.session_state["stops"].copy()
    stops["priority_score"] = calculate_priority_scores(stops, st.session_state["visualization"]["priority_weights"])
    config_json = study_config_json()
    raw_labels = active_raw_labels()

    files: dict[str, bytes] = {
        "app.py": published_app_source().encode("utf-8"),
        "public_voting.py": public_voting_source().encode("utf-8"),
        "shade_study_stops.csv": stops.to_csv(index=False).encode("utf-8"),
        "shade_study_config.json": config_json.encode("utf-8"),
        "requirements.txt": (
            "streamlit>=1.57,<2\npandas>=2.2,<3\npyarrow>=24,<25\npydeck>=0.8,<1\n"
            "psycopg[binary]>=3.2,<4\n"
        ).encode("utf-8"),
        ".streamlit/config.toml": (
            "[server]\nheadless = true\n\n[browser]\ngatherUsageStats = false\n"
        ).encode("utf-8"),
        ".gitignore": (
            "__pycache__/\n*.pyc\n*.sqlite3\n.streamlit/secrets.toml\n_shade_gis_publish_*/\n"
        ).encode("utf-8"),
        "deploy_to_github.ps1": deploy_script(repo_name, commit_message).encode("utf-8"),
    }
    if not raw_labels.empty:
        files["shade_study_raw_labels.csv"] = raw_labels.to_csv(index=False).encode("utf-8")

    file_hashes = {name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())}
    manifest_core = {
        "schema_version": 1,
        "study_id": str(st.session_state.get("active_project_id") or ""),
        "project_name": str(st.session_state["project"].get("name", "Shade Study")),
        "repository": repo_name.strip().removesuffix(".git"),
        "deploy_mode": deploy_mode,
        "commit_message": commit_message,
        "entrypoint": streamlit_entrypoint_path(deploy_mode),
        "files": file_hashes,
    }
    bundle_id = hashlib.sha256(
        json.dumps(manifest_core, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    manifest = {**manifest_core, "bundle_id": bundle_id}
    files["deployment_manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")

    folder_name = slugify_repo_name(repo_name.rstrip("/").split("/")[-1].replace(".git", ""))
    bundle_name = f"{folder_name}-{bundle_id[:12]}.zip"
    files["README.md"] = deploy_readme(
        repo_name,
        st.session_state["project"],
        deploy_mode,
        bundle_name=bundle_name,
        commit_message=commit_message,
    ).encode("utf-8")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
    return buffer.getvalue()


def set_page(page: str) -> None:
    if st.session_state.get("page") == page:
        return
    st.session_state["page"] = page


def open_project(project_id: str) -> None:
    current_project_id = st.session_state.get("active_project_id")
    if current_project_id and current_project_id != project_id:
        save_active_project_to_store()
        load_project_into_session(project_id)
    elif st.session_state.get("loaded_project_id") != project_id:
        load_project_into_session(project_id)
    set_page("Data")


def request_open_project(project_id: str, project_name: str) -> None:
    st.session_state["pending_project_open"] = {
        "id": project_id,
        "name": project_name,
    }


def clear_pending_project_open() -> None:
    st.session_state.pop("pending_project_open", None)


def clear_pending_main_menu() -> None:
    st.session_state.pop("pending_main_menu", None)


def request_main_menu() -> None:
    clear_pending_project_open()
    if st.session_state.get("page") == "Home":
        clear_pending_main_menu()
        return
    st.session_state["pending_main_menu"] = True


@st.dialog("Open project?", on_dismiss=clear_pending_project_open)
def render_open_project_confirmation() -> None:
    pending = st.session_state.get("pending_project_open") or {}
    project_id = str(pending.get("id") or "")
    project_name = str(pending.get("name") or "this project")
    st.markdown("<span class='open-project-dialog-marker'></span>", unsafe_allow_html=True)
    st.write(f"Open {project_name} and continue to its project workspace?")
    cancel_column, open_column = st.columns(2)
    with cancel_column:
        if st.button("Cancel", width="stretch"):
            clear_pending_project_open()
            st.rerun()
    with open_column:
        if st.button("Open Project", type="primary", width="stretch"):
            clear_pending_project_open()
            open_project(project_id)
            st.rerun()


@st.dialog("Return to main menu?", on_dismiss=clear_pending_main_menu)
def render_main_menu_confirmation() -> None:
    project_name = str(st.session_state.get("project", {}).get("name") or "this project")
    st.markdown("<span class='main-menu-dialog-marker'></span>", unsafe_allow_html=True)
    st.write(f"Leave {project_name} and return to your project list?")
    cancel_column, menu_column = st.columns(2)
    with cancel_column:
        if st.button("Cancel", key="cancel_main_menu", width="stretch"):
            clear_pending_main_menu()
            st.rerun()
    with menu_column:
        if st.button("Main Menu", key="confirm_main_menu", type="primary", width="stretch"):
            clear_pending_main_menu()
            set_page("Home")
            st.rerun()


def format_project_updated(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "Recently updated"
    try:
        updated = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return "Recently updated"
    now = datetime.now(updated.tzinfo) if updated.tzinfo else datetime.now()
    if updated.date() == now.date():
        return "Updated today"
    return f"Updated {updated.strftime('%b %d, %Y').replace(' 0', ' ')}"


def render_home_page() -> None:
    projects = list_projects()
    st.markdown(
        """
        <style>
        .st-key-home_page {
            margin: 0 auto;
            max-width: 1080px;
            padding: 0.15rem 0 2.5rem;
        }
        div[data-testid="stAppViewContainer"]:has(.st-key-home_page) {
            background: #f8fbf8;
        }
        div[data-testid="stAppViewContainer"]:has(.st-key-home_page)
        div[data-testid="stHorizontalBlock"]:has(.st-key-nav_home) {
            margin-bottom: 0.35rem;
        }
        .st-key-home_page .home-subtitle {
            color: #52605a;
            font-size: 1.05rem;
            line-height: 1.65;
            margin: 0 0 1.2rem;
            max-width: 46rem;
        }
        .st-key-home_page .home-section-title {
            color: #17211c;
            font-size: 1.9rem;
            letter-spacing: -0.025em;
            line-height: 1.2;
            margin: 0;
        }
        .st-key-home_page .home-project-count {
            color: #66736c;
            font-size: 0.92rem;
            margin: 0.35rem 0 0;
        }
        div[data-testid="stHorizontalBlock"]:has(.home-section-title) [data-testid="stPopover"] button,
        .st-key-home_create_project button {
            background: #166534;
            border-color: #166534;
            color: white;
            font-weight: 650;
        }
        div[data-testid="stHorizontalBlock"]:has(.home-section-title) [data-testid="stPopover"] button:hover,
        .st-key-home_create_project button:hover {
            background: #14532d;
            border-color: #14532d;
            color: white;
        }
        div[data-testid="stDialog"]:has(.open-project-dialog-marker) button[kind="primary"] {
            background: #166534;
            border-color: #166534;
            color: white;
        }
        div[data-testid="stDialog"]:has(.open-project-dialog-marker) button[kind="primary"]:hover {
            background: #14532d;
            border-color: #14532d;
        }
        div[data-testid="stDialog"]:has(.main-menu-dialog-marker) button[kind="primary"] {
            background: #166534;
            border-color: #166534;
            color: white;
        }
        div[data-testid="stDialog"]:has(.main-menu-dialog-marker) button[kind="primary"]:hover {
            background: #14532d;
            border-color: #14532d;
        }
        div[class*="st-key-project_card_"] {
            background: white;
            border: 1px solid #dce4df;
            border-radius: 0.85rem;
            box-shadow: 0 1px 2px rgba(15, 48, 30, 0.04);
            cursor: pointer;
            box-sizing: border-box;
            height: 24.5rem;
            overflow: hidden;
            padding: 1.25rem;
            position: relative;
            transition: border-color 150ms ease, box-shadow 150ms ease, transform 150ms ease;
        }
        div[class*="st-key-project_card_"]:hover {
            border-color: #4ade80;
            box-shadow: 0 0.75rem 1.8rem rgba(20, 83, 45, 0.13);
            transform: translateY(-3px);
        }
        div[class*="st-key-project_card_"]:active {
            box-shadow: 0 0.3rem 0.8rem rgba(20, 83, 45, 0.14);
            transform: translateY(-1px);
        }
        div[class*="st-key-project_card_"]:focus-within {
            border-color: #16a34a;
            box-shadow: 0 0 0 0.22rem rgba(34, 197, 94, 0.24);
        }
        div[class*="st-key-project_card_"] [data-testid="stButton"] {
            bottom: 0;
            left: 0;
            position: absolute;
            right: 0;
            z-index: 5;
        }
        div[class*="st-key-project_card_"] [data-testid="stButton"] button {
            bottom: 0;
            cursor: pointer;
            height: 24.5rem;
            left: 0;
            opacity: 0;
            position: absolute;
            width: 100%;
        }
        .project-card-content {
            display: flex;
            flex-direction: column;
            min-height: 15.5rem;
            pointer-events: none;
        }
        .project-card-topline {
            align-items: flex-start;
            display: flex;
            gap: 0.75rem;
            justify-content: space-between;
        }
        .project-card-title {
            color: #17211c;
            font-size: 1.3rem;
            font-weight: 720;
            letter-spacing: -0.012em;
            line-height: 1.35;
            margin: 0;
        }
        .project-card-location {
            color: #4f5e56;
            font-size: 0.94rem;
            line-height: 1.5;
            margin: 0.8rem 0 0;
        }
        .project-card-badge {
            align-items: center;
            background: #e9f8ee;
            border: 1px solid #b9e8c7;
            border-radius: 999px;
            color: #166534;
            display: inline-flex;
            font-size: 0.76rem;
            font-weight: 700;
            gap: 0.35rem;
            margin-top: 0.85rem;
            padding: 0.22rem 0.55rem;
            width: fit-content;
        }
        .project-card-badge::before {
            background: #22c55e;
            border-radius: 50%;
            content: "";
            height: 0.45rem;
            width: 0.45rem;
        }
        .project-card-badge.private {
            background: #f1f4f2;
            border-color: #d7ddd9;
            color: #52605a;
        }
        .project-card-badge.private::before {
            background: #87938c;
        }
        .project-location-label {
            color: #166534;
            font-size: 0.72rem;
            font-weight: 750;
            letter-spacing: 0.035em;
            text-transform: uppercase;
        }
        .project-card-meta {
            color: #6b7871;
            font-size: 0.84rem;
            line-height: 1.55;
            margin: 0.65rem 0 0.85rem;
        }
        .project-progress-label {
            align-items: center;
            color: #4f5e56;
            display: flex;
            font-size: 0.8rem;
            justify-content: space-between;
            margin-bottom: 0.38rem;
        }
        .project-progress-track {
            background: #e6ece8;
            border-radius: 999px;
            height: 0.48rem;
            overflow: hidden;
        }
        .project-progress-fill {
            background: #22a854;
            border-radius: inherit;
            height: 100%;
        }
        .project-card-stats {
            display: grid;
            gap: 0.6rem;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            margin: 0.9rem 0 1rem;
        }
        .project-card-stat strong {
            color: #26342c;
            display: block;
            font-size: 0.9rem;
        }
        .project-card-stat span {
            color: #738078;
            display: block;
            font-size: 0.7rem;
            line-height: 1.25;
        }
        .project-card-action {
            color: #166534;
            font-size: 0.92rem;
            font-weight: 700;
            margin-top: auto;
        }
        @media (max-width: 760px) {
            .st-key-home_page { padding-left: 0.2rem; padding-right: 0.2rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="home_page"):
        title_column, action_column = st.columns([4, 1], vertical_alignment="center")
        with title_column:
            project_word = "project" if len(projects) == 1 else "projects"
            st.markdown(
                f'<h1 class="home-section-title">Your Projects</h1>'
                f'<p class="home-project-count">{len(projects)} {project_word}</p>',
                unsafe_allow_html=True,
            )
        with action_column:
            with st.popover("＋ New Project", width="stretch"):
                st.markdown("**Create a shade study**")
                st.caption("Start with an empty project and add your own transit or GIS data.")
                new_project_name = st.text_input(
                    "Project name",
                    key="home_new_project_name",
                    placeholder="e.g. Downtown transit shade study",
                )
                if st.button("Create project", key="home_create_project", width="stretch"):
                    project_id = create_blank_project(new_project_name)
                    load_project_into_session(project_id)
                    set_page("Data")
                    st.rerun()

        st.markdown("<div style='height: 0.7rem'></div>", unsafe_allow_html=True)
        if not projects:
            st.info("No saved projects yet. Create your first project to get started.")
            return

        card_columns = st.columns(2, gap="large")
        for index, project in enumerate(projects):
            project_id = str(project["id"])
            project_name = str(project.get("name") or "Untitled Shade Study")
            name = html.escape(project_name)
            agency = html.escape(str(project.get("agency") or "No agency"))
            region = html.escape(str(project.get("region") or "No location set"))
            version = html.escape(str(project.get("dataset_version") or "draft"))
            visibility = html.escape(str(project.get("visibility") or "Private"))
            visibility_class = "public" if visibility.lower() == "public" else "private"
            updated = html.escape(format_project_updated(project.get("updated_at")))
            location_count = int(project.get("location_count") or 0)
            reviewed_count = int(project.get("reviewed_count") or 0)
            awaiting_count = int(project.get("awaiting_review_count") or 0)
            review_percent = round(reviewed_count / location_count * 100) if location_count else 0
            with card_columns[index % len(card_columns)]:
                with st.container(key=f"project_card_{index}"):
                    st.markdown(
                        f"""
                        <div class="project-card-content">
                            <div class="project-card-topline">
                                <h2 class="project-card-title">{name}</h2>
                            </div>
                            <span class="project-card-badge {visibility_class}">{visibility}</span>
                            <p class="project-card-location"><span class="project-location-label">Location</span> · {region} · {agency}</p>
                            <p class="project-card-meta">Dataset v{version} · {updated}</p>
                            <div class="project-progress-label"><span>Review progress</span><strong>{review_percent}%</strong></div>
                            <div class="project-progress-track"><div class="project-progress-fill" style="width: {review_percent}%"></div></div>
                            <div class="project-card-stats">
                                <div class="project-card-stat"><strong>{location_count:,}</strong><span>Locations</span></div>
                                <div class="project-card-stat"><strong>{reviewed_count:,}</strong><span>Reviewed</span></div>
                                <div class="project-card-stat"><strong>{awaiting_count:,}</strong><span>Need review</span></div>
                            </div>
                            <span class="project-card-action">Open Project →</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.button(
                        f"Open project: {name}",
                        key=f"home_open_{project_id}",
                        width="stretch",
                        on_click=request_open_project,
                        args=(project_id, project_name),
                    )
        if st.session_state.get("pending_project_open"):
            render_open_project_confirmation()


def render_header() -> str:
    data_pages = [("Overview", "Data"), ("Labels", "Labels"), ("Voting", "Voting")]
    build_pages = [
        ("Visuals", "Visuals"),
        ("Docs", "Docs"),
        ("Preview", "Preview"),
        ("Deploy", "Deploy"),
    ]
    pages = ["Home", *(page for _, page in data_pages), *(page for _, page in build_pages)]
    if st.session_state.get("page") not in pages:
        st.session_state["page"] = "Home"
    st.markdown(
        """
        <style>
        div[data-testid="stHorizontalBlock"]:has(.st-key-nav_home) {
            border-bottom: 1px solid #e5e7eb;
            margin-bottom: 1.2rem;
            padding: 0.9rem 0 1.1rem;
        }
        div[data-testid="stHorizontalBlock"]:has(.st-key-nav_home) [data-testid="stPopover"] > button {
            border-radius: 999px;
            font-size: 1.2rem;
            min-height: 3.05rem;
            font-weight: 680;
            padding: 0.5rem 1rem;
            white-space: nowrap;
            width: 100%;
        }
        div[data-testid="stHorizontalBlock"]:has(.st-key-nav_home) button p {
            white-space: nowrap;
        }
        .st-key-nav_home button {
            background: transparent;
            border: 2px solid transparent;
            border-radius: 0.8rem;
            color: #14532d;
            display: inline-flex;
            font-size: 2.85rem;
            font-weight: 800;
            justify-content: flex-start;
            letter-spacing: 0;
            line-height: 1.08;
            padding: 0.35rem 0.65rem;
            transform: translateY(0);
            transition: background-color 140ms ease, border-color 140ms ease,
                box-shadow 140ms ease, color 140ms ease, transform 100ms ease;
            width: auto;
        }
        .st-key-nav_home button:hover {
            background: #dcfce7;
            border-color: #86efac;
            box-shadow: 0 0.35rem 0.9rem rgba(20, 83, 45, 0.18);
            color: #0f6b35;
            transform: translateY(-2px);
        }
        .st-key-nav_home button:active {
            background: #bbf7d0;
            border-color: #22c55e;
            box-shadow: 0 0.12rem 0.3rem rgba(20, 83, 45, 0.24);
            color: #14532d;
            transform: translateY(1px) scale(0.98);
        }
        .st-key-nav_home button:focus-visible {
            border-color: #16a34a;
            box-shadow: 0 0 0 0.25rem rgba(34, 197, 94, 0.28);
            outline: none;
        }
        .st-key-nav_home button p {
            font-size: 2.85rem;
            font-weight: 800;
            line-height: 1.08;
        }
        h1 {
            font-size: 1.85rem;
            line-height: 1.15;
        }
        div[data-testid="stPopoverBody"]:has(.header-menu-marker) [data-testid="stVerticalBlock"] {
            gap: 0.25rem;
        }
        div[data-testid="stPopoverBody"]:has(.header-menu-marker) [data-testid="stButton"] button {
            min-height: 2.25rem;
            padding: 0.3rem 0.75rem;
        }
        div[data-testid="stDialog"]:has(.main-menu-dialog-marker) button[kind="primary"] {
            background: #166534;
            border-color: #166534;
            color: white;
        }
        div[data-testid="stDialog"]:has(.main-menu-dialog-marker) button[kind="primary"]:hover {
            background: #14532d;
            border-color: #14532d;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    on_home_page = st.session_state["page"] == "Home"
    cols = st.columns([1] if on_home_page else [5, 1, 1], gap="small", vertical_alignment="center")
    with cols[0]:
        st.button("Shade-GIS", key="nav_home", on_click=request_main_menu)
    if not on_home_page:
        for column, label, menu_pages in [
            (cols[1], "Data", data_pages),
            (cols[2], "Build", build_pages),
        ]:
            with column:
                with st.popover(label, width="stretch"):
                    st.markdown("<span class='header-menu-marker'></span>", unsafe_allow_html=True)
                    for button_label, page in menu_pages:
                        st.button(
                            button_label,
                            key=f"nav_{page}",
                            type="primary" if st.session_state["page"] == page else "secondary",
                            width="stretch",
                        on_click=set_page,
                        args=(page,),
                    )
    if st.session_state.get("pending_main_menu"):
        render_main_menu_confirmation()
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
    if page == "Home":
        render_home_page()
    elif page == "Labels":
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

