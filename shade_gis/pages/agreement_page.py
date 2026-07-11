from __future__ import annotations

from typing import Any

from builder_app import *
from shade_gis.pages.labels_page import (
    apply_review_decision_to_stop,
    normalized_shade_sources,
    raw_label_comparison_table,
    render_label_code_helper,
    render_stop_reference_map,
    shade_category_from_coverage_and_sources,
)


AGREEMENT_VIEWS = {"overview", "queue", "review"}
QUEUE_PAGE_SIZES = [10, 25, 50]


def set_agreement_view(view: str, stop_id: str | None = None) -> None:
    st.session_state["agreement_view"] = view if view in AGREEMENT_VIEWS else "overview"
    if stop_id is not None:
        st.session_state["agreement_selected_stop_id"] = str(stop_id)


def filter_disagreement_queue_records(
    queue: pd.DataFrame,
    minimum_labels: int = 2,
    maximum_agreement: float = 99.9,
    label_categories: list[str] | None = None,
) -> pd.DataFrame:
    if queue.empty:
        return queue.copy()
    filtered = queue[
        (pd.to_numeric(queue["label_count"], errors="coerce").fillna(0) >= int(minimum_labels))
        & (pd.to_numeric(queue["agreement_pct"], errors="coerce").fillna(100) <= float(maximum_agreement))
    ].copy()
    selected = {str(category) for category in (label_categories or []) if str(category).strip()}
    if selected:
        filtered = filtered[
            filtered["majority_label"].fillna("").astype(str).map(
                lambda value: bool(selected.intersection(part.strip() for part in value.split(";") if part.strip()))
            )
        ]
    return filtered.sort_values(["agreement_pct", "label_count", "stop_id"], ascending=[True, False, True])


def paginate_records(records: pd.DataFrame, page: int, page_size: int) -> tuple[pd.DataFrame, int, int]:
    page_size = max(int(page_size), 1)
    page_count = max(1, math.ceil(len(records) / page_size))
    safe_page = min(max(int(page), 1), page_count)
    start = (safe_page - 1) * page_size
    return records.iloc[start : start + page_size].copy(), safe_page, page_count


def disagreement_queue_display_table(queue: pd.DataFrame) -> pd.DataFrame:
    records = []
    for _, row in queue.iterrows():
        stop_id = str(row.get("stop_id", ""))
        stop_name = str(row.get("stop_name", "") or "").strip()
        stop_display = f"{stop_id} — {stop_name}" if stop_name else stop_id
        records.append(
            {
                "Stop": stop_display,
                "Majority Label": str(row.get("majority_label", "") or "Tied"),
                "Votes": f"{int(row.get('majority_count', 0) or 0)} / {int(row.get('label_count', 0) or 0)}",
                "Agreement": f"{float(row.get('agreement_pct', 0) or 0):.1f}%",
            }
        )
    return pd.DataFrame.from_records(records, columns=["Stop", "Majority Label", "Votes", "Agreement"])


def agreement_overview_markup(metrics: dict[str, int | float | None]) -> str:
    mean = metrics["mean_agreement"]
    alpha = metrics["krippendorff_alpha"]
    kappa = metrics["fleiss_kappa"]
    mean_text = f"{float(mean):.1f}%" if mean is not None else "Not enough data"
    alpha_text = f"{float(alpha):.2f}" if alpha is not None else "Not enough data"
    kappa_text = f"{float(kappa):.2f}" if kappa is not None else "Not enough data"
    return f"""
    <style>
    .agreement-dashboard {{ margin: .15rem 0 .8rem; }}
    .agreement-cards {{
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: .75rem;
        margin: .7rem 0 1rem;
    }}
    .agreement-stat {{
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        background: #ffffff;
        padding: .8rem 1rem .9rem;
        min-height: 106px;
        box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
    }}
    .agreement-stat-label {{ color: #475569; font-size: .92rem; font-weight: 650; }}
    .agreement-stat-value {{ color: #0f172a; font-size: 1.75rem; font-weight: 750; margin-top: .55rem; }}
    .agreement-reliability {{
        border-top: 1px solid #e2e8f0;
        border-bottom: 1px solid #e2e8f0;
        padding: .75rem 0;
        margin-bottom: .8rem;
    }}
    .agreement-reliability-title {{ color: #334155; font-weight: 700; margin-bottom: .45rem; }}
    .agreement-reliability-row {{
        display: grid;
        grid-template-columns: minmax(180px, 1fr) auto;
        gap: 1rem;
        padding: .2rem 0;
        color: #334155;
    }}
    .agreement-reliability-value {{ color: #0f172a; font-weight: 650; }}
    @media (max-width: 720px) {{ .agreement-cards {{ grid-template-columns: 1fr; }} }}
    </style>
    <div class="agreement-dashboard">
      <div class="agreement-cards">
        <div class="agreement-stat"><div class="agreement-stat-label">📍 Labeled</div><div class="agreement-stat-value">{int(metrics['stops_labeled']):,}</div></div>
        <div class="agreement-stat"><div class="agreement-stat-label">⚠️ Review</div><div class="agreement-stat-value">{int(metrics['stops_needing_review']):,}</div></div>
        <div class="agreement-stat"><div class="agreement-stat-label">🤝 Agreement</div><div class="agreement-stat-value">{mean_text}</div></div>
      </div>
      <div class="agreement-reliability">
        <div class="agreement-reliability-title">Reliability</div>
        <div class="agreement-reliability-row"><span>Krippendorff α</span><span class="agreement-reliability-value">{alpha_text}</span></div>
        <div class="agreement-reliability-row"><span>Fleiss κ</span><span class="agreement-reliability-value">{kappa_text}</span></div>
      </div>
    </div>
    """


