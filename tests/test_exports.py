from __future__ import annotations

import io
import json

import pandas as pd

import builder_app
from builder_app import dataframe_to_geojson, study_config_json
from platform_store import add_shade_label, create_project, list_shade_labels


def test_export_csv_geojson_raw_labels_and_config(db_path, project, taxonomy, methodology, visualization, minimal_stops):
    project_id = create_project(project, taxonomy, methodology, visualization, minimal_stops, [], db_path)
    add_shade_label(
        project_id,
        {
            "stop_id": "1001",
            "labeler_id": "alice",
            "labeler_role": "Expert",
            "shade_category": "No Shade",
            "confidence": 0.95,
            "source": "expert_review",
        },
        db_path,
    )
    builder_app.st.session_state.clear()
    builder_app.st.session_state["active_project_id"] = project_id
    builder_app.st.session_state["project"] = project
    builder_app.st.session_state["taxonomy"] = taxonomy
    builder_app.st.session_state["methodology"] = methodology
    builder_app.st.session_state["visualization"] = visualization
    builder_app.st.session_state["import_log"] = [{"source": "pytest", "format": "CSV", "rows": 2}]

    stops_csv = minimal_stops.to_csv(index=False)
    labels_csv = list_shade_labels(project_id, path=db_path).to_csv(index=False)
    geojson = json.loads(dataframe_to_geojson(minimal_stops))
    config = json.loads(study_config_json())

    assert len(pd.read_csv(io.StringIO(stops_csv))) == 2
    assert len(pd.read_csv(io.StringIO(labels_csv))) == 1
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 2
    assert geojson["features"][0]["properties"]["stop_id"] == "1001"
    assert config["project"]["name"] == "Test Shade Study"
    assert config["taxonomy"][0]["name"] == taxonomy[0]["name"]
    assert config["import_log"][0]["rows"] == 2
