import json
import math
import re
import urllib.parse
from pathlib import Path
from typing import Any

import pandas as pd
import pydeck as pdk
import streamlit as st

# The published app is standalone, so carry the same object-string guard used
# by the builder before any dataframe is constructed or displayed.
pd.options.future.infer_string = False

from public_voting import normalize_voting_config, render_voting_panel


APP_DIR = Path(__file__).parent
CONFIG_PATH = APP_DIR / "shade_study_config.json"
DATA_PATH = APP_DIR / "shade_study_stops.csv"
RAW_LABELS_PATH = APP_DIR / "shade_study_raw_labels.csv"
RECORD_COUNT_FIELD = "Record count"
MAP_PANEL_HEIGHT = 620
STOP_DETAIL_PANEL_HEIGHT = MAP_PANEL_HEIGHT

MAP_STYLES = {
    "Light": pdk.map_styles.CARTO_LIGHT,
    "Dark": pdk.map_styles.CARTO_DARK,
    "Road": pdk.map_styles.CARTO_ROAD,
    "Light, no labels": pdk.map_styles.CARTO_LIGHT_NO_LABELS,
    "Dark, no labels": pdk.map_styles.CARTO_DARK_NO_LABELS,
}

COLOR_MODE_FIELDS = {
    "Shade coverage": "shading",
    "Review status": "review_status",
    "Priority score": "priority_score",
}
LEGACY_COLOR_MODE_FIELDS = {"Shade category": "shading"}

DEFAULT_DISPLAY_COLUMNS = ["stop_id", "stop_name", "routes", "shading", "review_status", "priority_score"]
DEFAULT_PALETTE = [
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
MARKER_SHAPES = ["Circle", "Pin", "Square", "Diamond", "Triangle"]
FILTER_FIELD_LABELS = {
    "shading": "Shade coverage",
    "review_status": "Review status",
    "confidence": "Confidence",
    "ridership": "Ridership",
    "priority_score": "Priority score",
}
FIELD_LABELS = {
    "stop_id": "Stop ID",
    "stop_name": "Stop name",
    "stop_lat": "Latitude",
    "stop_lon": "Longitude",
    "agency": "Agency",
    "routes": "Routes",
    "municipality": "Municipality",
    "shading": "Shade coverage",
    "shade_coverage": "Shade coverage",
    "shade_sources": "Shade sources",
    "review_status": "Review status",
    "confidence": "Confidence",
    "ridership": "Ridership",
    "nearby_destinations": "Nearby destinations",
    "priority_score": "Priority score",
}
DESTINATION_FILTER_COLUMNS = ["nearby_destinations", "destinations", "destination"]
BASE_CATEGORICAL_MAP_FILTERS = ["shading", "review_status"]
BASE_NUMERIC_MAP_FILTERS = ["confidence", "ridership", "priority_score"]
FILTER_EXCLUDED_FIELDS = {
    "stop_id",
    "stop_name",
    "stop_lat",
    "stop_lon",
    "routes",
    "route",
    "nearby_destinations",
    "destinations",
    "destination",
}
METRIC_REQUIREMENTS = {
    "Shade sources": ["shade_sources"],
    "Shade coverage": ["shade_coverage"],
    "Shade distribution": ["shading"],
    "Stops without shade": ["shading"],
    "Stops requiring review": ["shading"],
    "Review status": ["review_status"],
    "Agreement metrics": [],
    "Shade by route": ["routes", "shading"],
    "Shade by neighborhood": ["municipality", "shading"],
    "Shade vs ridership": ["ridership", "shading"],
    "Priority stops": ["priority_score"],
}
DEFAULT_METRIC_CARDS = ["Shade sources", "Shade coverage"]
LEGACY_DEFAULT_METRIC_CARDS = [
    "Shade distribution",
    "Stops without shade",
    "Stops requiring review",
    "Review status",
    "Agreement metrics",
    "Shade by route",
    "Shade by neighborhood",
    "Shade vs ridership",
    "Priority stops",
]
SHADE_SOURCE_CHART_CODES = {"natural": "Natural", "constructed": "Constructed", "manmade": "Manmade"}
SHADE_SOURCE_CHART_ALIASES = {
    "intentional built": "Constructed",
    "intentional constructed": "Constructed",
    "constructed shade": "Constructed",
    "incidental built": "Manmade",
    "manmade shade": "Manmade",
    "natural shade": "Natural",
}
SHADE_COVERAGE_CHART_CODES = {
    "no shade": "No Shade",
    "limited": "Limited Shade",
    "limited shade": "Limited Shade",
    "limited natural shade": "Limited Shade",
    "significant": "Significant Shade",
    "significant shade": "Significant Shade",
    "significant natural shade": "Significant Shade",
}


def load_study() -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    stops = pd.read_csv(DATA_PATH)
    raw_labels = pd.read_csv(RAW_LABELS_PATH) if RAW_LABELS_PATH.exists() else pd.DataFrame()
    stops = normalize_published_stop_dimensions(stops)
    stops["priority_score"] = calculate_priority_scores(
        stops, config.get("visualization", {}).get("priority_weights", {})
    )
    return config, stops, raw_labels


def normalize_published_stop_dimensions(stops: pd.DataFrame) -> pd.DataFrame:
    normalized = stops.copy()
    if "shading" not in normalized.columns:
        normalized["shading"] = ""
    if "shade_coverage" not in normalized.columns:
        normalized["shade_coverage"] = ""
    if "shade_sources" not in normalized.columns:
        normalized["shade_sources"] = ""

    legacy_shading = normalized["shading"].fillna("").astype(str)
    explicit_coverage = normalized["shade_coverage"].fillna("").astype(str).str.strip()
    coverage_candidates = explicit_coverage.where(explicit_coverage != "", legacy_shading)
    normalized["shade_coverage"] = coverage_candidates.map(
        lambda value: normalize_shade_coverage_chart_value(value) or "Needs Review"
    )
    normalized["shading"] = normalized["shade_coverage"]

    def normalize_sources(value: Any, legacy_value: Any, coverage: str) -> str:
        sources = []
        for part in re.split(r"[;,|]", str(value or "")):
            source = normalize_shade_source_chart_value(part)
            if source and source not in sources:
                sources.append(source)
        legacy_text = str(legacy_value or "").lower()
        if not sources:
            if any(token in legacy_text for token in ["natural", "tree", "vegetation"]):
                sources.append("Natural")
            if any(token in legacy_text for token in ["constructed", "intentional", "shelter", "canopy"]):
                sources.append("Constructed")
            if any(token in legacy_text for token in ["manmade", "incidental", "building"]):
                sources.append("Manmade")
        return "" if coverage == "No Shade" else "; ".join(sources)

    normalized["shade_sources"] = [
        normalize_sources(source, legacy, coverage)
        for source, legacy, coverage in zip(
            normalized["shade_sources"],
            legacy_shading,
            normalized["shade_coverage"],
            strict=False,
        )
    ]
    return normalized


def normalize_hex_color(value: str, fallback: str = "#808080") -> str:
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
        if "shade_coverage" in df.columns:
            low_shade_values = df["shade_coverage"].fillna("").astype(str).str.strip()
        else:
            low_shade_values = df["shading"].fillna("").astype(str).str.strip()
        low_shade = low_shade_values.isin(
            ["No Shade", "Limited Shade", "Limited", "Limited Natural Shade", "Needs Review"]
        ).astype(float)
        score += low_shade_weight * low_shade
        weight_total += low_shade_weight
    if weight_total == 0:
        return pd.Series(0.0, index=df.index)
    return ((score / weight_total) * 100).round(1)


def get_selected_display_columns(df: pd.DataFrame, visualization: dict[str, Any]) -> list[str]:
    configured = visualization.get("display_columns") or DEFAULT_DISPLAY_COLUMNS
    columns = [column for column in configured if column in df.columns]
    return columns or [column for column in DEFAULT_DISPLAY_COLUMNS if column in df.columns] or list(df.columns[:8])


def display_label(column: str) -> str:
    return FIELD_LABELS.get(column, column.replace("_", " ").title())


def field_values_for_colors(df: pd.DataFrame, field: str) -> list[str]:
    if field not in df.columns:
        return []
    values = df[field].fillna("Unknown").astype(str).str.strip()
    values = values.where(values != "", "Unknown")
    return sorted(values.unique().tolist())[: len(DEFAULT_PALETTE)]


def ensure_field_color_map(visualization: dict[str, Any], df: pd.DataFrame, field: str) -> dict[str, str]:
    field_maps = visualization.setdefault("field_color_maps", {})
    color_map = field_maps.setdefault(field, {})
    for index, value in enumerate(field_values_for_colors(df, field)):
        color_map.setdefault(value, DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)])
    return color_map


