import hashlib
import time
from datetime import datetime

import pandas as pd
import pydeck as pdk
import streamlit as st
from pathlib import Path

DATA_PATH = Path(__file__).parent / "stops.txt"
SHADE_FILE = Path(__file__).parent / "shading_data.csv"
USERS_FILE = Path(__file__).parent / "users.csv"
VOTES_FILE = Path(__file__).parent / "shading_votes.csv"
SHADING_STATUS = ["Unknown", "Shaded", "No Shade"]
COLOR_MAP = {
    "Shaded": [34, 139, 34],
    "No Shade": [220, 20, 60],
    "Unknown": [128, 128, 128],
}


def load_stops() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, dtype={"stop_id": str})
    df["shading"] = "Unknown"
    # apply manual saved shading first
    if SHADE_FILE.exists():
        shading = pd.read_csv(SHADE_FILE, dtype={"stop_id": str})
        shading = shading.loc[:, ["stop_id", "shading"]].drop_duplicates(subset=["stop_id"])
        df = df.merge(shading, on="stop_id", how="left", suffixes=("", "_saved"))
        df["shading"] = df["shading_saved"].fillna(df["shading"]) if "shading_saved" in df.columns else df["shading"]
        df = df.drop(columns=[col for col in df.columns if col.endswith("_saved")])

    # now apply aggregated votes if present
    if VOTES_FILE.exists():
        votes = load_votes()
        # compute vote counts per stop
        agg = votes.groupby(["stop_id", "vote"]).size().unstack(fill_value=0)
        total = agg.sum(axis=1)
        for stop_id, row in agg.iterrows():
            t = int(total.loc[stop_id])
            shaded = int(row.get("Shaded", 0))
            noshade = int(row.get("No Shade", 0))
            if t >= 100:
                if shaded > noshade:
                    df.loc[df["stop_id"] == stop_id, "shading"] = "Shaded"
                elif noshade > shaded:
                    df.loc[df["stop_id"] == stop_id, "shading"] = "No Shade"
                else:
                    df.loc[df["stop_id"] == stop_id, "shading"] = "Unknown"

    df["fill_color"] = df["shading"].map(COLOR_MAP)
    return df


def save_shading_data(df: pd.DataFrame) -> None:
    df.loc[:, ["stop_id", "shading"]].to_csv(SHADE_FILE, index=False)


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def load_users() -> pd.DataFrame:
    if USERS_FILE.exists():
        return pd.read_csv(USERS_FILE, dtype={"username": str, "password_hash": str})
    return pd.DataFrame(columns=["username", "password_hash"])


def save_user(username: str, password: str) -> None:
    users = load_users()
    password_hash = _hash_password(password)
    if username in users["username"].values:
        raise ValueError("User already exists")
    users = pd.concat([users, pd.DataFrame([{"username": username, "password_hash": password_hash}])], ignore_index=True)
    users.to_csv(USERS_FILE, index=False)


def authenticate(username: str, password: str) -> bool:
    users = load_users()
    row = users[users["username"] == username]
    if row.empty:
        return False
    return row.iloc[0]["password_hash"] == _hash_password(password)


def load_votes() -> pd.DataFrame:
    if VOTES_FILE.exists():
        return pd.read_csv(VOTES_FILE, dtype={"stop_id": str, "user": str, "vote": str, "ts": float})
    return pd.DataFrame(columns=["stop_id", "user", "vote", "ts"])


def save_vote(stop_id: str, user: str, vote: str) -> None:
    votes = load_votes()
    # allow one vote per user per stop; overwrite any existing
    votes = votes[~((votes["stop_id"] == stop_id) & (votes["user"] == user))]
    votes = pd.concat([votes, pd.DataFrame([{"stop_id": stop_id, "user": user, "vote": vote, "ts": time.time()}])], ignore_index=True)
    votes.to_csv(VOTES_FILE, index=False)


