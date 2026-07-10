import json
import re
import urllib.parse
from typing import Any

import pandas as pd
import pydeck as pdk
import streamlit as st

import published_app
from public_voting import DEFAULT_VOTING_CONFIG

from shade_gis.builder_imports import REQUIRED_STOP_FIELDS, hex_to_rgb, normalize_hex_color

DEFAULT_DISPLAY_COLUMNS = ["stop_id", "stop_name", "routes", "shading", "review_status", "priority_score"]
RECORD_COUNT_FIELD = "Record count"
MAX_CUSTOM_CHARTS = 10
DEFAULT_METRIC_CARDS = [
    "Shade sources",
    "Shade coverage",
]
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
DEFAULT_CUSTOM_CHART = {
    "title": "Shade Sources",
    "x": "shade_sources",
    "y": RECORD_COUNT_FIELD,
    "aggregation": "Count",
    "chart_type": "Bar",
}
DEFAULT_CUSTOM_CHARTS = [
    DEFAULT_CUSTOM_CHART,
    {
        "title": "Shade Coverage",
        "x": "shade_coverage",
        "y": RECORD_COUNT_FIELD,
        "aggregation": "Count",
        "chart_type": "Bar",
    },
]

DEFAULT_VISUALIZATION = {
    "color_by": "Shade coverage",
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
    "metric_cards": DEFAULT_METRIC_CARDS,
    "overlays": [],
    "gis_overlays": [],
    "priority_weights": {
        "ridership": 0.5,
        "low_shade": 0.5,
    },
    "show_legend": True,
    "show_downloads": True,
    "voting": DEFAULT_VOTING_CONFIG,
    "display_columns": DEFAULT_DISPLAY_COLUMNS,
    "custom_charts": DEFAULT_CUSTOM_CHARTS,
}

MARKER_SHAPES = ["Circle", "Pin", "Square", "Diamond", "Triangle"]
DESTINATION_FILTER_COLUMNS = ["nearby_destinations", "destinations", "destination"]
CATEGORICAL_MAP_FILTERS = ["shading", "review_status"]
NUMERIC_MAP_FILTERS = ["confidence", "ridership", "priority_score"]
GIS_OVERLAY_CATEGORIES = ["Transportation", "Environmental", "Demographic", "Destinations", "Other"]
GIS_OVERLAY_CATEGORIES = ["Transportation", "Environmental", "Demographic", "Destinations", "Other"]

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