def clean_gis_overlays(visualization: dict[str, Any]) -> list[dict[str, Any]]:
    overlays = []
    for index, overlay in enumerate(visualization.get("gis_overlays") or []):
        if not isinstance(overlay, dict):
            continue
        geojson = overlay.get("geojson")
        if not isinstance(geojson, dict) or str(geojson.get("type", "")).lower() != "featurecollection":
            continue
        features = geojson.get("features")
        if not isinstance(features, list) or not features:
            continue
        cleaned = overlay.copy()
        cleaned.setdefault("id", f"gis_overlay_{index + 1}")
        cleaned.setdefault("name", f"GIS overlay {index + 1}")
        cleaned.setdefault("category", "Other")
        cleaned.setdefault("color", DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)])
        cleaned.setdefault("opacity", 0.35)
        cleaned.setdefault("line_width", 2)
        cleaned.setdefault("visible", True)
        cleaned["color"] = normalize_hex_color(cleaned.get("color", DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)]))
        cleaned["opacity"] = max(0.05, min(1.0, float(cleaned.get("opacity", 0.35) or 0.35)))
        cleaned["line_width"] = max(1, min(12, int(cleaned.get("line_width", 2) or 2)))
        overlays.append(cleaned)
    visualization["gis_overlays"] = overlays
    return overlays


def rgba_from_hex(value: str, opacity: float) -> list[int]:
    rgb = hex_to_rgb(normalize_hex_color(value))
    alpha = int(max(0.05, min(1.0, float(opacity))) * 255)
    return [rgb[0], rgb[1], rgb[2], alpha]


def build_gis_overlay_layers(visualization: dict[str, Any]) -> list[pdk.Layer]:
    layers = []
    for index, overlay in enumerate(clean_gis_overlays(visualization)):
        if not overlay.get("visible", True):
            continue
        color = rgba_from_hex(str(overlay.get("color", DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)])), overlay.get("opacity", 0.35))
        line_color = rgba_from_hex(str(overlay.get("color", DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)])), min(1.0, float(overlay.get("opacity", 0.35)) + 0.25))
        layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                data=overlay["geojson"],
                id=f"gis_overlay_{index}",
                pickable=True,
                stroked=True,
                filled=True,
                point_type="circle",
                get_fill_color=color,
                get_line_color=line_color,
                get_line_width=int(overlay.get("line_width", 2)),
                line_width_min_pixels=1,
                get_point_radius=35,
                point_radius_units=pdk.types.String("meters"),
                point_radius_min_pixels=4,
                auto_highlight=True,
            )
        )
    return layers


def build_tooltip_text(df: pd.DataFrame, visualization: dict[str, Any]) -> str:
    columns = get_selected_display_columns(df, visualization)[:8]
    return "\n".join(f"{display_label(column)}: {{{column}}}" for column in columns)


def get_color_options(df: pd.DataFrame) -> dict[str, str]:
    options = COLOR_MODE_FIELDS.copy()
    excluded = {"stop_id", "stop_name", "stop_lat", "stop_lon", "priority_score", "shading", "review_status"}
    for column in df.columns:
        if column in excluded:
            continue
        series = df[column].dropna().astype(str).str.strip()
        unique_count = series[series != ""].nunique()
        if 1 < unique_count <= len(DEFAULT_PALETTE):
            options[f"Column: {FIELD_LABELS.get(column, column)}"] = column
    return options


def color_for_priority(value: Any, visualization: dict[str, Any]) -> list[int]:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    score = 0.0 if pd.isna(numeric) else max(0.0, min(100.0, float(numeric)))
    colors = visualization.get("priority_colors", {})
    low = hex_to_rgb(colors.get("low", "#34d399"))
    mid = hex_to_rgb(colors.get("mid", "#facc15"))
    high = hex_to_rgb(colors.get("high", "#ef4444"))
    if score <= 50:
        start, end, fraction = low, mid, score / 50
    else:
        start, end, fraction = mid, high, (score - 50) / 50
    return [int(start[channel] + (end[channel] - start[channel]) * fraction) for channel in range(3)]


def color_dataset(df: pd.DataFrame, taxonomy: list[dict[str, Any]], visualization: dict[str, Any]) -> pd.DataFrame:
    colored = df.copy()
    color_options = get_color_options(colored)
    color_by = visualization.get("color_by", "Shade coverage")
    field = color_options.get(color_by) or LEGACY_COLOR_MODE_FIELDS.get(color_by, "shading")
    if field == "review_status":
        review_colors = visualization.get("review_status_colors", {})
        colored["fill_color"] = colored["review_status"].map(
            {status: hex_to_rgb(color) for status, color in review_colors.items()}
        )
    elif field == "priority_score":
        colored["fill_color"] = colored["priority_score"].apply(lambda value: color_for_priority(value, visualization))
    elif field == "shading":
        color_map = {
            str(item.get("name", "")).strip(): hex_to_rgb(str(item.get("color", "")))
            for item in taxonomy
            if str(item.get("name", "")).strip()
        }
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
    shaped["marker_size"] = int(visualization.get("marker_size", 7))
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
            radius_units=pdk.types.String("pixels"),
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
            size_units=pdk.types.String("pixels"),
            size_min_pixels=4,
            size_max_pixels=48,
            pickable=True,
            auto_highlight=True,
        )
    return pdk.Deck(
        initial_view_state=calculate_view_state(map_df),
        layers=[*build_gis_overlay_layers(visualization), layer],
        map_style=MAP_STYLES.get(visualization.get("map_style", "Light"), pdk.map_styles.CARTO_LIGHT),
        tooltip={"text": build_tooltip_text(map_df, visualization)},
    )


def filter_unlabeled_stops(df: pd.DataFrame, show_unlabeled: bool) -> pd.DataFrame:
    if show_unlabeled or "shading" not in df.columns:
        return df
    return df[df["shading"] != "Needs Review"].copy()


