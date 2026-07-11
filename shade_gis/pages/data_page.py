from builder_app import *
from shade_gis.shade_dimensions import normalize_shade_coverage


DATASET_REVIEWED_STATUSES = {"Crowd Reviewed", "Expert Reviewed", "Accepted", "Archived"}
DATASET_ATTENTION_STATUSES = {"Needs Review", "Disputed"}
DATASET_STATUS_OPTIONS = ["Needs Review", "Reviewed", "Unlabeled"]
DATASET_QUEUE_PAGE_SIZES = [10, 25, 50]
DATASET_PREVIEW_PAGE_SIZES = [25, 50, 100]


def dataset_status_table(
    stops: pd.DataFrame,
    labels: pd.DataFrame,
    review_history: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Combine canonical stop state and raw-label history into progress rows."""
    if stops.empty or "stop_id" not in stops.columns:
        return pd.DataFrame(
            columns=["stop_id", "dataset_status", "label_count", "final_label", "agreement_pct"]
        )
    status = stops.copy()
    status["stop_id"] = status["stop_id"].fillna("").astype(str).str.strip()
    majority = majority_label_table(labels)
    if not majority.empty:
        majority = majority.copy()
        majority["stop_id"] = majority["stop_id"].astype(str)
        computed_columns = [column for column in majority.columns if column != "stop_id" and column in status.columns]
        status = status.drop(columns=computed_columns)
        status = status.merge(majority, on="stop_id", how="left")
    for column, fallback in [
        ("label_count", 0),
        ("agreement_pct", None),
        ("disagreement_flag", False),
        ("review_status", "Unlabeled"),
        ("shading", ""),
        ("shade_coverage", ""),
    ]:
        if column not in status.columns:
            status[column] = fallback
        status[column] = status[column].fillna(fallback) if fallback is not None else status[column]
    status["label_count"] = pd.to_numeric(status["label_count"], errors="coerce").fillna(0).astype(int)
    status["review_status"] = status["review_status"].fillna("Unlabeled").astype(str)

    def final_label(row: pd.Series) -> str:
        coverage = normalize_shade_coverage(row.get("shade_coverage", ""), "")
        if not coverage:
            coverage = normalize_shade_coverage(row.get("shading", ""), "")
        return coverage if coverage and coverage != "Needs Review" else "Not set"

    status["final_label"] = status.apply(final_label, axis=1)
    unresolved = disagreement_queue_table(stops, labels, review_history)
    unresolved_ids = set(unresolved["stop_id"].astype(str)) if not unresolved.empty else set()
    status["unresolved_disagreement"] = status["stop_id"].isin(unresolved_ids)

    def work_status(row: pd.Series) -> str:
        review_status = str(row.get("review_status", "") or "")
        if bool(row.get("unresolved_disagreement", False)):
            return "Needs Review"
        if review_status in DATASET_REVIEWED_STATUSES:
            return "Reviewed"
        if review_status in DATASET_ATTENTION_STATUSES or bool(row.get("disagreement_flag", False)):
            return "Needs Review"
        if int(row.get("label_count", 0) or 0) == 0 and row.get("final_label") == "Not set":
            return "Unlabeled"
        return "Needs Review"

    status["dataset_status"] = status.apply(work_status, axis=1)
    status["is_labeled"] = (status["label_count"] > 0) | status["final_label"].ne("Not set")
    return status


def dataset_status_metrics(status: pd.DataFrame) -> dict[str, int | float]:
    total = len(status)
    labeled_mask = status.get("is_labeled", pd.Series(False, index=status.index)).fillna(False).astype(bool)
    labeled = int(labeled_mask.sum())
    reviewed = int((status.get("dataset_status", pd.Series(dtype=str)).eq("Reviewed") & labeled_mask).sum())
    needs_review = int(status.get("dataset_status", pd.Series(dtype=str)).eq("Needs Review").sum())
    unlabeled = int(status.get("dataset_status", pd.Series(dtype=str)).eq("Unlabeled").sum())
    return {
        "total_stops": total,
        "labeled_stops": labeled,
        "reviewed_stops": reviewed,
        "stops_needing_review": needs_review,
        "unlabeled_stops": unlabeled,
        "label_coverage": labeled / total if total else 0.0,
        "review_completion": reviewed / labeled if labeled else 0.0,
    }


def filter_dataset_work_queue(
    status: pd.DataFrame,
    selected_statuses: list[str],
    stop_search: str = "",
) -> pd.DataFrame:
    filtered = status.copy()
    if selected_statuses:
        filtered = filtered[filtered["dataset_status"].isin(selected_statuses)]
    if stop_search.strip():
        query = stop_search.strip().lower()
        filtered = filtered[filtered["stop_id"].astype(str).str.lower().str.contains(query, regex=False)]
    rank = {"Needs Review": 0, "Unlabeled": 1, "Reviewed": 2}
    filtered["status_rank"] = filtered["dataset_status"].map(rank).fillna(3)
    filtered["agreement_sort"] = pd.to_numeric(filtered["agreement_pct"], errors="coerce").fillna(101)
    return filtered.sort_values(["status_rank", "agreement_sort", "stop_id"])


def dataset_work_queue_display(status: pd.DataFrame) -> pd.DataFrame:
    records = []
    for _, row in status.iterrows():
        agreement = pd.to_numeric(pd.Series([row.get("agreement_pct")]), errors="coerce").iloc[0]
        records.append(
            {
                "Stop ID": str(row.get("stop_id", "")),
                "Status": str(row.get("dataset_status", "")),
                "Labels": int(row.get("label_count", 0) or 0),
                "Final Label": str(row.get("final_label", "Not set") or "Not set"),
                "Agreement": f"{float(agreement):.1f}%" if pd.notna(agreement) else "—",
            }
        )
    return pd.DataFrame.from_records(
        records,
        columns=["Stop ID", "Status", "Labels", "Final Label", "Agreement"],
    )


def dataset_preview_page(
    stops: pd.DataFrame,
    page: int,
    page_size: int,
) -> tuple[pd.DataFrame, int, int]:
    """Return only the requested preview slice so the UI never mounts all rows."""
    page_size = max(int(page_size), 1)
    page_count = max(1, math.ceil(len(stops) / page_size))
    safe_page = min(max(int(page), 1), page_count)
    start = (safe_page - 1) * page_size
    return stops.iloc[start : start + page_size].copy(), safe_page, page_count


def render_dataset_status(
    stops: pd.DataFrame,
    labels: pd.DataFrame,
    review_history: pd.DataFrame | None = None,
) -> None:
    st.subheader("Dataset Status")
    st.caption("Project progress, remaining work, and stops that need attention.")
    status = dataset_status_table(stops, labels, review_history)
    metrics = dataset_status_metrics(status)

    cards = st.columns(4)
    cards[0].metric("Total stops", f"{metrics['total_stops']:,}")
    cards[1].metric("Labeled stops", f"{metrics['labeled_stops']:,}")
    cards[2].metric("Reviewed stops", f"{metrics['reviewed_stops']:,}")
    cards[3].metric("Needs review", f"{metrics['stops_needing_review']:,}")

    progress = st.columns(2)
    with progress[0]:
        st.markdown("**Label coverage**")
        st.progress(float(metrics["label_coverage"]))
        st.caption(
            f"{metrics['labeled_stops']:,} of {metrics['total_stops']:,} stops have a raw or final label "
            f"({float(metrics['label_coverage']) * 100:.1f}%)."
        )
    with progress[1]:
        st.markdown("**Review completion**")
        st.progress(float(metrics["review_completion"]))
        st.caption(
            f"{metrics['reviewed_stops']:,} of {metrics['labeled_stops']:,} labeled stops are reviewed "
            f"({float(metrics['review_completion']) * 100:.1f}%)."
        )

    st.markdown("#### Work Queue")
    filters = st.columns([2, 1.2])
    selected_statuses = filters[0].multiselect(
        "Status",
        DATASET_STATUS_OPTIONS,
        default=["Needs Review", "Unlabeled"],
        key="dataset_queue_statuses",
    )
    stop_search = filters[1].text_input(
        "Search stop ID",
        key="dataset_queue_stop_search",
        placeholder="e.g. 4254",
    )
    filtered = filter_dataset_work_queue(status, selected_statuses, stop_search)
    if filtered.empty:
        st.info("No stops match the work queue filters.")
    else:
        paging = st.columns([1, 1, 3], vertical_alignment="bottom")
        page_size = paging[0].selectbox(
            "Rows per page",
            DATASET_QUEUE_PAGE_SIZES,
            index=1,
            key="dataset_queue_page_size",
        )
        page_count = max(1, math.ceil(len(filtered) / int(page_size)))
        current_page = st.session_state.get("dataset_queue_page", 1)
        if not isinstance(current_page, int) or current_page < 1 or current_page > page_count:
            st.session_state["dataset_queue_page"] = min(max(int(current_page or 1), 1), page_count)
        requested_page = paging[1].number_input(
            "Page",
            min_value=1,
            max_value=page_count,
            step=1,
            key="dataset_queue_page",
        )
        start = (int(requested_page) - 1) * int(page_size)
        visible = filtered.iloc[start : start + int(page_size)]
        paging[2].caption(
            f"{len(filtered):,} stops · Page {int(requested_page):,} of {page_count:,} · "
            f"{metrics['unlabeled_stops']:,} unlabeled overall"
        )
        st.dataframe(dataset_work_queue_display(visible), width="stretch", hide_index=True)

    with st.expander("Dataset Preview", expanded=False):
        st.caption("Browse the project dataset one page at a time. Only the visible page is rendered.")
        st.dataframe(validation_summary(stops), width="stretch", hide_index=True)
        preview_controls = st.columns([1, 1, 3], vertical_alignment="bottom")
        preview_page_size = preview_controls[0].selectbox(
            "Preview rows per page",
            DATASET_PREVIEW_PAGE_SIZES,
            index=1,
            key="dataset_preview_page_size",
        )
        preview_page_count = max(1, math.ceil(len(stops) / int(preview_page_size)))
        current_preview_page = st.session_state.get("dataset_preview_page", 1)
        if (
            not isinstance(current_preview_page, int)
            or current_preview_page < 1
            or current_preview_page > preview_page_count
        ):
            st.session_state["dataset_preview_page"] = min(
                max(int(current_preview_page or 1), 1),
                preview_page_count,
            )
        requested_preview_page = preview_controls[1].number_input(
            "Preview page",
            min_value=1,
            max_value=preview_page_count,
            step=1,
            key="dataset_preview_page",
        )
        visible_stops, preview_page, preview_page_count = dataset_preview_page(
            stops,
            int(requested_preview_page),
            int(preview_page_size),
        )
        first_row = (preview_page - 1) * int(preview_page_size) + 1 if len(stops) else 0
        last_row = min(preview_page * int(preview_page_size), len(stops))
        preview_controls[2].caption(
            f"Showing rows {first_row:,}–{last_row:,} of {len(stops):,} · "
            f"Page {preview_page:,} of {preview_page_count:,}"
        )
        st.dataframe(visible_stops, width="stretch", hide_index=True)

def render_project_storage_controls() -> None:
    projects = list_projects()
    project_ids = [project["id"] for project in projects]
    active_project_id = st.session_state.get("active_project_id")
    if active_project_id not in project_ids and project_ids:
        active_project_id = project_ids[0]

    def project_label(project_id: str) -> str:
        project = next((item for item in projects if item["id"] == project_id), {})
        name = project.get("name") or "Untitled Shade Study"
        region = project.get("region") or "No region"
        version = project.get("dataset_version") or "draft"
        return f"{name} - {region} - v{version}"

    st.subheader("Project Store")
    cols = st.columns([1.5, 0.55, 0.95], vertical_alignment="bottom")
    with cols[0]:
        if project_ids:
            selected_project_id = st.selectbox(
                "Active saved project",
                project_ids,
                index=project_ids.index(active_project_id),
                format_func=project_label,
            )
            if selected_project_id != active_project_id:
                save_active_project_to_store()
                load_project_into_session(selected_project_id)
                st.rerun()
    with cols[1]:
        if st.button("Save now", width="stretch"):
            save_active_project_to_store()
            st.success("Project saved.")
    with cols[2]:
        status = database_status()
        if status["using_fallback"]:
            st.caption(f"Database fallback: `{status['active_path']}`")
        else:
            st.caption(f"Database: `{status['active_path']}`")

    create_cols = st.columns([1.5, 0.65], vertical_alignment="bottom")
    with create_cols[0]:
        new_project_name = st.text_input("New blank project name", key="new_project_name")
    with create_cols[1]:
        if st.button("Create blank project", width="stretch"):
            new_project_id = create_blank_project(new_project_name)
            load_project_into_session(new_project_id)
            st.rerun()


def render_data_page() -> None:
    st.title("Project Data")
    render_project_storage_controls()
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
    file_tab, api_tab, manual_tab = st.tabs(["File Upload", "API URL", "Manual Entry"])
    with file_tab:
        uploaded = st.file_uploader(
            "Upload GTFS, CSV, GeoJSON, or a zipped Shapefile",
            type=["zip", "txt", "csv", "geojson", "json"],
        )
        st.caption(
            f"Upload limit: {format_bytes(max_upload_bytes())}; ZIPs may contain up to "
            f"{max_zip_members()} files and expand to {format_bytes(max_zip_uncompressed_bytes())}."
        )
        if uploaded is not None:
            if getattr(uploaded, "size", 0) > max_upload_bytes():
                st.error(f"This upload is larger than the {format_bytes(max_upload_bytes())} limit.")
                return
            contents = uploaded.getvalue()
            filename = uploaded.name
            key_prefix = f"file_{clean_import_key(filename)}"
            try:
                if filename.lower().endswith(".zip"):
                    zip_format = detect_zip_import_format(contents)
                    if zip_format == "GTFS":
                        raw, metadata = parse_gtfs_zip(contents)
                        st.dataframe(raw.head(25), width="stretch")
                        if st.button("Use uploaded GTFS stops", type="primary", key=f"{key_prefix}_gtfs"):
                            mapping = {field: field for field in REQUIRED_STOP_FIELDS + OPTIONAL_FIELDS if field in raw.columns}
                            metadata.update({"original_filename": filename})
                            prepared = import_stop_dataset(
                                raw,
                                mapping,
                                project=project,
                                taxonomy=taxonomy,
                                source_name=filename,
                                import_format="GTFS",
                                metadata=metadata,
                            )
                            st.success(f"Imported {len(prepared):,} mapped stops.")
                    else:
                        raw, metadata = parse_shapefile_zip(contents)
                        metadata.update({"original_filename": filename})
                        render_mapped_import_controls(
                            raw,
                            source_name=filename,
                            import_format="Shapefile",
                            project=project,
                            taxonomy=taxonomy,
                            metadata=metadata,
                            key_prefix=key_prefix,
                            button_label="Use mapped Shapefile",
                        )
                elif filename.lower().endswith((".geojson", ".json")):
                    raw, metadata = parse_geojson_bytes(contents)
                    metadata.update({"original_filename": filename})
                    render_mapped_import_controls(
                        raw,
                        source_name=filename,
                        import_format="GeoJSON",
                        project=project,
                        taxonomy=taxonomy,
                        metadata=metadata,
                        key_prefix=key_prefix,
                        button_label="Use mapped GeoJSON",
                    )
                else:
                    raw = read_csv_bytes(contents)
                    render_mapped_import_controls(
                        raw,
                        source_name=filename,
                        import_format="CSV",
                        project=project,
                        taxonomy=taxonomy,
                        metadata={"original_filename": filename},
                        key_prefix=key_prefix,
                        button_label="Use mapped CSV",
                    )
            except Exception as error:
                st.error(f"Could not import this file: {error}")

    with api_tab:
        api_url = st.text_input("Dataset API or file URL", key="api_import_url")
        api_format = st.selectbox("Response format", ["Auto detect", "CSV", "GeoJSON"], key="api_import_format")
        st.caption(
            f"API imports accept HTTP(S) CSV or GeoJSON responses up to {format_bytes(max_api_bytes())}. "
            "Private network URLs are blocked unless enabled by deployment settings."
        )
        if st.button("Fetch API dataset", key="fetch_api_dataset"):
            if not api_url.strip():
                st.warning("Enter a URL before fetching.")
            else:
                try:
                    contents = fetch_api_bytes(api_url)
                    requested = "Auto" if api_format == "Auto detect" else api_format
                    raw, metadata = parse_api_response(contents, api_url, requested)
                    st.session_state["api_import_raw"] = raw
                    st.session_state["api_import_metadata"] = metadata
                    st.session_state["api_import_source"] = api_url
                    st.success(f"Fetched {len(raw):,} records.")
                except Exception as error:
                    st.error(f"Could not fetch this API dataset: {error}")
        api_raw = st.session_state.get("api_import_raw")
        if isinstance(api_raw, pd.DataFrame):
            api_metadata = st.session_state.get("api_import_metadata", {})
            detected = api_metadata.get("detected_format") or api_format.replace("Auto detect", "API")
            render_mapped_import_controls(
                api_raw,
                source_name=st.session_state.get("api_import_source", api_url),
                import_format=str(detected),
                project=project,
                taxonomy=taxonomy,
                metadata=api_metadata,
                key_prefix="api_import",
                button_label="Use mapped API dataset",
            )

    with manual_tab:
        st.caption("Add one stop per row. Rows without a stop ID or valid coordinates are ignored on import.")
        manual_template = pd.DataFrame([{column: "" for column in MANUAL_ENTRY_COLUMNS}])
        manual_rows = st.data_editor(
            manual_template,
            num_rows="dynamic",
            width="stretch",
            hide_index=True,
            key="manual_import_rows",
        )
        manual_source = st.text_input("Manual import source label", "Manual entry", key="manual_import_source")
        if st.button("Use manual entries", type="primary", key="use_manual_entries"):
            mapping = {field: field for field in REQUIRED_STOP_FIELDS + OPTIONAL_FIELDS if field in manual_rows.columns}
            prepared = import_stop_dataset(
                manual_rows,
                mapping,
                project=project,
                taxonomy=taxonomy,
                source_name=manual_source,
                import_format="Manual",
                metadata={"entry_method": "manual"},
            )
            st.success(f"Imported {len(prepared):,} manually entered stops.")

    source_cols = st.columns(3)
    with source_cols[0]:
        project["source_name"] = st.text_input("Data source name", project["source_name"])
    with source_cols[1]:
        project["source_license"] = st.text_input("Source license", project["source_license"])
    with source_cols[2]:
        project["source_url"] = st.text_input("Source URL", project["source_url"])

    st.subheader("Shade Source Taxonomy")
    st.dataframe(
        pd.DataFrame(SHADE_SOURCE_TAXONOMY),
        width="stretch",
        hide_index=True,
        column_config={
            "shade_source": st.column_config.TextColumn("Shade Source"),
            "operational_definition": st.column_config.TextColumn("Operational Definition"),
        },
    )

    st.subheader("Shade Coverage Taxonomy")
    st.dataframe(
        pd.DataFrame(SHADE_COVERAGE_TAXONOMY),
        width="stretch",
        hide_index=True,
        column_config={
            "shade_coverage": st.column_config.TextColumn("Shade Coverage"),
            "operational_definition": st.column_config.TextColumn("Operational Definition"),
        },
    )

    project_id = st.session_state.get("active_project_id")
    labels = list_shade_labels(project_id) if project_id else pd.DataFrame()
    review_history = list_review_history(project_id) if project_id else pd.DataFrame()
    render_dataset_status(st.session_state["stops"], labels, review_history)




