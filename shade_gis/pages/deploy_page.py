from __future__ import annotations

import html
import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from builder_app import (
    build_github_deploy_bundle,
    deploy_launcher_script,
    github_new_repo_url,
    set_page,
    slugify_repo_name,
)
from shade_gis.deployment import (
    STREAMLIT_WORKSPACE_URL,
    DeploymentTarget,
    PublishResult,
    deployment_readiness,
    detect_deployment_target,
    github_repository_url,
    normalize_public_url,
    public_url_from_sources,
    publish_website,
    repository_has_published_app,
    repository_metadata,
    unpublish_website,
    verify_website,
)


DEPLOYMENT_RESULT_KEY = "deploy_page_result"
DEPLOYMENT_TARGET_KEY = "deploy_page_result_target"
DEPLOYMENT_ADVANCED_KEY = "deploy_page_show_advanced"
DEPLOYMENT_UNPUBLISH_KEY = "deploy_page_confirm_unpublish"
DEPLOYMENT_UNPUBLISHED_KEY = "deploy_page_unpublished"
DEPLOYMENT_STAGE_KEY = "deploy_page_stage"
STAGES = ("Check project", "Prepare website", "Publish", "Verify website")
BUNDLE_FILE_CATALOG = [
    ("app.py", "Public website"),
    ("public_voting.py", "Optional visitor voting"),
    ("shade_study_stops.csv", "Published stop data"),
    ("shade_study_raw_labels.csv", "Published label history, when available"),
    ("shade_study_config.json", "Project display settings"),
    ("requirements.txt", "Website runtime"),
    ("README.md", "Manual deployment documentation"),
    ("deploy_to_github.ps1", "Manual publishing fallback"),
]


def deployment_target_key(target: DeploymentTarget) -> str:
    return "|".join(
        [target.repository.strip(), target.branch.strip(), target.mode, target.public_url.strip()]
    )


def bundle_file_count(bundle_data: bytes) -> int:
    if not bundle_data:
        return len(BUNDLE_FILE_CATALOG)
    with zipfile.ZipFile(io.BytesIO(bundle_data)) as bundle:
        return len([name for name in bundle.namelist() if not name.endswith("/")])


@st.cache_data(ttl=60, show_spinner=False)
def cached_repository_metadata(repository: str, repository_url: str, branch: str, root: str) -> dict:
    return repository_metadata(
        DeploymentTarget(
            repository=repository,
            repository_url=repository_url,
            branch=branch,
            root=Path(root) if root else None,
        )
    )


@st.cache_data(ttl=45, show_spinner=False)
def cached_website_check(url: str) -> tuple[bool, str]:
    return verify_website(url, attempts=1, interval=0)


