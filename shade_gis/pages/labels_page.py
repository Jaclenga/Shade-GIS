from builder_app import *


REVIEW_STATUS_DEFINITIONS = {
    "Unlabeled": "No raw label or admin review has been collected for the stop.",
    "Needs Review": "The stop needs imagery review, more labels, or admin resolution.",
    "Crowd Reviewed": "Community or contributor labels have been collected but not accepted as final.",
    "Expert Reviewed": "An expert reviewer has made a decision that may still need project acceptance.",
    "Accepted": "The project accepts the current label for mapping, analysis, and export.",
    "Disputed": "Reviewers disagree or the evidence is ambiguous enough to require follow-up.",
    "Archived": "The stop or decision is retained for audit history but removed from active review.",
}

LABEL_WORKFLOW_OPTIONS = ["Review labels", "Submit raw label"]


def label_code_definition_tables(taxonomy: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    active_taxonomy = taxonomy or DEFAULT_TAXONOMY
    coverage = pd.DataFrame(
        [
            {
                "Code": item.get("shade_coverage", ""),
                "Definition": item.get("operational_definition", ""),
            }
            for item in SHADE_COVERAGE_TAXONOMY
        ]
    )
    sources = pd.DataFrame(
        [
            {
                "Code": item.get("shade_source", ""),
                "Definition": item.get("operational_definition", ""),
            }
            for item in SHADE_SOURCE_TAXONOMY
        ]
    )
    map_label_rows = [
        {
            "Code": normalize_shade_category_label(item.get("name", "")),
            "Definition": item.get("description", ""),
        }
        for item in active_taxonomy
        if str(item.get("name", "") or "").strip()
    ]
    map_labels = pd.DataFrame(map_label_rows, columns=["Code", "Definition"]).drop_duplicates(
        subset=["Code"],
        keep="first",
    )
    review_statuses = pd.DataFrame(
        [
            {
                "Code": status,
                "Definition": REVIEW_STATUS_DEFINITIONS.get(status, ""),
            }
            for status in REVIEW_STATUS_COLORS
        ]
    )
    storage_fields = pd.DataFrame(
        [
            {
                "Code": "shade_coverage",
                "Definition": "Extent of shade reaching the passenger waiting area.",
            },
            {
                "Code": "shade_sources",
                "Definition": "Observed source categories for shade reaching the waiting area.",
            },
            {
                "Code": "shading",
                "Definition": "Derived map label used for coloring, filtering, summaries, and exports.",
            },
            {
                "Code": "review_status",
                "Definition": "Workflow state for the current map label or admin decision.",
            },
            {
                "Code": "confidence",
                "Definition": "Reviewer confidence saved as a numeric score from 0 to 1.",
            },
        ]
    )
    return {
        "Stored fields": storage_fields,
        "Coverage codes": coverage,
        "Source codes": sources,
        "Map label codes": map_labels,
        "Review status codes": review_statuses,
    }


def render_label_code_helper(taxonomy: list[dict[str, Any]], title: str = "Label/code definitions") -> None:
    with st.expander(title, expanded=False):
        for section, table in label_code_definition_tables(taxonomy).items():
            st.markdown(f"##### {section}")
            st.dataframe(table, width="stretch", hide_index=True)


def render_label_workflow_toggle() -> str:
    if hasattr(st, "segmented_control"):
        selected = st.segmented_control(
            "Labeling workflow",
            LABEL_WORKFLOW_OPTIONS,
            default=LABEL_WORKFLOW_OPTIONS[0],
            key="label_workflow_mode",
        )
        return selected or LABEL_WORKFLOW_OPTIONS[0]
    return st.radio(
        "Labeling workflow",
        LABEL_WORKFLOW_OPTIONS,
        index=0,
        horizontal=True,
        key="label_workflow_mode",
    )


def render_shared_label_reference_map(
    stops: pd.DataFrame,
    selected_stop_id: str,
    taxonomy: list[dict[str, Any]],
) -> None:
    map_selected_stop_id = render_stop_reference_map(
        stops,
        selected_stop_id,
        taxonomy,
        st.session_state.get("visualization", {}),
    )
    if map_selected_stop_id and map_selected_stop_id != selected_stop_id:
        st.session_state["label_selected_stop_id"] = map_selected_stop_id
        st.rerun()


def sync_review_queue_stop_picker(queue_records: pd.DataFrame) -> None:
    if queue_records.empty or "stop_id" not in queue_records.columns:
        return
    stop_ids = queue_records["stop_id"].astype(str).tolist()
    selected_stop_id = str(st.session_state.get("label_selected_stop_id", "") or "")
    if selected_stop_id in stop_ids:
        st.session_state["review_queue_stop_index"] = stop_ids.index(selected_stop_id)
        return
    current_index = st.session_state.get("review_queue_stop_index")
    if not isinstance(current_index, int) or current_index < 0 or current_index >= len(stop_ids):
        st.session_state["review_queue_stop_index"] = 0


def render_review_queue_selector(
    stops: pd.DataFrame,
    labels: pd.DataFrame,
) -> tuple[str | None, pd.Series | None]:
    st.subheader("Admin Review Queue")
    queue = review_queue_table(stops, labels)
    if queue.empty:
        st.info("Submit raw labels before reviewing label decisions.")
        return None, None

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

    if filtered.empty:
        st.info("No stops match the review queue filters.")
        return None, None
    st.dataframe(review_queue_display_table(filtered).head(200), width="stretch", hide_index=True)

    queue_records = filtered.reset_index(drop=True)
    sync_review_queue_stop_picker(queue_records)
    queue_labels = [review_queue_label(row) for _, row in queue_records.iterrows()]
    selected_index = st.selectbox(
        "Stop to review",
        range(len(queue_records)),
        format_func=lambda index: queue_labels[index],
        key="review_queue_stop_index",
    )
    selected_stop = queue_records.iloc[int(selected_index)]
    selected_stop_id = str(selected_stop.get("stop_id", ""))
    st.session_state["label_selected_stop_id"] = selected_stop_id

    stop_labels = labels[labels["stop_id"].astype(str) == selected_stop_id] if not labels.empty else pd.DataFrame()
    detail_cols = st.columns([1.25, 1, 1.25, 1, 1])
    detail_cols[0].metric("Current map label", normalize_shade_category_label(selected_stop.get("shading", "Needs Review")))
    detail_cols[1].metric("Status", str(selected_stop.get("review_status", "Unlabeled") or "Unlabeled"))
    detail_cols[2].metric("Most common raw label", normalize_shade_category_label(selected_stop.get("majority_label", "")) or "Not enough labels")
    detail_cols[3].metric("Agreement", f"{float(selected_stop.get('agreement_pct', 0) or 0):.1f}%")
    detail_cols[4].metric("Submitted labels", int(float(selected_stop.get("label_count", 0) or 0)))

    if stop_labels.empty:
        st.info("No raw labels are attached to this stop yet.")
    else:
        st.markdown("#### Raw Label Comparison")
        st.dataframe(raw_label_comparison_table(stop_labels), width="stretch", hide_index=True)

    return selected_stop_id, selected_stop


def render_admin_review_decision(
    project_id: str,
    selected_stop_id: str,
    selected_stop: pd.Series,
    taxonomy: list[dict[str, Any]],
) -> None:
    previous = stop_review_snapshot(selected_stop)
    category_options = taxonomy_names(taxonomy)
    current_category = previous["shade_category"]
    category_index = category_options.index(current_category) if current_category in category_options else 0
    coverage_options = SHADE_COVERAGE_OPTIONS
    current_coverage = previous["shade_coverage"]
    coverage_index = coverage_options.index(current_coverage) if current_coverage in coverage_options else len(coverage_options) - 1
    current_sources = [source for source in normalized_shade_sources(previous["shade_sources"]) if source in SHADE_SOURCE_OPTIONS]
    current_confidence = previous["confidence"]
    try:
        confidence_default = float(current_confidence)
    except (TypeError, ValueError):
        confidence_default = 0.85
    confidence_default = max(0.0, min(1.0, confidence_default))

    with st.form("admin_review_decision_form", clear_on_submit=False):
        st.markdown("#### Admin Review Decision")
        render_label_code_helper(taxonomy, "Review label/code definitions")
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
            st.markdown("Final shade source(s)")
            final_sources = []
            final_source_cols = st.columns(len(SHADE_SOURCE_OPTIONS))
            for index, source in enumerate(SHADE_SOURCE_OPTIONS):
                with final_source_cols[index]:
                    if st.checkbox(
                        source,
                        value=source in current_sources and final_coverage != "No Shade",
                        key=f"review_final_source_{source.lower()}",
                        disabled=final_coverage == "No Shade",
                    ):
                        final_sources.append(source)
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


def render_review_queue(project_id: str, stops: pd.DataFrame, labels: pd.DataFrame, taxonomy: list[dict[str, Any]]) -> str | None:
    selected_stop_id, selected_stop = render_review_queue_selector(stops, labels)
    if not selected_stop_id or selected_stop is None:
        return None
    render_admin_review_decision(project_id, selected_stop_id, selected_stop, taxonomy)
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


def normalize_shade_category_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if ";" in text:
        return "; ".join(
            normalized for part in text.split(";") if (normalized := normalize_shade_category_label(part))
        )
    aliases = {
        "Intentional Built Shade": "Constructed Shade",
        "Incidental Built Shade": "Manmade Shade",
        "Unknown": "Needs Review",
    }
    return aliases.get(text, text)


def format_review_source(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("_", " ").title()


def format_confidence(value: Any) -> str:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return ""
    if pd.isna(confidence):
        return ""
    if 0 <= confidence <= 1:
        return f"{confidence * 100:.0f}%"
    return f"{confidence:.2f}"


def format_submitted_at(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("T", " ")


def reviewer_display(row: pd.Series) -> str:
    reviewer = str(row.get("labeler_id", "") or "").strip()
    role = str(row.get("labeler_role", "") or "").strip()
    if reviewer and role:
        return f"{reviewer} ({role})"
    return reviewer or role or "Unspecified"


def source_display(value: Any) -> str:
    sources = normalized_shade_sources(value)
    return "; ".join(sources)


def review_queue_display_table(queue: pd.DataFrame) -> pd.DataFrame:
    records = []
    for _, row in queue.iterrows():
        label_count = int(float(row.get("label_count", 0) or 0))
        agreement = float(row.get("agreement_pct", 0) or 0)
        if bool(row.get("disagreement_flag", False)):
            attention = "Disagreement"
        elif bool(row.get("tied_majority", False)):
            attention = "Tied vote"
        elif label_count == 0:
            attention = "Needs labels"
        else:
            attention = "Ready to review"
        records.append(
            {
                "Stop": stop_picker_label(row),
                "Status": str(row.get("review_status", "Unlabeled") or "Unlabeled"),
                "Current map label": normalize_shade_category_label(row.get("shading", "")),
                "Most common raw label": normalize_shade_category_label(row.get("majority_label", "")) or "Not enough labels",
                "Labels": label_count,
                "Agreement": f"{agreement:.1f}%",
                "Needs attention": attention,
                "Priority": f"{float(row.get('priority_score', 0) or 0):.2f}",
            }
        )
    return pd.DataFrame.from_records(records)


def raw_label_comparison_table(stop_labels: pd.DataFrame) -> pd.DataFrame:
    records = []
    for _, row in stop_labels.iterrows():
        records.append(
            {
                "Submitted": format_submitted_at(row.get("created_at", "")),
                "Label": normalize_shade_category_label(row.get("shade_category", "")),
                "Coverage": str(row.get("shade_coverage", "") or ""),
                "Sources": source_display(row.get("shade_sources", "")),
                "Confidence": format_confidence(row.get("confidence", "")),
                "Reviewer": reviewer_display(row),
                "Input": format_review_source(row.get("source", "")),
                "Notes": str(row.get("notes", "") or ""),
            }
        )
    display = pd.DataFrame.from_records(records)
    for column in display.columns:
        display[column] = display[column].astype(str)
    return display



def infer_shade_sources_from_category(shade_category: str) -> str:
    normalized = str(shade_category or "").strip().lower()
    if not normalized or "no shade" in normalized or "needs review" in normalized:
        return ""
    if "natural" in normalized or "tree" in normalized or "vegetation" in normalized:
        return "Natural"
    if "constructed" in normalized or "intentional" in normalized or "shelter" in normalized or "canopy" in normalized:
        return "Constructed"
    if "manmade" in normalized or "incidental" in normalized or "building" in normalized or "built" in normalized:
        return "Manmade"
    return ""


def normalize_shade_source(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "natural":
        return "Natural"
    if normalized in {"constructed", "intentional built", "intentional constructed"}:
        return "Constructed"
    if normalized in {"manmade", "incidental built"}:
        return "Manmade"
    return ""


def normalized_shade_sources(value: Any) -> list[str]:
    sources: list[str] = []
    for source in split_list_field(value):
        normalized = normalize_shade_source(source)
        if normalized and normalized not in sources:
            sources.append(normalized)
    return sources


def shade_type_from_category(shade_category: str) -> str:
    normalized = str(shade_category or "").strip().lower()
    if not normalized or "needs review" in normalized:
        return "Needs Review"
    if "no shade" in normalized:
        return "Needs Review"
    if "natural" in normalized or "tree" in normalized or "vegetation" in normalized:
        return "Natural Shade"
    if "constructed" in normalized or "intentional" in normalized or "shelter" in normalized or "canopy" in normalized:
        return "Constructed Shade"
    if "manmade" in normalized or "incidental" in normalized or "building" in normalized or "built" in normalized:
        return "Manmade Shade"
    return str(shade_category or "").strip() or "Needs Review"


def shade_type_options(taxonomy: list[dict[str, Any]]) -> list[str]:
    options: list[str] = []
    for category in taxonomy_names(taxonomy):
        shade_type = shade_type_from_category(category)
        if shade_type not in options:
            options.append(shade_type)
    for shade_type in ["Natural Shade", "Constructed Shade", "Manmade Shade", "Needs Review"]:
        if shade_type not in options:
            options.append(shade_type)
    return options


def coverage_from_category(shade_category: str, fallback: str = "") -> str:
    normalized = str(shade_category or "").strip().lower()
    if str(fallback or "").strip() in {"No Shade", "Limited", "Significant"}:
        return str(fallback).strip()
    if "no shade" in normalized:
        return "No Shade"
    if "limited" in normalized:
        return "Limited"
    if "significant" in normalized:
        return "Significant"
    return "Limited"


def shade_category_from_type(shade_type: str, shade_coverage: str) -> str:
    if shade_coverage == "No Shade":
        return "No Shade"
    if shade_type == "Natural Shade":
        return f"{shade_coverage} Natural Shade"
    return shade_type


def shade_category_from_coverage_and_sources(shade_coverage: str, shade_sources: list[str]) -> str:
    if shade_coverage == "No Shade":
        return "No Shade"
    if "Constructed" in shade_sources:
        return "Constructed Shade"
    if "Manmade" in shade_sources:
        return "Manmade Shade"
    if "Natural" in shade_sources:
        return f"{shade_coverage} Natural Shade"
    return "Needs Review"



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



def render_raw_label_collection(
    project_id: str,
    stops: pd.DataFrame,
    labels: pd.DataFrame,
    taxonomy: list[dict[str, Any]],
) -> None:
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
    selected_stop_labels = labels[labels["stop_id"].astype(str) == selected_stop_id] if not labels.empty else pd.DataFrame()
    detail_cols[2].metric("Raw labels for stop", len(selected_stop_labels))

    render_shared_label_reference_map(stops, selected_stop_id, taxonomy)

    with st.form("raw_label_form", clear_on_submit=False):
        st.subheader("Submit Raw Shade Label")
        render_label_code_helper(taxonomy, "Raw label/code definitions")
        current_category = str(selected_stop.get("shading", "")).strip()
        manual_source_index = LABEL_SOURCE_OPTIONS.index("Manual review") if "Manual review" in LABEL_SOURCE_OPTIONS else 0
        default_role = "Reviewer" if "Reviewer" in LABELER_ROLE_OPTIONS else LABELER_ROLE_OPTIONS[0]

        st.markdown("##### Label")
        coverage_labels = ["Limited", "No Shade", "Significant Shade"]
        coverage_values = {"Limited": "Limited", "No Shade": "No Shade", "Significant Shade": "Significant"}
        current_coverage = str(selected_stop.get("shade_coverage", "") or "")
        coverage_default = coverage_from_category(current_category, current_coverage)
        coverage_label_default = "Significant Shade" if coverage_default == "Significant" else coverage_default
        coverage_index = coverage_labels.index(coverage_label_default) if coverage_label_default in coverage_labels else 0
        coverage_label = st.selectbox("Coverage", coverage_labels, index=coverage_index, key="label_coverage")
        shade_coverage = coverage_values[coverage_label]

        existing_sources = normalized_shade_sources(selected_stop.get("shade_sources", ""))
        if not existing_sources:
            inferred_source = infer_shade_sources_from_category(current_category)
            existing_sources = [inferred_source] if inferred_source else []
        selected_sources = []
        st.markdown("Shade source")
        source_cols = st.columns(len(SHADE_SOURCE_OPTIONS))
        for index, source in enumerate(SHADE_SOURCE_OPTIONS):
            with source_cols[index]:
                if st.checkbox(
                    source,
                    value=source in existing_sources and shade_coverage != "No Shade",
                    key=f"label_source_{source.lower()}",
                    disabled=shade_coverage == "No Shade",
                ):
                    selected_sources.append(source)
        shade_sources = [] if shade_coverage == "No Shade" else selected_sources
        shade_sources_text = "; ".join(shade_sources)
        shade_category = shade_category_from_coverage_and_sources(shade_coverage, shade_sources)

        st.markdown("##### Assessment")
        confidence_choice = st.radio(
            "Confidence",
            ["Low", "Medium", "High"],
            index=1,
            horizontal=True,
            key="label_confidence_level",
        )
        confidence = {"Low": 0.35, "Medium": 0.7, "High": 1.0}[confidence_choice]

        st.markdown("##### Optional")
        notes = st.text_area("Notes", key="label_notes", height=80)

        with st.expander("Advanced", expanded=False):
            labeler_id = st.text_input("Reviewer", key="labeler_id")
            labeler_role = default_role
            source_label = st.selectbox(
                "Label source",
                LABEL_SOURCE_OPTIONS,
                index=manual_source_index,
                key="label_source",
            )
            image_id = st.text_input("Image reference", key="label_image_id")

        action_cols = st.columns([2, 1], vertical_alignment="bottom")
        with action_cols[0]:
            apply_current = st.checkbox(
                "Update map label immediately",
                value=False,
                help="The raw label is always saved. This additionally updates the current stop fields used by maps and exports.",
            )
        with action_cols[1]:
            submitted = st.form_submit_button("Save Label", type="primary", width="stretch")

    if submitted:
        if not selected_stop_id.strip():
            st.error("Selected stop is missing a stop ID.")
        else:
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


def render_review_label_section(
    project_id: str,
    stops: pd.DataFrame,
    labels: pd.DataFrame,
    taxonomy: list[dict[str, Any]],
) -> None:
    selected_stop_id, selected_stop = render_review_queue_selector(stops, labels)
    if selected_stop_id and selected_stop is not None:
        render_shared_label_reference_map(stops, selected_stop_id, taxonomy)
        render_admin_review_decision(project_id, selected_stop_id, selected_stop, taxonomy)
    render_review_audit_history(project_id, selected_stop_id)


def render_labeling_summary(labels: pd.DataFrame, stops: pd.DataFrame) -> None:
    st.subheader("Summary")
    st.dataframe(raw_label_summary(labels, stops), width="stretch", hide_index=True)
    render_agreement_metrics(labels, stops)


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
    workflow = render_label_workflow_toggle()
    if workflow == "Review labels":
        render_review_label_section(project_id, stops, labels, taxonomy)
    else:
        render_raw_label_collection(project_id, stops, labels, taxonomy)
    render_labeling_summary(labels, stops)