OVERLAY_REQUIREMENTS = {
    "GTFS routes": ["routes"],
    "Ridership": ["ridership"],
    "Existing shelters": ["shelter", "shelter_status", "has_shelter"],
    "Route frequency": ["route_frequency", "trips_per_day", "headway_minutes"],
    "Nearby destinations": ["nearby_destinations"],
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

CHART_TYPES = ["Bar", "Line", "Scatter"]
CHART_AGGREGATIONS = ["Count", "Mean", "Sum", "Median", "Min", "Max"]
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
DEFAULT_CHART_TITLES_BY_X = {
    "shade_sources": "Shade Sources",
    "shade_coverage": "Shade Coverage",
}
PRIORITY_FACTOR_DETAILS = {
    "ridership": (
        "Ridership",
        "Higher ridership increases priority when the dataset includes ridership values.",
    ),
    "low_shade": (
        "Low shade",
        "Stops with No Shade, Limited Shade, or Needs Review receive more priority.",
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
    "Infrastructure mix": ["#dc2626", "#ca8a04", "#16a34a", "#0ea5e9", "#9333ea", "#71717a"],
    "Civic map": ["#ef4444", "#f59e0b", "#22c55e", "#3b82f6", "#a855f7", "#64748b"],
}

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


def selected_dashboard_sections(df: pd.DataFrame, visualization: dict[str, Any]) -> list[str]:
    available = get_available_metric_cards(df)
    metric_cards = visualization.get("metric_cards", [])
    if metric_cards == LEGACY_DEFAULT_METRIC_CARDS:
        metric_cards = DEFAULT_METRIC_CARDS
    selected = clean_selected_options(metric_cards, available)
    return selected or available


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
        cleaned.setdefault("color", COLOR_PALETTE[index % len(COLOR_PALETTE)])
        cleaned.setdefault("opacity", 0.35)
        cleaned.setdefault("line_width", 2)
        cleaned.setdefault("visible", True)
        cleaned["color"] = normalize_hex_color(cleaned.get("color", COLOR_PALETTE[index % len(COLOR_PALETTE)]))
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
        color = rgba_from_hex(str(overlay.get("color", COLOR_PALETTE[index % len(COLOR_PALETTE)])), overlay.get("opacity", 0.35))
        line_color = rgba_from_hex(str(overlay.get("color", COLOR_PALETTE[index % len(COLOR_PALETTE)])), min(1.0, float(overlay.get("opacity", 0.35)) + 0.25))
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
    if str(chart.get("title", "")).strip().lower() in {"", "custom chart", f"custom chart {index + 1}"}:
        chart["title"] = DEFAULT_CHART_TITLES_BY_X.get(chart.get("x"), f"Custom chart {index + 1}")
    y_options = [RECORD_COUNT_FIELD] + columns
    if chart.get("y") not in y_options:
        chart["y"] = RECORD_COUNT_FIELD
    if chart.get("aggregation") not in CHART_AGGREGATIONS:
        chart["aggregation"] = "Count"
    if chart.get("chart_type") not in CHART_TYPES:
        chart["chart_type"] = "Bar"
    return chart


def default_custom_charts() -> list[dict[str, Any]]:
    return json.loads(json.dumps(DEFAULT_CUSTOM_CHARTS))


def normalize_shade_source_chart_value(value: Any) -> str:
    text = str(value or "").strip()
    normalized = text.lower()
    return SHADE_SOURCE_CHART_CODES.get(normalized) or SHADE_SOURCE_CHART_ALIASES.get(normalized, "")


def normalize_shade_coverage_chart_value(value: Any) -> str:
    text = str(value or "").strip()
    return SHADE_COVERAGE_CHART_CODES.get(text.lower(), "")


def get_custom_charts(df: pd.DataFrame, visualization: dict[str, Any]) -> list[dict[str, Any]]:
    charts = visualization.get("custom_charts")
    if not isinstance(charts, list):
        legacy_chart = visualization.get("custom_chart")
        charts = [legacy_chart] if isinstance(legacy_chart, dict) else default_custom_charts()
    if not charts:
        charts = default_custom_charts()
    charts = [
        ensure_custom_chart_defaults(df, chart if isinstance(chart, dict) else {}, index)
        for index, chart in enumerate(charts[:MAX_CUSTOM_CHARTS])
    ]
    visualization["custom_charts"] = charts
    return charts


def explode_list_chart_values(df: pd.DataFrame, column: str) -> pd.DataFrame:
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
        return explode_list_chart_values(df, column)
    if column == "shade_coverage":
        working = df.copy()
        working[column] = working[column].map(normalize_shade_coverage_chart_value)
        return working[working[column] != ""].copy()
    return df


def build_custom_chart_data(df: pd.DataFrame, chart: dict[str, Any]) -> tuple[pd.DataFrame, str, str]:
    x_column = chart.get("x", "")
    y_column = chart.get("y", RECORD_COUNT_FIELD)
    chart_type = chart.get("chart_type", "Bar")
    aggregation = chart.get("aggregation", "Count")
    if df.empty or x_column not in df.columns:
        return pd.DataFrame(), "", ""

    working = normalize_chart_dimension_values(df, x_column)
    if working.empty:
        return pd.DataFrame(), "", ""
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
    chart_spec = published_app.build_safe_chart(
        chart_df,
        x_column,
        y_column,
        chart.get("chart_type", "Bar"),
    )
    if chart_spec is not None:
        st.vega_lite_chart(spec=chart_spec, width="stretch")


def render_custom_charts(df: pd.DataFrame, visualization: dict[str, Any]) -> None:
    for index, chart in enumerate(get_custom_charts(df, visualization)):
        title = str(chart.get("title", "")).strip() or f"Custom chart {index + 1}"
        st.markdown(f"#### {title}")
        render_custom_chart(df, chart)


def priority_score_used_in_visualization(visualization: dict[str, Any]) -> bool:
    if {**LEGACY_COLOR_MODE_FIELDS, **COLOR_MODE_FIELDS}.get(visualization.get("color_by", "")) == "priority_score":
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



