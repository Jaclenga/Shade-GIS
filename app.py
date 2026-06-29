"""Compatibility entrypoint for the Shade Study Builder.

The legacy Tampa-specific Streamlit implementation remains below for reference,
but the exported ``main`` at the bottom of this file now points to
``builder_app.main``.
"""

import os
import time
import uuid
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

from about_page import render_about_page

APP_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get("APP_DATA_DIR", APP_DIR))
DATA_PATH = APP_DIR / "stops.txt"
SEED_SHADE_FILE = APP_DIR / "shading_data.csv"
SHADE_FILE = DATA_DIR / "shading_data.csv"
VOTES_FILE = DATA_DIR / "shading_votes.csv"
SHADING_STATUS = [
    "No Shade",
    "Limited Natural Shade",
    "Significant Natural Shade",
    "Constructed Shade",
    "Manmade Shade",
    "Unknown",
]
VALID_SHADING_VALUES = set(SHADING_STATUS)
VOTE_OPTIONS = [
    "No Shade",
    "Limited",
    "Significant",
]
SHADE_COVERAGE_OPTIONS = VOTE_OPTIONS
SHADE_SOURCE_OPTIONS = [
    "Natural",
    "Constructed",
    "Manmade",
]
VOTE_THRESHOLD = 5
VALID_SHADE_COVERAGE_VALUES = {*SHADE_COVERAGE_OPTIONS, "Unknown"}
VALID_SHADE_SOURCE_VALUES = set(SHADE_SOURCE_OPTIONS)
LEGACY_SHADING_MAP = {
    "shaded": "Significant Natural Shade",
    "natural shade": "Significant Natural Shade",
    "limited natural shade": "Limited Natural Shade",
    "limited natural shading": "Limited Natural Shade",
    "significant natural shade": "Significant Natural Shade",
    "significant natural shading": "Significant Natural Shade",
    "manmade shade": "Constructed Shade",
    "manmade shelter": "Constructed Shade",
    "constructed shade": "Constructed Shade",
    "manmade shade source": "Manmade Shade",
    "no shade": "No Shade",
    "unknown": "Unknown",
}
COLOR_MAP = {
    "No Shade": [220, 20, 60],
    "Limited Natural Shade": [214, 158, 46],
    "Significant Natural Shade": [34, 139, 34],
    "Constructed Shade": [70, 130, 180],
    "Manmade Shade": [128, 90, 170],
    "Unknown": [128, 128, 128],
}
LEGEND_LABELS = {
    "No Shade": "red marker",
    "Limited Natural Shade": "gold marker",
    "Significant Natural Shade": "green marker",
    "Constructed Shade": "steel blue marker",
    "Manmade Shade": "purple marker",
    "Unknown": "gray marker",
}
WAITING_AREA_DEFINITION = (
    "Waiting area: The space where a passenger would reasonably stand or sit while waiting for transit, "
    "including benches when present."
)
SHADE_SOURCE_GUIDE = [
    {
        "Shade Source": "Natural",
        "Operational Definition": "Trees, palms, hedges, or other vegetation visibly shade the waiting area",
    },
    {
        "Shade Source": "Constructed",
        "Operational Definition": "A designated, purpose-built bus shelter, awning, canopy, overhang, or similar passenger shelter visibly shades the waiting area",
    },
    {
        "Shade Source": "Manmade",
        "Operational Definition": "A nearby building or other non-shelter built feature visibly shades the waiting area",
    },
    {
        "Shade Source": "Natural; Constructed; Manmade",
        "Operational Definition": "More than one source type visibly shades the waiting area",
    },
]
SHADE_COVERAGE_GUIDE = [
    {
        "Shade Coverage": "No Shade",
        "Operational Definition": "No shade visibly reaches the waiting area",
    },
    {
        "Shade Coverage": "Limited",
        "Operational Definition": "Shade visibly reaches part of the waiting area, but does not cover most of it",
    },
    {
        "Shade Coverage": "Significant",
        "Operational Definition": "Shade visibly covers most of the waiting area or seating area",
    },
]
SHADE_VOTING_GUIDE = [
    {
        "Category": "No Shade",
        "Operational Definition": "No visible shelter and no vegetation visibly shading the waiting area",
    },
    {
        "Category": "Limited Natural Shade",
        "Operational Definition": "Vegetation visibly shades part of the waiting area, but does not visibly cover most of it",
    },
    {
        "Category": "Significant Natural Shade",
        "Operational Definition": "Vegetation visibly covers most of the waiting area or seating area",
    },
    {
        "Category": "Constructed Shade",
        "Operational Definition": "A purpose-built shelter, awning, canopy, or overhang visibly shades the waiting area",
    },
    {
        "Category": "Manmade Shade",
        "Operational Definition": "A nearby building or other non-shelter built feature visibly shades the waiting area",
    },
]
SHADE_METHODOLOGY_NOTE = (
    "Classifications were based on visible shade coverage of the waiting area in available imagery "
    "rather than the mere presence of nearby vegetation or structures. This is especially important with "
    "Street View winter imagery: code what visibly shades the waiting area, not what might shade it at "
    "another time."
)
SHADE_SOURCE_NOTE = (
    "Trees, utility poles, signs, and nearby buildings are not classified as Constructed unless they are "
    "clearly intended to provide passenger shade or weather protection. Nearby buildings that visibly shade "
    "the waiting area should be coded as Manmade."
)
SHADE_CLASSIFICATION_EXAMPLES = [
    {
        "Visible condition": "Bus shelter and trees both visibly shade the waiting area",
        "Shade Source": "Natural; Constructed",
        "Shade Coverage": "Limited or Significant, depending on coverage",
    },
    {
        "Visible condition": "Purpose-built bus shelter visibly shades where riders would wait",
        "Shade Source": "Constructed",
        "Shade Coverage": "Limited or Significant, depending on coverage",
    },
    {
        "Visible condition": "Large building casts shade onto the stop but is not intended as passenger shelter",
        "Shade Source": "Manmade",
        "Shade Coverage": "Limited or Significant, depending on coverage",
    },
    {
        "Visible condition": "Only a small sign or pole shadow reaches the stop",
        "Shade Source": "None",
        "Shade Coverage": "None unless it visibly shades the waiting area",
    },
    {
        "Visible condition": "Trees are nearby but do not visibly shade the waiting area",
        "Shade Source": "None",
        "Shade Coverage": "None",
    },
    {
        "Visible condition": "Hedges or shrubs visibly shade the bench or waiting area",
        "Shade Source": "Natural",
        "Shade Coverage": "Limited or Significant, depending on coverage",
    },
    {
        "Visible condition": "Palms provide partial coverage",
        "Shade Source": "Natural",
        "Shade Coverage": "Limited",
    },
    {
        "Visible condition": "Large oak canopy covers the stop",
        "Shade Source": "Natural",
        "Shade Coverage": "Significant",
    },
]
APP_TITLE = "Tampa Bus Stops Shade Map"
STUDY_SUMMARY = "Visualizing bus stop shade for a more comfortable and resilient transit system"
DATA_CITATION = (
    "Hillsborough Area Regional Transit. (2026). General Transit Feed Specification (GTFS) "
    "data feed [Data set]. Retrieved June 17, 2026, from the HART GTFS feed."
)
HEAT_VULNERABILITY_CITATION = (
    "Hillsborough County. (n.d.). Heat Vulnerability Index [Feature layer]. ArcGIS Feature Server. "
    "Retrieved June 20, 2026, from "
    "https://services1.arcgis.com/IbNXlmt2RVVRCZ6M/arcgis/rest/services/HeatVulnerabilityIndex/FeatureServer"
)
HEAT_VULNERABILITY_METADATA_CITATION = (
    "Hillsborough County. (n.d.). Heat Vulnerability Index (FeatureServer) [Layer metadata]. "
    "ArcGIS REST Services Directory. Retrieved June 20, 2026, from "
    "https://services1.arcgis.com/IbNXlmt2RVVRCZ6M/arcgis/rest/services/HeatVulnerabilityIndex/FeatureServer/0"
)
HEAT_DATA_COLUMNS = [
    "heat_vulnerability_index",
    "heat_vulnerability_label",
    "tree_canopy_pct",
    "lst_median",
]
HEAT_VULNERABILITY_KEY = [
    {"Weighted HVI range": "1-2", "Category": "Least Vulnerable"},
    {"Weighted HVI range": "3-4", "Category": "Low Vulnerability"},
    {"Weighted HVI range": "5-6", "Category": "Moderate Vulnerability"},
    {"Weighted HVI range": "7-8", "Category": "Elevated Vulnerability"},
    {"Weighted HVI range": "9-10", "Category": "Most Vulnerable"},
]
DATASET_FIELD_GUIDE = [
    {
        "Field": "shading",
        "What it measures": "Derived map label for the observed or voted shade condition at the stop itself.",
        "How to read it": "No Shade, Limited Natural Shade, Significant Natural Shade, Constructed Shade, Manmade Shade, or Unknown.",
        "What it implies": "This keeps the map and summary tables compatible with the original single-label shade categories.",
    },
    {
        "Field": "shade_coverage",
        "What it measures": "Observed or voted amount of shade reaching the waiting area.",
        "How to read it": "No Shade, Limited, Significant, or Unknown.",
        "What it implies": "This captures how much shade reaches riders without mixing in the source of shade.",
    },
    {
        "Field": "shade_sources",
        "What it measures": "Observed or voted source labels for shade reaching the waiting area.",
        "How to read it": "None, Natural, Constructed, Manmade, or multiple labels separated by semicolons.",
        "What it implies": "This captures whether shade comes from vegetation, a purpose-built passenger shelter, nearby buildings, or multiple sources.",
    },
    {
        "Field": "heat_vulnerability_index",
        "What it measures": "The county's weighted Heat Vulnerability Index score for the surrounding block group.",
        "How to read it": "Higher values mean greater relative vulnerability on a 1 to 10 scale.",
        "What it implies": "High values suggest the stop sits in an area where heat-related risks are more concentrated.",
    },
    {
        "Field": "heat_vulnerability_label",
        "What it measures": "The county's category label for the weighted HVI score.",
        "How to read it": "Least, Low, Moderate, Elevated, or Most Vulnerable.",
        "What it implies": "This makes the HVI easier to interpret on the map without reading the raw number first.",
    },
    {
        "Field": "tree_canopy_pct",
        "What it measures": "Estimated tree canopy share in the surrounding block group.",
        "How to read it": "Shown as a percentage; higher values mean more canopy cover nearby.",
        "What it implies": "Lower canopy can suggest less natural cooling and fewer opportunities for shade in the broader area.",
    },
    {
        "Field": "lst_median",
        "What it measures": "Median land surface temperature for the surrounding block group.",
        "How to read it": "Higher values mean hotter ground and built surfaces nearby.",
        "What it implies": "Higher LST suggests stronger local heat exposure, especially where shade and cooling surfaces are limited.",
    },
]
NAV_PAGES = ["Voting", "About"]
TAMPA_MAP_VIEW = {
    "latitude": 27.95,
    "longitude": -82.40,
    "zoom": 9.2,
    "min_zoom": 9.0,
    "max_zoom": 18,
}
TAMPA_MAP_BOUNDS = [[-82.70, 27.60], [-82.10, 28.30]]
TAMPA_MAP_CONTROLLER = {
    "dragPan": True,
    "dragRotate": False,
    "keyboard": False,
    "scrollZoom": True,
    "doubleClickZoom": True,
    "touchZoom": True,
    "touchRotate": False,
    "maxBounds": TAMPA_MAP_BOUNDS,
}