def get_vote_counts(stop_id: str):
    votes = load_votes()
    sel = votes[votes["stop_id"] == stop_id]
    return {
        "Shaded": int((sel["vote"] == "Shaded").sum()),
        "No Shade": int((sel["vote"] == "No Shade").sum()),
        "Total": len(sel),
    }


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

    # simple session-based user tracking
    if "user" not in st.session_state:
        st.session_state["user"] = None

    stops = load_stops()
    counts = stops["shading"].value_counts().reindex(SHADING_STATUS, fill_value=0)
    with st.sidebar:
        st.header("Account")
        if st.session_state["user"] is None:
            auth_mode = st.selectbox("Action", ["Login", "Register"])
            username = st.text_input("Username", key="auth_user")
            password = st.text_input("Password", key="auth_pass", type="password")
            if st.button("Submit", key="auth_submit"):
                if not username or not password:
                    st.error("Please provide username and password.")
                else:
                    try:
                        if auth_mode == "Register":
                            save_user(username, password)
                            st.success("Registered. You can now log in.")
                        else:
                            if authenticate(username, password):
                                st.session_state["user"] = username
                                st.success(f"Logged in as {username}")
                            else:
                                st.error("Invalid username or password.")
                    except Exception as exc:
                        st.error(f"Auth error: {exc}")
        else:
            st.markdown(f"**Logged in as:** {st.session_state['user']}")
            if st.button("Log out"):
                st.session_state["user"] = None

        st.write("---")
        st.header("Shading status")
        st.write("Counts of current stop states")
        st.write({"Shaded": int(counts["Shaded"]), "No Shade": int(counts["No Shade"]), "Unknown": int(counts["Unknown"])})

        st.write("---")
        st.subheader("Update a stop (manual)")
        stop_select = st.selectbox("Choose stop", stops["stop_name"] + " (" + stops["stop_id"] + ")", key="manual_stop")
        shading_choice = st.selectbox("Shading status", SHADING_STATUS, key="manual_choice")
        if st.button("Save shading status", key="manual_save"):
            stop_id = stop_select.split("(")[-1].replace(")", "")
            stops.loc[stops["stop_id"] == stop_id, "shading"] = shading_choice
            save_shading_data(stops)
            st.success(f"Saved {shading_choice} for stop {stop_select}")

        st.write("---")
        st.subheader("Upload shading data")
        uploaded = st.file_uploader("Upload CSV with stop_id, shading", type=["csv"], key="uploader")
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

    # Voting controls for logged-in users
    st.sidebar.write("---")
    st.sidebar.header("Vote on a stop")
    vote_stop = st.sidebar.selectbox("Select stop to vote", stops["stop_name"] + " (" + stops["stop_id"] + ")", key="vote_stop")
    if st.session_state.get("user") is None:
        st.sidebar.info("Log in to cast votes.")
    else:
        vote_choice = st.sidebar.radio("Your vote", ["Shaded", "No Shade"], index=0, key="vote_choice")
        if st.sidebar.button("Submit vote", key="vote_submit"):
            stop_id = vote_stop.split("(")[-1].replace(")", "")
            save_vote(stop_id, st.session_state["user"], vote_choice)
            st.sidebar.success("Vote recorded.")
            # check threshold and apply if necessary
            counts = get_vote_counts(stop_id)
            if counts["Total"] >= 100:
                if counts["Shaded"] > counts["No Shade"]:
                    # update manual shading
                    stops.loc[stops["stop_id"] == stop_id, "shading"] = "Shaded"
                elif counts["No Shade"] > counts["Shaded"]:
                    stops.loc[stops["stop_id"] == stop_id, "shading"] = "No Shade"
                else:
                    stops.loc[stops["stop_id"] == stop_id, "shading"] = "Unknown"
                save_shading_data(stops)

        # display current vote counts for selected stop
        stop_id = vote_stop.split("(")[-1].replace(")", "")
        vc = get_vote_counts(stop_id)
        st.sidebar.markdown(f"**Votes:** {vc['Total']} (Shaded: {vc['Shaded']}, No Shade: {vc['No Shade']})")

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
