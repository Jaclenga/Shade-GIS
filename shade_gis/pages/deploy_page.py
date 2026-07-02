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
        target_mode = st.radio(
            "GitHub target",
            ["Existing private repository", "New repository"],
            horizontal=True,
            help="Use an existing private repository when the GitHub repo already exists and your account has access.",
        )
        if target_mode == "Existing private repository":
            repo_target = st.text_input(
                "Existing repository",
                "",
                placeholder=f"OWNER/{default_repo_name}",
                help="Use OWNER/REPO or a full HTTPS GitHub URL.",
            ).strip()
            branch_name = st.text_input("Branch", "main").strip() or "main"
            repo_for_bundle = slugify_repo_name((repo_target or default_repo_name).rstrip("/").split("/")[-1].replace(".git", ""))
            st.caption("The deploy helper verifies private repo visibility when possible, copies only generated app files, previews the diff, and asks before committing.")
            if not repo_target:
                st.info("Enter the existing private repository before downloading the deploy bundle.")
        else:
            repo_target = st.text_input("GitHub repository name", default_repo_name)
            repo_target = slugify_repo_name(repo_target)
            branch_name = "main"
            repo_for_bundle = repo_target
            st.link_button("Create GitHub repository", github_new_repo_url(project, repo_target))
    with right:
        st.metric("Stops included", f"{len(stops_for_export):,}")
        st.metric("Dataset version", project.get("dataset_version", "draft"))

    bundle_name = f"{repo_for_bundle}.zip"
    deploy_mode = "existing" if target_mode == "Existing private repository" else "create"
    st.download_button(
        "Download GitHub deploy bundle",
        data=build_github_deploy_bundle(repo_target or repo_for_bundle, deploy_mode),
        file_name=bundle_name,
        mime="application/zip",
        type="primary",
        disabled=target_mode == "Existing private repository" and not repo_target,
    )

    st.markdown("#### After Downloading The Zip")
    st.markdown(
        f"Your browser should save the bundle as `{bundle_name}` in your Downloads folder. "
        "Open PowerShell and run the commands below; change `$ZipPath` only if your browser saves downloads somewhere else."
    )
    verification_lines = "git --version\ngh auth status"
    if target_mode == "Existing private repository" and repo_target:
        verification_lines += f'\ngh repo view "{repo_target}"'
    st.code(
        f'$BundleName = "{bundle_name}"\n'
        '$ZipPath = Join-Path (Join-Path $env:USERPROFILE "Downloads") $BundleName\n'
        f'$ExtractTo = Join-Path (Join-Path $env:USERPROFILE "Documents") "{repo_for_bundle}"\n'
        'if (-not (Test-Path $ZipPath)) { throw "Expected the deploy bundle at $ZipPath. If your browser saved it somewhere else, move it to Downloads or update $ZipPath." }\n'
        "Expand-Archive -Path $ZipPath -DestinationPath $ExtractTo -Force\n"
        "Set-Location $ExtractTo\n"
        'if (-not (Test-Path ".\\deploy_to_github.ps1")) { throw "deploy_to_github.ps1 was not found. Check that $ExtractTo points to the extracted deploy bundle folder, then run Set-Location $ExtractTo." }\n'
        f"{verification_lines}",
        language="powershell",
    )
    st.markdown(
        "If `gh auth status` reports that GitHub CLI is not authenticated, run `gh auth login` "
        "before publishing. If Windows blocks the downloaded script, run "
        "`Unblock-File .\\deploy_to_github.ps1` once from the extracted folder."
    )
    st.markdown(
        "The helper pauses before committing and asks you to type `PUBLISH` after showing the status "
        "and diff summary. Add `-Yes` to the command only when you intentionally want automated publishing."
    )
    if target_mode == "Existing private repository":
        st.markdown(
            "For an existing private repository, the helper clones the target repo into a temporary "
            "`_shade_gis_publish_*` folder under PowerShell's temp path, checks out the selected branch, "
            "copies only generated app/runtime files into that checkout, previews `git status` and "
            "`git diff --stat`, asks for confirmation, pushes changes, and cleans up the temp folder. "
            "Protected files such as `.git/`, `.github/`, `README.md`, `LICENSE`, `.env*`, and "
            "`secrets.toml` are not copied."
        )
    else:
        st.markdown(
            "For a new repository, the helper initializes Git in the extracted bundle, stages only "
            "generated app files, previews `git status` and `git diff --stat`, asks for confirmation, "
            "creates the GitHub repository, and pushes the branch. Public publishing requires the "
            "explicit `-AllowPublicTarget` flag."
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
        width="stretch",
        hide_index=True,
    )

    st.markdown("#### Command-Line Publish")
    if target_mode == "Existing private repository":
        st.code(
            f'$BundleName = "{bundle_name}"\n'
            '$ZipPath = Join-Path (Join-Path $env:USERPROFILE "Downloads") $BundleName\n'
            f'$ExtractTo = Join-Path (Join-Path $env:USERPROFILE "Documents") "{repo_for_bundle}"\n'
            'if (-not (Test-Path $ZipPath)) { throw "Expected the deploy bundle at $ZipPath. If your browser saved it somewhere else, move it to Downloads or update $ZipPath." }\n'
            "Expand-Archive -Path $ZipPath -DestinationPath $ExtractTo -Force\n"
            "Set-Location $ExtractTo\n"
            'if (-not (Test-Path ".\\deploy_to_github.ps1")) { throw "deploy_to_github.ps1 was not found. Check that $ExtractTo points to the extracted deploy bundle folder, then run Set-Location $ExtractTo." }\n'
            f'gh auth status\n'
            f'gh repo view "{repo_target}"\n'
            f'.\\deploy_to_github.ps1 -Mode existing -RepositoryName "{repo_target}" -Branch "{branch_name}"',
            language="powershell",
        )
    else:
        visibility = "public" if project.get("visibility") == "Public" else "private"
        public_flag = " -AllowPublicTarget" if visibility == "public" else ""
        st.code(
            f'$BundleName = "{bundle_name}"\n'
            '$ZipPath = Join-Path (Join-Path $env:USERPROFILE "Downloads") $BundleName\n'
            f'$ExtractTo = Join-Path (Join-Path $env:USERPROFILE "Documents") "{repo_for_bundle}"\n'
            'if (-not (Test-Path $ZipPath)) { throw "Expected the deploy bundle at $ZipPath. If your browser saved it somewhere else, move it to Downloads or update $ZipPath." }\n'
            "Expand-Archive -Path $ZipPath -DestinationPath $ExtractTo -Force\n"
            "Set-Location $ExtractTo\n"
            'if (-not (Test-Path ".\\deploy_to_github.ps1")) { throw "deploy_to_github.ps1 was not found. Check that $ExtractTo points to the extracted deploy bundle folder, then run Set-Location $ExtractTo." }\n'
            f'.\\deploy_to_github.ps1 -Mode create -RepositoryName "{repo_target}" -Branch "{branch_name}" -Visibility {visibility}{public_flag}',
            language="powershell",
        )