def normalize_shading_value(value: str) -> str:
    if pd.isna(value):
        return "Unknown"
    value = str(value).strip()
    if not value:
        return "Unknown"
    if value in VALID_SHADING_VALUES:
        return value
    normalized = LEGACY_SHADING_MAP.get(value.lower())
    if normalized:
        return normalized
    return "Unknown"


def normalize_shade_coverage(value: str) -> str:
    if pd.isna(value):
        return "Unknown"
    value = str(value).strip()
    if not value:
        return "Unknown"
    normalized = {
        "none": "No Shade",
        "no": "No Shade",
        "no shade": "No Shade",
        "limited": "Limited",
        "limited shade": "Limited",
        "limited natural shade": "Limited",
        "limited natural shading": "Limited",
        "significant": "Significant",
        "significant shade": "Significant",
        "significant natural shade": "Significant",
        "significant natural shading": "Significant",
        "constructed shade": "Significant",
        "manmade shade": "Significant",
        "manmade shelter": "Significant",
        "shaded": "Significant",
        "natural shade": "Significant",
        "unknown": "Unknown",
    }.get(value.lower())
    if normalized:
        return normalized
    if value in VALID_SHADE_COVERAGE_VALUES:
        return value
    return "Unknown"


def normalize_shade_sources(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        parts = [str(item).strip() for item in value]
    else:
        if pd.isna(value):
            return []
        text = str(value).replace(",", ";").strip()
        if not text or text.lower() in {"none", "unknown", "not available"}:
            return []
        parts = [part.strip() for part in text.split(";")]

    normalized = set()
    for part in parts:
        key = part.lower()
        if key in {"natural", "tree", "trees", "vegetation", "canopy"}:
            normalized.add("Natural")
        elif key in {
            "constructed",
            "constructed/manmade",
            "purpose-built shelter",
            "purpose built shelter",
            "shelter",
            "built",
            "built structure",
            "manmade shelter",
        }:
            normalized.add("Constructed")
        elif key in {
            "manmade",
            "man-made",
            "manmade shade",
            "building",
            "buildings",
            "tall building",
            "tall buildings",
            "nearby building",
            "nearby buildings",
            "incidental built shade",
        }:
            normalized.add("Manmade")

    return [source for source in SHADE_SOURCE_OPTIONS if source in normalized]


def serialize_shade_sources(value: object) -> str:
    sources = normalize_shade_sources(value)
    return "; ".join(sources) if sources else "None"


def infer_shade_coverage_from_shading(value: str) -> str:
    shading = normalize_shading_value(value)
    if shading == "No Shade":
        return "No Shade"
    if shading == "Limited Natural Shade":
        return "Limited"
    if shading in {"Significant Natural Shade", "Constructed Shade", "Manmade Shade"}:
        return "Significant"
    return "Unknown"


def infer_shade_sources_from_shading(value: str) -> str:
    shading = normalize_shading_value(value)
    if shading in {"Limited Natural Shade", "Significant Natural Shade"}:
        return "Natural"
    if shading == "Constructed Shade":
        return "Constructed"
    if shading == "Manmade Shade":
        return "Manmade"
    return "None"


def derive_shading_value(shade_coverage: str, shade_sources: object) -> str:
    coverage = normalize_shade_coverage(shade_coverage)
    sources = normalize_shade_sources(shade_sources)
    if coverage == "No Shade":
        return "No Shade"
    if coverage == "Limited":
        if "Constructed" in sources:
            return "Constructed Shade"
        if "Manmade" in sources:
            return "Manmade Shade"
        if "Natural" in sources:
            return "Limited Natural Shade"
    if coverage == "Significant":
        if "Constructed" in sources:
            return "Constructed Shade"
        if "Manmade" in sources:
            return "Manmade Shade"
        if "Natural" in sources:
            return "Significant Natural Shade"
    return "Unknown"


def prepare_shade_columns(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    if "shading" not in prepared.columns:
        prepared["shading"] = "Unknown"
    prepared["shading"] = prepared["shading"].apply(normalize_shading_value)

    if "shade_coverage" not in prepared.columns:
        prepared["shade_coverage"] = prepared["shading"].apply(infer_shade_coverage_from_shading)
    prepared["shade_coverage"] = prepared["shade_coverage"].apply(normalize_shade_coverage)

    if "shade_sources" not in prepared.columns:
        prepared["shade_sources"] = prepared["shading"].apply(infer_shade_sources_from_shading)
    prepared["shade_sources"] = prepared["shade_sources"].apply(serialize_shade_sources)
    prepared["shading"] = prepared.apply(
        lambda row: derive_shading_value(row["shade_coverage"], row["shade_sources"]),
        axis=1,
    )
    return prepared


def prepare_vote_columns(votes: pd.DataFrame) -> pd.DataFrame:
    prepared = votes.copy()
    if "vote" not in prepared.columns:
        prepared["vote"] = "Unknown"
    if "shade_coverage" not in prepared.columns:
        prepared["shade_coverage"] = prepared["vote"].apply(infer_shade_coverage_from_shading)
    if "shade_sources" not in prepared.columns:
        prepared["shade_sources"] = prepared["vote"].apply(infer_shade_sources_from_shading)
    prepared["shade_coverage"] = prepared["shade_coverage"].apply(normalize_shade_coverage)
    prepared["shade_sources"] = prepared["shade_sources"].apply(serialize_shade_sources)
    prepared["vote"] = prepared.apply(
        lambda row: derive_shading_value(row["shade_coverage"], row["shade_sources"]),
        axis=1,
    )
    return prepared


def get_readable_shading_file() -> Path:
    return SHADE_FILE if SHADE_FILE.exists() else SEED_SHADE_FILE


def normalize_text_column(series: pd.Series) -> pd.Series:
    values = series.astype("string").str.strip()
    return values.mask(values == "").fillna("Not available")


def load_stops() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, dtype={"stop_id": str})
    if df.empty:
        return df

    df["shading"] = "Unknown"
    df["shade_coverage"] = "Unknown"
    df["shade_sources"] = "None"
    # apply manual saved shading first
    shading_file = get_readable_shading_file()
    if shading_file.exists():
        shading = pd.read_csv(shading_file, dtype={"stop_id": str})
        if "stop_id" in shading.columns:
            shading = prepare_shade_columns(shading)
            shade_cols = ["shading", "shade_coverage", "shade_sources"]
            saved_shading = shading.loc[:, ["stop_id", *shade_cols]].drop_duplicates(subset=["stop_id"])
            df = df.merge(saved_shading, on="stop_id", how="left", suffixes=("", "_saved"))
            for column in shade_cols:
                saved_column = f"{column}_saved"
                if saved_column in df.columns:
                    df[column] = df[saved_column].fillna(df[column])
            df = df.drop(columns=[col for col in df.columns if col.endswith("_saved")])

        available_heat_cols = [col for col in HEAT_DATA_COLUMNS if col in shading.columns]
        if available_heat_cols:
            heat = shading.loc[:, ["stop_id", *available_heat_cols]].drop_duplicates(subset=["stop_id"])
            df = df.merge(heat, on="stop_id", how="left")

    for column in ["heat_vulnerability_index", "tree_canopy_pct", "lst_median"]:
        if column not in df.columns:
            df[column] = pd.NA
        df[column] = pd.to_numeric(df[column], errors="coerce")

    if "heat_vulnerability_label" not in df.columns:
        df["heat_vulnerability_label"] = pd.NA
    df["heat_vulnerability_label"] = normalize_text_column(df["heat_vulnerability_label"])

    # now apply aggregated votes if present
    if VOTES_FILE.exists():
        votes = load_votes()
        for stop_id, stop_votes in votes.groupby("stop_id"):
            winner = get_vote_decision(stop_votes)
            if winner is not None:
                for column, value in winner.items():
                    df.loc[df["stop_id"] == stop_id, column] = value

    df = prepare_shade_columns(df)
    df["fill_color"] = df["shading"].map(COLOR_MAP)
    return df


def format_numeric_value(value: object, decimals: int = 2, suffix: str = "") -> str:
    if pd.isna(value):
        return "Not available"
    return f"{float(value):.{decimals}f}{suffix}"


def format_percentage_value(value: object, decimals: int = 1) -> str:
    if pd.isna(value):
        return "Not available"
    return f"{float(value) * 100:.{decimals}f}%"


def prepare_map_display_data(df: pd.DataFrame) -> pd.DataFrame:
    map_df = df.copy()
    map_df["heat_vulnerability_index_display"] = map_df["heat_vulnerability_index"].apply(
        lambda value: format_numeric_value(value, decimals=2)
    )
    map_df["heat_vulnerability_label_display"] = normalize_text_column(map_df["heat_vulnerability_label"])
    map_df["tree_canopy_pct_display"] = map_df["tree_canopy_pct"].apply(format_percentage_value)
    map_df["lst_median_display"] = map_df["lst_median"].apply(
        lambda value: format_numeric_value(value, decimals=1)
    )
    return map_df


def build_heat_summary_table(df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        df.groupby("shading", dropna=False)
        .agg(
            stops=("stop_id", "size"),
            avg_weighted_hvi=("heat_vulnerability_index", "mean"),
            avg_tree_canopy_pct=("tree_canopy_pct", "mean"),
            avg_lst_median=("lst_median", "mean"),
        )
        .reindex(SHADING_STATUS)
        .reset_index()
    )
    summary["stops"] = summary["stops"].fillna(0).astype(int)
    summary["avg_weighted_hvi"] = summary["avg_weighted_hvi"].apply(format_numeric_value)
    summary["avg_tree_canopy_pct"] = summary["avg_tree_canopy_pct"].apply(format_percentage_value)
    summary["avg_lst_median"] = summary["avg_lst_median"].apply(
        lambda value: format_numeric_value(value, decimals=1)
    )
    return summary.rename(
        columns={
            "shading": "Current shading",
            "stops": "Stops",
            "avg_weighted_hvi": "Avg weighted HVI",
            "avg_tree_canopy_pct": "Avg tree canopy",
            "avg_lst_median": "Avg median LST",
        }
    )


def build_priority_stop_table(df: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    priority_order = {
        "No Shade": 0,
        "Unknown": 1,
        "Limited Natural Shade": 2,
        "Constructed Shade": 3,
        "Manmade Shade": 4,
        "Significant Natural Shade": 5,
    }
    sortable = df.copy()
    sortable["priority_group"] = sortable["shading"].map(priority_order).fillna(len(priority_order))
    sortable = sortable.dropna(subset=["heat_vulnerability_index"])
    if sortable.empty:
        return pd.DataFrame()

    sortable = sortable.sort_values(
        by=["priority_group", "heat_vulnerability_index", "lst_median", "tree_canopy_pct"],
        ascending=[True, False, False, True],
        kind="stable",
    )
    preview = sortable.head(limit).copy()
    preview["Weighted HVI"] = preview["heat_vulnerability_index"].apply(format_numeric_value)
    preview["Tree canopy"] = preview["tree_canopy_pct"].apply(format_percentage_value)
    preview["Median LST"] = preview["lst_median"].apply(
        lambda value: format_numeric_value(value, decimals=1)
    )
    return preview.loc[
        :,
        [
            "stop_name",
            "stop_id",
            "shading",
            "Weighted HVI",
            "heat_vulnerability_label",
            "Tree canopy",
            "Median LST",
        ],
    ].rename(
        columns={
            "stop_name": "Stop name",
            "stop_id": "Stop ID",
            "shading": "Current shading",
            "heat_vulnerability_label": "Vulnerability label",
        }
    )


def save_shading_data(df: pd.DataFrame) -> None:
    SHADE_FILE.parent.mkdir(parents=True, exist_ok=True)
    saved = df.drop(columns=["fill_color"], errors="ignore").copy()
    saved = prepare_shade_columns(saved)
    saved.to_csv(SHADE_FILE, index=False)


def format_stop_option(stop_id: str, stop_name: str) -> str:
    return f"{stop_name} ({stop_id})"


def get_or_create_voter_id() -> str:
    if "voter_id" not in st.session_state:
        st.session_state["voter_id"] = str(uuid.uuid4())
    return st.session_state["voter_id"]


def load_votes() -> pd.DataFrame:
    if VOTES_FILE.exists():
        votes = pd.read_csv(
            VOTES_FILE,
            dtype={
                "stop_id": str,
                "user": str,
                "vote": str,
                "shade_coverage": str,
                "shade_sources": str,
                "ts": float,
            },
        )
        return prepare_vote_columns(votes)
    return pd.DataFrame(columns=["stop_id", "user", "vote", "shade_coverage", "shade_sources", "ts"])


def save_vote(stop_id: str, user: str, shade_coverage: str, shade_sources: object) -> None:
    VOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    votes = load_votes()
    shade_coverage = normalize_shade_coverage(shade_coverage)
    shade_sources = serialize_shade_sources(shade_sources)
    if shade_coverage not in SHADE_COVERAGE_OPTIONS:
        raise ValueError("Invalid vote")
    source_values = normalize_shade_sources(shade_sources)
    if shade_coverage == "No Shade" and source_values:
        raise ValueError("No Shade votes cannot include a shade source")
    if shade_coverage != "No Shade" and not source_values:
        raise ValueError("Limited and Significant votes require at least one shade source")
    vote = derive_shading_value(shade_coverage, shade_sources)
    # allow one vote per user per stop; overwrite any existing
    votes = votes[~((votes["stop_id"] == stop_id) & (votes["user"] == user))]
    votes = pd.concat(
        [
            votes,
            pd.DataFrame(
                [
                    {
                        "stop_id": stop_id,
                        "user": user,
                        "vote": vote,
                        "shade_coverage": shade_coverage,
                        "shade_sources": shade_sources,
                        "ts": time.time(),
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    votes.to_csv(VOTES_FILE, index=False)


def get_vote_counts(stop_id: str):
    votes = load_votes()
    sel = votes[votes["stop_id"] == stop_id]
    counts = {
        option: sum(1 for value in sel["shade_coverage"] if value == option)
        for option in SHADE_COVERAGE_OPTIONS
    }
    counts["Total"] = sum(counts.values())
    for source in SHADE_SOURCE_OPTIONS:
        counts[source] = sum(
            1
            for value in sel["shade_sources"]
            if source in normalize_shade_sources(value)
        )
    return counts


def choose_oldest_tie(valid_votes: pd.DataFrame, column: str, options: list[str]) -> str:
    counts = valid_votes[column].value_counts()
    results = [(int(counts.get(label, 0)), label) for label in options]
    winning_count = max(count for count, _ in results)
    winners = [label for count, label in results if count == winning_count]
    if len(winners) == 1:
        return winners[0]

    tied_votes = valid_votes[valid_votes[column].isin(winners)].copy()
    tied_votes["ts"] = pd.to_numeric(tied_votes["ts"], errors="coerce")
    tied_votes = tied_votes.dropna(subset=["ts"])
    if tied_votes.empty:
        return winners[0]
    return str(tied_votes.sort_values("ts", kind="stable").iloc[0][column])


def source_wins_tie(valid_votes: pd.DataFrame, source: str) -> bool:
    tied_votes = valid_votes.copy()
    tied_votes["source_selected"] = tied_votes["shade_sources"].apply(
        lambda value: source in normalize_shade_sources(value)
    )
    tied_votes["ts"] = pd.to_numeric(tied_votes["ts"], errors="coerce")
    tied_votes = tied_votes.dropna(subset=["ts"])
    if tied_votes.empty:
        return False
    return bool(tied_votes.sort_values("ts", kind="stable").iloc[0]["source_selected"])


def get_vote_decision(votes: pd.DataFrame) -> dict[str, str] | None:
    votes = load_votes() if votes is None else prepare_vote_columns(votes)
    valid_votes = votes[votes["shade_coverage"].isin(SHADE_COVERAGE_OPTIONS)].copy()
    if len(valid_votes) < VOTE_THRESHOLD:
        return None

    shade_coverage = choose_oldest_tie(valid_votes, "shade_coverage", SHADE_COVERAGE_OPTIONS)
    shade_sources = "None"
    if shade_coverage != "No Shade":
        source_votes = valid_votes[valid_votes["shade_coverage"] == shade_coverage].copy()
        selected_sources = []
        for source in SHADE_SOURCE_OPTIONS:
            selected = source_votes["shade_sources"].apply(lambda value: source in normalize_shade_sources(value))
            yes_count = int(selected.sum())
            no_count = int(len(source_votes) - yes_count)
            if yes_count > no_count or (yes_count == no_count and source_wins_tie(source_votes, source)):
                selected_sources.append(source)
        shade_sources = serialize_shade_sources(selected_sources)

    shading = derive_shading_value(shade_coverage, shade_sources)
    return {
        "shading": shading,
        "shade_coverage": shade_coverage,
        "shade_sources": shade_sources,
    }


def get_vote_decision_for_stop(stop_id: str) -> dict[str, str] | None:
    votes = load_votes()
    return get_vote_decision(votes[votes["stop_id"] == stop_id])


def build_deck_chart(df: pd.DataFrame):
    view_state = pdk.ViewState(
        **TAMPA_MAP_VIEW,
        pitch=0,
    )
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        id="stops_layer",
        get_position="[stop_lon, stop_lat]",
        get_fill_color="fill_color",
        get_radius=6,
        radius_units="pixels",
        radius_scale=1,
        radius_min_pixels=4,
        radius_max_pixels=9,
        opacity=0.82,
        stroked=True,
        get_line_color=[20, 20, 20, 170],
        line_width_min_pixels=1,
        pickable=True,
        auto_highlight=True,
    )

    return pdk.Deck(
        initial_view_state=view_state,
        views=[pdk.View(type="MapView", controller=TAMPA_MAP_CONTROLLER)],
        layers=[layer],
        tooltip={
            "text": (
                "{stop_name} ({stop_id})\n"
                "Shading: {shading}\n"
                "Shade coverage: {shade_coverage}\n"
                "Shade sources: {shade_sources}\n"
                "Weighted HVI: {heat_vulnerability_index_display}\n"
                "Vulnerability label: {heat_vulnerability_label_display}\n"
                "Tree canopy: {tree_canopy_pct_display}\n"
                "Median LST: {lst_median_display}"
            )
        },
    )


def render_map_page() -> None:
    st.title(APP_TITLE)
    st.markdown(
        "This app visualizes bus stop shading to provide better insights on Tampa's transport. "
        "Stops are loaded from the GTFS `stops.txt` dataset, and shading status can be saved locally."
    )
    st.caption(DATA_CITATION)

    if not DATA_PATH.exists():
        st.error(f"Could not find stops file at: {DATA_PATH}")
        return

    # lightweight anonymous voting: one readable session identity per browser
    voter_id = get_or_create_voter_id()

    stops = load_stops()
    if stops.empty:
        st.warning("No stops were found in the GTFS stops file.")
        return
    map_stops = prepare_map_display_data(stops)

    counts = stops["shading"].value_counts().reindex(SHADING_STATUS, fill_value=0)
    stop_options = [format_stop_option(row["stop_id"], row["stop_name"]) for _, row in stops.iterrows()]
    if stop_options:
        st.session_state.setdefault("vote_stop", stop_options[0])
        st.session_state.setdefault("manual_stop", stop_options[0])

    st.subheader("Map of Tampa Bus Stops")
    map_selection = st.pydeck_chart(
        build_deck_chart(map_stops),
        on_select="rerun",
        selection_mode="single-object",
        key="stops_map",
    )

    if map_selection is not None:
        selected = None
        selection_objects = getattr(map_selection.selection, "objects", {})
        layer_objects = selection_objects.get("stops_layer") if isinstance(selection_objects, dict) else None
        if layer_objects:
            selected = layer_objects[0].get("stop_id")
        if selected is None:
            selected_indices = getattr(map_selection.selection, "indices", {})
            layer_indices = selected_indices.get("stops_layer") if isinstance(selected_indices, dict) else None
            if layer_indices:
                selected = stops.iloc[int(layer_indices[0])]["stop_id"]

        if selected is not None:
            selected_option = next(
                (opt for opt in stop_options if opt.endswith(f"({selected})")),
                None,
            )
            if selected_option is not None:
                st.session_state["vote_stop"] = selected_option
                st.session_state["manual_stop"] = selected_option

    st.write(
        "Use the map to explore stops; colors represent current shading status. Hover over a stop "
        "to see its weighted heat vulnerability index, vulnerability category, tree canopy, and median "
        "land surface temperature. The HVI fields describe relative neighborhood vulnerability, tree canopy "
        "helps explain local shade context, and LST reflects nearby heat exposure. Zoom in to separate "
        "nearby stops and select individual points."
    )
    st.caption(f"Heat vulnerability source: {HEAT_VULNERABILITY_CITATION}")
    st.markdown("### Heat Vulnerability Key")
    st.caption(
        "The county metadata defines the heat-vulnerability categories in five weighted-HVI bands."
    )
    st.dataframe(pd.DataFrame(HEAT_VULNERABILITY_KEY), use_container_width=True, hide_index=True)
    st.caption(f"Heat vulnerability key citation: {HEAT_VULNERABILITY_METADATA_CITATION}")
    st.markdown("### What The Dataset Fields Mean")
    st.caption(
        "These are the main fields used in the app. Some describe the stop itself, while others describe the surrounding block group."
    )
    st.dataframe(pd.DataFrame(DATASET_FIELD_GUIDE), use_container_width=True, hide_index=True)
    st.markdown("### Shade Voting Guide")
    st.caption(SHADE_METHODOLOGY_NOTE)
    st.caption(WAITING_AREA_DEFINITION)
    st.markdown("#### Shade Source")
    st.dataframe(pd.DataFrame(SHADE_SOURCE_GUIDE), use_container_width=True, hide_index=True)
    st.markdown("#### Shade Coverage")
    st.dataframe(pd.DataFrame(SHADE_COVERAGE_GUIDE), use_container_width=True, hide_index=True)
    st.caption(SHADE_SOURCE_NOTE)
    st.markdown("#### Current App Labels")
    st.dataframe(pd.DataFrame(SHADE_VOTING_GUIDE), use_container_width=True, hide_index=True)
    st.markdown("### Classification Examples")
    st.dataframe(pd.DataFrame(SHADE_CLASSIFICATION_EXAMPLES), use_container_width=True, hide_index=True)

    with st.sidebar:
        st.header("Shading status")
        st.write("Counts of current stop states")
        st.write({status: int(counts[status]) for status in SHADING_STATUS})

        st.write("---")
        st.info(
            "Voting is anonymous in this lightweight setup. Each browser session gets a temporary voter ID so you can vote without logging in."
        )
        st.caption(f"Session voter ID: {voter_id[:8]}")

    # Voting controls for anonymous users
    st.sidebar.write("---")
    st.sidebar.header("Vote on a stop")
    vote_stop = st.sidebar.selectbox("Select stop to vote", stops["stop_name"] + " (" + stops["stop_id"] + ")", key="vote_stop")
    stop_id = vote_stop.split("(")[-1].replace(")", "")

    vote_coverage = st.sidebar.radio("Shade coverage", SHADE_COVERAGE_OPTIONS, index=0, key="vote_coverage")
    source_disabled = vote_coverage == "No Shade"

    def vote_source_key(source: str) -> str:
        return f"vote_source_{source.lower()}"

    if source_disabled:
        for source in SHADE_SOURCE_OPTIONS:
            st.session_state[vote_source_key(source)] = False
    st.sidebar.write("Shade source")
    vote_sources = [
        source
        for source in SHADE_SOURCE_OPTIONS
        if st.sidebar.checkbox(source, key=vote_source_key(source), disabled=source_disabled)
        and not source_disabled
    ]
    if st.sidebar.button("Submit vote", key="vote_submit", type="primary"):
        try:
            save_vote(stop_id, voter_id, vote_coverage, vote_sources)
            st.sidebar.success("Vote recorded.")
            # check threshold and apply if necessary
            winner = get_vote_decision_for_stop(stop_id)
            if winner is not None:
                for column, value in winner.items():
                    stops.loc[stops["stop_id"] == stop_id, column] = value
                save_shading_data(stops)
        except ValueError as error:
            st.sidebar.error(str(error))
    vc = get_vote_counts(stop_id)
    vote_count_text = ", ".join(f"{option}: {vc[option]}" for option in SHADE_COVERAGE_OPTIONS)
    source_count_text = ", ".join(f"{source}: {vc[source]}" for source in SHADE_SOURCE_OPTIONS)
    st.sidebar.markdown(
        f"**Votes:** {vc['Total']} ({vote_count_text})"
    )
    st.sidebar.caption(f"Source selections: {source_count_text}")
    st.sidebar.caption(
        f"Decision after {VOTE_THRESHOLD} valid coverage votes. Coverage ties, and source yes/no ties, "
        "go to the oldest tied vote."
    )

    st.markdown("### Legend")
    st.markdown("\n".join(f"- **{status}**: {LEGEND_LABELS[status]}" for status in SHADING_STATUS))
    st.markdown("### Heat Exposure Snapshot")
    st.caption(
        "Weighted HVI, tree canopy, and median LST are averaged within each current shading group so you can "
        "compare shade conditions with broader heat exposure patterns."
    )
    st.dataframe(build_heat_summary_table(stops), use_container_width=True, hide_index=True)

    priority_stops = build_priority_stop_table(stops)
    st.markdown("### Priority Stops")
    st.caption(
        "This ranking prioritizes stops with no shade or unknown shade first, then sorts by higher weighted HVI, "
        "hotter median LST, and lower tree canopy."
    )
    if priority_stops.empty:
        st.info("No heat-vulnerability values are available yet for priority ranking.")
    else:
        st.dataframe(priority_stops, use_container_width=True, hide_index=True)

    shading_file = get_readable_shading_file()
    if shading_file.exists():
        st.sidebar.download_button(
            "Download shading data",
            data=shading_file.read_bytes(),
            file_name="shading_data.csv",
            mime="text/csv",
        )


def set_page(page: str) -> None:
    st.session_state["page"] = page


def render_site_header() -> str:
    pages = ["Voting", "About"]
    if st.session_state.get("page") not in pages:
        st.session_state["page"] = "Voting"
    st.markdown(
        """
        <style>
        .site-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            padding: 0.15rem 0 1rem 0;
        }
        .site-brand {
            color: #166534;
            font-size: 1.2rem;
            font-weight: 700;
            letter-spacing: 0;
            line-height: 1.15;
        }
        .site-subtitle {
            color: #6b7280;
            font-size: 0.9rem;
            margin-top: 0.2rem;
        }
        .site-nav {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 0.65rem;
            flex-wrap: wrap;
        }
        .stButton button[kind="secondary"] {
            background: #ffffff;
            border: 1px solid #d7dee5;
            border-radius: 999px;
            color: #1f2937;
            font-size: 0.95rem;
            font-weight: 600;
            min-height: 2.7rem;
            padding: 0.55rem 1rem;
            width: 100%;
        }
        .stButton button[kind="secondary"]:hover {
            background: #f8fafc;
            border-color: #c5d0da;
            color: #111827;
        }
        .stButton button[kind="secondary"]:focus {
            box-shadow: none;
        }
        .stButton button[kind="primary"] {
            border-radius: 999px;
            font-weight: 600;
            min-height: 2.7rem;
        }
        .stButton button[kind="primary"] {
            background: #22c55e;
            border-color: #22c55e;
            color: #ffffff;
            border-radius: 999px;
            font-weight: 600;
            min-height: 2.7rem;
        }
        .stButton button[kind="primary"]:hover {
            background: #16a34a;
            border-color: #16a34a;
            color: #ffffff;
        }
        @media (max-width: 640px) {
            .site-header {
                align-items: flex-start;
                flex-direction: column;
            }
            .site-nav {
                justify-content: flex-start;
                width: 100%;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    brand_col, spacer_col, voting_col, about_col = st.columns([4.6, 2.2, 1.25, 1.25])
    with brand_col:
        st.markdown(
            """
            <div class="site-header">
                <div>
                    <div class="site-brand">Tampa Shade Study</div>
                    <div class="site-subtitle">Visualizing bus stop shading for better transit insight</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with spacer_col:
        st.markdown("", unsafe_allow_html=True)
    with voting_col:
        st.button(
            "Voting",
            key="nav_voting",
            use_container_width=True,
            type="primary" if st.session_state["page"] == "Voting" else "secondary",
            on_click=set_page,
            args=("Voting",),
        )
    with about_col:
        st.button(
            "About",
            key="nav_about",
            use_container_width=True,
            type="primary" if st.session_state["page"] == "About" else "secondary",
            on_click=set_page,
            args=("About",),
        )

    return st.session_state["page"]


def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    page = render_site_header()

    if page == "About":
        render_about_page(
            STUDY_SUMMARY,
            DATA_CITATION,
            HEAT_VULNERABILITY_CITATION,
            HEAT_VULNERABILITY_METADATA_CITATION,
        )
        return

    render_map_page()


from builder_app import main as main


if __name__ == "__main__":
    main()