def split_route_values(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none"}:
        return []
    return [route.strip() for route in re.split(r"[;,|]+", text) if route.strip()]


def route_filter_options(df: pd.DataFrame) -> list[str]:
    if "routes" not in df.columns:
        return []
    routes: set[str] = set()
    for value in df["routes"].dropna():
        routes.update(split_route_values(value))
    return sorted(routes, key=lambda route: (len(route), route.lower()))


def filter_label(column: str) -> str:
    return FILTER_FIELD_LABELS.get(column, column.replace("_", " ").title())


def categorical_filter_options(df: pd.DataFrame, column: str) -> list[str]:
    if column not in df.columns:
        return []
    values = df[column].dropna().astype(str).str.strip()
    values = values[(values != "") & (values.str.lower() != "nan")]
    return sorted(values.unique().tolist())


def numeric_filter_bounds(df: pd.DataFrame, column: str) -> tuple[float, float] | None:
    if column not in df.columns:
        return None
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    values = values[values.apply(math.isfinite)]
    if values.empty:
        return None
    low = float(values.min())
    high = float(values.max())
    if math.isclose(low, high):
        return None
    return low, high


def categorical_map_filter_columns(df: pd.DataFrame) -> list[str]:
    columns = [column for column in BASE_CATEGORICAL_MAP_FILTERS if categorical_filter_options(df, column)]
    for column in df.columns:
        if column in columns or column in FILTER_EXCLUDED_FIELDS:
            continue
        if numeric_filter_bounds(df, column) is not None:
            continue
        options = categorical_filter_options(df, column)
        if 1 < len(options) <= 25:
            columns.append(column)
    return columns


def numeric_map_filter_columns(df: pd.DataFrame) -> list[str]:
    columns = [column for column in BASE_NUMERIC_MAP_FILTERS if numeric_filter_bounds(df, column) is not None]
    for column in df.columns:
        if column in columns or column in FILTER_EXCLUDED_FIELDS:
            continue
        if numeric_filter_bounds(df, column) is not None:
            columns.append(column)
    return columns


def destination_columns(df: pd.DataFrame) -> list[str]:
    return [column for column in DESTINATION_FILTER_COLUMNS if column in df.columns]


def current_map_filters(df: pd.DataFrame, key_prefix: str) -> dict[str, Any]:
    filters: dict[str, Any] = {
        "show_unlabeled": bool(st.session_state.get(f"{key_prefix}_show_unlabeled_stops", True)),
        "search_query": str(st.session_state.get(f"{key_prefix}_stop_search", "") or ""),
        "selected_routes": [
            route
            for route in st.session_state.get(f"{key_prefix}_route_filter", [])
            if route in route_filter_options(df)
        ],
        "categorical": {},
        "numeric": {},
        "destination_query": str(st.session_state.get(f"{key_prefix}_destination_filter", "") or ""),
    }
    for column in categorical_map_filter_columns(df):
        options = categorical_filter_options(df, column)
        selected = st.session_state.get(f"{key_prefix}_{column}_filter", [])
        filters["categorical"][column] = [value for value in selected if value in options]
    for column in numeric_map_filter_columns(df):
        bounds = numeric_filter_bounds(df, column)
        if bounds is None:
            continue
        selected = st.session_state.get(f"{key_prefix}_{column}_range", bounds)
        filters["numeric"][column] = {"selected": selected, "bounds": bounds}
    return filters


def render_map_filter_controls(df: pd.DataFrame, key_prefix: str) -> dict[str, Any]:
    with st.expander("Map filters", expanded=True):
        primary_cols = st.columns([1, 2, 2])
        primary_cols[0].toggle(
            "Show unlabeled bus stops",
            value=True,
            key=f"{key_prefix}_show_unlabeled_stops",
        )
        primary_cols[1].text_input(
            "Search stop name or ID",
            placeholder="Stop name or ID",
            key=f"{key_prefix}_stop_search",
        )
        primary_cols[2].multiselect(
            "Filter routes",
            route_filter_options(df),
            key=f"{key_prefix}_route_filter",
        )

        categorical_columns = categorical_map_filter_columns(df)
        if categorical_columns:
            category_cols = st.columns(min(3, len(categorical_columns)))
            for index, column in enumerate(categorical_columns):
                category_cols[index % len(category_cols)].multiselect(
                    filter_label(column),
                    categorical_filter_options(df, column),
                    key=f"{key_prefix}_{column}_filter",
                )

        numeric_columns = numeric_map_filter_columns(df)
        if numeric_columns:
            numeric_cols = st.columns(min(3, len(numeric_columns)))
            for index, column in enumerate(numeric_columns):
                bounds = numeric_filter_bounds(df, column)
                if bounds is None:
                    continue
                low, high = bounds
                step = max((high - low) / 100.0, 0.01)
                numeric_cols[index % len(numeric_cols)].slider(
                    filter_label(column),
                    min_value=low,
                    max_value=high,
                    value=(low, high),
                    step=step,
                    key=f"{key_prefix}_{column}_range",
                )

        if destination_columns(df):
            st.text_input(
                "Filter destinations",
                placeholder="Destination or nearby place",
                key=f"{key_prefix}_destination_filter",
            )
    return current_map_filters(df, key_prefix)


def filter_map_stops(
    df: pd.DataFrame,
    search_query: str = "",
    selected_routes: list[str] | None = None,
    filters: dict[str, Any] | None = None,
) -> pd.DataFrame:
    filtered = df.copy()
    selected_routes = selected_routes or []
    filters = filters or {}
    query = str(search_query or "").strip().lower()
    if query:
        searchable_columns = [column for column in ["stop_id", "stop_name", "routes"] if column in filtered.columns]
        if searchable_columns:
            search_blob = filtered[searchable_columns].fillna("").astype(str).agg(" ".join, axis=1).str.lower()
            filtered = filtered[search_blob.str.contains(re.escape(query), na=False)]
    if selected_routes and "routes" in filtered.columns:
        wanted = set(selected_routes)
        route_mask = filtered["routes"].apply(lambda value: bool(wanted.intersection(split_route_values(value))))
        filtered = filtered[route_mask]
    for column, selected in filters.get("categorical", {}).items():
        if selected and column in filtered.columns:
            values = filtered[column].fillna("").astype(str).str.strip()
            filtered = filtered[values.isin(set(selected))]
    for column, config in filters.get("numeric", {}).items():
        if column not in filtered.columns:
            continue
        selected = config.get("selected")
        bounds = config.get("bounds")
        if not selected or not bounds:
            continue
        low, high = float(selected[0]), float(selected[1])
        bound_low, bound_high = float(bounds[0]), float(bounds[1])
        if math.isclose(low, bound_low) and math.isclose(high, bound_high):
            continue
        values = pd.to_numeric(filtered[column], errors="coerce")
        filtered = filtered[values.between(low, high, inclusive="both")]
    destination_query = str(filters.get("destination_query", "") or "").strip().lower()
    if destination_query and destination_columns(filtered):
        destination_blob = (
            filtered[destination_columns(filtered)]
            .fillna("")
            .astype(str)
            .agg(" ".join, axis=1)
            .str.lower()
        )
        filtered = filtered[destination_blob.str.contains(re.escape(destination_query), na=False)]
    return filtered.copy()


def selected_stop_id_from_map_selection(selection_event: Any, df: pd.DataFrame) -> str | None:
    if selection_event is None:
        return None
    selection = getattr(selection_event, "selection", None)
    if selection is None and isinstance(selection_event, dict):
        selection = selection_event.get("selection")
    if selection is None:
        return None

    objects = getattr(selection, "objects", None)
    if objects is None and isinstance(selection, dict):
        objects = selection.get("objects")
    if isinstance(objects, dict):
        layer_objects = objects.get("stops_layer")
        if layer_objects:
            stop_id = layer_objects[0].get("stop_id")
            if stop_id is not None:
                return str(stop_id)

    indices = getattr(selection, "indices", None)
    if indices is None and isinstance(selection, dict):
        indices = selection.get("indices")
    if isinstance(indices, dict):
        layer_indices = indices.get("stops_layer")
        if layer_indices:
            index = int(layer_indices[0])
            if 0 <= index < len(df):
                return str(df.iloc[index].get("stop_id", ""))
    return None


def stop_picker_label(row: pd.Series) -> str:
    stop_id = str(row.get("stop_id", "")).strip()
    stop_name = str(row.get("stop_name", "")).strip() or "Unnamed stop"
    routes = str(row.get("routes", "")).strip()
    suffix = f" | routes {routes}" if routes else ""
    return f"{stop_name} ({stop_id}){suffix}"


def render_stop_detail_workflow(
    df: pd.DataFrame,
    visualization: dict[str, Any],
    key_prefix: str,
    *,
    show_details: bool = True,
    show_selection_summary: bool = True,
) -> pd.Series | None:
    if df.empty:
        st.info("No stop is available for the active map filters.")
        return None

    options = df.reset_index(drop=True)
    stop_ids = options["stop_id"].astype(str).tolist() if "stop_id" in options.columns else []
    selected_key = f"{key_prefix}_selected_stop_id"
    selected_stop_id = str(st.session_state.get(selected_key, "") or "")
    if selected_stop_id not in stop_ids and stop_ids:
        selected_stop_id = stop_ids[0]
        st.session_state[selected_key] = selected_stop_id

    selected_index = stop_ids.index(selected_stop_id) if selected_stop_id in stop_ids else 0
    picker_key = f"{key_prefix}_stop_picker"
    current_picker = st.session_state.get(picker_key)
    if (
        not isinstance(current_picker, int)
        or current_picker < 0
        or current_picker >= len(options)
        or stop_ids[int(current_picker)] != selected_stop_id
    ):
        st.session_state[picker_key] = selected_index
    picked_index = st.selectbox(
        "Selected stop",
        range(len(options)),
        format_func=lambda index: stop_picker_label(options.iloc[int(index)]),
        key=picker_key,
    )
    selected_stop = options.iloc[int(picked_index)]
    st.session_state[selected_key] = str(selected_stop.get("stop_id", ""))
    if show_selection_summary:
        st.markdown(f"**{stop_picker_label(selected_stop)}**")

    if not show_details:
        return selected_stop

    st.markdown("#### Stop Details")
    priority = pd.to_numeric(pd.Series([selected_stop.get("priority_score")]), errors="coerce").iloc[0]
    summary_rows = [
        ("Shade", str(selected_stop.get("shading", "Unknown") or "Unknown")),
        ("Review", str(selected_stop.get("review_status", "Unknown") or "Unknown")),
        ("Priority", "N/A" if pd.isna(priority) else f"{float(priority):.2f}"),
    ]
    for label, value in summary_rows:
        st.markdown(f"**{label}**  \n{value}")

    detail_columns = []
    for column in get_selected_display_columns(options, visualization) + [
        "shade_coverage",
        "shade_sources",
        "routes",
        "stop_lat",
        "stop_lon",
    ]:
        if column in options.columns and column not in detail_columns:
            detail_columns.append(column)
    detail_rows = [{"Field": column.replace("_", " ").title(), "Value": selected_stop.get(column, "")} for column in detail_columns]
    for row in detail_rows:
        value = str(row["Value"] if pd.notna(row["Value"]) else "")
        st.markdown(f"**{row['Field']}**  \n{value}")
    return selected_stop


def render_metric_cards(df: pd.DataFrame) -> None:
    metrics = summary_metric_cards(df)
    cols = st.columns(4)
    for col, metric in zip(cols, metrics):
        col.metric(
            metric["label"],
            metric["value"],
            delta=metric["delta"],
            delta_color="off",
            help=metric["help"],
        )


def render_stop_and_voting_panel(
    stops: pd.DataFrame,
    visualization: dict[str, Any],
    state_prefix: str,
    study_id: str,
    taxonomy: list[dict[str, Any]],
    voting: dict[str, Any] | None,
    *,
    app_dir: Path | None = None,
) -> Any:
    voting_config = normalize_voting_config(voting, taxonomy)
    if not voting_config["enabled"] or stops.empty:
        return render_stop_detail_workflow(stops, visualization, state_prefix)

    panel_tabs = st.tabs(
        ["Voting", "Stop details"],
        default="Voting",
        key=f"{state_prefix}_panel_tabs",
        on_change="rerun",
    )
    if panel_tabs[0].open:
        with panel_tabs[0]:
            selected_stop = render_stop_detail_workflow(
                stops,
                visualization,
                state_prefix,
                show_details=False,
                show_selection_summary=False,
            )
            render_voting_panel(
                selected_stop,
                study_id,
                taxonomy,
                voting_config,
                app_dir=app_dir or APP_DIR,
            )
            return selected_stop

    with panel_tabs[1]:
        return render_stop_detail_workflow(stops, visualization, state_prefix)


def format_summary_percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"


def summary_metric_cards(df: pd.DataFrame) -> list[dict[str, str]]:
    total = len(df)
    if {"stop_lat", "stop_lon"}.issubset(df.columns):
        coordinates = df.loc[:, ["stop_lat", "stop_lon"]].apply(pd.to_numeric, errors="coerce")
        mapped = int(coordinates.notna().all(axis=1).sum())
    else:
        mapped = 0

    if "shading" in df.columns:
        shade = normalized_category_series(df, "shading")
    else:
        shade = pd.Series(["Needs Review"] * total, index=df.index, dtype=str)
    review_backlog = int(shade.isin(["Needs Review", "Unknown", "(blank)"]).sum())
    no_shade = int(shade.eq("No Shade").sum())
    classified = max(total - review_backlog, 0)

    return [
        {
            "label": "Mapped stops",
            "value": f"{mapped:,}",
            "delta": f"{format_summary_percent(mapped, total)} with coordinates",
            "help": "Stops in the current view with usable latitude and longitude.",
        },
        {
            "label": "Classified stops",
            "value": f"{classified:,}",
            "delta": f"{format_summary_percent(classified, total)} of current view",
            "help": "Stops with shade coverage other than Needs Review or blank.",
        },
        {
            "label": "Review backlog",
            "value": f"{review_backlog:,}",
            "delta": f"{format_summary_percent(review_backlog, total)} remaining",
            "help": "Stops still marked Needs Review, Unknown, or blank in the current view.",
        },
        {
            "label": "No-shade stops",
            "value": f"{no_shade:,}",
            "delta": f"{format_summary_percent(no_shade, classified)} of classified",
            "help": "Classified stops where no shade visibly reaches the waiting area.",
        },
    ]


def chart_data(df: pd.DataFrame, chart: dict[str, Any]) -> tuple[pd.DataFrame, str, str]:
    x_field = chart.get("x", "shading")
    y_field = chart.get("y", RECORD_COUNT_FIELD)
    aggregation = chart.get("aggregation", "Count")
    if x_field not in df.columns:
        return pd.DataFrame(), "", ""
    working = normalize_chart_dimension_values(df, x_field)
    if working.empty:
        return pd.DataFrame(), "", ""
    if y_field == RECORD_COUNT_FIELD or aggregation == "Count":
        data = working.groupby(x_field, dropna=False).size().reset_index(name="stops")
        return data, x_field, "stops"
    if y_field not in df.columns:
        return pd.DataFrame(), "", ""
    working = working.loc[:, [x_field, y_field]].copy()
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


def build_safe_chart(
    data: pd.DataFrame,
    x_field: str,
    y_field: str,
    chart_type: str = "Bar",
    color_field: str | None = None,
) -> dict[str, Any] | None:
    """Build a finite-data chart without Streamlit's categorical scale binding."""
    required = [x_field, y_field] + ([color_field] if color_field else [])
    if data.empty or any(field not in data.columns for field in required):
        return None

    chart_data = data.loc[:, required].copy()
    chart_data[y_field] = pd.to_numeric(chart_data[y_field], errors="coerce")
    chart_data = chart_data.loc[
        chart_data[y_field].notna() & chart_data[y_field].map(lambda value: math.isfinite(float(value)))
    ]
    if chart_data.empty:
        return None

    chart_data[x_field] = chart_data[x_field].fillna("(blank)")
    x_is_numeric = chart_type == "Scatter" and pd.api.types.is_numeric_dtype(chart_data[x_field])
    x_type = "quantitative" if x_is_numeric else "nominal"
    x_sort = "-y" if chart_type == "Bar" and not x_is_numeric else None
    y_min = float(chart_data[y_field].min())
    y_max = float(chart_data[y_field].max())
    if chart_type in {"Bar", "Area"}:
        y_min = min(0.0, y_min)
        y_max = max(0.0, y_max)
    if y_min == y_max:
        y_max = y_min + 1.0
    x_encoding: dict[str, Any] = {
        "field": x_field,
        "type": x_type,
        "title": FIELD_LABELS.get(x_field, x_field.replace("_", " ").title()),
    }
    if x_sort is not None:
        x_encoding["sort"] = x_sort
    encoding: dict[str, Any] = {
        "x": x_encoding,
        "y": {
            "field": y_field,
            "type": "quantitative",
            "title": FIELD_LABELS.get(y_field, y_field.replace("_", " ").title()),
            "scale": {"domain": [y_min, y_max]},
        },
        "tooltip": [
            {"field": x_field, "type": x_type, "title": FIELD_LABELS.get(x_field, x_field.replace("_", " ").title())},
            {"field": y_field, "type": "quantitative", "title": FIELD_LABELS.get(y_field, y_field.replace("_", " ").title())},
        ],
    }
    if chart_type == "Bar":
        encoding["y"]["stack"] = None
    if color_field:
        chart_data[color_field] = chart_data[color_field].fillna("(blank)").astype(str)
        encoding["color"] = {
            "field": color_field,
            "type": "nominal",
            "title": FIELD_LABELS.get(color_field, color_field.replace("_", " ").title()),
        }
        encoding["tooltip"].insert(
            1,
            {"field": color_field, "type": "nominal", "title": FIELD_LABELS.get(color_field, color_field.replace("_", " ").title())},
        )
        if chart_type == "Bar":
            encoding["xOffset"] = {"field": color_field, "type": "nominal"}

    inline_values = chart_data.astype(object).where(pd.notna(chart_data), None).to_dict(orient="records")
    mark: dict[str, Any] = {"type": "bar"}
    if chart_type == "Line":
        mark = {"type": "line", "point": True}
    elif chart_type == "Area":
        mark = {"type": "area"}
    elif chart_type == "Scatter":
        mark = {"type": "circle", "size": 70}
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v6.json",
        "data": {"values": inline_values},
        "mark": mark,
        "encoding": encoding,
    }


