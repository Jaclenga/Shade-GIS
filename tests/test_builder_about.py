from __future__ import annotations

from builder_about_page import builder_taxonomy_display_table


def test_builder_docs_taxonomy_hides_sort_order_and_preserves_order():
    taxonomy = [
        {
            "sort_order": 2,
            "name": "Limited Shade",
            "description": "Partial coverage",
            "color": "#d69e2e",
        },
        {
            "sort_order": 1,
            "name": "No Shade",
            "description": "No coverage",
            "color": "#dc143c",
        },
    ]

    display = builder_taxonomy_display_table(taxonomy)

    assert display.columns.tolist() == ["name", "description", "color"]
    assert display["name"].tolist() == ["No Shade", "Limited Shade"]
    assert "sort_order" not in display.columns
