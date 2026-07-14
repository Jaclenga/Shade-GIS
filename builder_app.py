import html
import json
import math
import os
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
    migrate_legacy_analytics_config,
    priority_formula_for_about,
    priority_score_used_in_visualization,
    render_custom_chart,
    render_custom_charts,
    rgba_from_hex,
    selected_dashboard_sections,
)
from shade_gis.deploy import (
    DeploymentBundleSpec,
    build_deployment_bundle,
    deploy_launcher_script,
    deploy_readme,
    deploy_script,
    github_new_repo_url,
    powershell_literal,
    public_voting_source,
    published_app_source,
    slugify_repo_name,
    streamlit_entrypoint_path,
)
from shade_gis.deployment import (
    DEFAULT_DEPLOY_COMMIT_MESSAGE,
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
        "the waiting area; `Purpose-built` means a designated bus shelter, awning, canopy, "
        "overhang, or similar passenger shelter visibly shades the waiting area; `Incidental` means a nearby "
        "building or other non-shelter built feature visibly shades the waiting area.\n\n"
        "Trees, utility poles, signs, and nearby buildings should not be classified as `Purpose-built` unless "
        "they are clearly intended to provide passenger shade or weather protection. Nearby buildings that "
        "visibly shade the waiting area should be coded as `Incidental`. Store raw labels and consensus labels "
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
    visualization = migrate_legacy_analytics_config(visualization)
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
    visualization = normalized_visualization_values(bundle["visualization"], taxonomy)
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
    st.session_state.pop("deploy_page_settings_project_id", None)
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
    taxonomy = normalize_coverage_taxonomy(st.session_state["taxonomy"])
    public_project = with_default_project_values(st.session_state["project"])
    public_project.pop("deployment", None)
    return {
        "study_id": st.session_state.get("active_project_id")
        or slugify_repo_name(st.session_state["project"].get("name", "shade-study")),
        "project": public_project,
        "taxonomy": taxonomy,
        "methodology": with_default_methodology_values(st.session_state["methodology"]),
        "visualization": normalized_visualization_values(
            st.session_state["visualization"], taxonomy
        ),
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
    normalized_project.pop("deployment", None)
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




def build_github_deploy_bundle(
    repo_name: str,
    deploy_mode: str = "existing",
    commit_message: str = DEFAULT_DEPLOY_COMMIT_MESSAGE,
) -> bytes:
    return build_deployment_bundle(
        DeploymentBundleSpec(
            repository=repo_name,
            project=st.session_state["project"],
            study_id=str(st.session_state.get("active_project_id") or ""),
            stops=st.session_state["stops"],
            raw_labels=active_raw_labels(),
            config_json=study_config_json(),
            priority_weights=st.session_state["visualization"]["priority_weights"],
            deploy_mode=deploy_mode,
            commit_message=commit_message,
        )
    )


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

