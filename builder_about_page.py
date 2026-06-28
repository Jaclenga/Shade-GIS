from typing import Any

import pandas as pd
import streamlit as st


def render_builder_about_page(
    *,
    project: dict[str, Any],
    methodology: dict[str, Any],
    taxonomy: list[dict[str, Any]],
    import_log: list[dict[str, Any]],
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
        taxonomy_df = pd.DataFrame(taxonomy)
        visible_cols = [column for column in ["sort_order", "name", "description", "color"] if column in taxonomy_df.columns]
        st.dataframe(taxonomy_df.loc[:, visible_cols], use_container_width=True, hide_index=True)

    st.markdown("## Data Sources")
    st.markdown(methodology.get("data_sources", ""))
    if project.get("source_name") or project.get("source_url") or project.get("source_license"):
        st.caption(
            f"Primary source: {project.get('source_name', 'Not specified')} | "
            f"License: {project.get('source_license', 'Not specified')} | "
            f"URL: {project.get('source_url', 'Not specified')}"
        )

    st.markdown("## Contributors")
    st.markdown(methodology.get("contributors", ""))

    st.markdown("## Citation")
    st.markdown(methodology.get("citation", ""))

    st.markdown("## Known Limitations")
    st.markdown(methodology.get("limitations", ""))

    st.markdown("## Release History")
    st.markdown(methodology.get("release_history", ""))

    if import_log:
        st.markdown("## Import Log")
        st.dataframe(pd.DataFrame(import_log), use_container_width=True, hide_index=True)
