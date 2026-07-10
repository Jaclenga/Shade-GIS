from __future__ import annotations

import copy
import json

import pandas as pd

import published_app
from shade_gis.builder_visuals import (
    DEFAULT_VISUALIZATION,
    LEGACY_DEFAULT_METRIC_CARDS,
    RECORD_COUNT_FIELD,
    build_deck_chart,
    build_custom_chart_data,
    get_custom_charts,
    selected_dashboard_sections,
)


def test_public_voting_is_off_by_default_but_fully_configured():
    voting = DEFAULT_VISUALIZATION["voting"]

    assert voting["enabled"] is False
    assert voting["options"] == ["No Shade", "Limited Shade", "Significant Shade"]
    assert voting["minimum_votes_for_result"] == 5
    assert voting["allow_vote_changes"] is True


def test_default_custom_charts_count_sources_and_coverage():
    stops = pd.DataFrame(
        [
            {"shade_sources": "Natural", "shade_coverage": "Limited"},
            {"shade_sources": "Constructed", "shade_coverage": "Significant"},
        ]
    )
    visualization = {"custom_charts": []}

    charts = get_custom_charts(stops, visualization)

    assert charts == [
        {
            "title": "Shade Sources",
            "x": "shade_sources",
            "y": RECORD_COUNT_FIELD,
            "aggregation": "Count",
            "chart_type": "Bar",
        },
        {
            "title": "Shade Coverage",
            "x": "shade_coverage",
            "y": RECORD_COUNT_FIELD,
            "aggregation": "Count",
            "chart_type": "Bar",
        },
    ]
    assert DEFAULT_VISUALIZATION["custom_charts"][:2] == charts


def test_default_dashboard_charts_are_sources_and_coverage():
    stops = pd.DataFrame(
        [
            {
                "shade_sources": "Natural",
                "shade_coverage": "Limited",
                "shading": "Limited",
                "review_status": "Unlabeled",
            }
        ]
    )

    assert DEFAULT_VISUALIZATION["metric_cards"] == ["Shade sources", "Shade coverage"]
    assert selected_dashboard_sections(stops, DEFAULT_VISUALIZATION) == ["Shade sources", "Shade coverage"]
    assert published_app.selected_dashboard_sections(stops, DEFAULT_VISUALIZATION) == [
        "Shade sources",
        "Shade coverage",
    ]


def test_legacy_default_dashboard_selection_migrates_to_sources_and_coverage():
    stops = pd.DataFrame(
        [
            {
                "shade_sources": "Natural",
                "shade_coverage": "Limited",
                "shading": "Limited",
                "review_status": "Unlabeled",
            }
        ]
    )
    visualization = {"metric_cards": LEGACY_DEFAULT_METRIC_CARDS}

    assert selected_dashboard_sections(stops, visualization) == ["Shade sources", "Shade coverage"]
    assert published_app.selected_dashboard_sections(stops, visualization) == ["Shade sources", "Shade coverage"]


def test_source_count_chart_splits_semicolon_values():
    stops = pd.DataFrame(
        [
            {"shade_sources": "Natural; Manmade", "shade_coverage": "Limited"},
            {"shade_sources": "Natural; Intentional Built", "shade_coverage": "Significant Shade"},
            {"shade_sources": "Incidental Built", "shade_coverage": "No Shade"},
            {"shade_sources": "", "shade_coverage": "No Shade"},
        ]
    )
    chart = {
        "title": "Shade Sources",
        "x": "shade_sources",
        "y": RECORD_COUNT_FIELD,
        "aggregation": "Count",
        "chart_type": "Bar",
    }

    data, x_column, y_column = build_custom_chart_data(stops, chart)
    counts = dict(zip(data[x_column], data[y_column], strict=True))

    assert x_column == "shade_sources"
    assert y_column == "records"
    assert counts == {"Natural": 2, "Manmade": 2, "Constructed": 1}


def test_coverage_count_chart_uses_schema_codes():
    stops = pd.DataFrame(
        [
            {"shade_coverage": "Limited"},
            {"shade_coverage": "Significant Shade"},
            {"shade_coverage": "Unknown"},
            {"shade_coverage": ""},
        ]
    )
    chart = {
        "title": "Shade Coverage",
        "x": "shade_coverage",
        "y": RECORD_COUNT_FIELD,
        "aggregation": "Count",
        "chart_type": "Bar",
    }

    data, x_column, y_column = build_custom_chart_data(stops, chart)
    counts = dict(zip(data[x_column], data[y_column], strict=True))

    assert y_column == "records"
    assert counts == {"Limited Shade": 1, "Significant Shade": 1}


def test_defaultish_custom_chart_titles_follow_schema_columns():
    stops = pd.DataFrame([{"shade_sources": "Natural", "shade_coverage": "Limited"}])
    visualization = {
        "custom_charts": [
            {
                "title": "Custom chart",
                "x": "shade_sources",
                "y": RECORD_COUNT_FIELD,
                "aggregation": "Count",
                "chart_type": "Bar",
            }
        ]
    }

    charts = get_custom_charts(stops, visualization)

    assert charts[0]["title"] == "Shade Sources"
    assert published_app.custom_chart_title(charts[0], 0) == "Shade Sources"


def test_published_source_count_chart_splits_semicolon_values():
    stops = pd.DataFrame(
        [
            {"shade_sources": "Natural; Intentional Built"},
            {"shade_sources": "Constructed"},
            {"shade_sources": ""},
        ]
    )
    chart = {
        "title": "Shade Sources",
        "x": "shade_sources",
        "y": published_app.RECORD_COUNT_FIELD,
        "aggregation": "Count",
        "chart_type": "Bar",
    }

    data, x_column, y_column = published_app.chart_data(stops, chart)
    counts = dict(zip(data[x_column], data[y_column], strict=True))

    assert y_column == "stops"
    assert counts == {"Constructed": 2, "Natural": 1}


def test_published_map_matches_visuals_map_renderer():
    stops = pd.DataFrame(
        [
            {
                "stop_id": "1001",
                "stop_name": "Main St",
                "stop_lat": 27.9506,
                "stop_lon": -82.4572,
                "shading": "No Shade",
                "review_status": "Accepted",
                "priority_score": 75,
                "context_label": "High",
            },
            {
                "stop_id": "1002",
                "stop_name": "Central Ave",
                "stop_lat": 27.9510,
                "stop_lon": -82.4590,
                "shading": "Limited",
                "review_status": "Unlabeled",
                "priority_score": 25,
                "context_label": "Moderate",
            },
        ]
    )
    taxonomy = [
        {"name": "No Shade", "color": "#dc143c", "sort_order": 1},
        {"name": "Limited", "color": "#d69e2e", "sort_order": 2},
    ]
    visualization = copy.deepcopy(DEFAULT_VISUALIZATION)
    visualization.update(
        {
            "color_by": "Column: context_label",
            "marker_shape": "Diamond",
            "marker_size": 13,
            "marker_opacity": 0.65,
            "marker_stroke_color": "#222222",
            "marker_stroke_width": 2,
            "map_style": "Dark",
        }
    )

    visuals_deck = json.loads(build_deck_chart(stops, taxonomy, copy.deepcopy(visualization)).to_json())
    published_deck = json.loads(published_app.build_deck_chart(stops, taxonomy, copy.deepcopy(visualization)).to_json())

    assert published_deck == visuals_deck
