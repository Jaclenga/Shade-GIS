from builder_app import *

def render_deploy_page() -> None:
    project = st.session_state["project"]
    visualization = st.session_state["visualization"]
    stops = st.session_state["stops"]
    default_repo_name = slugify_repo_name(project.get("name", "shade-study-app"))

    st.title("Deploy")
    st.markdown(f"### Publish {project.get('name', 'this shade study')} as a GitHub-backed Streamlit app")

    if stops.empty:
        st.warning("Import a stop dataset before creating a deployment bundle.")
        return

    stops_for_export = stops.copy()
    stops_for_export["priority_score"] = calculate_priority_scores(stops_for_export, visualization["priority_weights"])

    left, right = st.columns([1, 1])
    with left:
        repo_name = st.text_input("GitHub repository name", default_repo_name)
        repo_name = slugify_repo_name(repo_name)
        st.link_button("Create GitHub repository", github_new_repo_url(project, repo_name))
    with right:
        st.metric("Stops included", f"{len(stops_for_export):,}")
        st.metric("Dataset version", project.get("dataset_version", "draft"))

    bundle_name = f"{repo_name}.zip"
    st.download_button(
        "Download GitHub deploy bundle",
        data=build_github_deploy_bundle(repo_name),
        file_name=bundle_name,
        mime="application/zip",
        type="primary",
    )

    st.markdown("#### Bundle Contents")
    st.dataframe(
        pd.DataFrame(
            [
                ("app.py", "Public Streamlit app rendered from the current builder state"),
                ("shade_study_stops.csv", "Published stop dataset"),
                ("shade_study_raw_labels.csv", "Raw label submissions, included when labels have been collected"),
                ("shade_study_config.json", "Project, methodology, taxonomy, visualization, and import-log settings"),
                ("requirements.txt", "Runtime dependencies for Streamlit Community Cloud"),
                ("README.md", "GitHub and Streamlit deployment notes"),
                ("deploy_to_github.ps1", "Optional GitHub CLI publishing helper"),
            ],
            columns=["File", "Purpose"],
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("#### Command-Line Publish")
    st.code(
        f'Expand-Archive .\\{bundle_name} -DestinationPath .\\{repo_name}\n'
        f"Set-Location .\\{repo_name}\n"
        f'.\\deploy_to_github.ps1 -RepositoryName "{repo_name}"',
        language="powershell",
    )



