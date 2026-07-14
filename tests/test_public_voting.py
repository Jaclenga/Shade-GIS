from __future__ import annotations

import sqlite3

import pandas as pd

import published_app
from public_voting import (
    PUBLIC_SOURCE_DEFINITIONS,
    community_result,
    get_existing_vote,
    get_existing_vote_details,
    get_vote_counts,
    normalize_voting_config,
    save_vote,
    source_taxonomy_help,
)


def test_shared_stop_panel_renders_voting_for_the_selected_stop(monkeypatch):
    selected_stop = {"stop_id": "1001", "stop_name": "Main Street"}
    captured = {}

    class FakeTab:
        def __init__(self, open_state):
            self.open = open_state

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakeStreamlit:
        @staticmethod
        def tabs(labels, **kwargs):
            captured["tabs"] = {"labels": labels, **kwargs}
            return [FakeTab(True), FakeTab(False)]

    monkeypatch.setattr(published_app, "st", FakeStreamlit)

    monkeypatch.setattr(
        published_app,
        "render_stop_detail_workflow",
        lambda stops, visualization, state_prefix, *, show_details, show_selection_summary: (
            captured.update(
                show_details=show_details,
                show_selection_summary=show_selection_summary,
            )
            or selected_stop
        ),
    )

    def capture_voting(stop, study_id, taxonomy, voting, *, app_dir):
        captured.update(
            stop=stop,
            study_id=study_id,
            taxonomy=taxonomy,
            voting=voting,
            app_dir=app_dir,
        )

    monkeypatch.setattr(published_app, "render_voting_panel", capture_voting)
    voting = {"enabled": True}
    taxonomy = [{"name": "No Shade"}]

    result = published_app.render_stop_and_voting_panel(
        pd.DataFrame([selected_stop]),
        {},
        "preview",
        "study-a",
        taxonomy,
        voting,
        app_dir=published_app.APP_DIR,
    )

    assert result == selected_stop
    assert captured["tabs"] == {
        "labels": ["Voting", "Stop details"],
        "default": "Voting",
        "key": "preview_panel_tabs",
        "on_change": "rerun",
    }
    assert captured["show_details"] is False
    assert captured["show_selection_summary"] is False
    assert {key: captured[key] for key in ["stop", "study_id", "taxonomy", "voting", "app_dir"]} == {
        "stop": selected_stop,
        "study_id": "study-a",
        "taxonomy": taxonomy,
        "voting": normalize_voting_config(voting, taxonomy),
        "app_dir": published_app.APP_DIR,
    }


def test_voting_config_uses_taxonomy_and_preserves_admin_copy(taxonomy):
    config = normalize_voting_config(
        {
            "enabled": True,
            "title": "Rate this waiting area",
            "options": ["No Shade", "Missing category", "Limited"],
            "minimum_votes_for_result": 500,
        },
        taxonomy,
    )

    assert config["enabled"] is True
    assert config["title"] == "Rate this waiting area"
    assert config["options"] == ["No Shade", "Limited Shade"]
    assert config["minimum_votes_for_result"] == 100


def test_voting_coverage_choices_never_include_source_or_review_categories():
    mixed_taxonomy = [
        {"name": "Limited Natural Shade"},
        {"name": "Intentional Built Shade"},
        {"name": "Needs Review"},
    ]

    config = normalize_voting_config(None, mixed_taxonomy)

    assert config["options"] == ["No Shade", "Limited Shade", "Significant Shade"]


def test_source_heading_tooltip_explains_all_source_categories():
    all_sources_help = source_taxonomy_help()
    for source, definition in PUBLIC_SOURCE_DEFINITIONS.items():
        assert f"**{source}:** {definition}" in all_sources_help


def test_sqlite_vote_store_upserts_one_vote_per_browser_session(db_path):
    assert save_vote(
        "study-a",
        "1001",
        "browser-a",
        "No Shade",
        shade_sources=["Natural"],
        database_url="",
        sqlite_path=db_path,
    )
    assert save_vote(
        "study-a",
        "1001",
        "browser-b",
        "Limited",
        shade_sources=["Natural", "Incidental Built"],
        database_url="",
        sqlite_path=db_path,
    )
    assert save_vote(
        "study-a",
        "1001",
        "browser-a",
        "Significant",
        shade_sources=["Constructed"],
        database_url="",
        sqlite_path=db_path,
    )

    assert get_existing_vote(
        "study-a", "1001", "browser-a", database_url="", sqlite_path=db_path
    ) == "Significant Shade"
    assert get_existing_vote_details(
        "study-a", "1001", "browser-a", database_url="", sqlite_path=db_path
    ) == {"coverage_status": "Significant Shade", "shade_sources": ["Purpose-built"]}
    assert get_existing_vote_details(
        "study-a", "1001", "browser-b", database_url="", sqlite_path=db_path
    ) == {"coverage_status": "Limited Shade", "shade_sources": ["Natural", "Incidental"]}
    assert get_vote_counts(
        "study-a",
        "1001",
        ["No Shade", "Limited Shade", "Significant Shade"],
        database_url="",
        sqlite_path=db_path,
    ) == {"No Shade": 0, "Limited Shade": 1, "Significant Shade": 1}


def test_no_shade_vote_clears_sources_and_migrates_an_existing_sqlite_store(db_path):
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE shade_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            study_id TEXT NOT NULL,
            stop_id TEXT NOT NULL,
            voter_id TEXT NOT NULL,
            coverage_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (study_id, stop_id, voter_id)
        )
        """
    )
    connection.commit()
    connection.close()

    assert save_vote(
        "study-a",
        "1001",
        "browser-a",
        "No Shade",
        shade_sources=["Natural", "Purpose-built"],
        database_url="",
        sqlite_path=db_path,
    )

    assert get_existing_vote_details(
        "study-a", "1001", "browser-a", database_url="", sqlite_path=db_path
    ) == {"coverage_status": "No Shade", "shade_sources": []}


def test_vote_changes_can_be_disabled_and_studies_are_isolated(db_path):
    assert save_vote(
        "study-a",
        "1001",
        "browser-a",
        "No Shade",
        allow_vote_changes=False,
        database_url="",
        sqlite_path=db_path,
    )
    assert not save_vote(
        "study-a",
        "1001",
        "browser-a",
        "Limited",
        allow_vote_changes=False,
        database_url="",
        sqlite_path=db_path,
    )
    assert save_vote(
        "study-b",
        "1001",
        "browser-a",
        "Limited",
        allow_vote_changes=False,
        database_url="",
        sqlite_path=db_path,
    )

    assert get_existing_vote(
        "study-a", "1001", "browser-a", database_url="", sqlite_path=db_path
    ) == "No Shade"
    assert get_vote_counts(
        "study-b", "1001", ["No Shade", "Limited Shade"], database_url="", sqlite_path=db_path
    ) == {"No Shade": 0, "Limited Shade": 1}


def test_community_result_requires_threshold_and_unique_leader():
    assert community_result({"No Shade": 2, "Limited Shade": 1}, 5)["status"] == "pending"
    assert community_result({"No Shade": 3, "Limited Shade": 3}, 5)["status"] == "tied"
    result = community_result({"No Shade": 4, "Limited Shade": 2}, 5)
    assert result["status"] == "consensus"
    assert result["label"] == "No Shade"
    assert result["total"] == 6
