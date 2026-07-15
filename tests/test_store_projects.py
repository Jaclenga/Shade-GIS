from __future__ import annotations

import sqlite3

import pytest

from platform_store import (
    create_project,
    delete_project,
    init_database,
    list_projects,
    load_project_bundle,
    mark_project_store_initialized,
    project_store_initialized,
    save_project_bundle,
    update_project_details,
)


def test_create_project_roundtrip(db_path, project, taxonomy, methodology, visualization, minimal_stops):
    project_id = create_project(project, taxonomy, methodology, visualization, minimal_stops, [], db_path)

    bundle = load_project_bundle(project_id, db_path)

    assert bundle["project"]["name"] == "Test Shade Study"
    assert bundle["project"]["agency"] == "Test Transit"
    assert bundle["project"]["region"] == "Test City"
    assert len(bundle["stops"]) == 2
    assert set(bundle["stops"]["stop_id"]) == {"1001", "1002"}
    assert bundle["stops"].loc[bundle["stops"]["stop_id"] == "1001", "context_label"].iloc[0] == "High"
    assert bundle["taxonomy"][0]["name"] == taxonomy[0]["name"]


def test_save_project_updates_metadata_without_corrupting_stops(db_path, project, taxonomy, methodology, visualization, minimal_stops):
    project_id = create_project(project, taxonomy, methodology, visualization, minimal_stops, [], db_path)
    project["name"] = "Updated Shade Study"
    project["dataset_version"] = "test-2"

    save_project_bundle(project_id, project, taxonomy, methodology, visualization, minimal_stops, [], db_path)
    bundle = load_project_bundle(project_id, db_path)
    projects = list_projects(db_path)

    assert bundle["project"]["name"] == "Updated Shade Study"
    assert bundle["project"]["dataset_version"] == "test-2"
    assert len(bundle["stops"]) == 2
    assert projects[0]["id"] == project_id
    assert projects[0]["location_count"] == 2
    assert projects[0]["reviewed_count"] == 0
    assert projects[0]["awaiting_review_count"] == 2


def test_deployment_settings_roundtrip_with_project(
    db_path, project, taxonomy, methodology, visualization, minimal_stops
):
    project["deployment"] = {
        "github_username": "example-owner",
        "destination_repository": "shade-study-site",
        "repository": "example-owner/shade-study-site",
        "branch": "main",
        "commit_message": "Publish field update",
        "mode": "existing",
        "visibility": "private",
        "public_url": "https://example-shade.streamlit.app",
    }

    project_id = create_project(
        project, taxonomy, methodology, visualization, minimal_stops, [], db_path
    )
    reloaded = load_project_bundle(project_id, db_path)

    assert reloaded["project"]["deployment"] == project["deployment"]


def test_update_project_details_preserves_project_data(
    db_path, project, taxonomy, methodology, visualization, minimal_stops
):
    project_id = create_project(
        project, taxonomy, methodology, visualization, minimal_stops, [], db_path
    )

    update_project_details(
        project_id,
        name="Renamed Shade Study",
        agency="Regional Transit",
        region="New Study Area",
        description="Updated from project settings.",
        visibility="Public",
        path=db_path,
    )
    bundle = load_project_bundle(project_id, db_path)

    assert bundle["project"]["name"] == "Renamed Shade Study"
    assert bundle["project"]["agency"] == "Regional Transit"
    assert bundle["project"]["region"] == "New Study Area"
    assert bundle["project"]["description"] == "Updated from project settings."
    assert bundle["project"]["visibility"] == "Public"
    assert len(bundle["stops"]) == 2
    assert bundle["taxonomy"] == taxonomy
    assert bundle["methodology"]["summary"] == methodology["summary"]

    with pytest.raises(ValueError, match="Project name is required"):
        update_project_details(project_id, name="   ", path=db_path)


