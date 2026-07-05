from __future__ import annotations

import pandas as pd

from platform_store import add_review_event, add_shade_label, create_project, list_review_history, list_shade_labels
from builder_app import (
    SHADE_COVERAGE_OPTIONS,
    SHADE_COVERAGE_TAXONOMY,
    SHADE_SOURCE_OPTIONS,
    SHADE_SOURCE_TAXONOMY,
    agreement_metric_summary,
    majority_label_table,
    review_queue_table,
)
from shade_gis.pages import labels_page


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


def test_agreement_metric_summary_value_column_is_arrow_safe(db_path, project, taxonomy, methodology, visualization, minimal_stops):
    project_id = create_project(project, taxonomy, methodology, visualization, minimal_stops, [], db_path)
    for labeler_id in ["alice", "bob"]:
        add_shade_label(
            project_id,
            {
                "stop_id": "1001",
                "labeler_id": labeler_id,
                "labeler_role": "Contributor",
                "shade_category": "No Shade",
                "confidence": 0.8,
                "source": "crowdsourcing",
            },
            db_path,
        )

    summary = agreement_metric_summary(list_shade_labels(project_id, "1001", db_path), minimal_stops)

    assert summary["Value"].map(type).eq(str).all()
    assert summary.loc[summary["Metric"] == "Mean majority agreement", "Value"].iloc[0] == "100.0%"


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


def test_apply_review_decision_updates_active_stop(monkeypatch):
    class FakeStreamlit:
        session_state = {
            "stops": pd.DataFrame(
                [
                    {
                        "stop_id": "1001",
                        "shading": "Needs Review",
                        "shade_coverage": "Unknown",
                        "shade_sources": "",
                        "confidence": 0.25,
                        "review_status": "Needs Review",
                    }
                ]
            )
        }

    monkeypatch.setattr(labels_page, "st", FakeStreamlit)

    labels_page.apply_review_decision_to_stop(
        "1001",
        "No Shade",
        "No Shade",
        "None",
        0.95,
        "Accepted",
    )

    updated = FakeStreamlit.session_state["stops"].iloc[0]
    assert updated["shading"] == "No Shade"
    assert updated["shade_coverage"] == "No Shade"
    assert updated["shade_sources"] == "None"
    assert updated["confidence"] == 0.95
    assert updated["review_status"] == "Accepted"


def test_selected_stop_reference_dataset_keeps_only_mappable_stop(minimal_stops):
    selected = labels_page.selected_stop_reference_dataset(minimal_stops, "1001")

    assert len(selected) == 1
    assert selected.iloc[0]["stop_id"] == "1001"
    assert selected.iloc[0]["stop_lat"] == 27.9506
    assert selected.iloc[0]["stop_lon"] == -82.4572

    no_coordinates = minimal_stops.copy()
    no_coordinates.loc[no_coordinates["stop_id"] == "1001", "stop_lat"] = None

    assert labels_page.selected_stop_reference_dataset(no_coordinates, "1001").empty


def test_stop_reference_map_datasets_include_all_points_and_selected_point(minimal_stops):
    all_stops, selected = labels_page.stop_reference_map_datasets(minimal_stops, "1002")

    assert set(all_stops["stop_id"]) == {"1001", "1002"}
    assert selected["stop_id"].tolist() == ["1002"]

    no_coordinates = minimal_stops.copy()
    no_coordinates.loc[no_coordinates["stop_id"] == "1001", "stop_lon"] = None

    all_stops, selected = labels_page.stop_reference_map_datasets(no_coordinates, "1002")

    assert all_stops["stop_id"].tolist() == ["1002"]
    assert selected["stop_id"].tolist() == ["1002"]


def test_stop_reference_deck_adds_selected_highlight_layer(minimal_stops, taxonomy, visualization):
    deck = labels_page.build_stop_reference_deck(minimal_stops, "1001", taxonomy, visualization)

    assert deck is not None
    assert deck.layers[-1].id == "selected_label_stop_layer"
    assert len(deck.layers[-1].data) == 1


