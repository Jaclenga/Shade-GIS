from __future__ import annotations

from pathlib import Path


def test_core_modules_compile_without_bytecode_writes():
    for filename in [
        "builder_app.py",
        "platform_store.py",
        "app.py",
        "published_app.py",
        "public_voting.py",
        "shade_gis/shade_dimensions.py",
        "shade_gis/pages/preview_page.py",
        "shade_gis/pages/voting_page.py",
    ]:
        source = Path(filename).read_text(encoding="utf-8")
        compile(source, filename, "exec")


def test_deploy_source_comes_from_public_app_module():
    import builder_app

    assert builder_app.published_app_source() == Path("published_app.py").read_text(encoding="utf-8")


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


def test_summary_metrics_only_render_in_analytics():
    published_source = Path("published_app.py").read_text(encoding="utf-8")
    preview_source = Path("shade_gis/pages/preview_page.py").read_text(encoding="utf-8")

    assert published_source.count("render_metric_cards(df)") == 1
    assert "published_app.render_metric_cards(visible_stops)" not in preview_source


def test_preview_uses_the_shared_stop_and_voting_panel():
    preview_source = Path("shade_gis/pages/preview_page.py").read_text(encoding="utf-8")

    assert "published_app.render_stop_and_voting_panel(" in preview_source
