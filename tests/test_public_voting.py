from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import published_app
from public_voting import (
    DEFAULT_VOTING_CONFIG,
    DEFAULT_VOTING_DESCRIPTION,
    PUBLIC_COVERAGE_DEFINITIONS,
    PUBLIC_SOURCE_DISPLAY_LABELS,
    PUBLIC_SOURCE_DEFINITIONS,
    VoteRateLimitError,
    community_result,
    coverage_taxonomy_help,
    get_existing_vote,
    get_existing_vote_details,
    get_vote_counts,
    normalize_voting_config,
    normalize_vote_sources,
    privacy_preserving_voter_id,
    save_vote,
    source_taxonomy_help,
)


def test_default_source_question_uses_plain_language_checkbox_copy():
    assert DEFAULT_VOTING_CONFIG["source_question"] == (
        "What creates the shade at this stop? Select all that apply."
    )
    assert PUBLIC_SOURCE_DISPLAY_LABELS == {
        "Natural": "Trees / vegetation",
        "Purpose-built": "Bus shelter / shade structure",
        "Incidental": "Nearby buildings or other structures",
    }
    assert normalize_vote_sources(list(PUBLIC_SOURCE_DISPLAY_LABELS.values())) == [
        "Natural",
        "Purpose-built",
        "Incidental",
    ]


def test_default_voting_instructions_add_waiting_area_guidance_without_overwriting_custom_copy():
    assert DEFAULT_VOTING_CONFIG["description"] == DEFAULT_VOTING_DESCRIPTION
    assert DEFAULT_VOTING_DESCRIPTION == (
        "Choose the shade coverage that best matches this stop. "
        "Answer based on where a passenger would normally wait for the bus."
    )
    assert normalize_voting_config(
        {
            "description": (
                "Use your current observation of the passenger waiting area. "
                "Choose the shade coverage that best matches this stop."
            )
        }
    )["description"] == DEFAULT_VOTING_CONFIG["description"]
    assert normalize_voting_config(
        {
            "description": (
                "Use your current observation of the passenger waiting area. "
                "Choose the shade coverage that best matches this stop. "
                "Answer based on where a passenger would normally wait for the bus right now."
            )
        }
    )["description"] == DEFAULT_VOTING_CONFIG["description"]
    assert normalize_voting_config(
        {"description": "Use the locally approved observation protocol."}
    )["description"] == "Use the locally approved observation protocol."


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
    assert config["abuse_protection_enabled"] is True
    assert config["vote_cooldown_seconds"] == 5
    assert config["max_new_votes_per_hour"] == 20


def test_voting_config_clamps_robustness_limits():
    config = normalize_voting_config(
        {
            "abuse_protection_enabled": True,
            "vote_cooldown_seconds": 500,
            "max_new_votes_per_hour": 0,
        }
    )

    assert config["vote_cooldown_seconds"] == 60
    assert config["max_new_votes_per_hour"] == 1


def test_privacy_preserving_voter_id_is_stable_without_storing_raw_signals():
    headers = {
        "X-Forwarded-For": "203.0.113.42, 10.0.0.2",
        "User-Agent": "ExampleBrowser/1.0",
        "Accept-Language": "en-US",
    }

    first = privacy_preserving_voter_id(headers, "server-secret", "session-a")
    second = privacy_preserving_voter_id(headers, "server-secret", "session-b")
    other_network = privacy_preserving_voter_id(
        {**headers, "X-Forwarded-For": "203.0.113.43"},
        "server-secret",
        "session-c",
    )

    assert first == second
    assert first.startswith("visitor_")
    assert "203.0.113.42" not in first
    assert "ExampleBrowser" not in first
    assert other_network != first
    assert privacy_preserving_voter_id(
        {"X-Forwarded-For": "not-an-ip", "User-Agent": "ExampleBrowser/1.0"},
        "server-secret",
        "session-fallback",
    ) == "session-fallback"


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


def test_coverage_question_tooltip_explains_configured_taxonomy_choices():
    taxonomy = [
        {"name": "No Shade", "description": "Configured no-shade definition."},
        {"name": "Limited Shade", "description": "Configured limited-shade definition."},
        {"name": "Significant Shade", "description": "Configured significant-shade definition."},
        {"name": "Needs Review", "description": "Not a public coverage choice."},
    ]

    guide = coverage_taxonomy_help(list(PUBLIC_COVERAGE_DEFINITIONS), taxonomy)

    for choice in PUBLIC_COVERAGE_DEFINITIONS:
        slug = choice.lower().replace(" ", "-")
        assert f"**{choice}:** Configured {slug} definition." in guide
    assert "Needs Review" not in guide


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


def test_vote_store_enforces_cooldown_and_hourly_new_stop_limit(db_path):
    started = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
    assert save_vote(
        "study-a",
        "1001",
        "visitor-a",
        "No Shade",
        cooldown_seconds=5,
        max_new_votes_per_hour=2,
        database_url="",
        sqlite_path=db_path,
        now=started,
    )

    with pytest.raises(VoteRateLimitError, match="Please wait 3 seconds") as cooldown_error:
        save_vote(
            "study-a",
            "1002",
            "visitor-a",
            "Limited Shade",
            cooldown_seconds=5,
            max_new_votes_per_hour=2,
            database_url="",
            sqlite_path=db_path,
            now=started + timedelta(seconds=2),
        )
    assert cooldown_error.value.retry_after_seconds == 3

    assert save_vote(
        "study-a",
        "1002",
        "visitor-a",
        "Limited Shade",
        cooldown_seconds=5,
        max_new_votes_per_hour=2,
        database_url="",
        sqlite_path=db_path,
        now=started + timedelta(seconds=5),
    )
    with pytest.raises(VoteRateLimitError, match="hourly voting limit"):
        save_vote(
            "study-a",
            "1003",
            "visitor-a",
            "Significant Shade",
            max_new_votes_per_hour=2,
            database_url="",
            sqlite_path=db_path,
            now=started + timedelta(seconds=10),
        )

    assert save_vote(
        "study-a",
        "1001",
        "visitor-a",
        "Limited Shade",
        max_new_votes_per_hour=2,
        database_url="",
        sqlite_path=db_path,
        now=started + timedelta(seconds=10),
    )


def test_community_result_requires_threshold_and_unique_leader():
    assert community_result({"No Shade": 2, "Limited Shade": 1}, 5)["status"] == "pending"
    assert community_result({"No Shade": 3, "Limited Shade": 3}, 5)["status"] == "tied"
    result = community_result({"No Shade": 4, "Limited Shade": 2}, 5)
    assert result["status"] == "consensus"
    assert result["label"] == "No Shade"
    assert result["total"] == 6