def test_delete_project_cascades_through_related_data(
    db_path, project, taxonomy, methodology, visualization, minimal_stops
):
    project_id = create_project(
        project, taxonomy, methodology, visualization, minimal_stops, [], db_path
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO images (id, project_id, stop_id, uri, created_at) VALUES (?, ?, ?, ?, ?)",
            ("image-1", project_id, "1001", "https://example.com/image.jpg", "2026-07-14T12:00:00-04:00"),
        )
        conn.execute(
            """
            INSERT INTO shade_labels (id, project_id, stop_id, image_id, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("label-1", project_id, "1001", "image-1", "manual", "2026-07-14T12:01:00-04:00"),
        )
        conn.execute(
            """
            INSERT INTO review_history (id, project_id, stop_id, action, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("review-1", project_id, "1001", "accepted", "2026-07-14T12:02:00-04:00"),
        )
        conn.execute(
            """
            INSERT INTO releases (id, project_id, version, created_at)
            VALUES (?, ?, ?, ?)
            """,
            ("release-1", project_id, "v1", "2026-07-14T12:03:00-04:00"),
        )
        conn.commit()

    assert delete_project(project_id, db_path) is True
    assert delete_project(project_id, db_path) is False
    assert list_projects(db_path) == []
    with pytest.raises(KeyError, match="was not found"):
        load_project_bundle(project_id, db_path)

    with sqlite3.connect(db_path) as conn:
        for table in (
            "project_settings",
            "shade_taxonomy",
            "stops",
            "images",
            "shade_labels",
            "review_history",
            "releases",
            "import_logs",
        ):
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE project_id = ?", (project_id,)
            ).fetchone()[0]
            assert count == 0, table


def test_project_store_initialization_marker_survives_deleting_last_project(
    db_path, project, taxonomy, methodology, visualization, minimal_stops
):
    assert project_store_initialized(db_path) is False
    project_id = create_project(
        project, taxonomy, methodology, visualization, minimal_stops, [], db_path
    )
    mark_project_store_initialized(db_path)

    assert project_store_initialized(db_path) is True
    assert delete_project(project_id, db_path) is True
    assert list_projects(db_path) == []
    assert project_store_initialized(db_path) is True


def test_init_database_adds_deployment_settings_column_to_existing_database(db_path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE projects (id TEXT PRIMARY KEY);
            CREATE TABLE project_settings (
                project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                methodology_json TEXT NOT NULL DEFAULT '{}',
                visualization_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            );
            """
        )

    init_database(db_path)

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(project_settings)")}
    assert "deployment_json" in columns


def test_init_database_migrates_retired_shade_source_labels(
    db_path, project, taxonomy, methodology, visualization, minimal_stops
):
    project_id = create_project(
        project, taxonomy, methodology, visualization, minimal_stops, [], db_path
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE stops SET shading = ?, shade_sources = ? WHERE project_id = ? AND stop_id = ?",
            ("Constructed Shade", "Natural; Manmade", project_id, "1001"),
        )
        conn.execute(
            """
            INSERT INTO shade_labels (
                id, project_id, stop_id, shade_category, shade_sources, source, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-label",
                project_id,
                "1001",
                "Constructed Shade",
                "Constructed; Manmade",
                "manual",
                '{"source_label": "Manmade"}',
                "2026-07-14T00:00:00-04:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO review_history (
                id, project_id, stop_id, action, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-review",
                project_id,
                "1001",
                "label_updated",
                '{"from_sources": "Constructed", "to_sources": "Manmade"}',
                "2026-07-14T00:00:00-04:00",
            ),
        )
        conn.commit()

    init_database(db_path)

    with sqlite3.connect(db_path) as conn:
        stop = conn.execute(
            "SELECT shading, shade_sources FROM stops WHERE project_id = ? AND stop_id = ?",
            (project_id, "1001"),
        ).fetchone()
        label = conn.execute(
            "SELECT shade_category, shade_sources, metadata_json FROM shade_labels WHERE id = 'legacy-label'"
        ).fetchone()
        review_metadata = conn.execute(
            "SELECT metadata_json FROM review_history WHERE id = 'legacy-review'"
        ).fetchone()[0]

    assert stop == ("Purpose-built Shade", "Natural; Incidental")
    assert label == (
        "Purpose-built Shade",
        "Purpose-built; Incidental",
        '{"source_label": "Incidental"}',
    )
    assert review_metadata == '{"from_sources": "Purpose-built", "to_sources": "Incidental"}'
