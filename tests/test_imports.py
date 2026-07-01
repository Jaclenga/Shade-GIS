from __future__ import annotations

import io
import zipfile

import pandas as pd
import pytest

import builder_app
from builder_app import (
    import_stop_dataset,
    parse_geojson_bytes,
    parse_geojson_overlay_bytes,
    parse_gtfs_zip,
    prepare_stop_dataset,
    read_csv_bytes,
)


def test_csv_import_maps_fields_deduplicates_and_logs(project, taxonomy):
    builder_app.st.session_state.clear()
    builder_app.st.session_state["import_log"] = []
    raw = read_csv_bytes((builder_app.APP_DIR / "tests" / "fixtures" / "stops_minimal.csv").read_bytes())
    mapping = {
        "stop_id": "stop_id",
        "stop_name": "stop_name",
        "stop_lat": "lat",
        "stop_lon": "lon",
        "routes": "route",
        "ridership": "ridership",
        "heat_vulnerability_index": "heat_vulnerability_index",
        "tree_canopy_pct": "tree_canopy_pct",
        "nearby_destinations": "nearby_destinations",
    }

    prepared = import_stop_dataset(
        raw,
        mapping,
        project=project,
        taxonomy=taxonomy,
        source_name="stops_minimal.csv",
        import_format="CSV",
        metadata={"original_filename": "stops_minimal.csv"},
    )

    assert len(prepared) == 2
    assert prepared.loc[prepared["stop_id"] == "1001", "stop_lat"].iloc[0] == pytest.approx(27.9506)
    assert prepared.loc[prepared["stop_id"] == "1001", "routes"].iloc[0] == "10"
    assert builder_app.st.session_state["import_log"][0]["rows"] == 2
    assert builder_app.st.session_state["import_log"][0]["source"] == "stops_minimal.csv"


def test_gtfs_zip_import_enriches_routes(project, taxonomy):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("stops.txt", "stop_id,stop_name,stop_lat,stop_lon\n2001,GTFS Main,27.9601,-82.4601\n2002,GTFS Central,27.9610,-82.4610\n")
        archive.writestr("stop_times.txt", "trip_id,stop_id\ntrip-a,2001\ntrip-b,2002\n")
        archive.writestr("trips.txt", "trip_id,route_id\ntrip-a,route-10\ntrip-b,route-20\n")
        archive.writestr("routes.txt", "route_id,route_short_name\nroute-10,10\nroute-20,20\n")

    raw, metadata = parse_gtfs_zip(buffer.getvalue())
    prepared = prepare_stop_dataset(raw, {**project, "agency": "GTFS Transit"}, taxonomy)

    assert metadata["routes_joined"] is True
    assert len(prepared) == 2
    assert prepared.loc[prepared["stop_id"] == "2001", "routes"].iloc[0] == "10"


def test_geojson_import_and_overlay_parser(project, taxonomy):
    contents = (builder_app.APP_DIR / "tests" / "fixtures" / "sample_overlay.geojson").read_bytes()

    raw, metadata = parse_geojson_bytes(contents)
    prepared = prepare_stop_dataset(raw, project, taxonomy)
    overlay, overlay_metadata = parse_geojson_overlay_bytes(contents)

    assert metadata["features"] == 2
    assert len(prepared) == 2
    assert prepared.loc[prepared["stop_id"] == "3001", "stop_lon"].iloc[0] == pytest.approx(-82.4701)
    assert overlay["type"] == "FeatureCollection"
    assert overlay_metadata["features"] == 2


def test_bad_csv_missing_coordinates_drops_rows(project, taxonomy):
    raw = pd.DataFrame(
        [
            {"stop_id": "bad-1", "stop_name": "Missing Lat", "stop_lat": "", "stop_lon": -82.0},
            {"stop_id": "bad-2", "stop_name": "Missing Lon", "stop_lat": 27.0, "stop_lon": ""},
        ]
    )

    prepared = prepare_stop_dataset(raw, project, taxonomy)

    assert prepared.empty

