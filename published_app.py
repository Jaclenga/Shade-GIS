import base64
import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd
import pydeck as pdk
import streamlit as st


APP_DIR = Path(__file__).parent
CONFIG_PATH = APP_DIR / "shade_study_config.json"
DATA_PATH = APP_DIR / "shade_study_stops.csv"
RAW_LABELS_PATH = APP_DIR / "shade_study_raw_labels.csv"
RECORD_COUNT_FIELD = "Record count"
STOP_DETAIL_PANEL_HEIGHT = 500

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
FILTER_FIELD_LABELS = {
    "shading": "Shade category",
    "review_status": "Review status",
    "confidence": "Confidence",
    "ridership": "Ridership",
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


def load_study() -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    stops = pd.read_csv(DATA_PATH)
    raw_labels = pd.read_csv(RAW_LABELS_PATH) if RAW_LABELS_PATH.exists() else pd.DataFrame()
    stops["priority_score"] = calculate_priority_scores(
        stops, config.get("visualization", {}).get("priority_weights", {})
    )
    return config, stops, raw_labels


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
                point_radius_units="meters",
                point_radius_min_pixels=4,
                auto_highlight=True,
            )
        )
    return layers


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
            id="stops_layer",
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
            id="stops_layer",
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


def render_stop_detail_workflow(df: pd.DataFrame, visualization: dict[str, Any], key_prefix: str) -> None:
    if df.empty:
        st.info("No stop is available for the active map filters.")
        return

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
    st.markdown(f"**{stop_picker_label(selected_stop)}**")

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
            "help": "Stops with a shade category other than Needs Review or blank.",
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
    selected = [label for label in visualization.get("metric_cards", []) if label in available]
    return selected or available


def normalized_category_series(df: pd.DataFrame, column: str) -> pd.Series:
    return df[column].fillna("(blank)").astype(str).str.strip().replace("", "(blank)")


def count_by_field(df: pd.DataFrame, column: str, count_name: str = "stops") -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return pd.DataFrame(columns=[column, count_name])
    working = df.copy()
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
    st.bar_chart(pivot)
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
    st.bar_chart(pivot)
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
    st.bar_chart(summary, x="shading", y=f"Mean {value_label}")
    st.dataframe(summary, width="stretch", hide_index=True)


def render_issue_analytics_dashboard(df: pd.DataFrame, visualization: dict[str, Any], raw_labels: pd.DataFrame) -> None:
    selected = selected_dashboard_sections(df, visualization)
    if df.empty:
        st.info("No stops match the active filters.")
        return

    st.markdown("#### Summary Statistics")
    render_metric_cards(df)

    summary_cols = st.columns(2)
    if "Shade distribution" in selected and "shading" in df.columns:
        with summary_cols[0]:
            st.markdown("#### Shade Distribution")
            shade_counts = count_by_field(df, "shading")
            st.bar_chart(shade_counts, x="shading", y="stops")
            st.dataframe(shade_counts, width="stretch", hide_index=True)
    if "Review status" in selected and "review_status" in df.columns:
        with summary_cols[1]:
            st.markdown("#### Review Status")
            review_counts = count_by_field(df, "review_status")
            st.bar_chart(review_counts, x="review_status", y="stops")
            st.dataframe(review_counts, width="stretch", hide_index=True)

    queue_rows = []
    if "Stops without shade" in selected and "shading" in df.columns:
        queue_rows.append({"Queue": "Stops without shade", "Stops": int(normalized_category_series(df, "shading").eq("No Shade").sum())})
    if "Stops requiring review" in selected and "shading" in df.columns:
        queue_rows.append({"Queue": "Stops requiring review", "Stops": int(normalized_category_series(df, "shading").eq("Needs Review").sum())})
    if queue_rows:
        st.markdown("#### Action Queues")
        st.dataframe(pd.DataFrame(queue_rows), width="stretch", hide_index=True)

    if "Agreement metrics" in selected:
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
        st.dataframe(pd.DataFrame(taxonomy), width="stretch", hide_index=True)


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


