import pandas as pd
import pydeck as pdk
import streamlit as st
from pathlib import Path

DATA_PATH = Path(__file__).parent / "stops.txt"
SHADE_FILE = Path(__file__).parent / "shading_data.csv"
SHADING_STATUS = ["Unknown", "Shaded", "No Shade"]
COLOR_MAP = {
    "Shaded": [34, 139, 34],
    "No Shade": [220, 20, 60],
    "Unknown": [128, 128, 128],
}


def load_stops() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, dtype={"stop_id": str})
    df["shading"] = "Unknown"
    if SHADE_FILE.exists():
        shading = pd.read_csv(SHADE_FILE, dtype={"stop_id": str})
        shading = shading.loc[:, ["stop_id", "shading"]].drop_duplicates(subset=["stop_id"])
        df = df.merge(shading, on="stop_id", how="left", suffixes=("", "_saved"))
        df["shading"] = df["shading_saved"].fillna(df["shading"]) if "shading_saved" in df.columns else df["shading"]
        df = df.drop(columns=[col for col in df.columns if col.endswith("_saved")])
    df["fill_color"] = df["shading"].map(COLOR_MAP)
    return df


def save_shading_data(df: pd.DataFrame) -> None:
    df.loc[:, ["stop_id", "shading"]].to_csv(SHADE_FILE, index=False)


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
        get_position="[stop_lon, stop_lat]",
        get_fill_color="fill_color",
        get_radius=90,
        radius_scale=1,
        radius_min_pixels=3,
        pickable=True,
        auto_highlight=True,
    )
    return pdk.Deck(initial_view_state=view_state, layers=[layer])


def main():
    st.set_page_config(page_title="Tampa Bus Shade Map", layout="wide")
    st.title("Tampa Bus Stops Shade Map")
    st.markdown(
        "This app visualizes Tampa bus stops and lets you track shading status for future field data collection. "
        "Stops are loaded from the GTFS `stops.txt` dataset, and shading status can be saved locally."
    )

    if not DATA_PATH.exists():
        st.error(f"Could not find stops file at: {DATA_PATH}")
        return

    stops = load_stops()
    counts = stops["shading"].value_counts().reindex(SHADING_STATUS, fill_value=0)

    with st.sidebar:
        st.header("Shading status")
        st.write("Counts of current stop states")
        st.write(
            {
                "Shaded": int(counts["Shaded"]),
                "No Shade": int(counts["No Shade"]),
                "Unknown": int(counts["Unknown"]),
            }
        )
        st.write("---")
        st.subheader("Update a stop")
        stop_select = st.selectbox("Choose stop", stops["stop_name"] + " (" + stops["stop_id"] + ")")
        shading_choice = st.selectbox("Shading status", SHADING_STATUS)
        if st.button("Save shading status"):
            stop_id = stop_select.split("(")[-1].replace(")", "")
            stops.loc[stops["stop_id"] == stop_id, "shading"] = shading_choice
            save_shading_data(stops)
            st.success(f"Saved {shading_choice} for stop {stop_select}")

        st.write("---")
        st.subheader("Upload shading data")
        uploaded = st.file_uploader("Upload CSV with stop_id, shading", type=["csv"])
        if uploaded is not None:
            try:
                uploaded_df = pd.read_csv(uploaded, dtype={"stop_id": str})
                if "shading" not in uploaded_df.columns:
                    st.error("Uploaded file must contain 'stop_id' and 'shading' columns.")
                else:
                    stops = stops.drop(columns=["shading"]).merge(uploaded_df.loc[:, ["stop_id", "shading"]], on="stop_id", how="left")
                    stops["shading"] = stops["shading"].fillna("Unknown")
                    save_shading_data(stops)
                    st.success("Uploaded shading data and saved locally.")
            except Exception as exc:
                st.error(f"Unable to process upload: {exc}")

        st.write("---")
        st.info("A local file named `shading_data.csv` is created in the app folder when shading is saved.")

    st.subheader("Map of Tampa Bus Stops")
    st.write("Use the map to explore stops; colors represent current shading status.")
    st.pydeck_chart(build_deck_chart(stops))

    st.markdown("### Legend")
    st.markdown(
        "- **Shaded**: green marker\n"
        "- **No Shade**: red marker\n"
        "- **Unknown**: gray marker"
    )

    if SHADE_FILE.exists():
        st.sidebar.download_button(
            "Download shading data",
            data=SHADE_FILE.read_bytes(),
            file_name="shading_data.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
