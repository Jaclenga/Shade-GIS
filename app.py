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
SHADING_STATUS = ["Unknown", "Natural Shade", "Manmade Shade", "No Shade"]
VALID_SHADING_VALUES = set(SHADING_STATUS)
VOTE_OPTIONS = ["Natural Shade", "Manmade Shade", "No Shade"]
VOTE_THRESHOLD = 5
LEGACY_SHADING_MAP = {
    "shaded": "Natural Shade",
    "natural shade": "Natural Shade",
    "manmade shade": "Manmade Shade",
    "no shade": "No Shade",
    "unknown": "Unknown",
}
COLOR_MAP = {
    "Natural Shade": [34, 139, 34],
    "Manmade Shade": [70, 130, 180],
    "No Shade": [220, 20, 60],
    "Unknown": [128, 128, 128],
}
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
        "What it measures": "Observed or voted shade condition at the stop itself.",
        "How to read it": "Natural Shade, Manmade Shade, No Shade, or Unknown.",
        "What it implies": "This is the direct rider experience variable. No Shade suggests the least protection while waiting.",
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


def normalize_shading_value(value: str) -> str:
    if pd.isna(value):
        return "Unknown"
    value = str(value).strip()
    if not value:
        return "Unknown"
    normalized = LEGACY_SHADING_MAP.get(value.lower())
    if normalized:
        return normalized
    if value in VALID_SHADING_VALUES:
        return value
    return "Unknown"


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
    # apply manual saved shading first
    shading_file = get_readable_shading_file()
    if shading_file.exists():
        shading = pd.read_csv(shading_file, dtype={"stop_id": str})
        if {"stop_id", "shading"}.issubset(shading.columns):
            saved_shading = shading.loc[:, ["stop_id", "shading"]].drop_duplicates(subset=["stop_id"])
            saved_shading["shading"] = saved_shading["shading"].apply(normalize_shading_value)
            df = df.merge(saved_shading, on="stop_id", how="left", suffixes=("", "_saved"))
            if "shading_saved" in df.columns:
                df["shading"] = df["shading_saved"].fillna(df["shading"])
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
                df.loc[df["stop_id"] == stop_id, "shading"] = winner

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
        "Manmade Shade": 2,
        "Natural Shade": 3,
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
    if "shading" in saved.columns:
        saved["shading"] = saved["shading"].apply(normalize_shading_value)
    saved.to_csv(SHADE_FILE, index=False)


def format_stop_option(stop_id: str, stop_name: str) -> str:
    return f"{stop_name} ({stop_id})"


def get_or_create_voter_id() -> str:
    if "voter_id" not in st.session_state:
        st.session_state["voter_id"] = str(uuid.uuid4())
    return st.session_state["voter_id"]


def load_votes() -> pd.DataFrame:
    if VOTES_FILE.exists():
        votes = pd.read_csv(VOTES_FILE, dtype={"stop_id": str, "user": str, "vote": str, "ts": float})
        if "vote" in votes.columns:
            votes["vote"] = votes["vote"].apply(normalize_shading_value)
        return votes
    return pd.DataFrame(columns=["stop_id", "user", "vote", "ts"])


def save_vote(stop_id: str, user: str, vote: str) -> None:
    VOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    votes = load_votes()
    vote = normalize_shading_value(vote)
    if vote not in VOTE_OPTIONS:
        raise ValueError("Invalid vote")
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
        "Natural Shade": int((sel["vote"] == "Natural Shade").sum()),
        "Manmade Shade": int((sel["vote"] == "Manmade Shade").sum()),
        "No Shade": int((sel["vote"] == "No Shade").sum()),
    }
    counts["Total"] = sum(counts.values())
    return counts


