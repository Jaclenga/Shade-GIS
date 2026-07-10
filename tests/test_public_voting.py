from __future__ import annotations

import sqlite3

from public_voting import (
    community_result,
    get_existing_vote,
    get_existing_vote_details,
    get_vote_counts,
    normalize_voting_config,
    save_vote,
)


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
    ) == {"coverage_status": "Significant Shade", "shade_sources": ["Constructed"]}
    assert get_existing_vote_details(
        "study-a", "1001", "browser-b", database_url="", sqlite_path=db_path
    ) == {"coverage_status": "Limited Shade", "shade_sources": ["Natural", "Manmade"]}
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
        shade_sources=["Natural", "Constructed"],
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
