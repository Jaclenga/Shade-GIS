import io
import json
import time
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


def ensure_state() -> None:
    st.session_state.setdefault("project", DEFAULT_PROJECT.copy())
    st.session_state.setdefault("taxonomy", [item.copy() for item in DEFAULT_TAXONOMY])
    st.session_state.setdefault("methodology", DEFAULT_METHODOLOGY.copy())
    st.session_state.setdefault("visualization", json.loads(json.dumps(DEFAULT_VISUALIZATION)))
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


def color_dataset(df: pd.DataFrame, taxonomy: list[dict[str, Any]], color_by: str) -> pd.DataFrame:
    colored = df.copy()
    if color_by == "Review status":
        colored["fill_color"] = colored["review_status"].map(REVIEW_STATUS_COLORS)
    elif color_by == "Priority score":
        score = pd.to_numeric(colored["priority_score"], errors="coerce").fillna(0).clip(0, 100)
        colored["fill_color"] = score.apply(lambda value: [int(120 + value), int(210 - value), 80])
    else:
        color_map = get_taxonomy_color_map(taxonomy)
        colored["fill_color"] = colored["shading"].map(color_map)
    colored["fill_color"] = colored["fill_color"].apply(lambda value: value if isinstance(value, list) else [128, 128, 128])
    return colored


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
    color_by = visualization.get("color_by", "Shade category")
    map_df = color_dataset(df, taxonomy, color_by)
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        id="stops_layer",
        get_position="[stop_lon, stop_lat]",
        get_fill_color="fill_color",
        get_radius=7,
        radius_units="pixels",
        radius_min_pixels=4,
        radius_max_pixels=11,
        opacity=0.82,
        stroked=True,
        get_line_color=[20, 20, 20, 160],
        line_width_min_pixels=1,
        pickable=True,
        auto_highlight=True,
    )
    return pdk.Deck(
        initial_view_state=calculate_view_state(map_df),
        layers=[layer],
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


def render_header() -> str:
    current_page = st.session_state.get("page", "Data")
    pages = ["Data", "Visuals", "Methodology", "Preview"]
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
            if st.button(page, key=f"nav_{page}", type="primary" if current_page == page else "secondary", use_container_width=True):
                current_page = page
                st.session_state["page"] = page
    st.session_state.setdefault("page", current_page)
    return current_page


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


def render_visuals_page() -> None:
    st.title("Metrics And Visualizations")
    visualization = st.session_state["visualization"]
    stops = st.session_state["stops"]

    left, right = st.columns([0.9, 1.1])
    with left:
        visualization["color_by"] = st.selectbox(
            "Map color",
            ["Shade category", "Review status", "Priority score"],
            index=["Shade category", "Review status", "Priority score"].index(visualization["color_by"]),
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
        visualization["show_downloads"] = st.checkbox("Show public downloads", value=visualization["show_downloads"])

    with right:
        st.subheader("Priority Formula")
        weights = visualization["priority_weights"]
        weights["heat_exposure"] = st.slider("Heat exposure weight", 0.0, 1.0, float(weights["heat_exposure"]), 0.05)
        weights["ridership"] = st.slider("Ridership weight", 0.0, 1.0, float(weights["ridership"]), 0.05)
        weights["transit_dependency"] = st.slider(
            "Transit dependency weight", 0.0, 1.0, float(weights["transit_dependency"]), 0.05
        )
        weights["low_shade"] = st.slider("Low shade weight", 0.0, 1.0, float(weights["low_shade"]), 0.05)
        st.caption("The preview stores the selected formula version with exported configuration.")

    st.session_state["stops"]["priority_score"] = calculate_priority_scores(stops, visualization["priority_weights"])

    st.subheader("Map Preview")
    if stops.empty:
        st.warning("Import a dataset before configuring the map.")
    else:
        st.pydeck_chart(build_deck_chart(stops, st.session_state["taxonomy"], visualization), use_container_width=True)

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
