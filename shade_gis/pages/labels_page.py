from builder_app import *

def render_review_queue(project_id: str, stops: pd.DataFrame, labels: pd.DataFrame, taxonomy: list[dict[str, Any]]) -> str | None:
    st.subheader("Admin Review Queue")
    queue = review_queue_table(stops, labels)
    if queue.empty:
        st.info("Import stops before reviewing labels.")
        return None

    filter_cols = st.columns([1.2, 1.1, 1.1], vertical_alignment="bottom")
    status_options = list(REVIEW_STATUS_COLORS)
    default_statuses = [status for status in REVIEW_QUEUE_DEFAULT_STATUSES if status in status_options]
    with filter_cols[0]:
        selected_statuses = st.multiselect(
            "Queue statuses",
            status_options,
            default=default_statuses,
            key="review_queue_statuses",
        )
    with filter_cols[1]:
        queue_search = st.text_input("Search queue", key="review_queue_search")
    with filter_cols[2]:
        only_conflicts = st.checkbox("Only disagreements", value=False, key="review_queue_conflicts_only")

    filtered = queue
    if selected_statuses:
        filtered = filtered[filtered["review_status"].isin(selected_statuses)]
    if queue_search.strip():
        haystack = (
            filtered["stop_id"].fillna("").astype(str)
            + " "
            + filtered["stop_name"].fillna("").astype(str)
            + " "
            + filtered["routes"].fillna("").astype(str)
        ).str.lower()
        filtered = filtered[haystack.str.contains(re.escape(queue_search.strip().lower()), na=False)]
    if only_conflicts:
        filtered = filtered[filtered["disagreement_flag"].astype(bool)]

    display_columns = [
        column
        for column in [
            "stop_id",
            "stop_name",
            "routes",
            "municipality",
            "shading",
            "review_status",
            "priority_score",
            "majority_label",
            "label_count",
            "agreement_pct",
            "disagreement_flag",
            "tied_majority",
        ]
        if column in filtered.columns
    ]
    if filtered.empty:
        st.info("No stops match the review queue filters.")
        return None
    st.dataframe(filtered.loc[:, display_columns].head(200), width="stretch", hide_index=True)

    queue_records = filtered.reset_index(drop=True)
    queue_labels = [review_queue_label(row) for _, row in queue_records.iterrows()]
    selected_index = st.selectbox(
        "Queue stop",
        range(len(queue_records)),
        format_func=lambda index: queue_labels[index],
        key="review_queue_stop_index",
    )
    selected_stop = queue_records.iloc[int(selected_index)]
    selected_stop_id = str(selected_stop.get("stop_id", ""))

    stop_labels = labels[labels["stop_id"].astype(str) == selected_stop_id] if not labels.empty else pd.DataFrame()
    detail_cols = st.columns([1, 1, 1, 1])
    detail_cols[0].metric("Current label", str(selected_stop.get("shading", "Needs Review") or "Needs Review"))
    detail_cols[1].metric("Review status", str(selected_stop.get("review_status", "Unlabeled") or "Unlabeled"))
    detail_cols[2].metric("Agreement", f"{float(selected_stop.get('agreement_pct', 0) or 0):.1f}%")
    detail_cols[3].metric("Raw labels", int(float(selected_stop.get("label_count", 0) or 0)))

    if stop_labels.empty:
        st.info("No raw labels are attached to this stop yet.")
    else:
        visible_label_columns = [
            column
            for column in [
                "created_at",
                "shade_category",
                "shade_coverage",
                "shade_sources",
                "confidence",
                "labeler_role",
                "labeler_id",
                "source",
                "notes",
            ]
            if column in stop_labels.columns
        ]
        st.dataframe(stop_labels.loc[:, visible_label_columns], width="stretch", hide_index=True)

    previous = stop_review_snapshot(selected_stop)
    category_options = taxonomy_names(taxonomy)
    current_category = previous["shade_category"]
    category_index = category_options.index(current_category) if current_category in category_options else 0
    coverage_options = SHADE_COVERAGE_OPTIONS
    current_coverage = previous["shade_coverage"]
    coverage_index = coverage_options.index(current_coverage) if current_coverage in coverage_options else len(coverage_options) - 1
    current_sources = [source for source in split_list_field(previous["shade_sources"]) if source in SHADE_SOURCE_OPTIONS]
    current_confidence = previous["confidence"]
    try:
        confidence_default = float(current_confidence)
    except (TypeError, ValueError):
        confidence_default = 0.85
    confidence_default = max(0.0, min(1.0, confidence_default))

    with st.form("admin_review_decision_form", clear_on_submit=False):
        st.markdown("#### Admin Review Decision")
        top_cols = st.columns([1, 1, 1])
        with top_cols[0]:
            action = st.selectbox("Decision type", REVIEW_ACTION_OPTIONS, key="review_action")
        default_status = REVIEW_ACTION_STATUS_DEFAULTS.get(action, "Needs Review")
        with top_cols[1]:
            actor_id = st.text_input("Reviewer or admin ID", key="review_actor_id")
        with top_cols[2]:
            actor_role = st.selectbox(
                "Reviewer role",
                LABELER_ROLE_OPTIONS,
                index=LABELER_ROLE_OPTIONS.index("Project Admin") if "Project Admin" in LABELER_ROLE_OPTIONS else 0,
                key="review_actor_role",
            )

        decision_cols = st.columns([1, 1, 1])
        with decision_cols[0]:
            final_status = st.selectbox(
                "Final review status",
                list(REVIEW_STATUS_COLORS),
                index=list(REVIEW_STATUS_COLORS).index(default_status),
                key="review_final_status",
            )
        with decision_cols[1]:
            final_category = st.selectbox("Final shade category", category_options, index=category_index, key="review_final_category")
        with decision_cols[2]:
            final_confidence = st.slider("Decision confidence", 0.0, 1.0, confidence_default, 0.05, key="review_final_confidence")

        lower_cols = st.columns([1, 1])
        with lower_cols[0]:
            final_coverage = st.selectbox("Final shade coverage", coverage_options, index=coverage_index, key="review_final_coverage")
        with lower_cols[1]:
            final_sources = st.multiselect("Final shade source(s)", SHADE_SOURCE_OPTIONS, default=current_sources, key="review_final_sources")
        notes = st.text_area("Decision notes", key="review_notes", height=110)
        decision_submitted = st.form_submit_button("Apply review decision", type="primary")

    if decision_submitted:
        if not selected_stop_id.strip():
            st.error("Selected stop is missing a stop ID.")
        else:
            final_sources_text = "; ".join(final_sources)
            apply_review_decision_to_stop(
                selected_stop_id,
                final_category,
                final_coverage,
                final_sources_text,
                final_confidence,
                final_status,
            )
            save_active_project_to_store()
            event_id = add_review_event(
                project_id,
                {
                    "stop_id": selected_stop_id,
                    "actor_id": actor_id,
                    "actor_role": actor_role,
                    "action": action,
                    "from_status": previous["review_status"],
                    "to_status": final_status,
                    "from_label": previous["shade_category"],
                    "to_label": final_category,
                    "from_coverage": previous["shade_coverage"],
                    "to_coverage": final_coverage,
                    "from_sources": previous["shade_sources"],
                    "to_sources": final_sources_text,
                    "from_confidence": previous["confidence"],
                    "to_confidence": final_confidence,
                    "majority_label": selected_stop.get("majority_label", ""),
                    "agreement_pct": selected_stop.get("agreement_pct", ""),
                    "label_count": selected_stop.get("label_count", 0),
                    "notes": notes,
                },
            )
            st.success(f"Applied review decision and saved audit event {event_id}.")
            st.rerun()

    return selected_stop_id



