from __future__ import annotations

import pandas as pd

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
