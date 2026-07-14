from __future__ import annotations

import sqlite3

from platform_store import (
    create_project,
    init_database,
    list_projects,
    load_project_bundle,
    save_project_bundle,
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