def render_review_audit_history(project_id: str, selected_stop_id: str | None) -> None:
    st.subheader("Review Audit History")
    show_selected = st.checkbox(
        "Show queue-selected stop only",
        value=bool(selected_stop_id),
        key="show_selected_review_history",
        disabled=not bool(selected_stop_id),
    )
    history = list_review_history(project_id, selected_stop_id if show_selected and selected_stop_id else None)
    if history.empty:
        st.info("No review decisions have been recorded yet.")
        return
    visible_columns = [
        column
        for column in [
            "created_at",
            "stop_id",
            "action",
            "from_status",
            "to_status",
            "metadata_from_label",
            "metadata_to_label",
            "metadata_actor_role",
            "actor_id",
            "notes",
        ]
        if column in history.columns
    ]
    st.dataframe(history.loc[:, visible_columns], width="stretch", hide_index=True)
    st.download_button(
        "Download review audit CSV",
        history.to_csv(index=False).encode("utf-8"),
        "shade_study_review_audit.csv",
        "text/csv",
    )



def selected_stop_reference_dataset(stops: pd.DataFrame, stop_id: str) -> pd.DataFrame:
    if stops.empty or "stop_id" not in stops.columns:
        return pd.DataFrame(columns=stops.columns)
    stop_mask = stops["stop_id"].astype(str) == str(stop_id)
    selected = stops.loc[stop_mask].copy()
    if selected.empty:
        return selected
    if {"stop_lat", "stop_lon"}.issubset(selected.columns):
        coordinates = selected[["stop_lat", "stop_lon"]].apply(pd.to_numeric, errors="coerce")
        selected = selected.loc[coordinates.notna().all(axis=1)].copy()
        selected[["stop_lat", "stop_lon"]] = coordinates.loc[selected.index]
    return selected