def render_safe_chart(
    data: pd.DataFrame,
    x_field: str,
    y_field: str,
    chart_type: str = "Bar",
    color_field: str | None = None,
) -> None:
    chart = build_safe_chart(data, x_field, y_field, chart_type, color_field)
    if chart is not None:
        st.vega_lite_chart(spec=chart, width="stretch")


def wide_chart_data(data: pd.DataFrame, value_name: str = "stops") -> tuple[pd.DataFrame, str, str]:
    if data.empty:
        return pd.DataFrame(), "", ""
    index_field = str(data.index.name or "group")
    wide = data.rename_axis(index_field).reset_index()
    long = wide.melt(id_vars=[index_field], var_name="series", value_name=value_name)
    return long, index_field, "series"


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
            st.markdown(f"#### {custom_chart_title(chart, index)}")
            chart_type = chart.get("chart_type", "Bar")
            render_safe_chart(data, x_field, y_field, chart_type)


def has_column_data(df: pd.DataFrame, column: str) -> bool:
    if column not in df.columns:
        return False
    values = df[column].dropna().astype(str).str.strip()
    return bool(values.ne("").any())


def available_dashboard_sections(df: pd.DataFrame) -> list[str]:
    sections = []
    for label, columns in METRIC_REQUIREMENTS.items():
        if all(has_column_data(df, column) for column in columns):
            sections.append(label)
    return sections


