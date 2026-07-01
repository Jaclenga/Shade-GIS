from __future__ import annotations

from platform_store import add_review_event, add_shade_label, create_project, list_review_history, list_shade_labels
from builder_app import majority_label_table, review_queue_table


def test_raw_labels_conflict_and_majority_are_queryable(db_path, project, taxonomy, methodology, visualization, minimal_stops):
    project_id = create_project(project, taxonomy, methodology, visualization, minimal_stops, [], db_path)
    add_shade_label(
        project_id,
        {
            "stop_id": "1001",
            "labeler_id": "alice",
            "labeler_role": "Contributor",
            "shade_category": "Limited Natural Shade",
            "confidence": 0.7,
            "source": "crowdsourcing",
        },
        db_path,
    )
    add_shade_label(
        project_id,
        {
            "stop_id": "1001",
            "labeler_id": "bob",
            "labeler_role": "Contributor",
            "shade_category": "No Shade",
            "confidence": 0.8,
            "source": "crowdsourcing",
        },
        db_path,
    )

    labels = list_shade_labels(project_id, "1001", db_path)
    majority = majority_label_table(labels)
    queue = review_queue_table(minimal_stops, labels)

    assert len(labels) == 2
    assert bool(majority.loc[0, "disagreement_flag"]) is True
    assert bool(majority.loc[0, "tied_majority"]) is True
    assert queue.loc[queue["stop_id"] == "1001", "label_count"].iloc[0] == 2


def test_review_lifecycle_records_every_admin_action(db_path, project, taxonomy, methodology, visualization, minimal_stops):
    project_id = create_project(project, taxonomy, methodology, visualization, minimal_stops, [], db_path)
    actions = [
        ("Expert override", "Needs Review", "Expert Reviewed", "No Shade"),
        ("Mark disputed", "Expert Reviewed", "Disputed", "No Shade"),
        ("Resolve dispute", "Disputed", "Accepted", "No Shade"),
        ("Archive", "Accepted", "Archived", "No Shade"),
    ]

    for action, from_status, to_status, to_label in actions:
        add_review_event(
            project_id,
            {
                "stop_id": "1001",
                "actor_id": "expert1",
                "actor_role": "Expert",
                "action": action,
                "from_status": from_status,
                "to_status": to_status,
                "from_label": "Needs Review",
                "to_label": to_label,
                "notes": f"{action} during pytest",
            },
            db_path,
        )

    history = list_review_history(project_id, "1001", db_path)

    assert len(history) == 4
    assert set(history["action"]) == {item[0] for item in actions}
    archive = history.loc[history["action"] == "Archive"].iloc[0]
    assert archive["to_status"] == "Archived"
    assert archive["metadata_to_label"] == "No Shade"
    assert archive["metadata_actor_role"] == "Expert"
