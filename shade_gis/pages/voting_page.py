from builder_app import *
from public_voting import (
    PUBLIC_COVERAGE_OPTIONS,
    PUBLIC_SOURCE_DISPLAY_LABELS,
    PUBLIC_SOURCE_OPTIONS,
    coverage_taxonomy_help,
    normalize_voting_config,
    source_taxonomy_help,
)


def render_voting_controls(
    visualization: dict[str, Any],
    taxonomy: list[dict[str, Any]],
) -> dict[str, Any]:
    voting = normalize_voting_config(visualization.get("voting"), taxonomy)
    project_key = str(st.session_state.get("active_project_id", "project"))
    key_prefix = f"voting_{project_key}"

    voting["enabled"] = st.checkbox(
        "Let deployed-app visitors vote on stop coverage",
        value=voting["enabled"],
        key=f"{key_prefix}_enabled",
        help="Adds the voting interface to the selected-stop panel in Preview and the generated public app.",
    )
    voting["title"] = st.text_input(
        "Voting heading",
        value=str(voting["title"]),
        key=f"{key_prefix}_title",
    )
    voting["description"] = st.text_area(
        "Voting instructions",
        value=str(voting["description"]),
        key=f"{key_prefix}_description",
        height=110,
    )
    voting["question"] = st.text_input(
        "Coverage question",
        value=str(voting["question"]),
        key=f"{key_prefix}_question",
    )

    voting["options"] = st.multiselect(
        "Coverage choices",
        PUBLIC_COVERAGE_OPTIONS,
        default=[option for option in voting["options"] if option in PUBLIC_COVERAGE_OPTIONS],
        key=f"{key_prefix}_options",
        help="Coverage and shade source are separate dimensions. Source labels never appear in this control.",
    )
    st.caption("Shade sources are recorded separately from coverage and cannot be used as coverage choices.")
    if not voting["options"]:
        st.warning("Select at least one coverage choice before enabling voting.")
    voting["source_question"] = st.text_input(
        "Shade source question",
        value=str(voting["source_question"]),
        key=f"{key_prefix}_source_question",
        help="Visitors can select multiple source checkboxes independently from coverage.",
    )

    voting["submit_label"] = st.text_input(
        "Submit button label",
        value=str(voting["submit_label"]),
        key=f"{key_prefix}_submit_label",
    )
    voting["success_message"] = st.text_input(
        "Confirmation message",
        value=str(voting["success_message"]),
        key=f"{key_prefix}_success_message",
    )
    voting["allow_vote_changes"] = st.checkbox(
        "Allow a browser session to change its vote",
        value=voting["allow_vote_changes"],
        key=f"{key_prefix}_allow_changes",
    )
    voting["show_results"] = st.checkbox(
        "Show community vote totals and result",
        value=voting["show_results"],
        key=f"{key_prefix}_show_results",
    )
    if voting["show_results"]:
        voting["results_label"] = st.text_input(
            "Result label",
            value=str(voting["results_label"]),
            key=f"{key_prefix}_results_label",
        )
        voting["minimum_votes_for_result"] = int(
            st.number_input(
                "Votes required before reporting a result",
                min_value=1,
                max_value=100,
                value=int(voting["minimum_votes_for_result"]),
                step=1,
                key=f"{key_prefix}_minimum_votes",
                help="A unique leading choice is reported after this many votes; tied leaders are reported as tied.",
            )
        )

    visualization["voting"] = voting
    return voting


def render_voting_preview(
    voting: dict[str, Any],
    taxonomy: list[dict[str, Any]] | None = None,
) -> None:
    st.subheader("Deployed Interface Preview")
    if not voting.get("enabled", False):
        st.info("Voting is currently hidden in the deployed app. Enable it to publish this interface.")
    with st.container(border=True):
        st.markdown(f"#### {voting['title']}")
        if voting.get("description"):
            st.markdown(str(voting["description"]))
        options = voting.get("options", [])
        if options:
            st.markdown(
                f"**{voting['question']}**",
                help=coverage_taxonomy_help(options, taxonomy),
            )
            st.radio(
                str(voting["question"]),
                options,
                disabled=True,
                key="voting_interface_preview_choice",
                label_visibility="collapsed",
            )
            st.divider()
            st.markdown(f"**{voting['source_question']}**", help=source_taxonomy_help())
            for source in PUBLIC_SOURCE_OPTIONS:
                st.checkbox(
                    PUBLIC_SOURCE_DISPLAY_LABELS[source],
                    disabled=True,
                    key=f"voting_interface_preview_source_{source.lower()}",
                )
            st.button(
                str(voting["submit_label"]),
                disabled=True,
                key="voting_interface_preview_submit",
                width="stretch",
            )
        else:
            st.warning("Choose at least one coverage option to complete the interface.")
        if voting.get("show_results", True):
            st.markdown(f"**{voting['results_label']}: More votes needed**")
            st.caption("Vote totals appear here in the deployed app.")


def render_voting_page() -> None:
    st.title("Public Voting")
    st.markdown(
        "Configure whether visitors to the generated study app can crowdsource shade coverage and sources, "
        "what they see, and when a community result is reported."
    )

    visualization = st.session_state["visualization"]
    taxonomy = st.session_state["taxonomy"]
    controls, preview = st.columns([0.95, 1.05], gap="large")

    with controls:
        st.subheader("Voting Settings")
        voting = render_voting_controls(visualization, taxonomy)
    with preview:
        render_voting_preview(voting, taxonomy)

    st.divider()
    st.subheader("Deployment Storage")
    st.markdown(
        "Generated apps use a local SQLite vote database for development. For durable hosted voting, "
        "set `SHADE_GIS_VOTE_DATABASE_URL` as a PostgreSQL secret in the deployment environment. "
        "Streamlit Community Cloud local files are ephemeral and may be lost when the app restarts."
    )