def selected_dashboard_sections(df: pd.DataFrame, visualization: dict[str, Any]) -> list[str]:
    available = available_dashboard_sections(df)
    metric_cards = visualization.get("metric_cards", [])
    if metric_cards == LEGACY_DEFAULT_METRIC_CARDS:
        metric_cards = DEFAULT_METRIC_CARDS
    selected = [label for label in metric_cards if label in available]
    return selected or available


def normalized_category_series(df: pd.DataFrame, column: str) -> pd.Series:
    return df[column].fillna("(blank)").astype(str).str.strip().replace("", "(blank)")


def normalize_shade_source_chart_value(value: Any) -> str:
    text = str(value or "").strip()
    normalized = text.lower()
    return SHADE_SOURCE_CHART_CODES.get(normalized) or SHADE_SOURCE_CHART_ALIASES.get(normalized, "")


def normalize_shade_coverage_chart_value(value: Any) -> str:
    text = str(value or "").strip()
    return SHADE_COVERAGE_CHART_CODES.get(text.lower(), "")


def explode_list_field(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if column != "shade_sources":
        return df
    rows = []
    for _, row in df.iterrows():
        pieces = re.split(r"\s*[;,]\s*", str(row.get(column, "") or ""))
        normalized_values = []
        for piece in pieces:
            normalized = normalize_shade_source_chart_value(piece)
            if normalized and normalized not in normalized_values:
                normalized_values.append(normalized)
        for normalized in normalized_values:
            output = row.copy()
            output[column] = normalized
            rows.append(output)
    return pd.DataFrame(rows, columns=df.columns)


def normalize_chart_dimension_values(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if column == "shade_sources":
        return explode_list_field(df, column)
    if column == "shade_coverage":
        working = df.copy()
        working[column] = working[column].map(normalize_shade_coverage_chart_value)
        return working[working[column] != ""].copy()
    return df


def custom_chart_title(chart: dict[str, Any], index: int) -> str:
    title = str(chart.get("title", "") or "").strip()
    if title.lower() in {"", "custom chart", f"custom chart {index + 1}"}:
        x_field = chart.get("x")
        if x_field == "shade_sources":
            return "Shade Sources"
        if x_field == "shade_coverage":
            return "Shade Coverage"
        return f"Custom chart {index + 1}"
    return title


def count_by_field(df: pd.DataFrame, column: str, count_name: str = "stops") -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return pd.DataFrame(columns=[column, count_name])
    working = normalize_chart_dimension_values(df, column)
    if working.empty:
        return pd.DataFrame(columns=[column, count_name])
    working[column] = normalized_category_series(working, column)
    return working.groupby(column, dropna=False).size().reset_index(name=count_name).sort_values(count_name, ascending=False)


def split_routes_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "routes" not in df.columns:
        return pd.DataFrame()
    rows = []
    for _, row in df.iterrows():
        for route in split_route_values(row.get("routes")):
            rows.append({"route": route, "shading": str(row.get("shading", "Unknown") or "Unknown")})
    return pd.DataFrame(rows)


def render_route_shade_dashboard(df: pd.DataFrame) -> None:
    routes = split_routes_table(df)
    if routes.empty:
        return
    grouped = routes.groupby(["route", "shading"], dropna=False).size().reset_index(name="stops")
    top_routes = grouped.groupby("route")["stops"].sum().sort_values(ascending=False).head(25).index
    grouped = grouped[grouped["route"].isin(top_routes)]
    pivot = grouped.pivot_table(index="route", columns="shading", values="stops", fill_value=0, aggfunc="sum")
    st.markdown("#### Shade By Route")
    chart_rows, x_field, color_field = wide_chart_data(pivot)
    render_safe_chart(chart_rows, x_field, "stops", color_field=color_field)
    st.dataframe(grouped.sort_values(["stops", "route"], ascending=[False, True]), width="stretch", hide_index=True)


def render_grouped_shade_dashboard(df: pd.DataFrame, group_column: str, title: str) -> None:
    if df.empty or group_column not in df.columns or "shading" not in df.columns:
        return
    working = df.loc[:, [group_column, "shading"]].copy()
    working[group_column] = normalized_category_series(working, group_column)
    working["shading"] = normalized_category_series(working, "shading")
    grouped = working.groupby([group_column, "shading"], dropna=False).size().reset_index(name="stops")
    top_groups = grouped.groupby(group_column)["stops"].sum().sort_values(ascending=False).head(25).index
    grouped = grouped[grouped[group_column].isin(top_groups)]
    if grouped.empty:
        return
    pivot = grouped.pivot_table(index=group_column, columns="shading", values="stops", fill_value=0, aggfunc="sum")
    st.markdown(f"#### {title}")
    chart_rows, x_field, color_field = wide_chart_data(pivot)
    render_safe_chart(chart_rows, x_field, "stops", color_field=color_field)
    st.dataframe(grouped.sort_values(["stops", group_column], ascending=[False, True]), width="stretch", hide_index=True)


def render_numeric_by_shade_dashboard(df: pd.DataFrame, numeric_column: str, value_label: str, title: str) -> None:
    if df.empty or numeric_column not in df.columns or "shading" not in df.columns:
        return
    working = df.loc[:, ["shading", numeric_column]].copy()
    working["shading"] = normalized_category_series(working, "shading")
    working[numeric_column] = pd.to_numeric(working[numeric_column], errors="coerce")
    working = working.dropna(subset=[numeric_column])
    if working.empty:
        return
    summary = (
        working.groupby("shading", dropna=False)[numeric_column]
        .agg(**{f"Mean {value_label}": "mean", f"Median {value_label}": "median", "Stops": "count"})
        .reset_index()
        .sort_values(f"Mean {value_label}", ascending=False)
    )
    st.markdown(f"#### {title}")
    render_safe_chart(summary, "shading", f"Mean {value_label}")
    st.dataframe(summary, width="stretch", hide_index=True)


def render_issue_analytics_dashboard(
    df: pd.DataFrame,
    visualization: dict[str, Any],
    raw_labels: pd.DataFrame,
    include_agreement: bool = True,
) -> None:
    selected = selected_dashboard_sections(df, visualization)
    if df.empty:
        st.info("No stops match the active filters.")
        return

    st.markdown("#### Summary Statistics")
    render_metric_cards(df)

    count_charts = [
        ("Shade sources", "Shade Sources", "shade_sources"),
        ("Shade coverage", "Shade Coverage", "shade_coverage"),
        ("Shade distribution", "Shade Distribution", "shading"),
        ("Review status", "Review Status", "review_status"),
    ]
    active_count_charts = [
        (title, column)
        for key, title, column in count_charts
        if key in selected and column in df.columns
    ]
    if active_count_charts:
        summary_cols = st.columns(2)
        for index, (title, column) in enumerate(active_count_charts):
            with summary_cols[index % 2]:
                st.markdown(f"#### {title}")
                counts = count_by_field(df, column)
                render_safe_chart(counts, column, "stops")
                st.dataframe(counts, width="stretch", hide_index=True)

    queue_rows = []
    if "Stops without shade" in selected and "shading" in df.columns:
        queue_rows.append({"Queue": "Stops without shade", "Stops": int(normalized_category_series(df, "shading").eq("No Shade").sum())})
    if "Stops requiring review" in selected and "shading" in df.columns:
        queue_rows.append({"Queue": "Stops requiring review", "Stops": int(normalized_category_series(df, "shading").eq("Needs Review").sum())})
    if queue_rows:
        st.markdown("#### Action Queues")
        st.dataframe(pd.DataFrame(queue_rows), width="stretch", hide_index=True)

    if include_agreement and "Agreement metrics" in selected:
        render_agreement_metrics(raw_labels)
    if "Shade by route" in selected:
        render_route_shade_dashboard(df)
    if "Shade by neighborhood" in selected:
        render_grouped_shade_dashboard(df, "municipality", "Shade By Neighborhood")
    if "Shade vs ridership" in selected:
        render_numeric_by_shade_dashboard(df, "ridership", "Ridership", "Shade Vs Ridership")
    if "Priority stops" in selected and "priority_score" in df.columns:
        st.markdown("#### Highest Priority Stops")
        priority = df.sort_values("priority_score", ascending=False).head(20)
        columns = get_selected_display_columns(priority, visualization)
        st.dataframe(priority.loc[:, columns], width="stretch", hide_index=True)


def taxonomy_display_table(taxonomy: list[dict[str, Any]]) -> pd.DataFrame:
    display = pd.DataFrame(taxonomy)
    if display.empty:
        return display
    if "sort_order" in display.columns:
        display = display.sort_values("sort_order", kind="stable")
    return display.drop(columns=["sort_order"], errors="ignore").reset_index(drop=True)


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
        st.dataframe(taxonomy_display_table(taxonomy), width="stretch", hide_index=True)


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


def clean_label_values(labels: pd.DataFrame, label_column: str = "shade_category") -> pd.DataFrame:
    if labels.empty or label_column not in labels.columns or "stop_id" not in labels.columns:
        return pd.DataFrame(columns=["stop_id", label_column])
    clean = labels.copy()
    clean["stop_id"] = clean["stop_id"].fillna("").astype(str).str.strip()
    clean[label_column] = clean[label_column].fillna("").astype(str).str.strip()
    return clean[(clean["stop_id"] != "") & (clean[label_column] != "")]


def majority_label_table(labels: pd.DataFrame, label_column: str = "shade_category") -> pd.DataFrame:
    clean = clean_label_values(labels, label_column)
    rows = []
    for stop_id, group in clean.groupby("stop_id", sort=True):
        counts = group[label_column].value_counts()
        max_count = int(counts.max())
        winners = sorted(counts[counts == max_count].index.astype(str).tolist())
        total = int(counts.sum())
        rows.append({
            "stop_id": stop_id,
            "majority_label": "; ".join(winners),
            "label_count": total,
            "majority_count": max_count,
            "agreement_pct": round(max_count / total * 100, 1) if total else 0.0,
            "disagreement_flag": len(counts) > 1,
            "tied_majority": len(winners) > 1,
        })
    return pd.DataFrame(rows)


def label_rater_key(row: pd.Series) -> str:
    labeler_id = str(row.get("labeler_id", "") or "").strip()
    if labeler_id:
        return labeler_id
    role = str(row.get("labeler_role", "") or "").strip()
    source = str(row.get("source", "") or "").strip()
    return f"{role or 'unknown'}:{source or 'manual'}"


def latest_labels_by_rater(labels: pd.DataFrame, label_column: str = "shade_category") -> pd.DataFrame:
    clean = clean_label_values(labels, label_column)
    if clean.empty:
        return pd.DataFrame(columns=["stop_id", "rater", label_column])
    clean = clean.copy()
    clean["rater"] = clean.apply(label_rater_key, axis=1)
    if "created_at" in clean.columns:
        clean = clean.sort_values("created_at")
    return clean.drop_duplicates(subset=["stop_id", "rater"], keep="last")


def cohen_kappa_for_pair(left: pd.Series, right: pd.Series, categories: list[str]) -> float | None:
    paired = pd.DataFrame({"left": left, "right": right}).dropna()
    if paired.empty:
        return None
    observed = float((paired["left"] == paired["right"]).mean())
    total = len(paired)
    expected = sum((paired["left"].eq(category).sum() / total) * (paired["right"].eq(category).sum() / total) for category in categories)
    if math.isclose(1.0 - expected, 0.0):
        return 1.0 if math.isclose(observed, 1.0) else None
    return (observed - expected) / (1.0 - expected)


def average_pairwise_cohen_kappa(labels: pd.DataFrame) -> tuple[float | None, int]:
    latest = latest_labels_by_rater(labels)
    if latest.empty or latest["rater"].nunique() < 2:
        return None, 0
    matrix = latest.pivot(index="stop_id", columns="rater", values="shade_category")
    categories = sorted(latest["shade_category"].dropna().astype(str).unique().tolist())
    kappas = []
    raters = list(matrix.columns)
    for left_index, left_rater in enumerate(raters):
        for right_rater in raters[left_index + 1:]:
            paired = matrix[[left_rater, right_rater]].dropna()
            if len(paired) < 2:
                continue
            kappa = cohen_kappa_for_pair(paired[left_rater], paired[right_rater], categories)
            if kappa is not None:
                kappas.append(kappa)
    return (float(sum(kappas) / len(kappas)), len(kappas)) if kappas else (None, 0)


def category_count_matrix(labels: pd.DataFrame) -> pd.DataFrame:
    clean = clean_label_values(labels)
    return pd.crosstab(clean["stop_id"], clean["shade_category"]) if not clean.empty else pd.DataFrame()


def fleiss_kappa(labels: pd.DataFrame) -> float | None:
    counts = category_count_matrix(labels)
    if counts.empty:
        return None
    counts = counts[counts.sum(axis=1) >= 2]
    if counts.empty:
        return None
    item_totals = counts.sum(axis=1)
    total_assignments = float(item_totals.sum())
    p_i = ((counts.pow(2).sum(axis=1) - item_totals) / (item_totals * (item_totals - 1))).fillna(0)
    p_bar = float((p_i * item_totals / total_assignments).sum())
    p_e = float((counts.sum(axis=0) / total_assignments).pow(2).sum())
    if math.isclose(1.0 - p_e, 0.0):
        return 1.0 if math.isclose(p_bar, 1.0) else None
    return (p_bar - p_e) / (1.0 - p_e)


def krippendorff_alpha_nominal(labels: pd.DataFrame) -> float | None:
    counts = category_count_matrix(labels)
    if counts.empty:
        return None
    counts = counts[counts.sum(axis=1) >= 2]
    if counts.empty:
        return None
    item_totals = counts.sum(axis=1)
    observed = sum(float((row * (float(item_totals.loc[stop_id]) - row)).sum() / (float(item_totals.loc[stop_id]) - 1)) for stop_id, row in counts.iterrows()) / float(item_totals.sum())
    category_totals = counts.sum(axis=0)
    total = float(category_totals.sum())
    if total <= 1:
        return None
    expected = float((category_totals * (total - category_totals)).sum() / (total - 1) / total)
    if math.isclose(expected, 0.0):
        return 1.0 if math.isclose(observed, 0.0) else None
    return 1.0 - (observed / expected)


def format_metric_value(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "Not enough data"
    return f"{float(value):.3f}"


def agreement_overview_values(labels: pd.DataFrame) -> dict[str, int | float | None]:
    majority = majority_label_table(labels)
    return {
        "stops_labeled": int(majority["stop_id"].nunique()) if not majority.empty else 0,
        "stops_needing_review": int(majority["disagreement_flag"].sum()) if not majority.empty else 0,
        "mean_agreement": float(majority["agreement_pct"].mean()) if not majority.empty else None,
        "krippendorff_alpha": krippendorff_alpha_nominal(labels),
        "fleiss_kappa": fleiss_kappa(labels),
    }


def published_disagreement_queue(labels: pd.DataFrame) -> pd.DataFrame:
    majority = majority_label_table(labels)
    if majority.empty:
        return majority
    return majority[majority["disagreement_flag"].astype(bool)].sort_values(
        ["agreement_pct", "label_count", "stop_id"], ascending=[True, False, True]
    )


def agreement_overview_markup(metrics: dict[str, int | float | None]) -> str:
    mean = metrics["mean_agreement"]
    alpha = metrics["krippendorff_alpha"]
    kappa = metrics["fleiss_kappa"]
    mean_text = f"{float(mean):.1f}%" if mean is not None else "Not enough data"
    alpha_text = f"{float(alpha):.2f}" if alpha is not None else "Not enough data"
    kappa_text = f"{float(kappa):.2f}" if kappa is not None else "Not enough data"
    return f"""
    <style>
    .agreement-cards {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:.75rem; margin:.7rem 0 1rem; }}
    .agreement-stat {{ border:1px solid #e2e8f0; border-radius:12px; background:#fff; padding:.8rem 1rem .9rem; min-height:106px; box-shadow:0 1px 2px rgba(15,23,42,.04); }}
    .agreement-stat-label {{ color:#475569; font-size:.92rem; font-weight:650; }}
    .agreement-stat-value {{ color:#0f172a; font-size:1.75rem; font-weight:750; margin-top:.55rem; }}
    .agreement-reliability {{ border-top:1px solid #e2e8f0; border-bottom:1px solid #e2e8f0; padding:.75rem 0; margin-bottom:.8rem; }}
    .agreement-reliability-title {{ color:#334155; font-weight:700; margin-bottom:.45rem; }}
    .agreement-reliability-row {{ display:grid; grid-template-columns:minmax(180px,1fr) auto; gap:1rem; padding:.2rem 0; color:#334155; }}
    .agreement-reliability-value {{ color:#0f172a; font-weight:650; }}
    @media (max-width:720px) {{ .agreement-cards {{ grid-template-columns:1fr; }} }}
    </style>
    <div class="agreement-cards">
      <div class="agreement-stat"><div class="agreement-stat-label">📍 Labeled</div><div class="agreement-stat-value">{int(metrics['stops_labeled']):,}</div></div>
      <div class="agreement-stat"><div class="agreement-stat-label">⚠️ Review</div><div class="agreement-stat-value">{int(metrics['stops_needing_review']):,}</div></div>
      <div class="agreement-stat"><div class="agreement-stat-label">🤝 Agreement</div><div class="agreement-stat-value">{mean_text}</div></div>
    </div>
    <div class="agreement-reliability">
      <div class="agreement-reliability-title">Reliability</div>
      <div class="agreement-reliability-row"><span>Krippendorff α</span><span class="agreement-reliability-value">{alpha_text}</span></div>
      <div class="agreement-reliability-row"><span>Fleiss κ</span><span class="agreement-reliability-value">{kappa_text}</span></div>
    </div>
    """


def render_agreement_metrics(labels: pd.DataFrame) -> None:
    st.markdown("#### Agreement")
    st.caption("Overview of annotation quality and review status.")
    if labels.empty:
        st.info("No raw labels were included with this published study.")
        return
    metrics = agreement_overview_values(labels)
    st.markdown(agreement_overview_markup(metrics), unsafe_allow_html=True)

    queue = published_disagreement_queue(labels)
    if queue.empty:
        st.success("✅ All labeled stops currently have unanimous agreement.")
        return
    st.markdown("##### Disagreements requiring project review")
    filters = st.columns([1, 1.25, 2])
    minimum_labels = filters[0].number_input(
        "Minimum labels", min_value=2, value=2, step=1, key="published_agreement_minimum_labels"
    )
    threshold = filters[1].slider(
        "Agreement threshold", 0.0, 99.9, 99.9, 0.1, key="published_agreement_threshold"
    )
    categories = sorted(
        {
            part.strip()
            for value in queue["majority_label"].fillna("").astype(str)
            for part in value.split(";")
            if part.strip()
        }
    )
    selected_categories = filters[2].multiselect(
        "Label category", categories, key="published_agreement_categories"
    )
    filtered = queue[
        (queue["label_count"] >= int(minimum_labels))
        & (queue["agreement_pct"] <= float(threshold))
    ].copy()
    if selected_categories:
        selected_set = set(selected_categories)
        filtered = filtered[
            filtered["majority_label"].astype(str).map(
                lambda value: bool(selected_set.intersection(part.strip() for part in value.split(";")))
            )
        ]
    if filtered.empty:
        st.info("No disagreements match these filters.")
        return
    paging = st.columns([1, 1, 3])
    page_size = paging[0].selectbox(
        "Rows per page", [10, 25, 50], index=1, key="published_agreement_page_size"
    )
    page_count = max(1, math.ceil(len(filtered) / int(page_size)))
    page_number = paging[1].number_input(
        "Page", min_value=1, max_value=page_count, value=1, step=1, key="published_agreement_page"
    )
    start = (int(page_number) - 1) * int(page_size)
    visible = filtered.iloc[start : start + int(page_size)]
    paging[2].caption(f"{len(filtered):,} disagreements · Page {int(page_number):,} of {page_count:,}")
    display = pd.DataFrame(
        {
            "Stop": visible["stop_id"].astype(str),
            "Majority Label": visible["majority_label"].astype(str),
            "Votes": visible.apply(
                lambda row: f"{int(row['majority_count'])} / {int(row['label_count'])}", axis=1
            ),
            "Agreement": visible["agreement_pct"].map(lambda value: f"{float(value):.1f}%"),
        }
    )
    st.dataframe(display, width="stretch", hide_index=True)


def readable_file_size(size_bytes: int) -> str:
    size = max(int(size_bytes), 0)
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def compact_timestamp(value: Any, fallback: str = "Current project") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return text.replace("T", " ")[:16]


def latest_import_timestamp(import_log: list[dict[str, Any]]) -> str:
    timestamps = [str(item.get("imported_at", "") or "").strip() for item in import_log]
    timestamps = [timestamp for timestamp in timestamps if timestamp]
    return max(timestamps) if timestamps else ""


def export_file_catalog(
    stops: pd.DataFrame,
    raw_labels: pd.DataFrame,
    config: dict[str, Any],
    import_log: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    provenance = import_log if import_log is not None else list(config.get("import_log") or [])
    imported_at = compact_timestamp(latest_import_timestamp(provenance))
    latest_label_at = ""
    if not raw_labels.empty and "created_at" in raw_labels.columns:
        label_dates = raw_labels["created_at"].dropna().astype(str).str.strip()
        if not label_dates.empty:
            latest_label_at = label_dates.max()

    stops_csv = stops.to_csv(index=False).encode("utf-8")
    stops_geojson = dataframe_to_geojson(stops).encode("utf-8")
    labels_csv = raw_labels.to_csv(index=False).encode("utf-8") if not raw_labels.empty else b""
    config_json = json.dumps(config, indent=2, default=str).encode("utf-8")
    return [
        {
            "name": "Stops CSV",
            "description": "All stop records and current shade, review, route, and project fields.",
            "records": len(stops),
            "data": stops_csv,
            "size": readable_file_size(len(stops_csv)),
            "updated": imported_at,
            "file_name": "shade_study_stops.csv",
            "mime": "text/csv",
            "available": True,
        },
        {
            "name": "Stops GeoJSON",
            "description": "Mapped stop features with coordinates and stop attributes for GIS software.",
            "records": len(stops),
            "data": stops_geojson,
            "size": readable_file_size(len(stops_geojson)),
            "updated": imported_at,
            "file_name": "shade_study_stops.geojson",
            "mime": "application/geo+json",
            "available": True,
        },
        {
            "name": "Raw Labels CSV",
            "description": "Every submitted annotation, reviewer reference, confidence, source, and note.",
            "records": len(raw_labels),
            "data": labels_csv,
            "size": readable_file_size(len(labels_csv)),
            "updated": compact_timestamp(latest_label_at, "No labels"),
            "file_name": "shade_study_raw_labels.csv",
            "mime": "text/csv",
            "available": not raw_labels.empty,
        },
        {
            "name": "Study Configuration",
            "description": "Project metadata, taxonomy, methodology, visualization settings, and import log.",
            "records": 1,
            "data": config_json,
            "size": readable_file_size(len(config_json)),
            "updated": imported_at,
            "file_name": "shade_study_config.json",
            "mime": "application/json",
            "available": True,
        },
    ]


def render_export_files(
    stops: pd.DataFrame,
    raw_labels: pd.DataFrame,
    config: dict[str, Any],
    import_log: list[dict[str, Any]] | None = None,
    key_prefix: str = "published",
) -> None:
    st.markdown("#### Export Files")
    st.caption("Download analysis-ready data, GIS features, annotation history, or reproducibility settings.")
    catalog = export_file_catalog(stops, raw_labels, config, import_log)
    with st.container(border=True):
        header = st.columns([1.15, 2.5, .65, .7, 1.05, .75], vertical_alignment="center")
        for column, label in zip(header, ["File", "Contents", "Records", "Size", "Updated", ""]):
            column.markdown(f"**{label}**")
        for index, export in enumerate(catalog):
            if index:
                st.divider()
            columns = st.columns([1.15, 2.5, .65, .7, 1.05, .75], vertical_alignment="center")
            columns[0].markdown(f"**{export['name']}**")
            columns[1].caption(str(export["description"]))
            columns[2].write(f"{int(export['records']):,}")
            columns[3].write(str(export["size"]))
            columns[4].caption(str(export["updated"]))
            columns[5].download_button(
                "Download",
                data=export["data"],
                file_name=str(export["file_name"]),
                mime=str(export["mime"]),
                key=f"{key_prefix}_export_{index}",
                disabled=not bool(export["available"]),
                width="stretch",
            )


def render_dataset_provenance(import_log: list[dict[str, Any]]) -> None:
    st.markdown("#### Dataset Provenance")
    st.caption("Sources and import events used to assemble the current project dataset.")
    if not import_log:
        st.info("No dataset import provenance has been recorded.")
        return
    with st.container(border=True):
        header = st.columns([2.4, .8, .7, 1.3])
        for column, label in zip(header, ["Source", "Format", "Records", "Imported"]):
            column.markdown(f"**{label}**")
        for index, entry in enumerate(reversed(import_log)):
            if index:
                st.divider()
            columns = st.columns([2.4, .8, .7, 1.3], vertical_alignment="center")
            columns[0].write(str(entry.get("source", "Unknown source") or "Unknown source"))
            columns[1].write(str(entry.get("format", "Unknown") or "Unknown"))
            columns[2].write(f"{int(entry.get('rows', 0) or 0):,}")
            columns[3].caption(compact_timestamp(entry.get("imported_at"), "Not recorded"))


def main() -> None:
    config, stops, raw_labels = load_study()
    project = config.get("project", {})
    methodology = config.get("methodology", {})
    visualization = config.get("visualization", {})
    taxonomy = config.get("taxonomy", [])
    voting = normalize_voting_config(visualization.get("voting"), taxonomy)
    study_id = str(config.get("study_id") or project.get("name") or "shade-study").strip()

    st.set_page_config(page_title=project.get("name", "Shade Study"), layout="wide")
    st.title(project.get("name", "Shade Study"))
    st.markdown(f"### {methodology.get('summary', '')}")
    st.caption(f"{project.get('agency', '')} | {project.get('region', '')} | dataset v{project.get('dataset_version', 'draft')}")

    filters = current_map_filters(stops, "published")
    visible_stops = filter_map_stops(
        filter_unlabeled_stops(stops, filters["show_unlabeled"]),
        filters["search_query"],
        filters["selected_routes"],
        filters,
    )
    tabs = st.tabs(
        ["Map", "Analytics", "Methodology", "Downloads"],
        key="published_tabs",
        on_change="rerun",
    )
    if tabs[0].open:
        with tabs[0]:
            if visible_stops.empty:
                st.info("No stops match the current visibility settings.")
            else:
                map_cols = st.columns([2, 1])
                with map_cols[0]:
                    map_selection = st.pydeck_chart(
                        build_deck_chart(visible_stops, taxonomy, visualization),
                        width="stretch",
                        height=MAP_PANEL_HEIGHT,
                        on_select="rerun",
                        selection_mode="single-object",
                        key="published_stops_map",
                    )
                    selected_stop_id = selected_stop_id_from_map_selection(map_selection, visible_stops)
                    if selected_stop_id:
                        st.session_state["published_selected_stop_id"] = selected_stop_id
                with map_cols[1]:
                    with st.container(height=MAP_PANEL_HEIGHT, border=False):
                        render_stop_and_voting_panel(
                            visible_stops,
                            visualization,
                            "published",
                            study_id,
                            taxonomy,
                            voting,
                            app_dir=APP_DIR,
                        )
            st.caption(f"{len(visible_stops):,} of {len(stops):,} stops match the active map filters.")
            render_map_filter_controls(stops, "published")
            if visualization.get("show_legend", True) and taxonomy:
                legend = pd.DataFrame(taxonomy)
                columns = [column for column in ["name", "description", "color"] if column in legend.columns]
                st.dataframe(legend.loc[:, columns], width="stretch", hide_index=True)
    elif tabs[1].open:
        with tabs[1]:
            render_issue_analytics_dashboard(visible_stops, visualization, raw_labels)
            render_custom_charts(visible_stops, visualization)
    elif tabs[2].open:
        with tabs[2]:
            render_methodology(config)
    elif tabs[3].open:
        with tabs[3]:
            if visualization.get("show_downloads", True):
                render_export_files(stops, raw_labels, config, key_prefix="published")
            else:
                st.info("Public file downloads are disabled for this study.")
            render_dataset_provenance(list(config.get("import_log") or []))


if __name__ == "__main__":
    main()

