from __future__ import annotations

import pandas as pd

import published_app
from published_app import summary_metric_cards


def metric_by_label(metrics: list[dict[str, str]], label: str) -> dict[str, str]:
    return next(metric for metric in metrics if metric["label"] == label)


def test_summary_metric_cards_report_inventory_readiness() -> None:
    stops = pd.DataFrame(
        [
            {"stop_lat": 27.95, "stop_lon": -82.45, "shading": "No Shade", "review_status": "Unlabeled"},
            {"stop_lat": 27.96, "stop_lon": -82.46, "shading": "Limited Natural Shade", "review_status": "Unlabeled"},
            {"stop_lat": 27.97, "stop_lon": -82.47, "shading": "Needs Review", "review_status": "Needs Review"},
            {"stop_lat": None, "stop_lon": -82.48, "shading": "", "review_status": "Unlabeled"},
            {"stop_lat": 27.98, "stop_lon": -82.49, "shading": "Unknown", "review_status": "Unlabeled"},
        ]
    )

    metrics = summary_metric_cards(stops)

    assert metric_by_label(metrics, "Mapped stops")["value"] == "4"
    assert metric_by_label(metrics, "Mapped stops")["delta"] == "80.0% with coordinates"
    assert metric_by_label(metrics, "Classified stops")["value"] == "2"
    assert metric_by_label(metrics, "Classified stops")["delta"] == "40.0% of current view"
    assert metric_by_label(metrics, "Review backlog")["value"] == "3"
    assert metric_by_label(metrics, "Review backlog")["delta"] == "60.0% remaining"
    assert metric_by_label(metrics, "No-shade stops")["value"] == "1"
    assert metric_by_label(metrics, "No-shade stops")["delta"] == "50.0% of classified"


def test_summary_metric_cards_do_not_surface_empty_accepted_status() -> None:
    stops = pd.DataFrame(
        {
            "stop_lat": [27.95] * 2315,
            "stop_lon": [-82.45] * 2315,
            "shading": ["No Shade"] * 12 + ["Limited Natural Shade"] * 22 + ["Needs Review"] * 2281,
            "review_status": ["Unlabeled"] * 2315,
        }
    )

    metrics = summary_metric_cards(stops)
    labels = [metric["label"] for metric in metrics]

    assert "Accepted" not in labels
    assert metric_by_label(metrics, "Classified stops")["value"] == "34"
    assert metric_by_label(metrics, "Review backlog")["delta"] == "98.5% remaining"
    assert metric_by_label(metrics, "No-shade stops")["delta"] == "35.3% of classified"


def test_published_agreement_metrics_value_column_is_arrow_safe(monkeypatch) -> None:
    captured = []

    class FakeStreamlit:
        @staticmethod
        def markdown(*args, **kwargs):
            return None

        @staticmethod
        def info(*args, **kwargs):
            return None

        @staticmethod
        def dataframe(data, *args, **kwargs):
            captured.append(data)

    labels = pd.DataFrame(
        [
            {
                "stop_id": "1001",
                "labeler_id": "alice",
                "labeler_role": "Contributor",
                "shade_category": "No Shade",
                "source": "crowdsourcing",
            },
            {
                "stop_id": "1001",
                "labeler_id": "bob",
                "labeler_role": "Contributor",
                "shade_category": "No Shade",
                "source": "crowdsourcing",
            },
        ]
    )
    monkeypatch.setattr(published_app, "st", FakeStreamlit)

    published_app.render_agreement_metrics(labels)

    summary = captured[0]
    assert summary["Value"].map(type).eq(str).all()
    assert summary.loc[summary["Metric"] == "Mean majority agreement", "Value"].iloc[0] == "100.0%"


def test_stop_detail_picker_avoids_session_state_default_warning(monkeypatch) -> None:
    selectbox_calls = []

    class FakeStreamlit:
        session_state = {}

        @staticmethod
        def info(*args, **kwargs):
            return None

        @staticmethod
        def selectbox(*args, **kwargs):
            selectbox_calls.append((args, kwargs))
            return 1

        @staticmethod
        def markdown(*args, **kwargs):
            return None

    stops = pd.DataFrame(
        [
            {
                "stop_id": "1001",
                "stop_name": "First Stop",
                "shading": "No Shade",
                "review_status": "Unlabeled",
                "priority_score": 0.0,
            },
            {
                "stop_id": "1002",
                "stop_name": "Second Stop",
                "shading": "Constructed Shade",
                "review_status": "Accepted",
                "priority_score": 1.0,
            },
        ]
    )
    FakeStreamlit.session_state["preview_selected_stop_id"] = "1002"
    monkeypatch.setattr(published_app, "st", FakeStreamlit)

    published_app.render_stop_detail_workflow(stops, {}, "preview")

    assert FakeStreamlit.session_state["preview_stop_picker"] == 1
    assert "index" not in selectbox_calls[0][1]