def test_reference_map_selection_returns_clicked_stop(minimal_stops):
    selection_event = {"selection": {"objects": {"stops_layer": [{"stop_id": "1002"}]}}}

    assert labels_page.stop_id_from_reference_map_selection(selection_event, minimal_stops) == "1002"


def test_sync_label_stop_picker_tracks_selected_stop(monkeypatch, minimal_stops):
    class FakeStreamlit:
        session_state = {"label_selected_stop_id": "1002"}

    monkeypatch.setattr(labels_page, "st", FakeStreamlit)

    labels_page.sync_label_stop_picker(minimal_stops.reset_index(drop=True))

    assert FakeStreamlit.session_state["label_stop_index"] == 1

    FakeStreamlit.session_state["label_selected_stop_id"] = "missing"
    labels_page.sync_label_stop_picker(minimal_stops.reset_index(drop=True))

    assert FakeStreamlit.session_state["label_selected_stop_id"] == "1001"
    assert FakeStreamlit.session_state["label_stop_index"] == 0


def test_infer_shade_sources_from_category():
    assert labels_page.infer_shade_sources_from_category("Significant Natural Shade") == "Natural"
    assert labels_page.infer_shade_sources_from_category("Constructed Shade") == "Constructed"
    assert labels_page.infer_shade_sources_from_category("Intentional Built Shade") == "Constructed"
    assert labels_page.infer_shade_sources_from_category("Manmade Shade") == "Manmade"
    assert labels_page.infer_shade_sources_from_category("Incidental Built Shade") == "Manmade"
    assert labels_page.infer_shade_sources_from_category("No Shade") == ""
    assert labels_page.infer_shade_sources_from_category("Needs Review") == ""


def test_source_and_coverage_taxonomies_match_schema_terms():
    assert SHADE_SOURCE_OPTIONS == ["Natural", "Constructed", "Manmade"]
    assert SHADE_COVERAGE_OPTIONS == ["No Shade", "Limited", "Significant"]
    assert [item["shade_source"] for item in SHADE_SOURCE_TAXONOMY] == SHADE_SOURCE_OPTIONS
    assert [item["shade_coverage"] for item in SHADE_COVERAGE_TAXONOMY] == SHADE_COVERAGE_OPTIONS


def test_shade_type_options_collapse_coverage_specific_categories(taxonomy):
    assert labels_page.shade_type_options(taxonomy) == [
        "Needs Review",
        "Natural Shade",
        "Constructed Shade",
        "Manmade Shade",
    ]


def test_shade_category_from_type_preserves_storage_compatibility():
    assert labels_page.shade_category_from_type("Natural Shade", "Limited") == "Limited Natural Shade"
    assert labels_page.shade_category_from_type("Natural Shade", "Significant") == "Significant Natural Shade"
    assert labels_page.shade_category_from_type("Natural Shade", "No Shade") == "No Shade"
    assert labels_page.shade_category_from_type("Constructed Shade", "Significant") == "Constructed Shade"


def test_normalized_shade_sources_preserves_distinct_constructed_and_manmade():
    assert labels_page.normalized_shade_sources("Natural; Intentional Built; Incidental Built") == [
        "Natural",
        "Constructed",
        "Manmade",
    ]


def test_shade_category_from_coverage_and_sources_derives_map_label():
    assert labels_page.shade_category_from_coverage_and_sources("No Shade", ["Natural"]) == "No Shade"
    assert labels_page.shade_category_from_coverage_and_sources("Limited", ["Natural"]) == "Limited Natural Shade"
    assert labels_page.shade_category_from_coverage_and_sources("Significant", ["Natural"]) == "Significant Natural Shade"
    assert labels_page.shade_category_from_coverage_and_sources("Limited", ["Manmade", "Natural"]) == "Manmade Shade"
    assert labels_page.shade_category_from_coverage_and_sources("Limited", ["Natural", "Constructed"]) == "Constructed Shade"
