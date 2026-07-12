from __future__ import annotations

import pandas as pd

from shade_gis.pages.data_page import (
    dataset_preview_page,
    dataset_status_metrics,
    dataset_status_table,
    dataset_work_queue_display,
    filter_dataset_work_queue,
    manual_entry_template,
)


def status_fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    stops = pd.DataFrame(
        [
            {
                "stop_id": "1001",
                "shading": "Significant Shade",
                "shade_coverage": "Significant Shade",
                "review_status": "Accepted",
            },
            {
                "stop_id": "1002",
                "shading": "Needs Review",
                "shade_coverage": "Needs Review",
                "review_status": "Needs Review",
            },
            {
                "stop_id": "1003",
                "shading": "Needs Review",
                "shade_coverage": "Needs Review",
                "review_status": "Unlabeled",
            },
            {
                "stop_id": "1004",
                "shading": "Limited Shade",
                "shade_coverage": "Limited Shade",
                "review_status": "Unlabeled",
            },
        ]
    )
    labels = pd.DataFrame(
        [
            {"stop_id": "1002", "shade_category": "No Shade"},
            {"stop_id": "1002", "shade_category": "Limited Shade"},
            {"stop_id": "1004", "shade_category": "Limited Shade"},
            {"stop_id": "1004", "shade_category": "Limited Shade"},
        ]
    )
    return stops, labels


def test_manual_entry_template_uses_object_dtype_for_editable_mixed_input():
    template = manual_entry_template()

    assert len(template) == 1
    assert template.dtypes.eq(object).all()
    assert template.iloc[0].eq("").all()


def test_dataset_status_combines_final_labels_raw_labels_and_review_state():
    stops, labels = status_fixture()

    status = dataset_status_table(stops, labels).set_index("stop_id")
    metrics = dataset_status_metrics(status)

    assert status.loc["1001", "dataset_status"] == "Reviewed"
    assert status.loc["1001", "label_count"] == 0
    assert status.loc["1002", "dataset_status"] == "Needs Review"
    assert status.loc["1002", "label_count"] == 2
    assert status.loc["1002", "agreement_pct"] == 50.0
    assert status.loc["1003", "dataset_status"] == "Unlabeled"
    assert status.loc["1004", "dataset_status"] == "Needs Review"
    assert metrics == {
        "total_stops": 4,
        "labeled_stops": 3,
        "reviewed_stops": 1,
        "stops_needing_review": 2,
        "unlabeled_stops": 1,
        "label_coverage": 0.75,
        "review_completion": 1 / 3,
    }


def test_dataset_work_queue_filters_searches_and_uses_concise_columns():
    stops, labels = status_fixture()
    status = dataset_status_table(stops, labels)

    filtered = filter_dataset_work_queue(status, ["Needs Review"], "1002")
    display = dataset_work_queue_display(filtered)

    assert filtered["stop_id"].tolist() == ["1002"]
    assert display.columns.tolist() == ["Stop ID", "Status", "Labels", "Final Label", "Agreement"]
    assert display.iloc[0].to_dict() == {
        "Stop ID": "1002",
        "Status": "Needs Review",
        "Labels": 2,
        "Final Label": "Not set",
        "Agreement": "50.0%",
    }


def test_dataset_status_handles_empty_dataset():
    status = dataset_status_table(pd.DataFrame(), pd.DataFrame())

    assert status.empty
    assert dataset_status_metrics(status)["total_stops"] == 0


def test_dataset_status_reopens_review_when_label_is_newer_than_resolution():
    stops = pd.DataFrame(
        [{"stop_id": "2001", "shading": "No Shade", "review_status": "Accepted"}]
    )
    labels = pd.DataFrame(
        [
            {"stop_id": "2001", "shade_category": "No Shade", "created_at": "2026-07-01T10:00:00Z"},
            {"stop_id": "2001", "shade_category": "Limited Shade", "created_at": "2026-07-01T12:00:00Z"},
        ]
    )
    stale_resolution = pd.DataFrame(
        [{"stop_id": "2001", "to_status": "Accepted", "created_at": "2026-07-01T11:00:00Z"}]
    )
    current_resolution = pd.DataFrame(
        [{"stop_id": "2001", "to_status": "Accepted", "created_at": "2026-07-01T13:00:00Z"}]
    )

    reopened = dataset_status_table(stops, labels, stale_resolution)
    resolved = dataset_status_table(stops, labels, current_resolution)

    assert reopened.iloc[0]["dataset_status"] == "Needs Review"
    assert resolved.iloc[0]["dataset_status"] == "Reviewed"


def test_dataset_preview_returns_only_requested_page():
    stops = pd.DataFrame({"stop_id": [str(index) for index in range(2278)]})

    visible, page, page_count = dataset_preview_page(stops, page=3, page_size=50)
    final_page, final_page_number, _ = dataset_preview_page(stops, page=999, page_size=100)

    assert len(visible) == 50
    assert visible["stop_id"].tolist() == [str(index) for index in range(100, 150)]
    assert (page, page_count) == (3, 46)
    assert final_page_number == 23
    assert len(final_page) == 78
    assert final_page.iloc[0]["stop_id"] == "2200"
