import io
import json
import re
import urllib.parse
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pydeck as pdk
import streamlit as st

from builder_about_page import render_builder_about_page


APP_DIR = Path(__file__).parent
DATA_PATH = APP_DIR / "stops.txt"
SHADE_DATA_PATH = APP_DIR / "shading_data.csv"
APP_TITLE = "Shade Study Builder"
VISUAL_MAP_HEIGHT = 500


def timestamp_with_timezone() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")

DEFAULT_PROJECT = {
    "name": "Tampa Bus Stop Shade Study",
    "agency": "Hillsborough Area Regional Transit (HART)",
    "region": "Tampa, Florida",
    "description": (
        "A reusable shade inventory project seeded with Tampa-area GTFS stops, "
        "shade classifications, and heat-context fields."
    ),
    "owners": "Open transit and climate research contributors",
    "visibility": "Public",
    "dataset_version": "0.1.0",
    "methodology_version": "0.1.0",
    "source_name": "HART GTFS feed",
    "source_license": "Agency GTFS terms",
    "source_url": "",
}

DEFAULT_TAXONOMY = [
    {
        "name": "No Shade",
        "description": "No shade visibly reaches the waiting area.",
        "color": "#dc143c",
        "sort_order": 1,
    },
    {
        "name": "Limited Natural Shade",
        "description": "Vegetation shades part of the waiting area, but not most of it.",
        "color": "#d69e2e",
        "sort_order": 2,
    },
    {
        "name": "Significant Natural Shade",
        "description": "Vegetation visibly covers most of the waiting area or seating area.",
        "color": "#228b22",
        "sort_order": 3,
    },
    {
        "name": "Intentional Built Shade",
        "description": "A purpose-built shelter, awning, canopy, or overhang shades riders.",
        "color": "#4682b4",
        "sort_order": 4,
    },
    {
        "name": "Incidental Built Shade",
        "description": "A nearby building or other non-shelter built feature shades riders.",
        "color": "#805aaa",
        "sort_order": 5,
    },
    {
        "name": "Needs Review",
        "description": "The stop needs imagery, review, or disagreement resolution.",
        "color": "#808080",
        "sort_order": 6,
    },
]

DEFAULT_METHODOLOGY = {
    "title": "Bus Stop Shade Study",
    "summary": "Preparing a reproducible, city-wide shade inventory from GTFS bus stop data.",
    "purpose": (
        "This project helps researchers, transit agencies, and municipalities collect, "
        "review, visualize, and publish standardized bus stop shade datasets."
    ),
    "shade_method": (
        "Classifications should describe visible shade reaching the passenger waiting area, "
        "not merely nearby trees or structures. Store raw labels and consensus labels so "
        "future reviewers can reproduce decisions."
    ),
    "data_sources": (
        "- GTFS stops and routes\n"
        "- Expert or crowdsourced shade labels\n"
        "- Optional environmental, demographic, and transportation overlays"
    ),
    "contributors": "Project team, reviewers, and community contributors",
    "citation": (
        "Dataset release:\n"
        "    Author or Organization. (Year). Title of dataset or study release (Version number) [Data set]. Publisher. URL"
    ),
    "bibliography": (
        "Works referenced:\n"
        "    Author, A. A., & Author, B. B. (Year). Title of article. Title of Journal, volume(issue), page range. https://doi.org/xxxxx\n"
        "    Author or Organization. (Year). Title of report. Publisher. URL"
    ),
    "limitations": (
        "Imagery date, time of day, season, and reviewer uncertainty can affect shade labels. "
        "Published releases should document these limitations."
    ),
    "release_history": "- 0.1.0: Draft project configuration and starter dataset",
}

DEFAULT_DISPLAY_COLUMNS = ["stop_id", "stop_name", "routes", "shading", "review_status", "priority_score"]
RECORD_COUNT_FIELD = "Record count"
MAX_CUSTOM_CHARTS = 10
DEFAULT_CUSTOM_CHART = {
    "title": "Custom chart",
    "x": "shading",
    "y": RECORD_COUNT_FIELD,
    "aggregation": "Count",
    "chart_type": "Bar",
}