def get_vote_decision(votes: pd.DataFrame) -> str | None:
    valid_votes = votes[votes["vote"].isin(VOTE_OPTIONS)].copy()
    if len(valid_votes) < VOTE_THRESHOLD:
        return None

    counts = valid_votes["vote"].value_counts()
    results = [(int(counts.get(label, 0)), label) for label in VOTE_OPTIONS]
    winning_count = max(count for count, _ in results)
    winners = [label for count, label in results if count == winning_count]
    if len(winners) == 1:
        return winners[0]

    tied_votes = valid_votes[valid_votes["vote"].isin(winners)].copy()
    tied_votes["ts"] = pd.to_numeric(tied_votes["ts"], errors="coerce")
    tied_votes = tied_votes.dropna(subset=["ts"])
    if tied_votes.empty:
        return winners[0]
    return str(tied_votes.sort_values("ts", kind="stable").iloc[0]["vote"])


def get_vote_decision_for_stop(stop_id: str) -> str | None:
    votes = load_votes()
    return get_vote_decision(votes[votes["stop_id"] == stop_id])


def build_deck_chart(df: pd.DataFrame):
    view_state = pdk.ViewState(
        latitude=float(df["stop_lat"].mean()),
        longitude=float(df["stop_lon"].mean()),
        zoom=11.2,
        pitch=0,
    )
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        id="stops_layer",
        get_position="[stop_lon, stop_lat]",
        get_fill_color="fill_color",
        get_radius=90,
        radius_scale=1,
        radius_min_pixels=3,
        pickable=True,
        auto_highlight=True,
    )

    return pdk.Deck(
        initial_view_state=view_state,
        layers=[layer],
        tooltip={
            "text": (
                "{stop_name} ({stop_id})\n"
                "Shading: {shading}\n"
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
    st.write(
        "Use the map to explore stops; colors represent current shading status. Hover over a stop "
        "to see its weighted heat vulnerability index, vulnerability category, tree canopy, and median "
        "land surface temperature. The HVI fields describe relative neighborhood vulnerability, tree canopy "
        "helps explain local shade context, and LST reflects nearby heat exposure."
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

    with st.sidebar:
        st.header("Shading status")
        st.write("Counts of current stop states")
        st.write(
            {
                "Natural Shade": int(counts["Natural Shade"]),
                "Manmade Shade": int(counts["Manmade Shade"]),
                "No Shade": int(counts["No Shade"]),
                "Unknown": int(counts["Unknown"]),
            }
        )

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

    vote_choice = st.sidebar.radio("Your vote", VOTE_OPTIONS, index=0, key="vote_choice")
    if st.sidebar.button("Submit vote", key="vote_submit", type="primary"):
        save_vote(stop_id, voter_id, vote_choice)
        st.sidebar.success("Vote recorded.")
        # check threshold and apply if necessary
        winner = get_vote_decision_for_stop(stop_id)
        if winner is not None:
            stops.loc[stops["stop_id"] == stop_id, "shading"] = winner
            save_shading_data(stops)
    vc = get_vote_counts(stop_id)
    st.sidebar.markdown(
        f"**Votes:** {vc['Total']} (Natural Shade: {vc['Natural Shade']}, Manmade Shade: {vc['Manmade Shade']}, No Shade: {vc['No Shade']})"
    )
    st.sidebar.caption(f"Decision after {VOTE_THRESHOLD} votes. Ties go to the tied status with the oldest vote.")

    st.markdown("### Legend")
    st.markdown(
        "- **Natural Shade**: green marker\n"
        "- **Manmade Shade**: steel blue marker\n"
        "- **No Shade**: red marker\n"
        "- **Unknown**: gray marker"
    )
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


def render_site_header() -> str:
    current_page = st.session_state.get("page", "Voting")
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
        voting_clicked = st.button(
            "Voting",
            key="nav_voting",
            use_container_width=True,
            type="primary" if current_page == "Voting" else "secondary",
        )
    with about_col:
        about_clicked = st.button(
            "About",
            key="nav_about",
            use_container_width=True,
            type="primary" if current_page == "About" else "secondary",
        )

    if voting_clicked:
        current_page = "Voting"
        st.session_state["page"] = current_page
    elif about_clicked:
        current_page = "About"
        st.session_state["page"] = current_page
    else:
        st.session_state.setdefault("page", current_page)

    return current_page


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


if __name__ == "__main__":
    main()