def render_deploy_styles() -> None:
    st.markdown(
        """
        <style>
        section.main > div.block-container { max-width: 900px; }
        .deploy-intro {
            max-width: 700px; color: #52606d; font-size: 1.04rem;
            margin: -0.25rem 0 1.4rem;
        }
        .deploy-readiness, .deploy-success, .deploy-almost {
            border-radius: 18px; padding: 1.25rem 1.35rem; margin: 0.75rem 0 1rem;
        }
        .deploy-readiness.ready {
            border: 1px solid #86c995; background: linear-gradient(135deg, #f0fdf4, #ffffff);
        }
        .deploy-readiness.blocked {
            border: 1px solid #f0b36a; background: linear-gradient(135deg, #fff7ed, #ffffff);
        }
        .deploy-card-kicker {
            color: #64748b; font-size: .76rem; font-weight: 750;
            letter-spacing: .06em; text-transform: uppercase; margin-bottom: .25rem;
        }
        .deploy-card-title { color: #0f172a; font-size: 1.28rem; font-weight: 780; }
        .deploy-card-copy { color: #475569; margin-top: .3rem; }
        .deploy-success {
            border: 1px solid #59a86b; background: linear-gradient(135deg, #ecfdf3, #ffffff);
            box-shadow: 0 14px 34px rgba(22, 101, 52, .10);
        }
        .deploy-success .deploy-card-title { font-size: 1.55rem; color: #14532d; }
        .deploy-success-url {
            display: block; color: #166534; font-weight: 700; overflow-wrap: anywhere;
            margin-top: .6rem;
        }
        .deploy-almost { border: 1px solid #93c5fd; background: #eff6ff; }
        .deploy-stage-list { display: grid; gap: .5rem; margin: .85rem 0 .5rem; }
        .deploy-stage {
            display: grid; grid-template-columns: 1.8rem 1fr auto; align-items: center;
            gap: .6rem; padding: .72rem .85rem; border-radius: 11px; background: #f8fafc;
        }
        .deploy-stage.active { background: #fff7ed; border: 1px solid #fed7aa; }
        .deploy-stage.complete { background: #f0fdf4; }
        .deploy-stage-icon { color: #94a3b8; font-weight: 800; }
        .deploy-stage.complete .deploy-stage-icon { color: #15803d; }
        .deploy-stage.active .deploy-stage-icon { color: #c2410c; }
        .deploy-stage-state { color: #64748b; font-size: .82rem; }
        .deploy-loading {
            width: .9rem; height: .9rem; display: inline-block; border-radius: 50%;
            border: 2px solid #fdba74; border-top-color: #c2410c;
            animation: deploy-spin .85s linear infinite;
        }
        @keyframes deploy-spin { to { transform: rotate(360deg); } }
        .st-key-deploy_publish button, .st-key-deploy_update button {
            min-height: 3.6rem; border-radius: 13px; font-size: 1.08rem; font-weight: 780;
            box-shadow: 0 10px 24px rgba(190, 24, 24, .16);
        }
        .deploy-estimate { color: #64748b; text-align: center; margin: .5rem 0 1rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_readiness_card(title: str, message: str, ready: bool) -> None:
    card_class = "ready" if ready else "blocked"
    kicker = "Publication check"
    st.markdown(
        f"""
        <div class="deploy-readiness {card_class}">
          <div class="deploy-card-kicker">{kicker}</div>
          <div class="deploy-card-title">{html.escape(title)}</div>
          <div class="deploy-card-copy">{html.escape(message)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def stage_markup(active_stage: str = "", completed: set[str] | None = None) -> str:
    completed = completed or set()
    rows: list[str] = []
    for index, label in enumerate(STAGES, start=1):
        if label in completed:
            css_class, icon, state = "complete", "✓", "Complete"
        elif label == active_stage:
            css_class = "active"
            icon = '<span class="deploy-loading" aria-label="In progress"></span>'
            state = "In progress"
        else:
            css_class, icon, state = "pending", str(index), "Waiting"
        rows.append(
            f'<div class="deploy-stage {css_class}">'
            f'<span class="deploy-stage-icon">{icon}</span>'
            f'<span>{html.escape(label)}</span>'
            f'<span class="deploy-stage-state">{state}</span></div>'
        )
    return '<div class="deploy-stage-list">' + "".join(rows) + "</div>"


def render_stages(active_stage: str = "", completed: set[str] | None = None, target=None) -> None:
    renderer = target or st
    renderer.markdown(stage_markup(active_stage, completed), unsafe_allow_html=True)


def render_copy_link(public_url: str) -> None:
    safe_url = json.dumps(public_url)
    components.html(
        f"""
        <button id="copy-link" style="width:100%;height:42px;border:1px solid #d1d5db;
          border-radius:8px;background:white;font:600 14px sans-serif;cursor:pointer;">
          Copy link
        </button>
        <script>
          const button = document.getElementById('copy-link');
          button.addEventListener('click', async () => {{
            await navigator.clipboard.writeText({safe_url});
            button.textContent = 'Copied';
            setTimeout(() => button.textContent = 'Copy link', 1600);
          }});
        </script>
        """,
        height=50,
    )


def render_success_card(public_url: str) -> None:
    st.markdown(
        f"""
        <div class="deploy-success">
          <div class="deploy-card-kicker">Website published</div>
          <div class="deploy-card-title">Your website is live</div>
          <div class="deploy-card-copy">The latest project is available at:</div>
          <span class="deploy-success-url">{html.escape(public_url)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _initialize_target_state(detected: DeploymentTarget, project: dict) -> None:
    default_repo_name = slugify_repo_name(project.get("name", "shade-study-app"))
    st.session_state.setdefault("deploy_repository", detected.repository or default_repo_name)
    st.session_state.setdefault("deploy_repository_url", detected.repository_url)
    st.session_state.setdefault("deploy_branch", detected.branch or "main")
    st.session_state.setdefault("deploy_mode", "existing" if detected.repository else "create")
    st.session_state.setdefault(
        "deploy_visibility", "public" if project.get("visibility") == "Public" else "private"
    )
    st.session_state.setdefault("deploy_public_url", detected.public_url)


def _current_target(detected: DeploymentTarget, project: dict) -> DeploymentTarget:
    mode_label = st.session_state.get("deploy_mode", "existing")
    mode = "create" if mode_label == "create" else "existing"
    repository = str(st.session_state.get("deploy_repository", "")).strip()
    repository_url = str(st.session_state.get("deploy_repository_url", "")).strip()
    if mode == "existing" and repository == detected.repository and detected.repository_url:
        repository_url = detected.repository_url
    if mode == "existing" and not repository_url:
        repository_url = github_repository_url(repository)
    public_url = normalize_public_url(st.session_state.get("deploy_public_url"))
    target = DeploymentTarget(
        repository=repository,
        repository_url=repository_url,
        branch=str(st.session_state.get("deploy_branch", "main")).strip() or "main",
        root=detected.root,
        mode=mode,
        visibility=str(st.session_state.get("deploy_visibility", "private")),
        public_url=public_url,
        detected=detected.detected and repository == detected.repository,
    )
    if not target.public_url and target.repository:
        metadata = cached_repository_metadata(
            target.repository,
            target.repository_url,
            target.branch,
            str(target.root or ""),
        )
        metadata_url = public_url_from_sources(project, target, metadata)
        if metadata_url:
            st.session_state["deploy_public_url"] = metadata_url
            target = replace(target, public_url=metadata_url)
        default_branch = (metadata.get("defaultBranchRef") or {}).get("name")
        if default_branch and not st.session_state.get("deploy_branch"):
            st.session_state["deploy_branch"] = default_branch
            target = replace(target, branch=default_branch)
    return target


def _store_result(target: DeploymentTarget, result: PublishResult) -> None:
    st.session_state[DEPLOYMENT_RESULT_KEY] = result
    st.session_state[DEPLOYMENT_TARGET_KEY] = deployment_target_key(target)


def _stored_result(target: DeploymentTarget) -> PublishResult | None:
    if st.session_state.get(DEPLOYMENT_TARGET_KEY) != deployment_target_key(target):
        return None
    result = st.session_state.get(DEPLOYMENT_RESULT_KEY)
    return result if isinstance(result, PublishResult) else None


def _run_publish(bundle_data: bytes, target: DeploymentTarget) -> PublishResult:
    stage_box = st.empty()
    completed: set[str] = set()

    def update(stage: str, _message: str) -> None:
        stage_index = STAGES.index(stage)
        completed.clear()
        completed.update(STAGES[:stage_index])
        render_stages(stage, completed, stage_box)

    result = publish_website(bundle_data, target, progress=update)
    if result.verified:
        render_stages("", set(STAGES), stage_box)
    elif result.needs_host_setup:
        render_stages("Verify website", set(STAGES[:3]), stage_box)
    _store_result(target, result)
    st.session_state[DEPLOYMENT_STAGE_KEY] = ""
    return result


def _render_technical_details(target: DeploymentTarget, result: PublishResult | None, bundle_data: bytes) -> None:
    with st.expander("View technical details", expanded=False):
        details = {
            "repository": target.repository,
            "repository_url": target.repository_url,
            "branch": target.branch,
            "mode": target.mode,
            "entrypoint": target.entrypoint,
            "public_url": target.public_url,
            "bundle_files": bundle_file_count(bundle_data),
        }
        if result:
            details.update(
                {
                    "commit": result.commit,
                    "changed": result.changed,
                    "verified": result.verified,
                }
            )
        st.json(details)
        if result and result.logs:
            st.markdown("##### Diagnostic output")
            st.code("\n\n".join(result.logs), language="text")


def _render_advanced_settings(
    project: dict,
    target: DeploymentTarget,
    bundle_data: bytes,
    bundle_name: str,
) -> None:
    expanded = bool(st.session_state.pop(DEPLOYMENT_ADVANCED_KEY, False))
    with st.expander("Advanced settings", expanded=expanded):
        st.caption("These settings are optional. Shade-GIS fills them in automatically when it can.")
        st.selectbox(
            "Publishing destination",
            options=["existing", "create"],
            format_func=lambda value: "Use an existing repository" if value == "existing" else "Create a repository",
            key="deploy_mode",
        )
        st.text_input("Repository", key="deploy_repository", help="GitHub OWNER/REPOSITORY")
        st.text_input(
            "Repository address",
            key="deploy_repository_url",
            help="Usually detected from this project's origin remote.",
        )
        st.text_input("Default branch", key="deploy_branch")
        st.selectbox(
            "Repository visibility",
            options=["private", "public"],
            key="deploy_visibility",
            disabled=st.session_state.get("deploy_mode") != "create",
        )
        st.text_input(
            "Hosted website address",
            key="deploy_public_url",
            placeholder="https://your-study.streamlit.app",
            help="Optional. Add an existing website address so Shade-GIS can verify it after publishing.",
        )
        st.markdown("##### Hosting")
        st.caption(
            f"The automatic package uses Streamlit Community Cloud and `{target.entrypoint}`. "
            "A connected site updates automatically when Shade-GIS publishes repository changes."
        )
        if target.mode == "create":
            st.link_button("Open repository setup", github_new_repo_url(project, target.repository))

        st.markdown("##### Manual fallback")
        st.caption("Use this only when automatic publishing is unavailable.")
        st.download_button(
            "Download website package",
            data=bundle_data,
            file_name=bundle_name,
            mime="application/zip",
            disabled=not bool(bundle_data),
            width="stretch",
        )
        if bundle_data and target.repository:
            st.code(
                deploy_launcher_script(
                    bundle_name,
                    target.repository,
                    target.branch,
                    target.mode,
                    target.visibility,
                ),
                language="powershell",
            )
        st.markdown("##### Package contents")
        st.dataframe(
            pd.DataFrame(BUNDLE_FILE_CATALOG, columns=["File", "Purpose"]),
            width="stretch",
            hide_index=True,
        )


def render_deploy_page() -> None:
    project = st.session_state["project"]
    stops = st.session_state["stops"]
    detected = detect_deployment_target()
    _initialize_target_state(detected, project)
    target = _current_target(detected, project)
    unpublished_notice = st.session_state.get(DEPLOYMENT_UNPUBLISHED_KEY)
    if unpublished_notice:
        st.session_state["deploy_public_url"] = ""
        target = replace(target, public_url="")

    render_deploy_styles()
    st.title("Publish website")
    st.markdown(
        f'<p class="deploy-intro">Turn <strong>{html.escape(project.get("name", "this shade study"))}</strong> '
        "into a public website. Shade-GIS prepares the files, publishes them, and checks the result.</p>",
        unsafe_allow_html=True,
    )

    bundle_data = b""
    bundle_error = ""
    if not stops.empty and target.repository:
        try:
            bundle_data = build_github_deploy_bundle(target.repository, target.mode)
        except Exception as exc:  # Builder validation errors are converted into one actionable readiness issue.
            bundle_error = str(exc).splitlines()[0] or "The project could not be prepared for publishing."
    readiness = deployment_readiness(stops.empty, target, bundle_error)
    existing_package = repository_has_published_app(target)
    if readiness.ready and existing_package:
        readiness = replace(
            readiness,
            message="Shade-GIS found the existing website and is ready to publish an update.",
        )
    bundle_name = f"{slugify_repo_name(target.repository.split('/')[-1] or project.get('name', 'shade-study'))}.zip"
    result = _stored_result(target)
    if result is None and readiness.ready and target.public_url:
        verified, verification_message = cached_website_check(target.public_url)
        if verified:
            result = PublishResult(
                True,
                public_url=target.public_url,
                verified=True,
                message="An existing published website was detected.",
                logs=[verification_message],
            )
            _store_result(target, result)

    if unpublished_notice:
        st.info(
            "The generated website files were removed. If the old address still appears, remove the app "
            "from the hosting workspace to finish unpublishing."
        )
        st.link_button("Finish unpublishing", STREAMLIT_WORKSPACE_URL, width="stretch")

    if result and result.verified and result.public_url:
        render_success_card(result.public_url)
        action_columns = st.columns(4, gap="small")
        with action_columns[0]:
            st.link_button("Open website", result.public_url, width="stretch")
        with action_columns[1]:
            render_copy_link(result.public_url)
        with action_columns[2]:
            publish_update = st.button("Publish update", width="stretch", key="deploy_update")
        with action_columns[3]:
            unpublish = st.button("Unpublish", width="stretch")

        if publish_update:
            with st.status("Publishing the latest update…", expanded=True) as status:
                updated_result = _run_publish(bundle_data, target)
                if updated_result.verified:
                    status.update(label="Website updated", state="complete", expanded=False)
                    st.rerun()
                else:
                    status.update(label="The update needs attention", state="error", expanded=True)
                    st.error(updated_result.message)

        if unpublish:
            st.session_state[DEPLOYMENT_UNPUBLISH_KEY] = True
        if st.session_state.get(DEPLOYMENT_UNPUBLISH_KEY):
            st.warning("Unpublishing removes the generated website files and may take the public site offline.")
            confirm_columns = st.columns(2)
            if confirm_columns[0].button("Keep website", width="stretch"):
                st.session_state.pop(DEPLOYMENT_UNPUBLISH_KEY, None)
                st.rerun()
            if confirm_columns[1].button("Confirm unpublish", type="primary", width="stretch"):
                with st.spinner("Unpublishing website…"):
                    unpublish_result = unpublish_website(target)
                _store_result(target, unpublish_result)
                st.session_state.pop(DEPLOYMENT_UNPUBLISH_KEY, None)
                if unpublish_result.success:
                    st.session_state[DEPLOYMENT_UNPUBLISHED_KEY] = {
                        "public_url": result.public_url,
                        "commit": unpublish_result.commit,
                    }
                    st.session_state["deploy_public_url"] = ""
                    st.session_state.pop(DEPLOYMENT_RESULT_KEY, None)
                    st.session_state.pop(DEPLOYMENT_TARGET_KEY, None)
                    st.rerun()
                else:
                    st.error(unpublish_result.message)
        _render_technical_details(target, result, bundle_data)
        _render_advanced_settings(project, target, bundle_data, bundle_name)
        return

    render_readiness_card(readiness.title, readiness.message, readiness.ready)
    if not readiness.ready:
        if readiness.action == "data":
            st.button(readiness.action_label, type="primary", width="stretch", on_click=set_page, args=("Data",))
        else:
            if st.button(readiness.action_label, type="primary", width="stretch"):
                st.session_state[DEPLOYMENT_ADVANCED_KEY] = True
                st.rerun()
    else:
        render_stages()
        with st.container(key="deploy_publish"):
            publish_clicked = st.button("Publish app", type="primary", width="stretch")
        st.markdown('<div class="deploy-estimate">This usually takes 1–3 minutes.</div>', unsafe_allow_html=True)
        if publish_clicked:
            st.session_state.pop(DEPLOYMENT_UNPUBLISHED_KEY, None)
            with st.status("Publishing your website…", expanded=True) as status:
                result = _run_publish(bundle_data, target)
                if result.verified:
                    status.update(label="Website published", state="complete", expanded=False)
                    st.rerun()
                elif result.needs_host_setup:
                    status.update(label="One quick setup remains", state="running", expanded=True)
                else:
                    status.update(label="Publishing stopped", state="error", expanded=True)
                    st.error(result.message)

    result = _stored_result(target)
    if result and result.needs_host_setup:
        render_stages("Verify website", set(STAGES[:3]))
        st.markdown(
            """
            <div class="deploy-almost">
              <div class="deploy-card-title">One-time website setup</div>
              <div class="deploy-card-copy">Your website files are published. Connect them to the website host once, then paste the website link below.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.link_button("Finish website setup", STREAMLIT_WORKSPACE_URL, type="primary", width="stretch")
        website_url = st.text_input(
            "Website link",
            value=st.session_state.get("deploy_public_url", ""),
            placeholder="https://your-study.streamlit.app",
        )
        if st.button("Verify website", width="stretch"):
            normalized_url = normalize_public_url(website_url)
            with st.spinner("Checking the website…"):
                verified, message = verify_website(normalized_url)
            if verified:
                st.session_state["deploy_public_url"] = normalized_url
                target = replace(target, public_url=normalized_url)
                result.public_url = normalized_url
                result.verified = True
                result.needs_host_setup = False
                result.message = "The website is published and responding."
                result.logs.append(message)
                _store_result(target, result)
                st.rerun()
            else:
                st.error("The website is not reachable yet. Wait a moment, then verify it again.")

    if result:
        _render_technical_details(target, result, bundle_data)
    _render_advanced_settings(project, target, bundle_data, bundle_name)
