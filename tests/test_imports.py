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
    parse_api_response,
    parse_gtfs_zip,
    prepare_stop_dataset,
    read_csv_bytes,
    validate_api_url,
    validate_zip_bytes,
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
    assert prepared.loc[prepared["stop_id"] == "1001", "context_label"].iloc[0] == "High"
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


def test_legacy_combined_labels_are_split_into_coverage_and_sources(project, taxonomy):
    raw = pd.DataFrame(
        [
            {
                "stop_id": "legacy-1",
                "stop_name": "Legacy natural",
                "stop_lat": 27.95,
                "stop_lon": -82.45,
                "shading": "Limited Natural Shade",
            },
            {
                "stop_id": "legacy-2",
                "stop_name": "Legacy shelter",
                "stop_lat": 27.96,
                "stop_lon": -82.46,
                "shading": "Intentional Built Shade",
            },
        ]
    )

    prepared = prepare_stop_dataset(raw, project, taxonomy).set_index("stop_id")

    assert prepared.loc["legacy-1", "shade_coverage"] == "Limited Shade"
    assert prepared.loc["legacy-1", "shading"] == "Limited Shade"
    assert prepared.loc["legacy-1", "shade_sources"] == "Natural"
    assert prepared.loc["legacy-2", "shade_coverage"] == "Needs Review"
    assert prepared.loc["legacy-2", "shade_sources"] == "Purpose-built"


def test_api_url_guard_blocks_private_and_credentialed_urls(monkeypatch):
    monkeypatch.delenv("SHADE_GIS_ALLOW_PRIVATE_API_URLS", raising=False)
    monkeypatch.delenv("SHADE_GIS_ALLOWED_API_HOSTS", raising=False)

    with pytest.raises(ValueError, match="http or https"):
        validate_api_url("ftp://example.org/stops.csv")
    with pytest.raises(ValueError, match="credentials"):
        credentialed_url = "https://" + "user" + ":" + "pass" + "@example.org/stops.csv"
        validate_api_url(credentialed_url)
    with pytest.raises(ValueError, match="Private or localhost"):
        validate_api_url("http://127.0.0.1/stops.csv")


def test_api_url_guard_supports_deployment_allowlist(monkeypatch):
    monkeypatch.setenv("SHADE_GIS_ALLOW_PRIVATE_API_URLS", "1")
    monkeypatch.setenv("SHADE_GIS_ALLOWED_API_HOSTS", "transit.example.org")

    assert validate_api_url("https://data.transit.example.org/stops.csv") == "https://data.transit.example.org/stops.csv"
    with pytest.raises(ValueError, match="not in SHADE_GIS_ALLOWED_API_HOSTS"):
        validate_api_url("https://other.example.org/stops.csv")


def test_import_size_limits_are_enforced(monkeypatch):
    monkeypatch.setenv("SHADE_GIS_MAX_UPLOAD_BYTES", "16")
    monkeypatch.setenv("SHADE_GIS_MAX_API_BYTES", "16")

    with pytest.raises(ValueError, match="CSV upload"):
        read_csv_bytes(b"stop_id,stop_name\n1001,This row is too large\n")
    with pytest.raises(ValueError, match="API response"):
        parse_api_response(b"stop_id,stop_name\n1001,This row is too large\n", "https://example.org/stops.csv", "CSV")


def test_zip_guard_limits_members_and_expanded_size(monkeypatch):
    monkeypatch.setenv("SHADE_GIS_MAX_ZIP_MEMBERS", "1")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("stops.txt", "stop_id,stop_name,stop_lat,stop_lon\n")
        archive.writestr("routes.txt", "route_id,route_short_name\n")

    with pytest.raises(ValueError, match="contains 2 files"):
        validate_zip_bytes(buffer.getvalue(), "test ZIP")

    monkeypatch.setenv("SHADE_GIS_MAX_ZIP_MEMBERS", "10")
    monkeypatch.setenv("SHADE_GIS_MAX_ZIP_UNCOMPRESSED_BYTES", "8")
    with pytest.raises(ValueError, match="expands to"):
        validate_zip_bytes(buffer.getvalue(), "test ZIP")