def render_agreement_overview(
    stops: pd.DataFrame,
    labels: pd.DataFrame,
    review_history: pd.DataFrame,
) -> None:
    metrics = agreement_overview_metrics(stops, labels, review_history)
    st.markdown("#### Agreement")
    st.caption("Overview of annotation quality and review status.")
    st.markdown(agreement_overview_markup(metrics), unsafe_allow_html=True)

    review_count = int(metrics["stops_needing_review"])
    if review_count == 0:
        if int(metrics["stops_labeled"]) == 0:
            st.info("No submitted labels are available for agreement analysis yet.")
        elif int(metrics["raw_disagreements"]) == 0:
            st.success("✅ All labeled stops currently have unanimous agreement.")
        else:
            st.success("✅ All raw-label disagreements have been reviewed.")
    elif st.button(
        f"🔍 Review Disagreements ({review_count:,})",
        type="primary",
        width="stretch",
        key="open_disagreement_queue",
    ):
        set_agreement_view("queue")
        st.rerun()


def render_queue_rows(queue_page: pd.DataFrame) -> None:
    headers = st.columns([2.2, 2, .8, .8, .7], vertical_alignment="center")
    for column, label in zip(headers, ["Stop", "Majority Label", "Votes", "Agreement", "Action"]):
        column.markdown(f"**{label}**")
    for _, row in queue_page.iterrows():
        columns = st.columns([2.2, 2, .8, .8, .7], vertical_alignment="center")
        stop_id = str(row.get("stop_id", ""))
        stop_name = str(row.get("stop_name", "") or "").strip()
        columns[0].markdown(f"**{stop_id}**" + (f"  \n{stop_name}" if stop_name else ""))
        columns[1].write(str(row.get("majority_label", "") or "Tied"))
        columns[2].write(f"{int(row.get('majority_count', 0) or 0)} / {int(row.get('label_count', 0) or 0)}")
        columns[3].write(f"{float(row.get('agreement_pct', 0) or 0):.1f}%")
        if columns[4].button("Review", key=f"review_disagreement_{stop_id}", type="primary"):
            set_agreement_view("review", stop_id)
            st.rerun()
        st.divider()


def render_disagreement_queue(queue: pd.DataFrame) -> None:
    title_cols = st.columns([1, 5], vertical_alignment="center")
    if title_cols[0].button("← Overview", key="agreement_back_overview"):
        set_agreement_view("overview")
        st.rerun()
    title_cols[1].subheader("Disagreement Review Queue")
    st.caption("Only unresolved disagreements are shown. Lowest agreement appears first.")

    categories = sorted(
        {
            part.strip()
            for value in queue.get("majority_label", pd.Series(dtype=str)).fillna("").astype(str)
            for part in value.split(";")
            if part.strip()
        }
    )
    filters = st.columns([1, 1.35, 2])
    minimum_labels = filters[0].number_input(
        "Minimum labels", min_value=2, value=2, step=1, key="agreement_minimum_labels"
    )
    maximum_agreement = filters[1].slider(
        "Agreement threshold", min_value=0.0, max_value=99.9, value=99.9, step=0.1,
        help="Show stops at or below this agreement percentage.", key="agreement_maximum_agreement"
    )
    selected_categories = filters[2].multiselect(
        "Label category", categories, key="agreement_label_categories"
    )
    filtered = filter_disagreement_queue_records(
        queue, int(minimum_labels), float(maximum_agreement), selected_categories
    )
    if filtered.empty:
        st.info("No unresolved disagreements match these filters.")
        return

    paging = st.columns([1, 1, 3], vertical_alignment="bottom")
    page_size = paging[0].selectbox("Rows per page", QUEUE_PAGE_SIZES, index=1, key="agreement_page_size")
    page_count = max(1, math.ceil(len(filtered) / int(page_size)))
    requested_page = paging[1].number_input(
        "Page", min_value=1, max_value=page_count, value=min(int(st.session_state.get("agreement_page", 1)), page_count),
        step=1, key="agreement_page"
    )
    page_records, current_page, page_count = paginate_records(filtered, int(requested_page), int(page_size))
    paging[2].caption(f"{len(filtered):,} disagreements · Page {current_page:,} of {page_count:,}")
    render_queue_rows(page_records)