DEFAULT_VISUALIZATION = {
    "color_by": "Shade category",
    "marker_shape": "Circle",
    "marker_size": 7,
    "marker_opacity": 0.82,
    "marker_stroke_color": "#141414",
    "marker_stroke_width": 1,
    "map_style": "Light",
    "priority_colors": {
        "low": "#34d399",
        "mid": "#facc15",
        "high": "#ef4444",
    },
    "field_color_maps": {},
    "metric_cards": ["Shade distribution", "Review status", "Priority stops"],
    "overlays": [],
    "priority_weights": {
        "ridership": 0.5,
        "low_shade": 0.5,
    },
    "show_legend": True,
    "show_downloads": True,
    "display_columns": DEFAULT_DISPLAY_COLUMNS,
    "custom_charts": [DEFAULT_CUSTOM_CHART],
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

MARKER_SHAPES = ["Circle", "Pin", "Square", "Diamond", "Triangle"]

MAP_STYLES = {
    "Light": pdk.map_styles.CARTO_LIGHT,
    "Dark": pdk.map_styles.CARTO_DARK,
    "Road": pdk.map_styles.CARTO_ROAD,
    "Light, no labels": pdk.map_styles.CARTO_LIGHT_NO_LABELS,
    "Dark, no labels": pdk.map_styles.CARTO_DARK_NO_LABELS,
}

COLOR_MODE_FIELDS = {
    "Shade category": "shading",
    "Review status": "review_status",
    "Priority score": "priority_score",
}

FIELD_LABELS = {
    "stop_id": "Stop ID",
    "stop_name": "Stop name",
    "stop_lat": "Latitude",
    "stop_lon": "Longitude",
    "agency": "Agency",
    "routes": "Routes",
    "municipality": "Municipality",
    "shading": "Shade category",
    "shade_coverage": "Shade coverage",
    "shade_sources": "Shade sources",
    "review_status": "Review status",
    "confidence": "Confidence",
    "ridership": "Ridership",
    "heat_vulnerability_index": "Heat vulnerability index",
    "heat_vulnerability_label": "Heat vulnerability label",
    "tree_canopy_pct": "Tree canopy percent",
    "lst_median": "Land surface temperature",
    "priority_score": "Priority score",
}

OVERLAY_REQUIREMENTS = {
    "GTFS routes": ["routes"],
    "Ridership": ["ridership"],
    "Existing shelters": ["shelter", "shelter_status", "has_shelter"],
    "Route frequency": ["route_frequency", "trips_per_day", "headway_minutes"],
    "Tree canopy": ["tree_canopy_pct"],
    "Land surface temperature": ["lst_median"],
    "Heat vulnerability": ["heat_vulnerability_index", "heat_vulnerability_label"],
    "NDVI": ["ndvi"],
    "Zero-vehicle households": ["zero_vehicle_households"],
    "Older adult population": ["older_adult_population"],
    "Nearby destinations": ["nearby_destinations"],
}

METRIC_REQUIREMENTS = {
    "Shade distribution": ["shading"],
    "Stops without shade": ["shading"],
    "Review status": ["review_status"],
    "Agreement metrics": ["confidence"],
    "Shade by route": ["routes", "shading"],
    "Shade by neighborhood": ["municipality", "shading"],
    "Shade vs heat vulnerability": ["heat_vulnerability_index", "shading"],
    "Priority stops": ["priority_score"],
}

CHART_TYPES = ["Bar", "Line", "Scatter"]
CHART_AGGREGATIONS = ["Count", "Mean", "Sum", "Median", "Min", "Max"]
PRIORITY_FACTOR_DETAILS = {
    "ridership": (
        "Ridership",
        "Higher ridership increases priority when the dataset includes ridership values.",
    ),
    "low_shade": (
        "Low shade",
        "Stops labeled No Shade or Needs Review receive more priority.",
    ),
    "heat_vulnerability_index": (
        "Heat vulnerability",
        "Higher heat vulnerability values increase priority when that field is present.",
    ),
    "low_tree_canopy": (
        "Low tree canopy",
        "Lower tree canopy share increases priority when tree canopy data is present.",
    ),
}

COLOR_PALETTE = [
    "#2563eb",
    "#16a34a",
    "#dc2626",
    "#9333ea",
    "#0891b2",
    "#ea580c",
    "#4f46e5",
    "#65a30d",
    "#db2777",
    "#0f766e",
    "#7c3aed",
    "#ca8a04",
    "#475569",
    "#be123c",
    "#0284c7",
    "#15803d",
]

SHADE_PALETTES = {
    "Default shade study": ["#dc143c", "#d69e2e", "#228b22", "#4682b4", "#805aaa", "#808080"],
    "Colorblind friendly": ["#d55e00", "#e69f00", "#009e73", "#0072b2", "#cc79a7", "#999999"],
    "High contrast": ["#b91c1c", "#f97316", "#15803d", "#2563eb", "#7c3aed", "#475569"],
    "Canopy and shelter": ["#dc2626", "#ca8a04", "#16a34a", "#0ea5e9", "#9333ea", "#71717a"],
    "Civic map": ["#ef4444", "#f59e0b", "#22c55e", "#3b82f6", "#a855f7", "#64748b"],
}

SHADE_ALIASES = {
    "Constructed Shade": "Intentional Built Shade",
    "Manmade Shade": "Incidental Built Shade",
    "Unknown": "Needs Review",
}

REQUIRED_STOP_FIELDS = ["stop_id", "stop_name", "stop_lat", "stop_lon"]
OPTIONAL_FIELDS = [
    "agency",
    "routes",
    "municipality",
    "shading",
    "shade_coverage",
    "shade_sources",
    "review_status",
    "confidence",
    "ridership",
    "heat_vulnerability_index",
    "heat_vulnerability_label",
    "tree_canopy_pct",
    "lst_median",
]


def hex_to_rgb(value: str) -> list[int]:
    text = str(value or "").strip().lstrip("#")
    if len(text) != 6:
        return [128, 128, 128]
    try:
        return [int(text[index : index + 2], 16) for index in (0, 2, 4)]
    except ValueError:
        return [128, 128, 128]


def rgb_to_hex(value: list[int]) -> str:
    rgb = [max(0, min(255, int(channel))) for channel in value[:3]]
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def normalize_hex_color(value: Any, fallback: str = "#808080") -> str:
    text = str(value or "").strip()
    if not text.startswith("#"):
        text = f"#{text}"
    if len(text) != 7:
        return fallback
    try:
        int(text[1:], 16)
    except ValueError:
        return fallback
    return text.lower()


def normalize_category(value: Any, taxonomy: list[dict[str, Any]]) -> str:
    categories = [str(item.get("name", "")).strip() for item in taxonomy if str(item.get("name", "")).strip()]
    fallback = "Needs Review" if "Needs Review" in categories else (categories[-1] if categories else "Needs Review")
    if pd.isna(value):
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    text = SHADE_ALIASES.get(text, text)
    return text if text in categories else fallback


def normalize_review_status(value: Any) -> str:
    if pd.isna(value) or not str(value).strip():
        return "Unlabeled"
    text = str(value).strip()
    return text if text in REVIEW_STATUS_COLORS else "Needs Review"


def read_csv_bytes(contents: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(contents), dtype=str)


def find_gtfs_member(archive: zipfile.ZipFile, filename: str) -> str | None:
    filename = filename.lower()
    for member in archive.namelist():
        if Path(member).name.lower() == filename:
            return member
    return None


def read_gtfs_table(
    archive: zipfile.ZipFile, filename: str, usecols: list[str] | None = None
) -> pd.DataFrame | None:
    member = find_gtfs_member(archive, filename)
    if member is None:
        return None
    with archive.open(member) as handle:
        try:
            return pd.read_csv(handle, dtype=str, usecols=usecols)
        except ValueError:
            handle.seek(0)
            return pd.read_csv(handle, dtype=str)


def parse_gtfs_zip(contents: bytes) -> tuple[pd.DataFrame, dict[str, Any]]:
    with zipfile.ZipFile(io.BytesIO(contents)) as archive:
        stops = read_gtfs_table(archive, "stops.txt")
        if stops is None:
            raise ValueError("GTFS upload must include stops.txt")

        route_map: dict[str, str] = {}
        stop_times = read_gtfs_table(archive, "stop_times.txt", ["trip_id", "stop_id"])
        trips = read_gtfs_table(archive, "trips.txt", ["trip_id", "route_id"])
        routes = read_gtfs_table(archive, "routes.txt")
        if stop_times is not None and trips is not None and routes is not None:
            route_label_col = "route_short_name" if "route_short_name" in routes.columns else "route_long_name"
            if route_label_col in routes.columns and "route_id" in routes.columns:
                route_lookup = routes.loc[:, ["route_id", route_label_col]].dropna().drop_duplicates()
                joined = stop_times.merge(trips, on="trip_id", how="left").merge(route_lookup, on="route_id", how="left")
                joined = joined.dropna(subset=["stop_id", route_label_col])
                route_map = (
                    joined.groupby("stop_id")[route_label_col]
                    .apply(lambda values: "; ".join(sorted({str(value) for value in values if str(value).strip()})))
                    .to_dict()
                )

    if route_map:
        stops["routes"] = stops["stop_id"].map(route_map).fillna("")
    metadata = {
        "format": "GTFS",
        "tables": ["stops.txt"],
        "routes_joined": bool(route_map),
        "imported_at": timestamp_with_timezone(),
    }
    return stops, metadata


def apply_field_mapping(raw: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    mapped = pd.DataFrame(index=raw.index)
    used_sources = set()
    for target, source in mapping.items():
        if source and source in raw.columns:
            mapped[target] = raw[source]
            used_sources.add(source)
    for column in raw.columns:
        if column not in used_sources and column not in mapped.columns:
            mapped[column] = raw[column]
    for field in REQUIRED_STOP_FIELDS:
        if field not in mapped.columns:
            mapped[field] = ""
    return mapped


def prepare_stop_dataset(raw: pd.DataFrame, project: dict[str, Any], taxonomy: list[dict[str, Any]]) -> pd.DataFrame:
    df = raw.copy()
    for field in REQUIRED_STOP_FIELDS:
        if field not in df.columns:
            df[field] = ""
    for field in OPTIONAL_FIELDS:
        if field not in df.columns:
            df[field] = ""

    df["stop_id"] = df["stop_id"].astype(str).str.strip()
    df["stop_name"] = df["stop_name"].fillna("").astype(str).str.strip()
    df["stop_name"] = df["stop_name"].where(df["stop_name"] != "", "Unnamed stop")
    df["stop_lat"] = pd.to_numeric(df["stop_lat"], errors="coerce")
    df["stop_lon"] = pd.to_numeric(df["stop_lon"], errors="coerce")
    df["agency"] = df["agency"].fillna("").replace("", project.get("agency", ""))
    df["routes"] = df["routes"].fillna("").astype(str)
    df["municipality"] = df["municipality"].fillna("").astype(str)
    df["shading"] = df["shading"].apply(lambda value: normalize_category(value, taxonomy))
    df["review_status"] = df["review_status"].apply(normalize_review_status)

    numeric_fields = ["confidence", "ridership", "heat_vulnerability_index", "tree_canopy_pct", "lst_median"]
    for field in numeric_fields:
        df[field] = pd.to_numeric(df[field], errors="coerce")

    df = df.dropna(subset=["stop_lat", "stop_lon"])
    df = df[df["stop_id"] != ""].drop_duplicates(subset=["stop_id"], keep="first")
    df["priority_score"] = calculate_priority_scores(df)
    return df.reset_index(drop=True)


def calculate_priority_scores(df: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    weights = weights or DEFAULT_VISUALIZATION["priority_weights"]
    score_parts: list[tuple[float, pd.Series]] = []

    ridership_weight = float(weights.get("ridership", 0.0))
    if ridership_weight > 0 and has_column_data(df, "ridership"):
        ridership = pd.to_numeric(df.get("ridership"), errors="coerce").fillna(0)
        ridership = ridership / ridership.max() if ridership.max() and ridership.max() > 0 else ridership
        score_parts.append((ridership_weight, ridership))

    heat_weight = float(weights.get("heat_vulnerability_index", 0.0))
    if heat_weight > 0 and has_column_data(df, "heat_vulnerability_index"):
        heat = pd.to_numeric(df.get("heat_vulnerability_index"), errors="coerce").fillna(0)
        heat = heat / heat.max() if heat.max() and heat.max() > 0 else heat
        score_parts.append((heat_weight, heat))

    canopy_weight = float(weights.get("low_tree_canopy", 0.0))
    if canopy_weight > 0 and has_column_data(df, "tree_canopy_pct"):
        canopy = pd.to_numeric(df.get("tree_canopy_pct"), errors="coerce").fillna(0)
        canopy = canopy.clip(lower=0, upper=1)
        score_parts.append((canopy_weight, 1 - canopy))

    low_shade_weight = float(weights.get("low_shade", 0.0))
    if low_shade_weight > 0 and "shading" in df.columns:
        low_shade = df.get("shading", pd.Series(index=df.index, dtype=str)).isin(["No Shade", "Needs Review"]).astype(float)
        score_parts.append((low_shade_weight, low_shade))

    total_weight = sum(weight for weight, _series in score_parts)
    if total_weight <= 0:
        return pd.Series(0.0, index=df.index)
    score = sum(series * weight for weight, series in score_parts) / total_weight
    return (score * 100).round(1)


def load_seed_dataset(taxonomy: list[dict[str, Any]], project: dict[str, Any]) -> pd.DataFrame:
    if not DATA_PATH.exists():
        return pd.DataFrame(columns=REQUIRED_STOP_FIELDS)
    stops = pd.read_csv(DATA_PATH, dtype={"stop_id": str})
    if SHADE_DATA_PATH.exists():
        shade = pd.read_csv(SHADE_DATA_PATH, dtype={"stop_id": str})
        keep_cols = [column for column in shade.columns if column != "stop_name"]
        stops = stops.merge(shade.loc[:, keep_cols], on="stop_id", how="left")
    return prepare_stop_dataset(stops, project, taxonomy)


def ensure_visualization_defaults() -> None:
    visualization = st.session_state["visualization"]
    if "custom_charts" not in visualization and isinstance(visualization.get("custom_chart"), dict):
        visualization["custom_charts"] = [visualization["custom_chart"]]
    for key, value in DEFAULT_VISUALIZATION.items():
        visualization.setdefault(key, json.loads(json.dumps(value)))

    review_colors = visualization.setdefault("review_status_colors", {})
    for status, color in REVIEW_STATUS_COLORS.items():
        review_colors.setdefault(status, rgb_to_hex(color))

    priority_colors = visualization.setdefault("priority_colors", {})
    for key, color in DEFAULT_VISUALIZATION["priority_colors"].items():
        priority_colors.setdefault(key, color)


def ensure_state() -> None:
    st.session_state.setdefault("project", DEFAULT_PROJECT.copy())
    st.session_state.setdefault("taxonomy", [item.copy() for item in DEFAULT_TAXONOMY])
    st.session_state.setdefault("methodology", DEFAULT_METHODOLOGY.copy())
    st.session_state.setdefault("visualization", json.loads(json.dumps(DEFAULT_VISUALIZATION)))
    ensure_visualization_defaults()
    st.session_state.setdefault("import_log", [])
    if "stops" not in st.session_state:
        st.session_state["stops"] = load_seed_dataset(st.session_state["taxonomy"], st.session_state["project"])
        st.session_state["import_log"] = [
            {
                "source": "Seed Tampa GTFS and shade CSV",
                "format": "CSV",
                "rows": len(st.session_state["stops"]),
                "imported_at": timestamp_with_timezone(),
            }
        ]


def get_taxonomy_color_map(taxonomy: list[dict[str, Any]]) -> dict[str, list[int]]:
    return {
        str(item.get("name", "")).strip(): hex_to_rgb(str(item.get("color", "")))
        for item in taxonomy
        if str(item.get("name", "")).strip()
    }


def has_column_data(df: pd.DataFrame, column: str) -> bool:
    if column not in df.columns:
        return False
    series = df[column].dropna()
    if series.empty:
        return False
    return bool(series.astype(str).str.strip().ne("").any())


def has_any_column_data(df: pd.DataFrame, columns: list[str]) -> bool:
    return any(has_column_data(df, column) for column in columns)


def has_all_column_data(df: pd.DataFrame, columns: list[str]) -> bool:
    return all(has_column_data(df, column) for column in columns)


def get_color_options(df: pd.DataFrame) -> dict[str, str]:
    options = COLOR_MODE_FIELDS.copy()
    excluded = {"stop_id", "stop_name", "stop_lat", "stop_lon", "priority_score", "shading", "review_status"}
    for column in df.columns:
        if column in excluded:
            continue
        series = df[column].dropna().astype(str).str.strip()
        unique_count = series[series != ""].nunique()
        if 1 < unique_count <= len(COLOR_PALETTE):
            options[f"Column: {FIELD_LABELS.get(column, column)}"] = column
    return options


def display_label(column: str) -> str:
    return FIELD_LABELS.get(column, column.replace("_", " ").title())


def get_active_data_columns(df: pd.DataFrame) -> list[str]:
    always_show = set(REQUIRED_STOP_FIELDS + ["priority_score"])
    return [column for column in df.columns if column in always_show or has_column_data(df, column)]


def get_display_column_options(df: pd.DataFrame) -> list[str]:
    options = get_active_data_columns(df)
    if "priority_score" not in options:
        options.append("priority_score")
    return options


def get_selected_display_columns(df: pd.DataFrame, visualization: dict[str, Any]) -> list[str]:
    options = get_display_column_options(df)
    selected = [column for column in visualization.get("display_columns", []) if column in options]
    if not selected:
        selected = [column for column in DEFAULT_DISPLAY_COLUMNS if column in options]
    if not selected:
        selected = options[: min(6, len(options))]
    visualization["display_columns"] = selected
    return selected


def build_tooltip_text(df: pd.DataFrame, visualization: dict[str, Any]) -> str:
    columns = get_selected_display_columns(df, visualization)[:8]
    return "\n".join(f"{display_label(column)}: {{{column}}}" for column in columns)


def get_available_overlays(df: pd.DataFrame) -> list[str]:
    return [
        label
        for label, columns in OVERLAY_REQUIREMENTS.items()
        if has_any_column_data(df, columns)
    ]


def get_available_metric_cards(df: pd.DataFrame) -> list[str]:
    return [
        label
        for label, columns in METRIC_REQUIREMENTS.items()
        if has_all_column_data(df, columns)
    ]


def clean_selected_options(selected: list[str], options: list[str]) -> list[str]:
    return [item for item in selected if item in options]


def get_chart_column_options(df: pd.DataFrame) -> list[str]:
    return get_display_column_options(df)


def ensure_custom_chart_defaults(df: pd.DataFrame, chart: dict[str, Any] | None = None, index: int = 0) -> dict[str, Any]:
    chart = chart if isinstance(chart, dict) else {}
    for key, value in DEFAULT_CUSTOM_CHART.items():
        chart.setdefault(key, json.loads(json.dumps(value)))
    if not str(chart.get("title", "")).strip():
        chart["title"] = f"Custom chart {index + 1}"
    columns = get_chart_column_options(df)
    fallback_x = "shading" if "shading" in columns else (columns[0] if columns else "")
    if chart.get("x") not in columns:
        chart["x"] = fallback_x
    y_options = [RECORD_COUNT_FIELD] + columns
    if chart.get("y") not in y_options:
        chart["y"] = RECORD_COUNT_FIELD
    if chart.get("aggregation") not in CHART_AGGREGATIONS:
        chart["aggregation"] = "Count"
    if chart.get("chart_type") not in CHART_TYPES:
        chart["chart_type"] = "Bar"
    return chart


def get_custom_charts(df: pd.DataFrame, visualization: dict[str, Any]) -> list[dict[str, Any]]:
    charts = visualization.get("custom_charts")
    if not isinstance(charts, list):
        legacy_chart = visualization.get("custom_chart")
        charts = [legacy_chart] if isinstance(legacy_chart, dict) else [json.loads(json.dumps(DEFAULT_CUSTOM_CHART))]
    if not charts:
        charts = [json.loads(json.dumps(DEFAULT_CUSTOM_CHART))]
    charts = [
        ensure_custom_chart_defaults(df, chart if isinstance(chart, dict) else {}, index)
        for index, chart in enumerate(charts[:MAX_CUSTOM_CHARTS])
    ]
    visualization["custom_charts"] = charts
    return charts


def build_custom_chart_data(df: pd.DataFrame, chart: dict[str, Any]) -> tuple[pd.DataFrame, str, str]:
    x_column = chart.get("x", "")
    y_column = chart.get("y", RECORD_COUNT_FIELD)
    chart_type = chart.get("chart_type", "Bar")
    aggregation = chart.get("aggregation", "Count")
    if df.empty or x_column not in df.columns:
        return pd.DataFrame(), "", ""

    working = df.copy()
    working[x_column] = working[x_column].fillna("(blank)").astype(str).str.strip().replace("", "(blank)")
    if y_column == RECORD_COUNT_FIELD or y_column not in working.columns:
        chart_df = working.groupby(x_column, dropna=False).size().reset_index(name="records")
        return chart_df.sort_values("records", ascending=False).head(50), x_column, "records"

    numeric_y = pd.to_numeric(working[y_column], errors="coerce")
    if chart_type == "Scatter":
        chart_df = working.loc[numeric_y.notna(), [x_column]].copy()
        chart_df[y_column] = numeric_y[numeric_y.notna()]
        return chart_df.head(500), x_column, y_column

    if numeric_y.notna().any():
        working[y_column] = numeric_y
        if aggregation == "Sum":
            grouped = working.groupby(x_column, dropna=False)[y_column].sum()
        elif aggregation == "Median":
            grouped = working.groupby(x_column, dropna=False)[y_column].median()
        elif aggregation == "Min":
            grouped = working.groupby(x_column, dropna=False)[y_column].min()
        elif aggregation == "Max":
            grouped = working.groupby(x_column, dropna=False)[y_column].max()
        elif aggregation == "Count":
            grouped = working.groupby(x_column, dropna=False)[y_column].count()
        else:
            grouped = working.groupby(x_column, dropna=False)[y_column].mean()
        chart_df = grouped.reset_index(name=display_label(y_column))
        return chart_df.sort_values(display_label(y_column), ascending=False).head(50), x_column, display_label(y_column)

    working[y_column] = working[y_column].fillna("(blank)").astype(str).str.strip().replace("", "(blank)")
    chart_df = working.groupby([x_column, y_column], dropna=False).size().reset_index(name="records")
    chart_df["pair"] = chart_df[x_column].astype(str) + " / " + chart_df[y_column].astype(str)
    return chart_df.sort_values("records", ascending=False).head(50), "pair", "records"


def render_custom_chart(df: pd.DataFrame, chart: dict[str, Any]) -> None:
    chart_df, x_column, y_column = build_custom_chart_data(df, chart)
    if chart_df.empty or not x_column or not y_column:
        st.info("No data is available for the selected chart columns.")
        return
    if chart.get("chart_type") == "Line":
        st.line_chart(chart_df, x=x_column, y=y_column)
    elif chart.get("chart_type") == "Scatter":
        st.scatter_chart(chart_df, x=x_column, y=y_column)
    else:
        st.bar_chart(chart_df, x=x_column, y=y_column)


def render_custom_charts(df: pd.DataFrame, visualization: dict[str, Any]) -> None:
    for index, chart in enumerate(get_custom_charts(df, visualization)):
        title = str(chart.get("title", "")).strip() or f"Custom chart {index + 1}"
        st.markdown(f"#### {title}")
        render_custom_chart(df, chart)


def priority_score_used_in_visualization(visualization: dict[str, Any]) -> bool:
    if COLOR_MODE_FIELDS.get(visualization.get("color_by", "")) == "priority_score":
        return True
    if "Priority stops" in visualization.get("metric_cards", []):
        return True
    if "priority_score" in visualization.get("display_columns", []):
        return True
    charts = visualization.get("custom_charts")
    if not isinstance(charts, list) and isinstance(visualization.get("custom_chart"), dict):
        charts = [visualization["custom_chart"]]
    for chart in charts or []:
        if isinstance(chart, dict) and "priority_score" in {chart.get("x"), chart.get("y")}:
            return True
    return False


def priority_formula_for_about(visualization: dict[str, Any]) -> dict[str, Any] | None:
    if not priority_score_used_in_visualization(visualization):
        return None

    weights = visualization.get("priority_weights", {})
    rows = []
    for key, (label, description) in PRIORITY_FACTOR_DETAILS.items():
        weight = float(weights.get(key, 0.0))
        if weight > 0:
            rows.append(
                {
                    "Factor": label,
                    "Weight": f"{weight:.2f}",
                    "Role in score": description,
                }
            )

    if rows:
        summary = (
            "Priority score is calculated from the weighted factors below and normalized to a 0-100 scale. "
            "The score is included here automatically because at least one configured visualization uses "
            "`priority_score`."
        )
    else:
        summary = (
            "Priority score is included in at least one configured visualization, but no weighted priority "
            "factors are currently active or available. Scores will remain 0 until a factor is enabled."
        )

    return {"summary": summary, "weights": rows}


def field_values_for_colors(df: pd.DataFrame, field: str) -> list[str]:
    if field not in df.columns:
        return []
    values = df[field].fillna("Unknown").astype(str).str.strip()
    values = values.where(values != "", "Unknown")
    return sorted(values.unique().tolist())[: len(COLOR_PALETTE)]


def ensure_field_color_map(visualization: dict[str, Any], df: pd.DataFrame, field: str) -> dict[str, str]:
    field_maps = visualization.setdefault("field_color_maps", {})
    color_map = field_maps.setdefault(field, {})
    for index, value in enumerate(field_values_for_colors(df, field)):
        color_map.setdefault(value, COLOR_PALETTE[index % len(COLOR_PALETTE)])
    return color_map


def color_for_priority(value: Any, visualization: dict[str, Any]) -> list[int]:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    score = 0.0 if pd.isna(numeric) else max(0.0, min(100.0, float(numeric)))
    colors = visualization.get("priority_colors", DEFAULT_VISUALIZATION["priority_colors"])
    low = hex_to_rgb(colors.get("low", DEFAULT_VISUALIZATION["priority_colors"]["low"]))
    mid = hex_to_rgb(colors.get("mid", DEFAULT_VISUALIZATION["priority_colors"]["mid"]))
    high = hex_to_rgb(colors.get("high", DEFAULT_VISUALIZATION["priority_colors"]["high"]))
    if score <= 50:
        start, end, fraction = low, mid, score / 50
    else:
        start, end, fraction = mid, high, (score - 50) / 50
    return [int(start[channel] + (end[channel] - start[channel]) * fraction) for channel in range(3)]


def color_dataset(df: pd.DataFrame, taxonomy: list[dict[str, Any]], visualization: dict[str, Any]) -> pd.DataFrame:
    colored = df.copy()
    color_options = get_color_options(colored)
    color_by = visualization.get("color_by", "Shade category")
    field = color_options.get(color_by, "shading")
    if field == "review_status":
        review_colors = visualization.get("review_status_colors", {})
        colored["fill_color"] = colored["review_status"].map(
            {status: hex_to_rgb(color) for status, color in review_colors.items()}
        )
    elif field == "priority_score":
        colored["fill_color"] = colored["priority_score"].apply(lambda value: color_for_priority(value, visualization))
    elif field == "shading":
        color_map = get_taxonomy_color_map(taxonomy)
        colored["fill_color"] = colored["shading"].map(color_map)
    else:
        color_map = ensure_field_color_map(visualization, colored, field)
        values = colored[field].fillna("Unknown").astype(str).str.strip()
        values = values.where(values != "", "Unknown")
        colored["fill_color"] = values.map({value: hex_to_rgb(color) for value, color in color_map.items()})
    colored["fill_color"] = colored["fill_color"].apply(lambda value: value if isinstance(value, list) else [128, 128, 128])
    return colored


def marker_icon_svg(
    shape: str,
    fill_color: list[int],
    stroke_color: list[int],
    opacity: float,
    stroke_width: int,
) -> str:
    fill = f"rgb({fill_color[0]},{fill_color[1]},{fill_color[2]})"
    stroke = f"rgb({stroke_color[0]},{stroke_color[1]},{stroke_color[2]})"
    stroke_width = max(0, int(stroke_width))
    base_attrs = f'fill="{fill}" fill-opacity="{opacity:.2f}" stroke="{stroke}" stroke-width="{stroke_width}"'
    if shape == "Pin":
        body = (
            f'<path {base_attrs} d="M32 4C20.4 4 11 13.4 11 25c0 15.2 21 35 21 35s21-19.8 21-35C53 13.4 43.6 4 32 4z"/>'
            f'<circle cx="32" cy="25" r="8" fill="#ffffff" fill-opacity="0.8" stroke="none"/>'
        )
    elif shape == "Square":
        body = f'<rect {base_attrs} x="12" y="12" width="40" height="40" rx="4"/>'
    elif shape == "Diamond":
        body = f'<polygon {base_attrs} points="32,6 58,32 32,58 6,32"/>'
    elif shape == "Triangle":
        body = f'<polygon {base_attrs} points="32,7 58,55 6,55"/>'
    else:
        body = f'<circle {base_attrs} cx="32" cy="32" r="24"/>'
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">{body}</svg>'
    return f"data:image/svg+xml;charset=utf-8,{urllib.parse.quote(svg)}"


def add_marker_icons(map_df: pd.DataFrame, visualization: dict[str, Any]) -> pd.DataFrame:
    shaped = map_df.copy()
    shape = visualization.get("marker_shape", "Circle")
    if shape not in MARKER_SHAPES:
        shape = "Circle"
    opacity = max(0.1, min(1.0, float(visualization.get("marker_opacity", 0.82))))
    stroke_color = hex_to_rgb(visualization.get("marker_stroke_color", "#141414"))
    stroke_width = int(visualization.get("marker_stroke_width", 1))
    shaped["icon_data"] = shaped["fill_color"].apply(
        lambda color: {
            "url": marker_icon_svg(shape, color, stroke_color, opacity, stroke_width),
            "width": 64,
            "height": 64,
            "anchorY": 64 if shape == "Pin" else 32,
        }
    )
    shaped["marker_size"] = int(visualization.get("marker_size", 18))
    return shaped


def calculate_view_state(df: pd.DataFrame) -> pdk.ViewState:
    if df.empty:
        return pdk.ViewState(latitude=39.5, longitude=-98.35, zoom=3, min_zoom=2, max_zoom=18, pitch=0)
    lat = pd.to_numeric(df["stop_lat"], errors="coerce")
    lon = pd.to_numeric(df["stop_lon"], errors="coerce")
    return pdk.ViewState(
        latitude=float(lat.mean()),
        longitude=float(lon.mean()),
        zoom=10 if max(lat.max() - lat.min(), lon.max() - lon.min()) < 0.8 else 8,
        min_zoom=2,
        max_zoom=18,
        pitch=0,
    )


def build_deck_chart(df: pd.DataFrame, taxonomy: list[dict[str, Any]], visualization: dict[str, Any]) -> pdk.Deck:
    map_df = color_dataset(df, taxonomy, visualization)
    if visualization.get("marker_shape", "Circle") == "Circle":
        marker_size = max(4, min(48, int(visualization.get("marker_size", 7))))
        map_df["marker_size"] = marker_size
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            id="stops_layer",
            get_position="[stop_lon, stop_lat]",
            get_fill_color="fill_color",
            get_radius="marker_size",
            radius_units="pixels",
            radius_min_pixels=4,
            radius_max_pixels=48,
            opacity=max(0.1, min(1.0, float(visualization.get("marker_opacity", 0.82)))),
            stroked=True,
            get_line_color=hex_to_rgb(visualization.get("marker_stroke_color", "#141414")),
            line_width_min_pixels=max(0, int(visualization.get("marker_stroke_width", 1))),
            pickable=True,
            auto_highlight=True,
        )
    else:
        map_df = add_marker_icons(map_df, visualization)
        layer = pdk.Layer(
            "IconLayer",
            data=map_df,
            id="stops_layer",
            get_icon="icon_data",
            get_position="[stop_lon, stop_lat]",
            get_size="marker_size",
            size_units="pixels",
            size_min_pixels=4,
            size_max_pixels=48,
            pickable=True,
            auto_highlight=True,
        )
    return pdk.Deck(
        initial_view_state=calculate_view_state(map_df),
        layers=[layer],
        map_style=MAP_STYLES.get(visualization.get("map_style", "Light"), pdk.map_styles.CARTO_LIGHT),
        tooltip={"text": build_tooltip_text(map_df, visualization)},
    )


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
        "project": st.session_state["project"],
        "taxonomy": st.session_state["taxonomy"],
        "methodology": st.session_state["methodology"],
        "visualization": st.session_state["visualization"],
        "import_log": st.session_state["import_log"],
    }


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


def published_app_source() -> str:
    return r'''import base64
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pydeck as pdk
import streamlit as st


APP_DIR = Path(__file__).parent
CONFIG_PATH = APP_DIR / "shade_study_config.json"
DATA_PATH = APP_DIR / "shade_study_stops.csv"
RECORD_COUNT_FIELD = "Record count"

MAP_STYLES = {
    "Light": pdk.map_styles.CARTO_LIGHT,
    "Dark": pdk.map_styles.CARTO_DARK,
    "Road": pdk.map_styles.CARTO_ROAD,
    "Light, no labels": pdk.map_styles.CARTO_LIGHT_NO_LABELS,
    "Dark, no labels": pdk.map_styles.CARTO_DARK_NO_LABELS,
}

COLOR_MODE_FIELDS = {
    "Shade category": "shading",
    "Review status": "review_status",
    "Priority score": "priority_score",
}

DEFAULT_DISPLAY_COLUMNS = ["stop_id", "stop_name", "routes", "shading", "review_status", "priority_score"]
DEFAULT_PALETTE = [
    "#2563eb", "#16a34a", "#dc2626", "#9333ea", "#d97706",
    "#0891b2", "#be123c", "#4d7c0f", "#7c3aed", "#0f766e",
]


def load_study() -> tuple[dict[str, Any], pd.DataFrame]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    stops = pd.read_csv(DATA_PATH)
    stops["priority_score"] = calculate_priority_scores(
        stops, config.get("visualization", {}).get("priority_weights", {})
    )
    return config, stops


def normalize_hex_color(value: str, fallback: str = "#808080") -> str:
    text = str(value or "").strip()
    if not text.startswith("#"):
        text = f"#{text}"
    return text if len(text) == 7 else fallback


def hex_to_rgb(value: str) -> list[int]:
    color = normalize_hex_color(value).lstrip("#")
    return [int(color[index : index + 2], 16) for index in (0, 2, 4)]


def calculate_priority_scores(df: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    score = pd.Series(0.0, index=df.index)
    weight_total = 0.0
    ridership_weight = float(weights.get("ridership", 0) or 0)
    if ridership_weight and "ridership" in df:
        ridership = pd.to_numeric(df["ridership"], errors="coerce").fillna(0)
        max_ridership = ridership.max()
        if max_ridership > 0:
            score += ridership_weight * (ridership / max_ridership)
            weight_total += ridership_weight
    low_shade_weight = float(weights.get("low_shade", 0) or 0)
    if low_shade_weight and "shading" in df:
        low_shade = df["shading"].isin(["No Shade", "Limited Natural Shade", "Needs Review"]).astype(float)
        score += low_shade_weight * low_shade
        weight_total += low_shade_weight
    if weight_total == 0:
        return pd.Series(0.0, index=df.index)
    return (score / weight_total).round(4)


def get_selected_display_columns(df: pd.DataFrame, visualization: dict[str, Any]) -> list[str]:
    configured = visualization.get("display_columns") or DEFAULT_DISPLAY_COLUMNS
    columns = [column for column in configured if column in df.columns]
    return columns or [column for column in DEFAULT_DISPLAY_COLUMNS if column in df.columns] or list(df.columns[:8])


def color_lookup(df: pd.DataFrame, taxonomy: list[dict[str, Any]], visualization: dict[str, Any]) -> tuple[str, dict[str, list[int]]]:
    label = visualization.get("color_by", "Shade category")
    field = COLOR_MODE_FIELDS.get(label, label)
    if field not in df.columns:
        field = "shading" if "shading" in df.columns else df.columns[0]
    if field == "priority_score":
        colors = visualization.get("priority_colors", {})
        return field, {
            "low": hex_to_rgb(colors.get("low", "#34d399")),
            "mid": hex_to_rgb(colors.get("mid", "#facc15")),
            "high": hex_to_rgb(colors.get("high", "#ef4444")),
        }
    if field == "shading":
        mapping = {
            str(item.get("name", "")): hex_to_rgb(item.get("color", "#808080"))
            for item in taxonomy
        }
    else:
        stored = visualization.get("field_color_maps", {}).get(field, {})
        values = sorted(str(value) for value in df[field].fillna("Unknown").unique())
        mapping = {
            value: hex_to_rgb(stored.get(value, DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)]))
            for index, value in enumerate(values)
        }
    mapping.setdefault("Unknown", [128, 128, 128])
    return field, mapping


def marker_color(row: pd.Series, field: str, mapping: dict[str, list[int]]) -> list[int]:
    if field == "priority_score":
        score = float(row.get("priority_score", 0) or 0)
        if score >= 0.66:
            return mapping["high"]
        if score >= 0.33:
            return mapping["mid"]
        return mapping["low"]
    return mapping.get(str(row.get(field, "Unknown")), mapping.get("Unknown", [128, 128, 128]))


def build_tooltip_text(df: pd.DataFrame, visualization: dict[str, Any]) -> str:
    columns = get_selected_display_columns(df, visualization)[:8]
    return "\n".join([f"{column}: {{{column}}}" for column in columns])


def marker_svg(shape: str, fill: list[int], stroke: str) -> str:
    fill_hex = "#%02x%02x%02x" % tuple(fill)
    stroke_hex = normalize_hex_color(stroke, "#141414")
    if shape == "Square":
        body = f"<rect x='6' y='6' width='52' height='52' rx='6' fill='{fill_hex}' stroke='{stroke_hex}' stroke-width='4'/>"
    elif shape == "Diamond":
        body = f"<path d='M32 4 L60 32 L32 60 L4 32 Z' fill='{fill_hex}' stroke='{stroke_hex}' stroke-width='4'/>"
    elif shape == "Triangle":
        body = f"<path d='M32 5 L60 58 L4 58 Z' fill='{fill_hex}' stroke='{stroke_hex}' stroke-width='4'/>"
    else:
        body = f"<path d='M32 4 C18 4 7 15 7 29 C7 49 32 62 32 62 C32 62 57 49 57 29 C57 15 46 4 32 4 Z' fill='{fill_hex}' stroke='{stroke_hex}' stroke-width='4'/><circle cx='32' cy='29' r='9' fill='white' fill-opacity='0.85'/>"
    svg = f"<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 64 64'>{body}</svg>"
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def calculate_view_state(df: pd.DataFrame) -> pdk.ViewState:
    return pdk.ViewState(
        latitude=float(df["stop_lat"].mean()),
        longitude=float(df["stop_lon"].mean()),
        zoom=10,
        pitch=0,
    )


def build_deck_chart(df: pd.DataFrame, taxonomy: list[dict[str, Any]], visualization: dict[str, Any]) -> pdk.Deck:
    map_df = df.dropna(subset=["stop_lat", "stop_lon"]).copy()
    field, colors = color_lookup(map_df, taxonomy, visualization)
    map_df["marker_color"] = map_df.apply(lambda row: marker_color(row, field, colors), axis=1)
    marker_size = int(visualization.get("marker_size", 7) or 7)
    shape = visualization.get("marker_shape", "Circle")
    if shape == "Circle":
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position="[stop_lon, stop_lat]",
            get_fill_color="marker_color",
            get_radius=marker_size,
            radius_units="pixels",
            radius_min_pixels=4,
            radius_max_pixels=48,
            opacity=float(visualization.get("marker_opacity", 0.82) or 0.82),
            stroked=True,
            get_line_color=hex_to_rgb(visualization.get("marker_stroke_color", "#141414")),
            line_width_min_pixels=int(visualization.get("marker_stroke_width", 1) or 1),
            pickable=True,
            auto_highlight=True,
        )
    else:
        stroke = visualization.get("marker_stroke_color", "#141414")
        map_df["icon_data"] = map_df["marker_color"].apply(
            lambda color: {"url": marker_svg(shape, color, stroke), "width": 64, "height": 64, "anchorY": 64}
        )
        map_df["icon_size"] = marker_size * 4
        layer = pdk.Layer(
            "IconLayer",
            data=map_df,
            get_icon="icon_data",
            get_position="[stop_lon, stop_lat]",
            get_size="icon_size",
            size_units="pixels",
            size_min_pixels=16,
            size_max_pixels=96,
            pickable=True,
            auto_highlight=True,
        )
    return pdk.Deck(
        initial_view_state=calculate_view_state(map_df),
        layers=[layer],
        map_style=MAP_STYLES.get(visualization.get("map_style", "Light"), pdk.map_styles.CARTO_LIGHT),
        tooltip={"text": build_tooltip_text(map_df, visualization)},
    )


def filter_unlabeled_stops(df: pd.DataFrame, show_unlabeled: bool) -> pd.DataFrame:
    if show_unlabeled or "shading" not in df.columns:
        return df
    return df[df["shading"] != "Needs Review"].copy()


def render_metric_cards(df: pd.DataFrame) -> None:
    no_shade = int((df.get("shading", pd.Series(dtype=str)) == "No Shade").sum()) if not df.empty else 0
    needs_review = int((df.get("shading", pd.Series(dtype=str)) == "Needs Review").sum()) if not df.empty else 0
    accepted = int((df.get("review_status", pd.Series(dtype=str)) == "Accepted").sum()) if not df.empty else 0
    cols = st.columns(4)
    cols[0].metric("Stops", f"{len(df):,}")
    cols[1].metric("No shade", f"{no_shade:,}")
    cols[2].metric("Needs review", f"{needs_review:,}")
    cols[3].metric("Accepted", f"{accepted:,}")


def chart_data(df: pd.DataFrame, chart: dict[str, Any]) -> tuple[pd.DataFrame, str, str]:
    x_field = chart.get("x", "shading")
    y_field = chart.get("y", RECORD_COUNT_FIELD)
    aggregation = chart.get("aggregation", "Count")
    if x_field not in df.columns:
        return pd.DataFrame(), "", ""
    if y_field == RECORD_COUNT_FIELD or aggregation == "Count":
        data = df.groupby(x_field, dropna=False).size().reset_index(name="stops")
        return data, x_field, "stops"
    if y_field not in df.columns:
        return pd.DataFrame(), "", ""
    working = df.loc[:, [x_field, y_field]].copy()
    working[y_field] = pd.to_numeric(working[y_field], errors="coerce")
    grouped = working.groupby(x_field, dropna=False)[y_field]
    if aggregation == "Average":
        data = grouped.mean().reset_index()
    elif aggregation == "Maximum":
        data = grouped.max().reset_index()
    elif aggregation == "Minimum":
        data = grouped.min().reset_index()
    else:
        data = grouped.sum().reset_index()
    return data, x_field, y_field


def render_custom_charts(df: pd.DataFrame, visualization: dict[str, Any]) -> None:
    charts = visualization.get("custom_charts") or []
    if not charts:
        return
    columns = st.columns(2)
    for index, chart in enumerate(charts):
        data, x_field, y_field = chart_data(df, chart)
        if data.empty:
            continue
        with columns[index % 2]:
            st.markdown(f"#### {chart.get('title') or 'Chart'}")
            chart_type = chart.get("chart_type", "Bar")
            if chart_type == "Line":
                st.line_chart(data, x=x_field, y=y_field)
            elif chart_type == "Area":
                st.area_chart(data, x=x_field, y=y_field)
            elif chart_type == "Scatter":
                st.scatter_chart(data, x=x_field, y=y_field)
            else:
                st.bar_chart(data, x=x_field, y=y_field)


def render_methodology(config: dict[str, Any]) -> None:
    project = config.get("project", {})
    methodology = config.get("methodology", {})
    st.title(methodology.get("title") or project.get("name") or "Bus Stop Shade Study")
    st.markdown(f"### {methodology.get('summary', '')}")
    st.caption(
        f"{project.get('agency', 'Transit agency')} | {project.get('region', 'Region')} | "
        f"dataset v{project.get('dataset_version', 'draft')} | methodology v{project.get('methodology_version', 'draft')}"
    )
    sections = [
        ("Rationale", methodology.get("purpose", "")),
        ("Shade Assessment Method", methodology.get("shade_method", "")),
        ("Data Sources", methodology.get("data_sources", "")),
        ("Contributors", methodology.get("contributors", "")),
        ("Known Limitations", methodology.get("limitations", "")),
        ("Bibliography", methodology.get("bibliography", "")),
        ("Release History", methodology.get("release_history", "")),
        ("Citation", methodology.get("citation", "")),
    ]
    for title, body in sections:
        if str(body or "").strip():
            st.markdown(f"## {title}")
            st.markdown(body)
    taxonomy = config.get("taxonomy", [])
    if taxonomy:
        st.markdown("## Shade Taxonomy")
        st.dataframe(pd.DataFrame(taxonomy), use_container_width=True, hide_index=True)


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


def main() -> None:
    config, stops = load_study()
    project = config.get("project", {})
    methodology = config.get("methodology", {})
    visualization = config.get("visualization", {})
    taxonomy = config.get("taxonomy", [])

    st.set_page_config(page_title=project.get("name", "Shade Study"), layout="wide")
    st.title(project.get("name", "Shade Study"))
    st.markdown(f"### {methodology.get('summary', '')}")
    st.caption(f"{project.get('agency', '')} | {project.get('region', '')} | dataset v{project.get('dataset_version', 'draft')}")

    show_unlabeled = st.toggle("Show unlabeled bus stops", value=True)
    visible_stops = filter_unlabeled_stops(stops, show_unlabeled)
    render_metric_cards(visible_stops)

    tabs = st.tabs(["Map", "Analytics", "Methodology", "Downloads"])
    with tabs[0]:
        if visible_stops.empty:
            st.info("No stops match the current visibility settings.")
        else:
            st.pydeck_chart(build_deck_chart(visible_stops, taxonomy, visualization), use_container_width=True)
        if visualization.get("show_legend", True) and taxonomy:
            legend = pd.DataFrame(taxonomy)
            columns = [column for column in ["name", "description", "color"] if column in legend.columns]
            st.dataframe(legend.loc[:, columns], use_container_width=True, hide_index=True)
    with tabs[1]:
        render_custom_charts(visible_stops, visualization)
        selected = visualization.get("metric_cards", [])
        summary_cols = st.columns([1, 1])
        if "Shade distribution" in selected and "shading" in visible_stops.columns:
            with summary_cols[0]:
                st.markdown("#### Shade Distribution")
                counts = visible_stops["shading"].value_counts().rename_axis("shade_category").reset_index(name="stops")
                st.bar_chart(counts, x="shade_category", y="stops")
        if "Review status" in selected and "review_status" in visible_stops.columns:
            with summary_cols[1]:
                st.markdown("#### Review Status")
                counts = visible_stops["review_status"].value_counts().rename_axis("review_status").reset_index(name="stops")
                st.bar_chart(counts, x="review_status", y="stops")
        if "Priority stops" in selected:
            st.markdown("#### Highest Priority Stops")
            priority = visible_stops.sort_values("priority_score", ascending=False).head(20)
            columns = get_selected_display_columns(priority, visualization)
            st.dataframe(priority.loc[:, columns], use_container_width=True, hide_index=True)
    with tabs[2]:
        render_methodology(config)
    with tabs[3]:
        if visualization.get("show_downloads", True):
            st.download_button("Download stops CSV", stops.to_csv(index=False).encode("utf-8"), "shade_study_stops.csv", "text/csv")
            st.download_button("Download stops GeoJSON", dataframe_to_geojson(stops).encode("utf-8"), "shade_study_stops.geojson", "application/geo+json")
            st.download_button("Download study configuration", json.dumps(config, indent=2).encode("utf-8"), "shade_study_config.json", "application/json")


if __name__ == "__main__":
    main()
'''


def deploy_readme(repo_name: str, project: dict[str, Any]) -> str:
    app_name = project.get("name", "Shade Study")
    return f"""# {app_name}

This repository was generated by Shade Study Builder. It contains a public Streamlit app rendered from the builder state at export time.

## Files

- `app.py`: public Streamlit app.
- `shade_study_stops.csv`: published stop dataset.
- `shade_study_config.json`: project metadata, methodology, taxonomy, visualization settings, and import log.
- `requirements.txt`: Python dependencies for Streamlit deployment.

## Publish To GitHub

Either create a new GitHub repository named `{repo_name}` and upload these files, or run:

```powershell
./deploy_to_github.ps1 -RepositoryName "{repo_name}"
```

The script requires Git and the GitHub CLI (`gh`) with an authenticated account.

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
    [string]$RepositoryName = "{repo_name}",
    [ValidateSet("public", "private")]
    [string]$Visibility = "public"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {{
    throw "Git is required before publishing."
}}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {{
    throw "GitHub CLI is required before publishing. Install gh and run gh auth login."
}}

if (-not (Test-Path ".git")) {{
    git init
    git branch -M main
}}

git add .
git commit -m "Publish shade study app"
gh repo create $RepositoryName --$Visibility --source=. --remote=origin --push
"""


def build_github_deploy_bundle(repo_name: str) -> bytes:
    stops = st.session_state["stops"].copy()
    stops["priority_score"] = calculate_priority_scores(stops, st.session_state["visualization"]["priority_weights"])
    config_json = study_config_json()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("app.py", published_app_source())
        bundle.writestr("shade_study_stops.csv", stops.to_csv(index=False))
        bundle.writestr("shade_study_config.json", config_json)
        bundle.writestr("requirements.txt", "streamlit>=1.57,<2\npandas>=2,<4\npydeck>=0.8,<1\n")
        bundle.writestr(".streamlit/config.toml", "[server]\nheadless = true\n\n[browser]\ngatherUsageStats = false\n")
        bundle.writestr(".gitignore", "__pycache__/\n*.pyc\n.streamlit/secrets.toml\n")
        bundle.writestr("README.md", deploy_readme(repo_name, st.session_state["project"]))
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
    pages = ["Data", "Visuals", "Methods", "Preview", "Deploy"]
    if st.session_state.get("page") not in pages:
        st.session_state["page"] = "Data"
    st.markdown(
        """
        <style>
        .builder-topbar {
            border-bottom: 1px solid #e5e7eb;
            margin: -1rem -1rem 1.2rem;
            padding: 0.55rem 1rem 0.85rem;
        }
        .builder-brand {
            color: #14532d;
            font-size: 1.12rem;
            font-weight: 700;
            letter-spacing: 0;
            white-space: nowrap;
        }
        .stButton button {
            border-radius: 999px;
            font-size: 0.86rem;
            min-height: 2.25rem;
            font-weight: 650;
            padding: 0.3rem 0.45rem;
            white-space: nowrap;
        }
        .stButton button p {
            white-space: nowrap;
        }
        .stButton button[kind="primary"] {
            background: #ff4b4b;
            border-color: #ff4b4b;
            color: white;
        }
        .stButton button[kind="secondary"] {
            background: white;
            border-color: #d1d5db;
            color: #31333f;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div class='builder-topbar'>", unsafe_allow_html=True)
    cols = st.columns([2.15, 2.25, 0.92, 0.92, 0.92, 0.92, 0.92], gap="small", vertical_alignment="center")
    with cols[0]:
        st.markdown("<div class='builder-brand'>Shade-GIS Study Builder</div>", unsafe_allow_html=True)
    for index, page in enumerate(pages, start=2):
        with cols[index]:
            st.button(
                page,
                key=f"nav_{page}",
                type="primary" if st.session_state["page"] == page else "secondary",
                use_container_width=True,
                on_click=set_page,
                args=(page,),
            )
    st.markdown("</div>", unsafe_allow_html=True)
    return st.session_state["page"]


def render_data_page() -> None:
    st.title("Project Data")
    project = st.session_state["project"]
    taxonomy = st.session_state["taxonomy"]

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Project")
        project["name"] = st.text_input("Project name", project["name"])
        project["agency"] = st.text_input("Transit agency", project["agency"])
        project["region"] = st.text_input("Geographic region", project["region"])
        project["owners"] = st.text_input("Owner(s)", project["owners"])
    with right:
        st.subheader("Publication")
        project["visibility"] = st.selectbox("Visibility", ["Public", "Private"], index=0 if project["visibility"] == "Public" else 1)
        project["dataset_version"] = st.text_input("Dataset version", project["dataset_version"])
        project["methodology_version"] = st.text_input("Methodology version", project["methodology_version"])
        project["description"] = st.text_area("Description", project["description"], height=118)

    st.subheader("Upload Or Map A Dataset")
    uploaded = st.file_uploader("Upload a GTFS .zip, stops.txt, or bus-stop CSV", type=["zip", "txt", "csv"])
    if uploaded is not None:
        contents = uploaded.getvalue()
        try:
            if uploaded.name.lower().endswith(".zip"):
                raw, metadata = parse_gtfs_zip(contents)
                st.dataframe(raw.head(25), use_container_width=True)
                if st.button("Use uploaded GTFS stops", type="primary"):
                    prepared = prepare_stop_dataset(raw, project, taxonomy)
                    st.session_state["stops"] = prepared
                    project["source_name"] = uploaded.name
                    st.session_state["import_log"].append(
                        {"source": uploaded.name, "format": "GTFS", "rows": len(prepared), **metadata}
                    )
                    st.success(f"Imported {len(prepared):,} mapped stops.")
            else:
                raw = read_csv_bytes(contents)
                st.dataframe(raw.head(25), use_container_width=True)
                choices = [""] + list(raw.columns)
                st.markdown("#### Field Mapping")
                mapping: dict[str, str] = {}
                fields = REQUIRED_STOP_FIELDS + OPTIONAL_FIELDS
                grid = st.columns(4)
                for index, field in enumerate(fields):
                    default_index = choices.index(field) if field in choices else 0
                    with grid[index % 4]:
                        mapping[field] = st.selectbox(field, choices, index=default_index, key=f"map_{field}")
                if st.button("Use mapped CSV", type="primary"):
                    prepared = prepare_stop_dataset(apply_field_mapping(raw, mapping), project, taxonomy)
                    st.session_state["stops"] = prepared
                    project["source_name"] = uploaded.name
                    st.session_state["import_log"].append(
                        {
                            "source": uploaded.name,
                            "format": "CSV",
                            "rows": len(prepared),
                            "imported_at": timestamp_with_timezone(),
                        }
                    )
                    st.success(f"Imported {len(prepared):,} mapped stops.")
        except Exception as error:
            st.error(f"Could not import this file: {error}")

    source_cols = st.columns(3)
    with source_cols[0]:
        project["source_name"] = st.text_input("Data source name", project["source_name"])
    with source_cols[1]:
        project["source_license"] = st.text_input("Source license", project["source_license"])
    with source_cols[2]:
        project["source_url"] = st.text_input("Source URL", project["source_url"])

    st.subheader("Shade Taxonomy")
    edited_taxonomy = st.data_editor(
        pd.DataFrame(taxonomy),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "name": st.column_config.TextColumn("Category"),
            "description": st.column_config.TextColumn("Definition"),
            "color": st.column_config.TextColumn("Hex color"),
            "sort_order": st.column_config.NumberColumn("Sort order", min_value=1, step=1),
        },
    )
    if st.button(
        "Apply taxonomy",
        help=(
            "Save the edited shade categories and reapply them to the active dataset "
            "so maps, legends, previews, and exports use the latest taxonomy."
        ),
    ):
        st.session_state["taxonomy"] = edited_taxonomy.fillna("").to_dict("records")
        st.session_state["stops"] = prepare_stop_dataset(st.session_state["stops"], project, st.session_state["taxonomy"])
        st.success("Taxonomy applied to the active dataset.")

    st.subheader("Dataset Health")
    st.dataframe(validation_summary(st.session_state["stops"]), use_container_width=True, hide_index=True)
    st.dataframe(st.session_state["stops"].head(50), use_container_width=True, hide_index=True)


def render_palette_controls(
    visualization: dict[str, Any],
    stops: pd.DataFrame,
    taxonomy: list[dict[str, Any]],
    color_options: dict[str, str],
) -> None:
    field = color_options.get(visualization.get("color_by", "Shade category"), "shading")
    st.markdown("#### Color Palette")
    if field == "shading":
        previous_palette = visualization.get("shade_palette", "Custom")
        palette_options = ["Custom"] + list(SHADE_PALETTES)
        if previous_palette not in palette_options:
            previous_palette = "Custom"
        selected_palette = st.selectbox(
            "Premade shade palette",
            palette_options,
            index=palette_options.index(previous_palette),
        )
        if selected_palette != "Custom" and selected_palette != previous_palette:
            palette = SHADE_PALETTES[selected_palette]
            for index, item in enumerate(taxonomy):
                color = palette[index % len(palette)]
                item["color"] = color
                st.session_state[f"shade_color_{index}"] = color
        visualization["shade_palette"] = selected_palette

        grid = st.columns(2)
        for index, item in enumerate(taxonomy):
            name = str(item.get("name", "")).strip() or f"Category {index + 1}"
            with grid[index % 2]:
                item["color"] = st.color_picker(
                    name,
                    normalize_hex_color(item.get("color", "#808080")),
                    key=f"shade_color_{index}",
                )
        return

    if field == "review_status":
        review_colors = visualization.setdefault("review_status_colors", {})
        grid = st.columns(2)
        for index, status in enumerate(REVIEW_STATUS_COLORS):
            review_colors.setdefault(status, rgb_to_hex(REVIEW_STATUS_COLORS[status]))
            with grid[index % 2]:
                review_colors[status] = st.color_picker(
                    status,
                    normalize_hex_color(review_colors[status]),
                    key=f"review_color_{status}",
                )
        return

    if field == "priority_score":
        priority_colors = visualization.setdefault("priority_colors", DEFAULT_VISUALIZATION["priority_colors"].copy())
        grid = st.columns(3)
        with grid[0]:
            priority_colors["low"] = st.color_picker(
                "Low score",
                normalize_hex_color(priority_colors.get("low"), DEFAULT_VISUALIZATION["priority_colors"]["low"]),
                key="priority_color_low",
            )
        with grid[1]:
            priority_colors["mid"] = st.color_picker(
                "Mid score",
                normalize_hex_color(priority_colors.get("mid"), DEFAULT_VISUALIZATION["priority_colors"]["mid"]),
                key="priority_color_mid",
            )
        with grid[2]:
            priority_colors["high"] = st.color_picker(
                "High score",
                normalize_hex_color(priority_colors.get("high"), DEFAULT_VISUALIZATION["priority_colors"]["high"]),
                key="priority_color_high",
            )
        return

    color_map = ensure_field_color_map(visualization, stops, field)
    values = field_values_for_colors(stops, field)
    if not values:
        st.caption("No values are available for the selected column.")
        return
    total_unique = stops[field].fillna("Unknown").astype(str).str.strip().replace("", "Unknown").nunique()
    if total_unique > len(values):
        st.caption(f"Showing colors for the first {len(values)} values in this column.")
    grid = st.columns(2)
    for index, value in enumerate(values):
        with grid[index % 2]:
            color_map[value] = st.color_picker(
                value[:80],
                normalize_hex_color(color_map.get(value, COLOR_PALETTE[index % len(COLOR_PALETTE)])),
                key=f"field_color_{field}_{index}",
            )


def render_visuals_page() -> None:
    st.title("Metrics And Visualizations")
    visualization = st.session_state["visualization"]
    stops = st.session_state["stops"]
    taxonomy = st.session_state["taxonomy"]

    controls, preview = st.columns([0.85, 1.15])
    with controls:
        with st.expander("Visualization Controls", expanded=True):
            with st.container(height=VISUAL_MAP_HEIGHT, border=False):
                color_options = get_color_options(stops)
                if visualization.get("color_by") not in color_options:
                    visualization["color_by"] = "Shade category"
                color_labels = list(color_options)
                visualization["color_by"] = st.selectbox(
                    "Color stops by",
                    color_labels,
                    index=color_labels.index(visualization["color_by"]),
                )
                marker_shape = visualization.get("marker_shape", "Circle")
                if marker_shape not in MARKER_SHAPES:
                    marker_shape = "Circle"
                visualization["marker_shape"] = st.selectbox(
                    "Marker shape",
                    MARKER_SHAPES,
                    index=MARKER_SHAPES.index(marker_shape),
                )
                visualization["marker_size"] = st.slider(
                    "Marker size",
                    4,
                    48,
                    int(visualization.get("marker_size", 7)),
                    1,
                )
                visualization["marker_opacity"] = st.slider(
                    "Marker opacity",
                    0.1,
                    1.0,
                    float(visualization.get("marker_opacity", 0.82)),
                    0.05,
                )
                visualization["marker_stroke_color"] = st.color_picker(
                    "Marker outline",
                    normalize_hex_color(visualization.get("marker_stroke_color", "#141414"), "#141414"),
                )
                visualization["marker_stroke_width"] = st.slider(
                    "Outline width",
                    0,
                    6,
                    int(visualization.get("marker_stroke_width", 1)),
                    1,
                )
                map_style = visualization.get("map_style", "Light")
                if map_style not in MAP_STYLES:
                    map_style = "Light"
                visualization["map_style"] = st.selectbox(
                    "Base map style",
                    list(MAP_STYLES),
                    index=list(MAP_STYLES).index(map_style),
                )
                overlay_options = get_available_overlays(stops)
                visualization["overlays"] = clean_selected_options(visualization.get("overlays", []), overlay_options)
                if overlay_options:
                    visualization["overlays"] = st.multiselect(
                        "Context layers to include",
                        overlay_options,
                        default=visualization["overlays"],
                        help=(
                            "Context layers are optional map/data overlays from fields in the active dataset, "
                            "such as routes, ridership, shelters, heat vulnerability, or canopy. They only appear "
                            "when those columns have usable values: at least one non-null cell with text or data "
                            "after blank spaces are trimmed."
                        ),
                    )
                else:
                    visualization["overlays"] = []
                    st.caption("No optional context layers are available in the active dataset.")

                metric_options = get_available_metric_cards(stops)
                visualization["metric_cards"] = clean_selected_options(
                    visualization.get("metric_cards", []), metric_options
                )
                if metric_options:
                    visualization["metric_cards"] = st.multiselect(
                        "Dashboard summaries",
                        metric_options,
                        default=visualization["metric_cards"],
                    )
                else:
                    visualization["metric_cards"] = []
                    st.caption("No dashboard summaries are available for the active dataset yet.")

                st.subheader("Custom Chart")
                charts = get_custom_charts(stops, visualization)
                chart_columns = get_chart_column_options(stops)
                if chart_columns:
                    chart_count = st.number_input(
                        "Number of custom charts",
                        min_value=1,
                        max_value=MAX_CUSTOM_CHARTS,
                        value=len(charts),
                        step=1,
                        help="Configure up to 10 charts for the public Analytics tab.",
                    )
                    chart_count = int(chart_count)
                    while len(charts) < chart_count:
                        charts.append(
                            ensure_custom_chart_defaults(
                                stops,
                                json.loads(json.dumps(DEFAULT_CUSTOM_CHART)),
                                len(charts),
                            )
                        )
                    charts = charts[:chart_count]
                    for index, chart in enumerate(charts):
                        chart = ensure_custom_chart_defaults(stops, chart, index)
                        with st.expander(chart.get("title", f"Custom chart {index + 1}"), expanded=index == 0):
                            chart["title"] = st.text_input(
                                "Chart title",
                                chart.get("title", f"Custom chart {index + 1}"),
                                key=f"custom_chart_title_{index}",
                            )
                            chart["x"] = st.selectbox(
                                "X column",
                                chart_columns,
                                index=chart_columns.index(chart["x"]),
                                format_func=display_label,
                                key=f"custom_chart_x_{index}",
                            )
                            y_options = [RECORD_COUNT_FIELD] + chart_columns
                            chart["y"] = st.selectbox(
                                "Y column",
                                y_options,
                                index=y_options.index(chart["y"]),
                                format_func=lambda value: value if value == RECORD_COUNT_FIELD else display_label(value),
                                key=f"custom_chart_y_{index}",
                            )
                            chart["aggregation"] = st.selectbox(
                                "Y aggregation",
                                CHART_AGGREGATIONS,
                                index=CHART_AGGREGATIONS.index(chart["aggregation"]),
                                key=f"custom_chart_aggregation_{index}",
                            )
                            chart["chart_type"] = st.selectbox(
                                "Chart type",
                                CHART_TYPES,
                                index=CHART_TYPES.index(chart["chart_type"]),
                                key=f"custom_chart_type_{index}",
                            )
                    visualization["custom_charts"] = charts
                else:
                    st.caption("Import a dataset before configuring a custom chart.")

                current_display_columns = get_selected_display_columns(stops, visualization)
                display_columns = st.multiselect(
                    "Published data columns",
                    get_display_column_options(stops),
                    default=current_display_columns,
                    format_func=display_label,
                    help="Choose which stop fields appear in the public analytics data table and map hover details.",
                )
                if display_columns:
                    visualization["display_columns"] = display_columns
                else:
                    st.warning("Select at least one column for the public data table.")
                    visualization["display_columns"] = current_display_columns
                visualization["show_legend"] = st.checkbox("Show legend", value=visualization["show_legend"])
                visualization["show_downloads"] = st.checkbox(
                    "Show public downloads", value=visualization["show_downloads"]
                )

                st.divider()
                render_palette_controls(visualization, stops, taxonomy, color_options)
                st.divider()
                st.subheader("Priority Formula")
                weights = visualization["priority_weights"]
                priority_factors = []
                if has_column_data(stops, "ridership"):
                    priority_factors.append(("ridership", "Ridership weight"))
                if "shading" in stops.columns:
                    priority_factors.append(("low_shade", "Low shade weight"))
                if has_column_data(stops, "heat_vulnerability_index"):
                    priority_factors.append(("heat_vulnerability_index", "Heat vulnerability weight"))
                if has_column_data(stops, "tree_canopy_pct"):
                    priority_factors.append(("low_tree_canopy", "Low tree canopy weight"))

                if priority_factors:
                    for key, label in priority_factors:
                        weights[key] = st.slider(label, 0.0, 1.0, float(weights.get(key, 0.0)), 0.05)
                else:
                    st.caption("No priority factors are available in the active dataset.")
                st.caption("The preview stores the selected formula version with exported configuration.")

    st.session_state["stops"]["priority_score"] = calculate_priority_scores(stops, visualization["priority_weights"])
    display_columns = get_selected_display_columns(st.session_state["stops"], visualization)

    with preview:
        st.subheader("Map Preview")
        if stops.empty:
            st.warning("Import a dataset before configuring the map.")
        else:
            st.pydeck_chart(
                build_deck_chart(stops, st.session_state["taxonomy"], visualization),
                use_container_width=True,
                height=VISUAL_MAP_HEIGHT,
            )

    st.subheader("Custom Chart Preview")
    if stops.empty:
        st.info("Import a dataset to preview a custom chart.")
    else:
        render_custom_charts(st.session_state["stops"], visualization)

    st.subheader("Data Table Preview")
    if stops.empty:
        st.info("Import a dataset to preview selected data columns.")
    else:
        st.dataframe(
            st.session_state["stops"].loc[:, display_columns].head(20),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Available Fields")
    active_columns = get_active_data_columns(stops)
    field_summary = pd.DataFrame(
        [{"field": column, "non_null_values": int(stops[column].notna().sum())} for column in active_columns]
    )
    st.dataframe(field_summary, use_container_width=True, hide_index=True)


def render_methodology_page() -> None:
    st.title("Rationale And About Page")
    methodology = st.session_state["methodology"]

    edit, preview = st.columns([1, 1])
    with edit:
        methodology["title"] = st.text_input("About page title", methodology["title"])
        methodology["summary"] = st.text_area("Summary", methodology["summary"], height=85)
        methodology["purpose"] = st.text_area("Rationale", methodology["purpose"], height=130)
        methodology["shade_method"] = st.text_area("Shade assessment method", methodology["shade_method"], height=130)
        methodology["data_sources"] = st.text_area("Data sources", methodology["data_sources"], height=135)
        methodology["contributors"] = st.text_area("Contributors", methodology["contributors"], height=85)
        methodology["limitations"] = st.text_area("Known limitations", methodology["limitations"], height=110)
        methodology.setdefault("bibliography", DEFAULT_METHODOLOGY["bibliography"])
        methodology["bibliography"] = st.text_area(
            "Bibliography",
            methodology["bibliography"],
            height=170,
            help=(
                "Use the same grouped APA format as citations: unindented lines are group labels, "
                "and indented lines render as hanging-indent bibliography entries."
            ),
            placeholder=(
                "Works referenced:\n"
                "    Author, A. A., & Author, B. B. (Year). Title of article. Title of Journal, volume(issue), page range. https://doi.org/xxxxx\n"
                "    Author or Organization. (Year). Title of report. Publisher. URL\n\n"
                "Data and software:\n"
                "    Author or Organization. (Year). Title of software or dataset (Version number) [Software or data set]. Publisher. URL"
            ),
        )
        methodology["release_history"] = st.text_area("Release history", methodology["release_history"], height=95)
        methodology["citation"] = st.text_area(
            "Citation",
            methodology["citation"],
            height=150,
            help=(
                "Use unindented lines as citation group labels. Put each citation on an indented line "
                "under its group to render a hanging indent on the public methodology page. The examples use APA style."
            ),
            placeholder=(
                "Transit data:\n"
                "    Author or Organization. (Year). Title of dataset (Version number) [Data set]. Publisher. URL\n\n"
                "Methods and references:\n"
                "    Author, A. A., & Author, B. B. (Year). Title of article. Title of Journal, volume(issue), page range. https://doi.org/xxxxx\n"
                "    Author or Organization. (Year). Title of report. Publisher. URL"
            ),
        )
    with preview:
        render_builder_about_page(
            project=st.session_state["project"],
            methodology=methodology,
            taxonomy=st.session_state["taxonomy"],
            import_log=st.session_state["import_log"],
            priority_formula=priority_formula_for_about(st.session_state["visualization"]),
        )


def render_metric_cards(df: pd.DataFrame) -> None:
    no_shade = int((df["shading"] == "No Shade").sum()) if not df.empty else 0
    needs_review = int((df["shading"] == "Needs Review").sum()) if not df.empty else 0
    accepted = int((df["review_status"] == "Accepted").sum()) if not df.empty else 0
    cols = st.columns(4)
    cols[0].metric("Stops", f"{len(df):,}")
    cols[1].metric("No shade", f"{no_shade:,}")
    cols[2].metric("Needs review", f"{needs_review:,}")
    cols[3].metric("Accepted", f"{accepted:,}")


def filter_unlabeled_stops(df: pd.DataFrame, show_unlabeled: bool) -> pd.DataFrame:
    if show_unlabeled or "shading" not in df.columns:
        return df
    return df[df["shading"] != "Needs Review"].copy()


def render_preview_page() -> None:
    project = st.session_state["project"]
    methodology = st.session_state["methodology"]
    visualization = st.session_state["visualization"]
    taxonomy = st.session_state["taxonomy"]
    stops = st.session_state["stops"]
    stops["priority_score"] = calculate_priority_scores(stops, visualization["priority_weights"])

    st.title(project["name"])
    st.markdown(f"### {methodology['summary']}")
    st.caption(f"{project['agency']} | {project['region']} | dataset v{project['dataset_version']}")

    if stops.empty:
        st.warning("Import a stop dataset before previewing the public app.")
        return

    show_unlabeled = st.toggle("Show unlabeled bus stops", value=True, key="preview_show_unlabeled_stops")
    visible_stops = filter_unlabeled_stops(stops, show_unlabeled)

    render_metric_cards(visible_stops)
    tabs = st.tabs(["Map", "Analytics", "Methodology", "Exports"])
    with tabs[0]:
        if visible_stops.empty:
            st.info("No stops match the current visibility settings.")
        else:
            st.pydeck_chart(build_deck_chart(visible_stops, taxonomy, visualization), use_container_width=True)
        if visualization.get("show_legend", True):
            legend = pd.DataFrame(taxonomy).sort_values("sort_order")
            st.dataframe(legend.loc[:, ["name", "description", "color"]], use_container_width=True, hide_index=True)
    with tabs[1]:
        render_custom_charts(visible_stops, visualization)

        selected_metrics = clean_selected_options(
            visualization.get("metric_cards", []), get_available_metric_cards(visible_stops)
        )
        summary_cols = st.columns([1, 1])
        if "Shade distribution" in selected_metrics and "shading" in visible_stops.columns:
            with summary_cols[0]:
                st.markdown("#### Shade Distribution")
                shade_counts = (
                    visible_stops["shading"].value_counts().rename_axis("shade_category").reset_index(name="stops")
                )
                st.bar_chart(shade_counts, x="shade_category", y="stops")
        if "Review status" in selected_metrics and "review_status" in visible_stops.columns:
            with summary_cols[1]:
                st.markdown("#### Review Status")
                review_counts = (
                    visible_stops["review_status"]
                    .value_counts()
                    .rename_axis("review_status")
                    .reset_index(name="stops")
                )
                st.bar_chart(review_counts, x="review_status", y="stops")
        if "Priority stops" in selected_metrics:
            st.markdown("#### Highest Priority Stops")
            priority = visible_stops.sort_values("priority_score", ascending=False).head(20)
            display_columns = get_selected_display_columns(priority, visualization)
            st.dataframe(
                priority.loc[:, display_columns],
                use_container_width=True,
                hide_index=True,
            )
    with tabs[2]:
        render_builder_about_page(
            project=project,
            methodology=methodology,
            taxonomy=taxonomy,
            import_log=st.session_state["import_log"],
            priority_formula=priority_formula_for_about(visualization),
        )
    with tabs[3]:
        if visualization.get("show_downloads", True):
            st.download_button(
                "Download stops CSV",
                data=stops.to_csv(index=False).encode("utf-8"),
                file_name="shade_study_stops.csv",
                mime="text/csv",
            )
            st.download_button(
                "Download stops GeoJSON",
                data=dataframe_to_geojson(stops).encode("utf-8"),
                file_name="shade_study_stops.geojson",
                mime="application/geo+json",
            )
            st.download_button(
                "Download study configuration",
                data=study_config_json().encode("utf-8"),
                file_name="shade_study_config.json",
                mime="application/json",
            )
        st.dataframe(pd.DataFrame(st.session_state["import_log"]), use_container_width=True, hide_index=True)


def render_deploy_page() -> None:
    project = st.session_state["project"]
    visualization = st.session_state["visualization"]
    stops = st.session_state["stops"]
    default_repo_name = slugify_repo_name(project.get("name", "shade-study-app"))

    st.title("Deploy")
    st.markdown(f"### Publish {project.get('name', 'this shade study')} as a GitHub-backed Streamlit app")

    if stops.empty:
        st.warning("Import a stop dataset before creating a deployment bundle.")
        return

    stops_for_export = stops.copy()
    stops_for_export["priority_score"] = calculate_priority_scores(stops_for_export, visualization["priority_weights"])

    left, right = st.columns([1, 1])
    with left:
        repo_name = st.text_input("GitHub repository name", default_repo_name)
        repo_name = slugify_repo_name(repo_name)
        st.link_button("Create GitHub repository", github_new_repo_url(project, repo_name))
    with right:
        st.metric("Stops included", f"{len(stops_for_export):,}")
        st.metric("Dataset version", project.get("dataset_version", "draft"))

    bundle_name = f"{repo_name}.zip"
    st.download_button(
        "Download GitHub deploy bundle",
        data=build_github_deploy_bundle(repo_name),
        file_name=bundle_name,
        mime="application/zip",
        type="primary",
    )

    st.markdown("#### Bundle Contents")
    st.dataframe(
        pd.DataFrame(
            [
                ("app.py", "Public Streamlit app rendered from the current builder state"),
                ("shade_study_stops.csv", "Published stop dataset"),
                ("shade_study_config.json", "Project, methodology, taxonomy, visualization, and import-log settings"),
                ("requirements.txt", "Runtime dependencies for Streamlit Community Cloud"),
                ("README.md", "GitHub and Streamlit deployment notes"),
                ("deploy_to_github.ps1", "Optional GitHub CLI publishing helper"),
            ],
            columns=["File", "Purpose"],
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("#### Command-Line Publish")
    st.code(
        f'Expand-Archive .\\{bundle_name} -DestinationPath .\\{repo_name}\n'
        f"Set-Location .\\{repo_name}\n"
        f'.\\deploy_to_github.ps1 -RepositoryName "{repo_name}"',
        language="powershell",
    )


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    ensure_state()
    if st.session_state.get("page") == "Methodology":
        st.session_state["page"] = "Methods"
    page = render_header()
    if page == "Visuals":
        render_visuals_page()
    elif page == "Methods":
        render_methodology_page()
    elif page == "Preview":
        render_preview_page()
    elif page == "Deploy":
        render_deploy_page()
    else:
        render_data_page()
