from builder_app import *

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
        if st.button("Save now", use_container_width=True):
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
        if st.button("Create blank project", use_container_width=True):
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
                        st.dataframe(raw.head(25), use_container_width=True)
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
            use_container_width=True,
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
    if st.button(
        "Apply taxonomy",
        help=(
            "Save the edited shade categories and reapply them to the active dataset "
            "so maps, legends, previews, and exports use the latest taxonomy."
        ),
    ):
        st.session_state["taxonomy"] = edited_taxonomy.fillna("").to_dict("records")
        st.session_state["stops"] = prepare_stop_dataset(st.session_state["stops"], project, st.session_state["taxonomy"])
        st.success("Taxonomy applied to the active dataset.")

    st.subheader("Dataset Health")
    st.dataframe(validation_summary(st.session_state["stops"]), use_container_width=True, hide_index=True)
    st.dataframe(st.session_state["stops"].head(50), use_container_width=True, hide_index=True)