def stop_reference_map_datasets(stops: pd.DataFrame, selected_stop_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    if stops.empty or "stop_id" not in stops.columns:
        empty = pd.DataFrame(columns=stops.columns)
        return empty, empty
    if not {"stop_lat", "stop_lon"}.issubset(stops.columns):
        empty = pd.DataFrame(columns=stops.columns)
        return empty, empty

    mappable = stops.copy()
    coordinates = mappable[["stop_lat", "stop_lon"]].apply(pd.to_numeric, errors="coerce")
    mappable = mappable.loc[coordinates.notna().all(axis=1)].copy()
    if mappable.empty:
        return mappable, mappable
    mappable[["stop_lat", "stop_lon"]] = coordinates.loc[mappable.index]
    selected = mappable.loc[mappable["stop_id"].astype(str) == str(selected_stop_id)].copy()
    return mappable, selected



def build_stop_reference_deck(
    stops: pd.DataFrame,
    selected_stop_id: str,
    taxonomy: list[dict[str, Any]],
    visualization: dict[str, Any],
) -> pdk.Deck | None:
    mappable_stops, selected_stop = stop_reference_map_datasets(stops, selected_stop_id)
    if mappable_stops.empty or selected_stop.empty:
        return None

    map_visualization = dict(visualization)
    map_visualization["marker_size"] = min(8, max(5, int(map_visualization.get("marker_size", 7))))
    deck = build_deck_chart(mappable_stops, taxonomy, map_visualization)
    highlight_layer = pdk.Layer(
        "ScatterplotLayer",
        data=selected_stop,
        id="selected_label_stop_layer",
        get_position="[stop_lon, stop_lat]",
        get_fill_color=[255, 75, 75, 70],
        get_line_color=[255, 75, 75],
        get_radius=18,
        radius_units="pixels",
        radius_min_pixels=18,
        radius_max_pixels=18,
        stroked=True,
        filled=True,
        line_width_min_pixels=4,
        pickable=False,
    )
    deck.layers = [*deck.layers, highlight_layer]
    return deck



def stop_id_from_reference_map_selection(selection_event: Any, mappable_stops: pd.DataFrame) -> str | None:
    return published_app.selected_stop_id_from_map_selection(selection_event, mappable_stops)



def render_stop_reference_map(
    stops: pd.DataFrame,
    selected_stop_id: str,
    taxonomy: list[dict[str, Any]],
    visualization: dict[str, Any],
) -> str | None:
    mappable_stops, selected_stop = stop_reference_map_datasets(stops, selected_stop_id)
    if mappable_stops.empty or selected_stop.empty:
        st.info("No map location is available for the selected stop.")
        return None
    deck = build_stop_reference_deck(mappable_stops, selected_stop_id, taxonomy, visualization)
    if deck is None:
        st.info("No map location is available for the selected stop.")
        return None
    selection = st.pydeck_chart(
        deck,
        width="stretch",
        height=320,
        on_select="rerun",
        selection_mode="single-object",
        key=f"label_reference_map_{selected_stop_id}",
    )
    return stop_id_from_reference_map_selection(selection, mappable_stops)



def sync_label_stop_picker(stop_options: pd.DataFrame) -> None:
    if stop_options.empty or "stop_id" not in stop_options.columns:
        return
    stop_ids = stop_options["stop_id"].astype(str).tolist()
    selected_stop_id = str(st.session_state.get("label_selected_stop_id", "") or "")
    if selected_stop_id not in stop_ids:
        selected_stop_id = stop_ids[0]
        st.session_state["label_selected_stop_id"] = selected_stop_id
    selected_index = stop_ids.index(selected_stop_id)
    current_index = st.session_state.get("label_stop_index")
    if not isinstance(current_index, int) or current_index < 0 or current_index >= len(stop_ids):
        st.session_state["label_stop_index"] = selected_index
    elif stop_ids[current_index] != selected_stop_id:
        st.session_state["label_stop_index"] = selected_index



def apply_label_to_current_stop(
    stop_id: str,
    shade_category: str,
    shade_coverage: str,
    shade_sources: str,
    confidence: float,
) -> None:
    stops = st.session_state.get("stops", pd.DataFrame()).copy()
    if stops.empty or "stop_id" not in stops.columns:
        return
    mask = stops["stop_id"].astype(str) == str(stop_id)
    if not mask.any():
        return
    stops.loc[mask, "shading"] = shade_category
    stops.loc[mask, "shade_coverage"] = shade_coverage
    stops.loc[mask, "shade_sources"] = shade_sources
    stops.loc[mask, "confidence"] = confidence
    stops.loc[mask, "review_status"] = "Needs Review"
    st.session_state["stops"] = stops



def apply_review_decision_to_stop(
    stop_id: str,
    shade_category: str,
    shade_coverage: str,
    shade_sources: str,
    confidence: float,
    review_status: str,
) -> None:
    stops = st.session_state.get("stops", pd.DataFrame()).copy()
    if stops.empty or "stop_id" not in stops.columns:
        return
    mask = stops["stop_id"].astype(str) == str(stop_id)
    if not mask.any():
        return
    for column in ["shading", "shade_coverage", "shade_sources", "confidence", "review_status"]:
        if column not in stops.columns:
            stops[column] = ""
    stops.loc[mask, "shading"] = shade_category
    stops.loc[mask, "shade_coverage"] = shade_coverage
    stops.loc[mask, "shade_sources"] = shade_sources
    stops.loc[mask, "confidence"] = confidence
    stops.loc[mask, "review_status"] = review_status
    st.session_state["stops"] = stops



def render_labels_page() -> None:
    st.title("Labeling")
    project_id = st.session_state.get("active_project_id")
    stops = st.session_state.get("stops", pd.DataFrame())
    taxonomy = st.session_state.get("taxonomy", [])
    if not project_id:
        st.warning("Save or load a project before collecting labels.")
        return
    if stops.empty:
        st.warning("Import a stop dataset before collecting labels.")
        return

    labels = list_shade_labels(project_id)
    st.dataframe(raw_label_summary(labels, stops), width="stretch", hide_index=True)
    render_agreement_metrics(labels, stops)
    queue_stop_id = render_review_queue(project_id, stops, labels, taxonomy)
    render_review_audit_history(project_id, queue_stop_id)

    st.subheader("Raw Label Collection")
    stop_options = stops.reset_index(drop=True)
    sync_label_stop_picker(stop_options)
    stop_labels = [stop_picker_label(row) for _, row in stop_options.iterrows()]
    selected_index = st.selectbox(
        "Stop to label",
        range(len(stop_options)),
        format_func=lambda index: stop_labels[index],
        key="label_stop_index",
    )
    selected_stop = stop_options.iloc[int(selected_index)]
    selected_stop_id = str(selected_stop.get("stop_id", ""))
    st.session_state["label_selected_stop_id"] = selected_stop_id

    detail_cols = st.columns([1, 1, 1])
    detail_cols[0].metric("Current label", str(selected_stop.get("shading", "Needs Review") or "Needs Review"))
    detail_cols[1].metric("Review status", str(selected_stop.get("review_status", "Unlabeled") or "Unlabeled"))
    detail_cols[2].metric("Raw labels for stop", len(list_shade_labels(project_id, selected_stop_id)))

    map_selected_stop_id = render_stop_reference_map(stops, selected_stop_id, taxonomy, st.session_state.get("visualization", {}))
    if map_selected_stop_id and map_selected_stop_id != selected_stop_id:
        st.session_state["label_selected_stop_id"] = map_selected_stop_id
        st.rerun()

    with st.form("raw_label_form", clear_on_submit=False):
        st.subheader("Submit Raw Shade Label")
        form_cols = st.columns([1, 1, 1])
        with form_cols[0]:
            labeler_id = st.text_input("Reviewer or contributor ID", key="labeler_id")
            labeler_role = st.selectbox("Reviewer role", LABELER_ROLE_OPTIONS, key="labeler_role")
        with form_cols[1]:
            source_label = st.selectbox("Label source", LABEL_SOURCE_OPTIONS, key="label_source")
            image_id = st.text_input("Image ID or reference", key="label_image_id")
        with form_cols[2]:
            confidence = st.slider("Confidence", 0.0, 1.0, 0.75, 0.05, key="label_confidence")
            apply_current = st.checkbox(
                "Also update current map label",
                value=False,
                help="The raw label is always saved. This additionally updates the current stop fields used by maps and exports.",
            )

        category_options = taxonomy_names(taxonomy)
        current_category = str(selected_stop.get("shading", "")).strip()
        category_index = category_options.index(current_category) if current_category in category_options else 0
        shade_category = st.selectbox("Shade category", category_options, index=category_index, key="label_category")
        coverage_cols = st.columns([1, 1])
        with coverage_cols[0]:
            shade_coverage = st.selectbox("Shade coverage", SHADE_COVERAGE_OPTIONS, key="label_coverage")
        with coverage_cols[1]:
            shade_sources = st.multiselect("Shade source(s)", SHADE_SOURCE_OPTIONS, key="label_sources")
        notes = st.text_area("Notes", key="label_notes", height=120)
        submitted = st.form_submit_button("Save raw label", type="primary")

    if submitted:
        if not selected_stop_id.strip():
            st.error("Selected stop is missing a stop ID.")
        else:
            shade_sources_text = "; ".join(shade_sources)
            label_id = add_shade_label(
                project_id,
                {
                    "stop_id": selected_stop_id,
                    "image_id": image_id,
                    "labeler_id": labeler_id,
                    "labeler_role": labeler_role,
                    "shade_category": shade_category,
                    "shade_coverage": shade_coverage,
                    "shade_sources": shade_sources_text,
                    "confidence": confidence,
                    "notes": notes,
                    "source": label_source_code(source_label),
                    "source_label": source_label,
                    "stop_name": selected_stop.get("stop_name", ""),
                },
            )
            if apply_current:
                previous = stop_review_snapshot(selected_stop)
                apply_label_to_current_stop(selected_stop_id, shade_category, shade_coverage, shade_sources_text, confidence)
                save_active_project_to_store()
                add_review_event(
                    project_id,
                    {
                        "stop_id": selected_stop_id,
                        "actor_id": labeler_id,
                        "actor_role": labeler_role,
                        "action": "Raw label applied to map",
                        "from_status": previous["review_status"],
                        "to_status": "Needs Review",
                        "from_label": previous["shade_category"],
                        "to_label": shade_category,
                        "from_coverage": previous["shade_coverage"],
                        "to_coverage": shade_coverage,
                        "from_sources": previous["shade_sources"],
                        "to_sources": shade_sources_text,
                        "from_confidence": previous["confidence"],
                        "to_confidence": confidence,
                        "source": source_label,
                        "label_id": label_id,
                        "notes": notes,
                    },
                )
            st.success(f"Saved raw label {label_id}.")
            st.rerun()

    st.subheader("Raw Label History")
    show_selected_only = st.checkbox("Show selected stop only", value=False, key="show_selected_label_history")
    history = list_shade_labels(project_id, selected_stop_id if show_selected_only else None)
    if history.empty:
        st.info("No raw labels have been submitted yet.")
    else:
        visible_columns = [
            column
            for column in [
                "created_at",
                "stop_id",
                "shade_category",
                "shade_coverage",
                "shade_sources",
                "confidence",
                "labeler_role",
                "labeler_id",
                "source",
                "notes",
            ]
            if column in history.columns
        ]
        st.dataframe(history.loc[:, visible_columns], width="stretch", hide_index=True)
        st.download_button(
            "Download raw labels CSV",
            history.to_csv(index=False).encode("utf-8"),
            "shade_study_raw_labels.csv",
            "text/csv",
        )