def street_view_url(stop: pd.Series) -> str | None:
    lat = pd.to_numeric(pd.Series([stop.get("stop_lat")]), errors="coerce").iloc[0]
    lon = pd.to_numeric(pd.Series([stop.get("stop_lon")]), errors="coerce").iloc[0]
    if pd.isna(lat) or pd.isna(lon):
        return None
    return f"https://www.google.com/maps?layer=c&cbll={float(lat):.7f},{float(lon):.7f}&output=svembed"


def render_uploaded_images(images: pd.DataFrame) -> None:
    if images.empty:
        st.info("No uploaded or referenced photos are attached to this stop.")
        return
    columns = st.columns(min(3, len(images)))
    for index, (_, image) in enumerate(images.iterrows()):
        uri = str(image.get("storage_path", "") or image.get("uri", "") or "").strip()
        caption_parts = [str(image.get("image_type", "") or "Photo").replace("_", " ").title()]
        if str(image.get("captured_at", "") or "").strip():
            caption_parts.append(str(image.get("captured_at")))
        if str(image.get("attribution", "") or "").strip():
            caption_parts.append(str(image.get("attribution")))
        with columns[index % len(columns)]:
            if uri:
                st.image(uri, caption=" · ".join(caption_parts), width="stretch")
            else:
                st.warning("An image record is missing its file or URL.")


def render_review_imagery(
    project_id: str,
    stop: pd.Series,
    stops: pd.DataFrame,
    taxonomy: list[dict[str, Any]],
) -> None:
    street_tab, map_tab, photos_tab = st.tabs(["Street View", "Map", "Uploaded Photos"])
    with street_tab:
        url = street_view_url(stop)
        if url:
            st.components.v1.iframe(url, height=430, scrolling=False)
            st.link_button("Open Street View in Google Maps", url.replace("&output=svembed", ""))
        else:
            st.info("This stop has no coordinates for Street View.")
    with map_tab:
        render_stop_reference_map(stops, str(stop.get("stop_id", "")), taxonomy, st.session_state.get("visualization", {}))
    with photos_tab:
        render_uploaded_images(list_images(project_id, str(stop.get("stop_id", ""))))


def default_sources_from_labels(stop_labels: pd.DataFrame, fallback: Any = "") -> list[str]:
    source_votes: dict[str, int] = {}
    if not stop_labels.empty and "shade_sources" in stop_labels.columns:
        for value in stop_labels["shade_sources"]:
            for source in normalized_shade_sources(value):
                source_votes[source] = source_votes.get(source, 0) + 1
    if source_votes:
        max_votes = max(source_votes.values())
        return [source for source in SHADE_SOURCE_OPTIONS if source_votes.get(source) == max_votes]
    return [source for source in normalized_shade_sources(fallback) if source in SHADE_SOURCE_OPTIONS]


