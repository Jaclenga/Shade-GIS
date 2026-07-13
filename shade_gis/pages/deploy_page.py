from __future__ import annotations

import html
import io
import re
import urllib.parse
import zipfile
from datetime import datetime

import pandas as pd
import streamlit as st

from builder_app import (
    build_github_deploy_bundle,
    calculate_priority_scores,
    deploy_launcher_script,
    github_new_repo_url,
    slugify_repo_name,
    streamlit_entrypoint_path,
)


DEPLOYMENT_PROGRESS_KEY = "deploy_page_progress"
BUNDLE_FILE_CATALOG = [
    ("app.py", "Standalone public preview entrypoint"),
    ("public_voting.py", "Crowd voting interface and vote storage"),
    ("shade_study_stops.csv", "Published stop dataset"),
    ("shade_study_raw_labels.csv", "Raw labels, when available"),
    ("shade_study_config.json", "Project and visualization configuration"),
    ("requirements.txt", "Runtime dependencies"),
    ("README.md", "Deployment documentation"),
    ("deploy_to_github.ps1", "GitHub publishing helper"),
]


def deployment_target_key(repository: str, branch: str, bundle_name: str) -> str:
    return "|".join([repository.strip(), branch.strip(), bundle_name.strip()])


def deployment_progress(repository: str, branch: str, bundle_name: str) -> dict:
    progress = st.session_state.get(DEPLOYMENT_PROGRESS_KEY, {})
    if progress.get("target_key") != deployment_target_key(repository, branch, bundle_name):
        return {}
    return progress


