import hashlib
import os
import time
from datetime import datetime
from typing import Optional

import pandas as pd
import pydeck as pdk
import streamlit as st
from pathlib import Path

DATA_PATH = Path(__file__).parent / "stops.txt"
SHADE_FILE = Path(__file__).parent / "shading_data.csv"
USERS_FILE = Path(__file__).parent / "users.csv"
VOTES_FILE = Path(__file__).parent / "shading_votes.csv"
ADMIN_REGISTRATION_CODE = os.environ.get("ADMIN_REGISTRATION_CODE", "adminpass")
SHADING_STATUS = ["Unknown", "Natural Shade", "Manmade Shade", "No Shade"]
VALID_SHADING_VALUES = set(SHADING_STATUS)
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
    return value


def load_stops() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, dtype={"stop_id": str})
    df["shading"] = "Unknown"
    # apply manual saved shading first
    if SHADE_FILE.exists():
        shading = pd.read_csv(SHADE_FILE, dtype={"stop_id": str})
        shading = shading.loc[:, ["stop_id", "shading"]].drop_duplicates(subset=["stop_id"])
        shading["shading"] = shading["shading"].apply(normalize_shading_value)
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
            natural = int(row.get("Natural Shade", 0))
            manmade = int(row.get("Manmade Shade", 0))
            noshade = int(row.get("No Shade", 0))
            if t >= 100:
                winner = max(
                    [
                        (natural, "Natural Shade"),
                        (manmade, "Manmade Shade"),
                        (noshade, "No Shade"),
                    ],
                    key=lambda x: x[0],
                )
                top_counts = [
                    v for v, _ in [
                        (natural, "Natural Shade"),
                        (manmade, "Manmade Shade"),
                        (noshade, "No Shade"),
                    ]
                    if v == winner[0]
                ]
                if len(top_counts) == 1:
                    df.loc[df["stop_id"] == stop_id, "shading"] = winner[1]
                else:
                    df.loc[df["stop_id"] == stop_id, "shading"] = "Unknown"

    df["fill_color"] = df["shading"].map(COLOR_MAP)
    return df


def save_shading_data(df: pd.DataFrame) -> None:
    saved = df.loc[:, ["stop_id", "shading"]].copy()
    saved["shading"] = saved["shading"].apply(normalize_shading_value)
    saved.to_csv(SHADE_FILE, index=False)


def format_stop_option(stop_id: str, stop_name: str) -> str:
    return f"{stop_name} ({stop_id})"


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def load_users() -> pd.DataFrame:
    if USERS_FILE.exists():
        users = pd.read_csv(USERS_FILE, dtype={"username": str, "password_hash": str})
        if "role" not in users.columns:
            users["role"] = "user"
        return users
    return pd.DataFrame(columns=["username", "password_hash", "role"])


