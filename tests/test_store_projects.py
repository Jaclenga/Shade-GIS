from __future__ import annotations

from platform_store import create_project, list_projects, load_project_bundle, save_project_bundle


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