def render_agreement_metrics(labels: pd.DataFrame) -> None:
    st.markdown("#### Agreement Metrics")
    if labels.empty:
        st.info("No raw labels were included with this published study.")
        return
    majority = majority_label_table(labels)
    cohen, cohen_pairs = average_pairwise_cohen_kappa(labels)
    summary = pd.DataFrame([
        ("Stops with labels", int(majority["stop_id"].nunique()) if not majority.empty else 0),
        ("Stops with 2+ labels", int((majority["label_count"] >= 2).sum()) if not majority.empty else 0),
        ("Stops with disagreement", int(majority["disagreement_flag"].sum()) if not majority.empty else 0),
        ("Mean majority agreement", f"{float(majority['agreement_pct'].mean()):.1f}%" if not majority.empty else "Not enough data"),
        ("Average pairwise Cohen kappa", format_metric_value(cohen)),
        ("Cohen rater pairs compared", cohen_pairs),
        ("Fleiss kappa", format_metric_value(fleiss_kappa(labels))),
        ("Krippendorff alpha", format_metric_value(krippendorff_alpha_nominal(labels))),
    ], columns=["Metric", "Value"])
    summary["Value"] = summary["Value"].astype(str)
    st.dataframe(summary, width="stretch", hide_index=True)
    if not majority.empty:
        st.dataframe(majority.sort_values(["disagreement_flag", "agreement_pct", "stop_id"], ascending=[False, True, True]), width="stretch", hide_index=True)


def main() -> None:
    config, stops, raw_labels = load_study()
    project = config.get("project", {})
    methodology = config.get("methodology", {})
    visualization = config.get("visualization", {})
    taxonomy = config.get("taxonomy", [])

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
    render_metric_cards(visible_stops)

    tabs = st.tabs(["Map", "Analytics", "Methodology", "Downloads"])
    with tabs[0]:
        if visible_stops.empty:
            st.info("No stops match the current visibility settings.")
        else:
            map_cols = st.columns([2, 1])
            with map_cols[0]:
                map_selection = st.pydeck_chart(
                    build_deck_chart(visible_stops, taxonomy, visualization),
                    width="stretch",
                    on_select="rerun",
                    selection_mode="single-object",
                    key="published_stops_map",
                )
                selected_stop_id = selected_stop_id_from_map_selection(map_selection, visible_stops)
                if selected_stop_id:
                    st.session_state["published_selected_stop_id"] = selected_stop_id
            with map_cols[1]:
                with st.container(height=STOP_DETAIL_PANEL_HEIGHT, border=False):
                    render_stop_detail_workflow(visible_stops, visualization, "published")
        st.caption(f"{len(visible_stops):,} of {len(stops):,} stops match the active map filters.")
        render_map_filter_controls(stops, "published")
        if visualization.get("show_legend", True) and taxonomy:
            legend = pd.DataFrame(taxonomy)
            columns = [column for column in ["name", "description", "color"] if column in legend.columns]
            st.dataframe(legend.loc[:, columns], width="stretch", hide_index=True)
    with tabs[1]:
        render_issue_analytics_dashboard(visible_stops, visualization, raw_labels)
        render_custom_charts(visible_stops, visualization)
    with tabs[2]:
        render_methodology(config)
    with tabs[3]:
        if visualization.get("show_downloads", True):
            st.download_button("Download stops CSV", stops.to_csv(index=False).encode("utf-8"), "shade_study_stops.csv", "text/csv")
            st.download_button("Download stops GeoJSON", dataframe_to_geojson(stops).encode("utf-8"), "shade_study_stops.geojson", "application/geo+json")
            st.download_button("Download study configuration", json.dumps(config, indent=2).encode("utf-8"), "shade_study_config.json", "application/json")
            if not raw_labels.empty:
                st.download_button("Download raw labels CSV", raw_labels.to_csv(index=False).encode("utf-8"), "shade_study_raw_labels.csv", "text/csv")


if __name__ == "__main__":
    main()