def save_user(username: str, password: str, role: str = "user", admin_code: Optional[str] = None) -> None:
    users = load_users()
    password_hash = _hash_password(password)
    if username in users["username"].values:
        raise ValueError("User already exists")
    role = role.lower()
    if role == "admin":
        if admin_code != ADMIN_REGISTRATION_CODE:
            raise ValueError("Invalid admin registration code")
    users = pd.concat(
        [
            users,
            pd.DataFrame(
                [
                    {
                        "username": username,
                        "password_hash": password_hash,
                        "role": role,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    users.to_csv(USERS_FILE, index=False)


def get_user_role(username: str) -> str:
    users = load_users()
    row = users[users["username"] == username]
    if row.empty:
        return "user"
    role = row.iloc[0].get("role", "user")
    return str(role) if pd.notna(role) else "user"


def authenticate(username: str, password: str) -> bool:
    users = load_users()
    row = users[users["username"] == username]
    if row.empty:
        return False
    return row.iloc[0]["password_hash"] == _hash_password(password)


def load_votes() -> pd.DataFrame:
    if VOTES_FILE.exists():
        votes = pd.read_csv(VOTES_FILE, dtype={"stop_id": str, "user": str, "vote": str, "ts": float})
        if "vote" in votes.columns:
            votes["vote"] = votes["vote"].apply(normalize_shading_value)
        return votes
    return pd.DataFrame(columns=["stop_id", "user", "vote", "ts"])


def save_vote(stop_id: str, user: str, vote: str) -> None:
    votes = load_votes()
    vote = normalize_shading_value(vote)
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
    return {
        "Natural Shade": int((sel["vote"] == "Natural Shade").sum()),
        "Manmade Shade": int((sel["vote"] == "Manmade Shade").sum()),
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
        id="stops_layer",
        get_position="[stop_lon, stop_lat]",
        get_fill_color="fill_color",
        get_radius=90,
        radius_scale=1,
        radius_min_pixels=3,
        pickable=True,
        auto_highlight=True,
    )
    return pdk.Deck(initial_view_state=view_state, layers=[layer], tooltip={"text": "{stop_name} ({stop_id})\nShading: {shading}"})


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
        st.session_state["user_role"] = "user"

    stops = load_stops()
    counts = stops["shading"].value_counts().reindex(SHADING_STATUS, fill_value=0)
    stop_options = [format_stop_option(row["stop_id"], row["stop_name"]) for _, row in stops.iterrows()]
    if stop_options:
        st.session_state.setdefault("vote_stop", stop_options[0])
        st.session_state.setdefault("manual_stop", stop_options[0])

    st.subheader("Map of Tampa Bus Stops")
    st.write("Use the map to explore stops; colors represent current shading status.")
    map_selection = st.pydeck_chart(
        build_deck_chart(stops),
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
        st.header("Account")
        if st.session_state["user"] is None:
            auth_mode = st.selectbox("Action", ["Login", "Register"], key="auth_mode")
            username = st.text_input("Username", key="auth_user")
            password = st.text_input("Password", key="auth_pass", type="password")
            role_selection = "User"
            admin_code = None
            if auth_mode == "Register":
                role_selection = st.selectbox("Register as", ["User", "Admin"], key="auth_role")
                if role_selection == "Admin":
                    admin_code = st.text_input("Admin registration code", key="auth_admin_code", type="password")
            if st.button("Submit", key="auth_submit"):
                if not username or not password:
                    st.error("Please provide username and password.")
                else:
                    try:
                        if auth_mode == "Register":
                            save_user(username, password, role=role_selection, admin_code=admin_code)
                            st.success("Registered. You can now log in.")
                        else:
                            if authenticate(username, password):
                                st.session_state["user"] = username
                                st.session_state["user_role"] = get_user_role(username)
                                st.success(f"Logged in as {username}")
                            else:
                                st.error("Invalid username or password.")
                    except Exception as exc:
                        st.error(f"Auth error: {exc}")
        else:
            st.markdown(f"**Logged in as:** {st.session_state['user']} ({st.session_state['user_role']})")
            if st.button("Log out"):
                st.session_state["user"] = None
                st.session_state["user_role"] = "user"

        st.write("---")
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
        st.subheader("Update a stop (manual)")
        is_admin = st.session_state["user_role"] == "admin"
        if not st.session_state.get("user"):
            st.info("Log in as an admin to update stop shading manually.")
        elif not is_admin:
            st.warning("Manual shading updates are available to admin accounts only.")
        else:
            stop_select = st.selectbox("Choose stop", stops["stop_name"] + " (" + stops["stop_id"] + ")", key="manual_stop")
            shading_choice = st.selectbox("Shading status", SHADING_STATUS, key="manual_choice")
            if st.button("Save shading status", key="manual_save"):
                stop_id = stop_select.split("(")[-1].replace(")", "")
                stops.loc[stops["stop_id"] == stop_id, "shading"] = shading_choice
                save_shading_data(stops)
                st.success(f"Saved {shading_choice} for stop {stop_select}")

        st.write("---")
        st.subheader("Upload shading data")
        if not st.session_state.get("user"):
            st.info("Log in to upload shading files.")
        elif not is_admin:
            st.warning("File uploads for shading data are available to admin accounts only.")
        else:
            uploaded = st.file_uploader("Upload CSV with stop_id, shading", type=["csv"], key="uploader")
            if uploaded is not None:
                try:
                    uploaded_df = pd.read_csv(uploaded, dtype={"stop_id": str})
                    if "shading" not in uploaded_df.columns:
                        st.error("Uploaded file must contain 'stop_id' and 'shading' columns.")
                    else:
                        uploaded_df["shading"] = uploaded_df["shading"].apply(normalize_shading_value)
                        invalid = uploaded_df.loc[~uploaded_df["shading"].isin(VALID_SHADING_VALUES), "shading"]
                        if not invalid.empty:
                            st.error(
                                "Uploaded file must contain valid shading values: "
                                + ", ".join(SHADING_STATUS)
                            )
                        else:
                            stops = stops.drop(columns=["shading"]).merge(uploaded_df.loc[:, ["stop_id", "shading"]], on="stop_id", how="left")
                            stops["shading"] = stops["shading"].fillna("Unknown")
                            save_shading_data(stops)
                            st.success("Uploaded shading data and saved locally.")
                except Exception as exc:
                    st.error(f"Unable to process upload: {exc}")

        if not st.session_state.get("user") or not is_admin:
            st.write("---")
            st.info("Admin accounts are required to set shading manually or upload shading corrections.")
        st.write("---")
        st.info("A local file named `shading_data.csv` is created in the app folder when shading is saved.")

    # Voting controls for logged-in users
    st.sidebar.write("---")
    st.sidebar.header("Vote on a stop")
    vote_stop = st.sidebar.selectbox("Select stop to vote", stops["stop_name"] + " (" + stops["stop_id"] + ")", key="vote_stop")
    stop_id = vote_stop.split("(")[-1].replace(")", "")
    if st.session_state.get("user") is None:
        st.sidebar.info("Log in to cast votes.")
    else:
        vote_choice = st.sidebar.radio("Your vote", ["Natural Shade", "Manmade Shade", "No Shade"], index=0, key="vote_choice")
        if st.sidebar.button("Submit vote", key="vote_submit"):
            save_vote(stop_id, st.session_state["user"], vote_choice)
            st.sidebar.success("Vote recorded.")
            # check threshold and apply if necessary
            counts = get_vote_counts(stop_id)
            if counts["Total"] >= 100:
                winner = max(
                    [
                        (counts["Natural Shade"], "Natural Shade"),
                        (counts["Manmade Shade"], "Manmade Shade"),
                        (counts["No Shade"], "No Shade"),
                    ],
                    key=lambda x: x[0],
                )
                top_counts = [
                    v for v, label in [
                        (counts["Natural Shade"], "Natural Shade"),
                        (counts["Manmade Shade"], "Manmade Shade"),
                        (counts["No Shade"], "No Shade"),
                    ]
                    if v == winner[0]
                ]
                if len(top_counts) == 1:
                    stops.loc[stops["stop_id"] == stop_id, "shading"] = winner[1]
                    save_shading_data(stops)
    vc = get_vote_counts(stop_id)
    st.sidebar.markdown(
        f"**Votes:** {vc['Total']} (Natural Shade: {vc['Natural Shade']}, Manmade Shade: {vc['Manmade Shade']}, No Shade: {vc['No Shade']})"
    )

    st.markdown("### Legend")
    st.markdown(
        "- **Natural Shade**: green marker\n"
        "- **Manmade Shade**: steel blue marker\n"
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
