from __future__ import annotations

import pandas as pd

from builder_app import calculate_priority_scores


def test_priority_scoring_is_deterministic_for_fixed_weights():
    stops = pd.DataFrame(
        [
            {
                "stop_id": "1001",
                "shading": "No Shade",
                "ridership": 100,
                "heat_vulnerability_index": 0.9,
                "tree_canopy_pct": 0.1,
            },
            {
                "stop_id": "1002",
                "shading": "Limited Natural Shade",
                "ridership": 50,
                "heat_vulnerability_index": 0.3,
                "tree_canopy_pct": 0.6,
            },
        ]
    )
    weights = {
        "ridership": 1,
        "heat_vulnerability_index": 1,
        "low_tree_canopy": 1,
        "low_shade": 1,
    }

    scores = calculate_priority_scores(stops, weights)

    assert scores.tolist() == [97.5, 30.8]


def test_priority_scoring_handles_missing_inputs_zero_weights_and_unknown_shade():
    stops = pd.DataFrame(
        [
            {"stop_id": "1001", "shading": "Needs Review", "ridership": None},
            {"stop_id": "1002", "shading": "Unknown", "ridership": None},
        ]
    )

    zero_scores = calculate_priority_scores(stops, {"ridership": 0, "low_shade": 0})
    low_shade_scores = calculate_priority_scores(stops, {"low_shade": 1})

    assert zero_scores.tolist() == [0.0, 0.0]
    assert low_shade_scores.tolist() == [100.0, 0.0]
