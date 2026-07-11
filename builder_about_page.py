import html
from typing import Any

import pandas as pd
import streamlit as st


def builder_taxonomy_display_table(taxonomy: list[dict[str, Any]]) -> pd.DataFrame:
    display = pd.DataFrame(taxonomy)
    if display.empty:
        return display
    if "sort_order" in display.columns:
        display = display.sort_values("sort_order", kind="stable")
    visible_cols = [column for column in ["name", "description", "color"] if column in display.columns]
    return display.loc[:, visible_cols].reset_index(drop=True)


def render_grouped_citations(citation_text: str) -> None:
    lines = str(citation_text or "").splitlines()
    if not any(line.strip() for line in lines):
        return

    st.markdown(
        """
        <style>
        .citation-group {font-weight: 700; margin: 0.85rem 0 0.25rem;}
        .citation-entry {
            margin: 0.25rem 0 0.45rem 1.5rem;
            padding-left: 1.5rem;
            text-indent: -1.5rem;
            line-height: 1.45;
        }
        .citation-gap {height: 0.35rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )

    html_parts = []
    for index, line in enumerate(lines):
        if not line.strip():
            html_parts.append("<div class='citation-gap'></div>")
            continue
        stripped = line.strip()
        is_indented = line.startswith((" ", "\t")) or stripped.startswith(("- ", "* "))
        next_content = next((candidate for candidate in lines[index + 1 :] if candidate.strip()), "")
        next_is_indented = next_content.startswith((" ", "\t")) or next_content.strip().startswith(("- ", "* "))
        if is_indented:
            text = stripped[2:].strip() if stripped.startswith(("- ", "* ")) else stripped
            html_parts.append(f"<div class='citation-entry'>{html.escape(text)}</div>")
        elif stripped.endswith(":") or next_is_indented:
            html_parts.append(f"<div class='citation-group'>{html.escape(stripped)}</div>")
        else:
            html_parts.append(f"<div class='citation-entry'>{html.escape(stripped)}</div>")

    st.markdown("".join(html_parts), unsafe_allow_html=True)


def render_builder_about_page(
    *,
    project: dict[str, Any],
    methodology: dict[str, Any],
    taxonomy: list[dict[str, Any]],
    import_log: list[dict[str, Any]],
    priority_formula: dict[str, Any] | None = None,
) -> None:
    st.title(methodology.get("title") or project.get("name") or "Bus Stop Shade Study")
    st.markdown(f"### {methodology.get('summary', '')}")
    st.caption(
        f"{project.get('agency', 'Transit agency')} | {project.get('region', 'Region')} | "
        f"dataset v{project.get('dataset_version', 'draft')} | methodology v{project.get('methodology_version', 'draft')}"
    )

    st.markdown("## Rationale")
    st.markdown(methodology.get("purpose", ""))

    st.markdown("## Shade Assessment Method")
    st.markdown(methodology.get("shade_method", ""))

    if taxonomy:
        st.markdown("## Shade Taxonomy")
        st.dataframe(builder_taxonomy_display_table(taxonomy), width="stretch", hide_index=True)

    st.markdown("## Data Sources")
    st.markdown(methodology.get("data_sources", ""))
    if project.get("source_name") or project.get("source_url") or project.get("source_license"):
        st.caption(
            f"Primary source: {project.get('source_name', 'Not specified')} | "
            f"License: {project.get('source_license', 'Not specified')} | "
            f"URL: {project.get('source_url', 'Not specified')}"
        )

    if priority_formula:
        st.markdown("## Priority Formula")
        st.markdown(priority_formula.get("summary", ""))
        weights = priority_formula.get("weights", [])
        if weights:
            st.dataframe(pd.DataFrame(weights), width="stretch", hide_index=True)

    st.markdown("## Contributors")
    st.markdown(methodology.get("contributors", ""))

    st.markdown("## Known Limitations")
    st.markdown(methodology.get("limitations", ""))

    bibliography = methodology.get("bibliography", "")
    if str(bibliography or "").strip():
        st.markdown("## Bibliography")
        render_grouped_citations(bibliography)

    st.markdown("## Release History")
    st.markdown(methodology.get("release_history", ""))

    if import_log:
        st.markdown("## Import Log")
        st.dataframe(pd.DataFrame(import_log), width="stretch", hide_index=True)

    st.markdown("## Citation")
    render_grouped_citations(methodology.get("citation", ""))