def record_bundle_download(repository: str, branch: str, bundle_name: str, version: str) -> None:
    target_key = deployment_target_key(repository, branch, bundle_name)
    progress = st.session_state.get(DEPLOYMENT_PROGRESS_KEY, {})
    if progress.get("target_key") != target_key:
        progress = {"target_key": target_key}
    progress.update(
        {
            "repository": repository,
            "branch": branch,
            "bundle_name": bundle_name,
            "version": version,
            "downloaded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    )
    st.session_state[DEPLOYMENT_PROGRESS_KEY] = progress


def record_github_publish(repository: str, branch: str, bundle_name: str, version: str) -> None:
    target_key = deployment_target_key(repository, branch, bundle_name)
    progress = st.session_state.get(DEPLOYMENT_PROGRESS_KEY, {})
    if progress.get("target_key") != target_key:
        progress = {"target_key": target_key}
    progress.update(
        {
            "repository": repository,
            "branch": branch,
            "bundle_name": bundle_name,
            "version": version,
            "published_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    )
    st.session_state[DEPLOYMENT_PROGRESS_KEY] = progress


def reset_deployment_progress() -> None:
    st.session_state.pop(DEPLOYMENT_PROGRESS_KEY, None)


def relative_timestamp(value: str | None) -> str:
    if not value:
        return "Not yet"
    try:
        timestamp = datetime.fromisoformat(value)
        elapsed = max(0, int((datetime.now().astimezone() - timestamp).total_seconds()))
    except (TypeError, ValueError):
        return "Recorded"
    if elapsed < 60:
        return "Just now"
    minutes = elapsed // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def github_repository_url(repository: str) -> str | None:
    value = repository.strip()
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", value):
        return f"https://github.com/{value.removesuffix('.git')}"
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc.lower() == "github.com":
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2:
            return f"https://github.com/{parts[0]}/{parts[1].removesuffix('.git')}"
    return None


def bundle_file_count(bundle_data: bytes) -> int:
    if not bundle_data:
        return len(BUNDLE_FILE_CATALOG)
    with zipfile.ZipFile(io.BytesIO(bundle_data)) as bundle:
        return len([name for name in bundle.namelist() if not name.endswith("/")])


def render_deploy_styles() -> None:
    st.markdown(
        """
        <style>
        section.main > div.block-container {
            max-width: 920px;
        }
        .deploy-intro {
            max-width: 720px;
            color: #52606d;
            font-size: 1.02rem;
            margin: -0.25rem 0 1.2rem;
        }
        .deploy-section-rule {
            border-top: 1px solid #e5e7eb;
            margin: 1.5rem 0;
        }
        .st-key-deploy_metrics div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 14px;
            padding: 0.9rem 1rem;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
        }
        .st-key-deploy_metrics div[data-testid="stMetricValue"] {
            font-size: 1.45rem;
            font-weight: 750;
        }
        .st-key-deploy_primary_action div[data-testid="stDownloadButton"] button,
        .st-key-deploy_confirm_publish button {
            min-height: 3.6rem;
            border-radius: 12px;
            font-size: 1.08rem;
            font-weight: 750;
            box-shadow: 0 10px 24px rgba(190, 24, 24, 0.18);
        }
        .deploy-status-card {
            border: 1px solid #d9e2ec;
            border-radius: 16px;
            padding: 1.1rem 1.2rem;
            background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
            margin-bottom: 1rem;
        }
        .deploy-status-title {
            display: flex;
            align-items: center;
            gap: 0.55rem;
            font-size: 1.1rem;
            font-weight: 750;
            margin-bottom: 0.9rem;
        }
        .deploy-status-dot {
            width: 0.72rem;
            height: 0.72rem;
            border-radius: 999px;
            display: inline-block;
        }
        .deploy-status-dot.ready { background: #16a34a; box-shadow: 0 0 0 4px #dcfce7; }
        .deploy-status-dot.action { background: #d97706; box-shadow: 0 0 0 4px #fef3c7; }
        .deploy-status-dot.blocked { background: #94a3b8; box-shadow: 0 0 0 4px #f1f5f9; }
        .deploy-status-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.9rem;
        }
        .deploy-status-label {
            color: #64748b;
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .deploy-status-value {
            color: #0f172a;
            font-weight: 650;
            overflow-wrap: anywhere;
            margin-top: 0.15rem;
        }
        .deploy-progress-list {
            display: grid;
            gap: 0.45rem;
            margin: 0.65rem 0 1rem;
        }
        .deploy-progress-step {
            display: grid;
            grid-template-columns: 1.8rem 1fr auto;
            align-items: center;
            gap: 0.55rem;
            padding: 0.68rem 0.8rem;
            border-radius: 10px;
            background: #f8fafc;
        }
        .deploy-progress-icon.complete { color: #15803d; font-weight: 800; }
        .deploy-progress-icon.current { color: #b45309; font-weight: 800; }
        .deploy-progress-icon.pending { color: #94a3b8; }
        .deploy-progress-state { color: #64748b; font-size: 0.82rem; }
        @media (max-width: 720px) {
            .deploy-status-grid { grid-template-columns: 1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_status_card(
    repository: str,
    version: str,
    configured: bool,
    downloaded: bool,
    published: bool,
    published_at: str | None,
) -> None:
    if published:
        status_text, status_class = "Published successfully", "ready"
    elif downloaded:
        status_text, status_class = "Bundle downloaded — run PowerShell", "action"
    elif configured:
        status_text, status_class = "Ready to publish", "ready"
    else:
        status_text, status_class = "Repository required", "blocked"
    repository_text = repository or "Not configured"
    st.markdown(
        f"""
        <div class="deploy-status-card">
          <div class="deploy-status-title">
            <span class="deploy-status-dot {status_class}"></span>
            {html.escape(status_text)}
          </div>
          <div class="deploy-status-grid">
            <div><div class="deploy-status-label">Repository</div><div class="deploy-status-value">{html.escape(repository_text)}</div></div>
            <div><div class="deploy-status-label">Last published</div><div class="deploy-status-value">{html.escape(relative_timestamp(published_at))}</div></div>
            <div><div class="deploy-status-label">Current version</div><div class="deploy-status-value">{html.escape(version)}</div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_progress_steps(configured: bool, downloaded: bool, published: bool) -> None:
    steps = [
        ("Configure project", configured),
        ("Download deployment bundle", downloaded),
        ("Run PowerShell script", published),
        ("Push to GitHub", published),
        ("Deploy to Streamlit", False),
    ]
    current_assigned = False
    rows: list[str] = []
    for index, (label, complete) in enumerate(steps, start=1):
        if complete:
            icon, icon_class, state = "✓", "complete", "Complete"
        elif not current_assigned:
            icon, icon_class, state = str(index), "current", "Next"
            current_assigned = True
        else:
            icon, icon_class, state = str(index), "pending", "Pending"
        rows.append(
            '<div class="deploy-progress-step">'
            f'<span class="deploy-progress-icon {icon_class}">{icon}</span>'
            f'<span>{html.escape(label)}</span><span class="deploy-progress-state">{state}</span></div>'
        )
    st.markdown('<div class="deploy-progress-list">' + "".join(rows) + "</div>", unsafe_allow_html=True)


def render_deploy_page() -> None:
    project = st.session_state["project"]
    visualization = st.session_state["visualization"]
    stops = st.session_state["stops"]
    default_repo_name = slugify_repo_name(project.get("name", "shade-study-app"))
    version = str(project.get("dataset_version") or "draft")

    render_deploy_styles()
    st.title("Deploy")
    st.markdown(
        f'<p class="deploy-intro">Publish <strong>{html.escape(project.get("name", "this shade study"))}</strong> '
        "as a GitHub-backed Streamlit application.</p>",
        unsafe_allow_html=True,
    )

    if stops.empty:
        st.warning("Import a stop dataset before creating a deployment bundle.")
        return

    target_mode = st.radio(
        "Publish mode",
        ["Existing repository", "New repository"],
        horizontal=True,
        help="Choose an existing repository when GitHub already has the target project.",
    )
    if target_mode == "Existing repository":
        repo_target = st.text_input(
            "Repository",
            "",
            placeholder=f"OWNER/{default_repo_name}",
            help="Enter OWNER/REPO or a full GitHub repository URL.",
        ).strip()
        deploy_mode = "existing"
    else:
        repo_target = slugify_repo_name(st.text_input("Repository", default_repo_name))
        deploy_mode = "create"

    main_file_path = streamlit_entrypoint_path(deploy_mode)
    if deploy_mode == "existing":
        st.info(
            "Only the standalone public preview will be published under `preview_app/`. "
            "The repository's root `app.py` and Shade-GIS builder files will not be replaced."
        )
    else:
        st.info("The new repository will contain only the standalone public preview and its runtime files.")

    branch_name = st.text_input("Branch", "main").strip() or "main"
    repo_for_bundle = slugify_repo_name(
        (repo_target or default_repo_name).rstrip("/").split("/")[-1].replace(".git", "")
    )
    deploy_visibility = "public" if project.get("visibility") == "Public" else "private"
    deployment_ready = deploy_mode == "create" or bool(repo_target)
    bundle_name = f"{repo_for_bundle}.zip"

    stops_for_export = stops.copy()
    stops_for_export["priority_score"] = calculate_priority_scores(
        stops_for_export,
        visualization["priority_weights"],
    )
    bundle_data = (
        build_github_deploy_bundle(repo_target or repo_for_bundle, deploy_mode)
        if deployment_ready
        else b""
    )
    progress = deployment_progress(repo_target, branch_name, bundle_name)
    downloaded = bool(progress.get("downloaded_at"))
    published = bool(progress.get("published_at"))

    st.markdown('<div class="deploy-section-rule"></div>', unsafe_allow_html=True)
    with st.container(key="deploy_primary_action"):
        st.download_button(
            "🚀 Download deployment bundle" if not downloaded else "Download bundle again",
            data=bundle_data,
            file_name=bundle_name,
            mime="application/zip",
            type="primary" if not downloaded else "secondary",
            disabled=not deployment_ready,
            use_container_width=True,
            on_click=record_bundle_download,
            args=(repo_target, branch_name, bundle_name, version),
        )
    if not deployment_ready:
        st.caption("Enter an existing repository to enable deployment.")
    else:
        st.caption(
            "This prepares the public preview bundle. GitHub publishing completes after you run the generated "
            f"PowerShell command. Use `{main_file_path}` as the Streamlit main file. Numbered browser downloads "
            "such as `project (2).zip` are detected automatically, and the newest copy is used."
        )

    st.markdown('<div class="deploy-section-rule"></div>', unsafe_allow_html=True)
    st.subheader("Deployment status")
    render_status_card(
        repo_target,
        version,
        deployment_ready,
        downloaded,
        published,
        progress.get("published_at"),
    )
    with st.container(key="deploy_metrics"):
        metric_columns = st.columns(3)
        metric_columns[0].metric("Stops", f"{len(stops_for_export):,}")
        metric_columns[1].metric("Version", version)
        metric_columns[2].metric("Bundle files", str(bundle_file_count(bundle_data)))
    st.markdown("#### Deployment progress")
    render_progress_steps(deployment_ready, downloaded, published)

    if deployment_ready:
        with st.expander("Show PowerShell commands", expanded=False):
            st.caption("Use the copy control in the code block, then run the entire block in PowerShell.")
            st.code(
                deploy_launcher_script(
                    bundle_name,
                    repo_target,
                    branch_name,
                    deploy_mode,
                    deploy_visibility,
                ),
                language="powershell",
            )
    else:
        st.info("PowerShell commands appear after a repository is configured.")

    if downloaded and not published:
        st.info(
            "After the PowerShell script finishes and GitHub confirms the push, mark this step complete. "
            "The builder cannot observe the external terminal automatically."
        )
        with st.container(key="deploy_confirm_publish"):
            st.button(
                "✓ I completed the GitHub publish",
                type="primary",
                use_container_width=True,
                on_click=record_github_publish,
                args=(repo_target, branch_name, bundle_name, version),
            )

    if published:
        st.success("Published Successfully")
        st.markdown(f"Streamlit main file: `{main_file_path}`")
        action_columns = st.columns(2)
        repository_url = github_repository_url(repo_target)
        with action_columns[0]:
            if repository_url:
                st.link_button("View on GitHub", repository_url, use_container_width=True)
        with action_columns[1]:
            st.link_button("Deploy on Streamlit", "https://share.streamlit.io/", use_container_width=True)
        st.button(
            "Publish Again",
            use_container_width=True,
            on_click=reset_deployment_progress,
        )

    st.markdown('<div class="deploy-section-rule"></div>', unsafe_allow_html=True)
    with st.expander("Advanced deployment options", expanded=False):
        if deploy_mode == "create":
            st.link_button("Create GitHub repository", github_new_repo_url(project, repo_target))
            st.caption(
                f"New repositories use `{deploy_visibility}` visibility. Public creation requires the generated "
                "helper's explicit safety flag."
            )
        else:
            st.markdown(
                "The helper verifies repository access, clones into a temporary directory, copies only generated "
                "runtime files into `preview_app/`, previews the diff, and asks for confirmation before pushing."
            )

        if visualization.get("voting", {}).get("enabled", False):
            st.markdown("##### Voting storage")
            st.info(
                "Public voting is enabled. Set `SHADE_GIS_VOTE_DATABASE_URL` as a Streamlit PostgreSQL secret "
                "for durable hosted storage. The local SQLite fallback is intended for development."
            )

        st.markdown("##### Bundle contents")
        st.dataframe(
            pd.DataFrame(BUNDLE_FILE_CATALOG, columns=["File", "Purpose"]),
            width="stretch",
            hide_index=True,
        )
        st.caption(
            "The generated README repeats the guarded deployment workflow. Protected repository files such as "
            "`.git`, `.github`, `.streamlit`, `README.md`, `LICENSE`, `.env*`, and `secrets.toml` are not overwritten "
            "in existing mode."
        )
