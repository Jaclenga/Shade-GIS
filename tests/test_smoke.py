from __future__ import annotations

from pathlib import Path

import pandas as pd


def test_core_modules_compile_without_bytecode_writes():
    for filename in [
        "builder_app.py",
        "platform_store.py",
        "app.py",
        "published_app.py",
        "public_voting.py",
        "shade_gis/shade_dimensions.py",
        "shade_gis/pages/preview_page.py",
        "shade_gis/pages/agreement_page.py",
        "shade_gis/pages/voting_page.py",
    ]:
        source = Path(filename).read_text(encoding="utf-8")
        compile(source, filename, "exec")


def test_deploy_source_comes_from_public_app_module():
    import builder_app

    assert builder_app.published_app_source() == Path("published_app.py").read_text(encoding="utf-8")


def test_builder_and_published_runtime_disable_arrow_string_inference():
    import builder_app  # noqa: F401 - importing applies the runtime guard

    for filename in ["builder_app.py", "published_app.py"]:
        source = Path(filename).read_text(encoding="utf-8")
        assert 'pd.options.mode.string_storage = "python"' in source

    inferred = pd.DataFrame({"value": [""]})
    assert pd.options.mode.string_storage == "python"
    assert type(inferred["value"].array).__name__ == "StringArray"


def test_app_py_is_builder_entrypoint():
    import app

    assert app.main.__module__ == "builder_app"


def test_ui_smoke_can_disable_expensive_automatic_persistence(monkeypatch):
    import builder_app

    monkeypatch.setenv("SHADE_GIS_TEST_DISABLE_AUTO_SAVE", "1")
    monkeypatch.setattr(builder_app, "st", type("FakeStreamlit", (), {"session_state": {"active_project_id": "ui-test"}}))
    monkeypatch.setattr(
        builder_app,
        "save_project_bundle",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("auto-save should be skipped")),
    )

    builder_app.save_active_project_to_store()


def test_ui_seed_limit_is_test_only(monkeypatch, taxonomy, project):
    import builder_app

    full_seed = builder_app.load_seed_dataset(taxonomy, project)
    monkeypatch.setenv("SHADE_GIS_TEST_MAX_SEED_ROWS", "25")
    monkeypatch.setattr(builder_app, "load_seed_dataset", lambda *args: full_seed)
    captured = {}
    monkeypatch.setattr(
        builder_app,
        "create_project",
        lambda project, taxonomy, methodology, visualization, stops, import_log: captured.update(
            {"stops": stops, "rows": import_log[0]["rows"]}
        )
        or "ui-seed",
    )

    assert builder_app.create_seed_project() == "ui-seed"
    assert len(captured["stops"]) == 25
    assert captured["rows"] == 25


def test_summary_metrics_only_render_in_analytics():
    published_source = Path("published_app.py").read_text(encoding="utf-8")
    preview_source = Path("shade_gis/pages/preview_page.py").read_text(encoding="utf-8")

    assert published_source.count("render_metric_cards(df)") == 1
    assert "published_app.render_metric_cards(visible_stops)" not in preview_source


def test_public_taxonomy_table_does_not_expose_sort_order():
    source = Path("published_app.py").read_text(encoding="utf-8")

    assert 'st.dataframe(taxonomy_display_table(taxonomy)' in source
    assert 'drop(columns=["sort_order"]' in source


def test_builder_docs_taxonomy_table_does_not_expose_sort_order():
    source = Path("builder_about_page.py").read_text(encoding="utf-8")

    assert "st.dataframe(builder_taxonomy_display_table(taxonomy)" in source
    assert '["sort_order", "name", "description", "color"]' not in source


def test_preview_uses_the_shared_stop_and_voting_panel():
    preview_source = Path("shade_gis/pages/preview_page.py").read_text(encoding="utf-8")

    assert "published_app.render_stop_and_voting_panel(" in preview_source


def test_agreement_workflow_is_embedded_in_preview_analytics_not_top_level_navigation():
    builder_source = Path("builder_app.py").read_text(encoding="utf-8")
    preview_source = Path("shade_gis/pages/preview_page.py").read_text(encoding="utf-8")

    assert 'data_pages = [("Overview", "Data"), ("Labels", "Labels"), ("Voting", "Voting")]' in builder_source
    assert '(cols[2], "Build", build_pages)' in builder_source
    assert 'elif page == "Agreement"' not in builder_source
    assert 'agreement_enabled = "Agreement metrics" in selected_sections' in preview_source
    assert "render_agreement_analytics_section(" in preview_source
    assert "include_agreement=False" in preview_source


def test_builder_has_project_home_and_clickable_brand_navigation():
    source = Path("builder_app.py").read_text(encoding="utf-8")

    assert 'st.title("Shade-GIS Projects")' not in source
    assert 'st.button("Shade-GIS", key="nav_home", on_click=request_main_menu)' in source
    assert '@st.dialog("Open project?", on_dismiss=clear_pending_project_open)' in source
    assert '@st.dialog("Return to main menu?", on_dismiss=clear_pending_main_menu)' in source
    assert 'with st.container(key="home_page")' in source
    assert 'f"Open project: {name}"' in source
    assert "max-width: 1080px" in source
    assert 'class="home-summary"' not in source
    assert 'div[class*="st-key-project_card_"]:hover' in source
    assert 'div[class*="st-key-project_card_"] [data-testid="stButton"] {' in source
    assert ".st-key-nav_home button:hover" in source
    assert ".st-key-nav_home button:active" in source
    assert ".st-key-nav_home button:focus-visible" in source


def test_data_page_uses_progress_dashboard_and_collapsed_dataset_preview():
    source = Path("shade_gis/pages/data_page.py").read_text(encoding="utf-8")

    assert 'st.subheader("Dataset Status")' in source
    assert 'st.markdown("#### Work Queue")' in source
    assert 'st.expander("Dataset Preview", expanded=False)' in source
    assert "st.dataframe(visible_stops" in source
    assert "st.dataframe(stops," not in source
    assert 'st.subheader("Dataset Health")' not in source


def test_preview_exports_use_catalog_and_provenance_sections():
    source = Path("shade_gis/pages/preview_page.py").read_text(encoding="utf-8")

    assert "published_app.render_export_files(" in source
    assert "published_app.render_dataset_provenance(" in source
    assert 'st.dataframe(pd.DataFrame(st.session_state["import_log"])' not in source
    assert '"Download stops CSV"' not in source