def render_canonical_decision(
    project_id: str,
    stop: pd.Series,
    stop_labels: pd.DataFrame,
    taxonomy: list[dict[str, Any]],
) -> None:
    stop_id = str(stop.get("stop_id", ""))
    majority = normalize_shade_coverage(stop.get("majority_label", ""), "Needs Review")
    default_coverage = majority if majority in SHADE_COVERAGE_OPTIONS else normalize_shade_coverage(stop.get("shade_coverage", ""), "Limited Shade")
    default_sources = default_sources_from_labels(stop_labels, stop.get("shade_sources", ""))

    with st.form(f"canonical_decision_{stop_id}"):
        st.subheader("Final Canonical Label")
        render_label_code_helper(taxonomy, "Label definitions")
        final_coverage = st.radio(
            "Shade coverage", SHADE_COVERAGE_OPTIONS,
            index=SHADE_COVERAGE_OPTIONS.index(default_coverage), key=f"canonical_coverage_{stop_id}"
        )
        st.markdown("**Shade source(s)**")
        final_sources: list[str] = []
        source_columns = st.columns(len(SHADE_SOURCE_OPTIONS))
        for index, source in enumerate(SHADE_SOURCE_OPTIONS):
            with source_columns[index]:
                if st.checkbox(
                    source, value=source in default_sources and final_coverage != "No Shade",
                    disabled=final_coverage == "No Shade", key=f"canonical_source_{stop_id}_{source}"
                ):
                    final_sources.append(source)
        reviewer_columns = st.columns(2)
        actor_id = reviewer_columns[0].text_input(
            "Reviewer ID", placeholder="Use an anonymized ID if preferred", key=f"canonical_actor_{stop_id}"
        )
        notes = reviewer_columns[1].text_area("Decision notes", height=90, key=f"canonical_notes_{stop_id}")
        submitted = st.form_submit_button("Save Decision", type="primary", width="stretch")

    if submitted:
        previous = stop_review_snapshot(stop)
        final_sources_text = "; ".join(final_sources) if final_coverage != "No Shade" else ""
        final_category = shade_category_from_coverage_and_sources(final_coverage, final_sources)
        apply_review_decision_to_stop(
            stop_id, final_category, final_coverage, final_sources_text, 1.0, "Accepted"
        )
        save_active_project_to_store()
        event_id = add_review_event(
            project_id,
            {
                "stop_id": stop_id,
                "actor_id": actor_id,
                "actor_role": "Agreement Reviewer",
                "action": "Resolve disagreement",
                "from_status": previous["review_status"],
                "to_status": "Accepted",
                "from_label": previous["shade_category"],
                "to_label": final_category,
                "from_coverage": previous["shade_coverage"],
                "to_coverage": final_coverage,
                "from_sources": previous["shade_sources"],
                "to_sources": final_sources_text,
                "from_confidence": previous["confidence"],
                "to_confidence": 1.0,
                "majority_label": stop.get("majority_label", ""),
                "agreement_pct": stop.get("agreement_pct", ""),
                "label_count": stop.get("label_count", 0),
                "notes": notes,
            },
        )
        st.session_state.pop("agreement_selected_stop_id", None)
        st.success(f"Decision saved to review history ({event_id}). Loading the next disagreement…")
        st.rerun()


def render_single_disagreement(
    project_id: str,
    queue: pd.DataFrame,
    stops: pd.DataFrame,
    labels: pd.DataFrame,
    taxonomy: list[dict[str, Any]],
) -> None:
    if queue.empty:
        st.success("All disagreements have been reviewed.")
        if st.button("Return to overview", type="primary"):
            set_agreement_view("overview")
            st.rerun()
        return
    stop_ids = queue["stop_id"].astype(str).tolist()
    selected_id = str(st.session_state.get("agreement_selected_stop_id", "") or "")
    if selected_id not in stop_ids:
        selected_id = stop_ids[0]
        st.session_state["agreement_selected_stop_id"] = selected_id
    stop = queue.loc[queue["stop_id"].astype(str) == selected_id].iloc[0]

    navigation = st.columns([1, 5, 1], vertical_alignment="center")
    if navigation[0].button("← Queue", key="agreement_back_queue"):
        set_agreement_view("queue")
        st.rerun()
    navigation[1].subheader(f"Stop #{selected_id}")
    navigation[2].caption(f"{stop_ids.index(selected_id) + 1} of {len(stop_ids)}")
    if str(stop.get("stop_name", "") or "").strip():
        st.caption(str(stop.get("stop_name")))

    stop_labels = labels[labels["stop_id"].astype(str) == selected_id].copy() if not labels.empty else pd.DataFrame()
    st.subheader("Current Labels")
    if stop_labels.empty:
        st.info("No submitted labels are attached to this stop.")
    else:
        st.dataframe(raw_label_comparison_table(stop_labels), width="stretch", hide_index=True)
    render_review_imagery(project_id, stop, stops, taxonomy)
    render_canonical_decision(project_id, stop, stop_labels, taxonomy)

    history = list_review_history(project_id, selected_id)
    if not history.empty:
        with st.expander("Review history", expanded=False):
            visible = [column for column in ["created_at", "actor_id", "action", "from_status", "to_status", "notes"] if column in history]
            st.dataframe(history[visible], width="stretch", hide_index=True)


def render_agreement_analytics_section(
    project_id: str | None,
    stops: pd.DataFrame,
    labels: pd.DataFrame,
    taxonomy: list[dict[str, Any]],
) -> None:
    """Render the admin agreement workflow inside the Preview Analytics tab."""
    if not project_id:
        st.warning("Save or load a project before reviewing agreement.")
        return
    if stops.empty:
        st.warning("Import a stop dataset before reviewing agreement.")
        return

    review_history = list_review_history(project_id)
    queue = disagreement_queue_table(stops, labels, review_history)
    view = str(st.session_state.get("agreement_view", "overview"))
    if view not in AGREEMENT_VIEWS:
        view = "overview"
    if view == "overview":
        render_agreement_overview(stops, labels, review_history)
    elif view == "queue":
        render_disagreement_queue(queue)
    else:
        render_single_disagreement(project_id, queue, stops, labels, taxonomy)
