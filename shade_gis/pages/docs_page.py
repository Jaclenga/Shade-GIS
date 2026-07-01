from builder_app import *

def render_methodology_page() -> None:
    st.title("Project Documentation")
    methodology = st.session_state["methodology"]

    edit, preview = st.columns([1, 1])
    with edit:
        methodology["title"] = st.text_input("About page title", methodology["title"])
        methodology["summary"] = st.text_area("Summary", methodology["summary"], height=85)
        methodology["purpose"] = st.text_area("Rationale", methodology["purpose"], height=130)
        methodology["shade_method"] = st.text_area("Shade assessment method", methodology["shade_method"], height=130)
        methodology["data_sources"] = st.text_area("Data sources", methodology["data_sources"], height=135)
        methodology["contributors"] = st.text_area("Contributors", methodology["contributors"], height=85)
        methodology["limitations"] = st.text_area("Known limitations", methodology["limitations"], height=110)
        methodology.setdefault("bibliography", DEFAULT_METHODOLOGY["bibliography"])
        methodology["bibliography"] = st.text_area(
            "Bibliography",
            methodology["bibliography"],
            height=170,
            help=(
                "Use the same grouped APA format as citations: unindented lines are group labels, "
                "and indented lines render as hanging-indent bibliography entries."
            ),
            placeholder=(
                "Works referenced:\n"
                "    Author, A. A., & Author, B. B. (Year). Title of article. Title of Journal, volume(issue), page range. https://doi.org/xxxxx\n"
                "    Author or Organization. (Year). Title of report. Publisher. URL\n\n"
                "Data and software:\n"
                "    Author or Organization. (Year). Title of software or dataset (Version number) [Software or data set]. Publisher. URL"
            ),
        )
        methodology["release_history"] = st.text_area("Release history", methodology["release_history"], height=95)
        methodology["citation"] = st.text_area(
            "Citation",
            methodology["citation"],
            height=150,
            help=(
                "Use unindented lines as citation group labels. Put each citation on an indented line "
                "under its group to render a hanging indent on the public methodology page. The examples use APA style."
            ),
            placeholder=(
                "Transit data:\n"
                "    Author or Organization. (Year). Title of dataset (Version number) [Data set]. Publisher. URL\n\n"
                "Methods and references:\n"
                "    Author, A. A., & Author, B. B. (Year). Title of article. Title of Journal, volume(issue), page range. https://doi.org/xxxxx\n"
                "    Author or Organization. (Year). Title of report. Publisher. URL"
            ),
        )
    with preview:
        with st.container(height=METHODS_PREVIEW_HEIGHT, border=False):
            render_builder_about_page(
                project=st.session_state["project"],
                methodology=methodology,
                taxonomy=st.session_state["taxonomy"],
                import_log=st.session_state["import_log"],
                priority_formula=priority_formula_for_about(st.session_state["visualization"]),
            )



