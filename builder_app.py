import io
import json
import time
import urllib.parse
import zipfile
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
    "citation": "Cite the released dataset version, source GTFS feed, and methodology version.",
    "limitations": (
        "Imagery date, time of day, season, and reviewer uncertainty can affect shade labels. "
        "Published releases should document these limitations."
    ),
    "release_history": "- 0.1.0: Draft project configuration and starter dataset",
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
    "overlays": ["Heat vulnerability", "Tree canopy"],
    "priority_weights": {
        "heat_exposure": 0.4,
        "ridership": 0.2,
        "transit_dependency": 0.2,
        "low_shade": 0.2,
    },
    "show_legend": True,
    "show_downloads": True,
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
    "agency": "Agency",
    "routes": "Routes",
    "municipality": "Municipality",
    "shade_coverage": "Shade coverage",
    "shade_sources": "Shade sources",
    "confidence": "Confidence",
    "heat_vulnerability_label": "Heat vulnerability label",
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
        "imported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return stops, metadata


def apply_field_mapping(raw: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    mapped = pd.DataFrame()
    for target, source in mapping.items():
        if source and source in raw.columns:
            mapped[target] = raw[source]
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
    heat_weight = float(weights.get("heat_exposure", 0.0))
    ridership_weight = float(weights.get("ridership", 0.0))
    transit_dependency_weight = float(weights.get("transit_dependency", 0.0))
    low_shade_weight = float(weights.get("low_shade", 0.0))
    total_weight = heat_weight + ridership_weight + transit_dependency_weight + low_shade_weight
    if total_weight <= 0:
        total_weight = 1.0
    heat = pd.to_numeric(df.get("heat_vulnerability_index"), errors="coerce").fillna(0) / 10
    ridership = pd.to_numeric(df.get("ridership"), errors="coerce").fillna(0)
    ridership = ridership / ridership.max() if ridership.max() and ridership.max() > 0 else ridership
    low_shade = df.get("shading", pd.Series(index=df.index, dtype=str)).isin(["No Shade", "Needs Review"]).astype(float)
    canopy = pd.to_numeric(df.get("tree_canopy_pct"), errors="coerce").fillna(0)
    low_canopy = 1 - canopy.clip(lower=0, upper=1)
    score = (
        (heat * heat_weight)
        + (ridership * ridership_weight)
        + (low_canopy * transit_dependency_weight)
        + (low_shade * low_shade_weight)
    ) / total_weight
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
                "imported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]


def get_taxonomy_color_map(taxonomy: list[dict[str, Any]]) -> dict[str, list[int]]:
    return {
        str(item.get("name", "")).strip(): hex_to_rgb(str(item.get("color", "")))
        for item in taxonomy
        if str(item.get("name", "")).strip()
    }


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
        tooltip={
            "text": (
                "{stop_name} ({stop_id})\n"
                "Shade: {shading}\n"
                "Review: {review_status}\n"
                "Routes: {routes}\n"
                "Priority: {priority_score}"
            )
        },
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
    return json.dumps(
        {
            "project": st.session_state["project"],
            "taxonomy": st.session_state["taxonomy"],
            "methodology": st.session_state["methodology"],
            "visualization": st.session_state["visualization"],
            "import_log": st.session_state["import_log"],
        },
        indent=2,
    )


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
    pages = ["Data", "Visuals", "Methodology", "Preview"]
    if st.session_state.get("page") not in pages:
        st.session_state["page"] = "Data"
    st.markdown(
        """
        <style>
        .builder-brand {font-size: 1.25rem; font-weight: 700; color: #14532d; line-height: 1.15;}
        .builder-subtitle {color: #64748b; font-size: 0.92rem; margin-top: 0.2rem;}
        .stButton button {border-radius: 999px; min-height: 2.6rem; font-weight: 650;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    cols = st.columns([3.2, 1, 1, 1, 1])
    with cols[0]:
        st.markdown(
            "<div class='builder-brand'>Shade Study Builder</div>"
            "<div class='builder-subtitle'>Prepare, configure, and preview reusable bus stop shade studies</div>",
            unsafe_allow_html=True,
        )
    for index, page in enumerate(pages, start=1):
        with cols[index]:
            st.button(
                page,
                key=f"nav_{page}",
                type="primary" if st.session_state["page"] == page else "secondary",
                use_container_width=True,
                on_click=set_page,
                args=(page,),
            )
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
                            "imported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
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
    if st.button("Apply taxonomy"):
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
                visualization["overlays"] = st.multiselect(
                    "Context layers to include",
                    [
                        "GTFS routes",
                        "Ridership",
                        "Existing shelters",
                        "Route frequency",
                        "Tree canopy",
                        "Land surface temperature",
                        "Heat vulnerability",
                        "NDVI",
                        "Zero-vehicle households",
                        "Older adult population",
                        "Nearby destinations",
                    ],
                    default=visualization["overlays"],
                )
                visualization["metric_cards"] = st.multiselect(
                    "Dashboard summaries",
                    [
                        "Shade distribution",
                        "Stops without shade",
                        "Review status",
                        "Agreement metrics",
                        "Shade by route",
                        "Shade by neighborhood",
                        "Shade vs heat vulnerability",
                        "Priority stops",
                    ],
                    default=visualization["metric_cards"],
                )
                visualization["show_legend"] = st.checkbox("Show legend", value=visualization["show_legend"])
                visualization["show_downloads"] = st.checkbox(
                    "Show public downloads", value=visualization["show_downloads"]
                )

                st.divider()
                render_palette_controls(visualization, stops, taxonomy, color_options)
                st.divider()
                st.subheader("Priority Formula")
                weights = visualization["priority_weights"]
                weights["heat_exposure"] = st.slider(
                    "Heat exposure weight", 0.0, 1.0, float(weights["heat_exposure"]), 0.05
                )
                weights["ridership"] = st.slider(
                    "Ridership weight", 0.0, 1.0, float(weights["ridership"]), 0.05
                )
                weights["transit_dependency"] = st.slider(
                    "Transit dependency weight", 0.0, 1.0, float(weights["transit_dependency"]), 0.05
                )
                weights["low_shade"] = st.slider("Low shade weight", 0.0, 1.0, float(weights["low_shade"]), 0.05)
                st.caption("The preview stores the selected formula version with exported configuration.")

    st.session_state["stops"]["priority_score"] = calculate_priority_scores(stops, visualization["priority_weights"])

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

    st.subheader("Available Fields")
    field_summary = pd.DataFrame(
        [{"field": column, "non_null_values": int(stops[column].notna().sum())} for column in stops.columns]
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
        methodology["citation"] = st.text_area("Citation", methodology["citation"], height=85)
        methodology["limitations"] = st.text_area("Known limitations", methodology["limitations"], height=110)
        methodology["release_history"] = st.text_area("Release history", methodology["release_history"], height=95)
    with preview:
        render_builder_about_page(
            project=st.session_state["project"],
            methodology=methodology,
            taxonomy=st.session_state["taxonomy"],
            import_log=st.session_state["import_log"],
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

    render_metric_cards(stops)
    tabs = st.tabs(["Map", "Analytics", "Methodology", "Exports"])
    with tabs[0]:
        st.pydeck_chart(build_deck_chart(stops, taxonomy, visualization), use_container_width=True)
        if visualization.get("show_legend", True):
            legend = pd.DataFrame(taxonomy).sort_values("sort_order")
            st.dataframe(legend.loc[:, ["name", "description", "color"]], use_container_width=True, hide_index=True)
    with tabs[1]:
        cols = st.columns([1, 1])
        with cols[0]:
            st.markdown("#### Shade Distribution")
            shade_counts = stops["shading"].value_counts().rename_axis("shade_category").reset_index(name="stops")
            st.bar_chart(shade_counts, x="shade_category", y="stops")
        with cols[1]:
            st.markdown("#### Review Status")
            review_counts = stops["review_status"].value_counts().rename_axis("review_status").reset_index(name="stops")
            st.bar_chart(review_counts, x="review_status", y="stops")
        st.markdown("#### Highest Priority Stops")
        priority = stops.sort_values("priority_score", ascending=False).head(20)
        st.dataframe(
            priority.loc[:, ["stop_id", "stop_name", "routes", "shading", "review_status", "priority_score"]],
            use_container_width=True,
            hide_index=True,
        )
    with tabs[2]:
        render_builder_about_page(
            project=project,
            methodology=methodology,
            taxonomy=taxonomy,
            import_log=st.session_state["import_log"],
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


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    ensure_state()
    page = render_header()
    if page == "Visuals":
        render_visuals_page()
    elif page == "Methodology":
        render_methodology_page()
    elif page == "Preview":
        render_preview_page()
    else:
        render_data_page()
