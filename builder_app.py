import io
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pydeck as pdk
import streamlit as st

from builder_about_page import render_builder_about_page
from platform_store import (
    add_review_event,
    add_shade_label,
    create_project,
    database_status,
    init_database,
    list_review_history,
    list_shade_labels,
    list_projects,
    load_project_bundle,
    save_project_bundle,
)


APP_DIR = Path(__file__).parent
DATA_PATH = APP_DIR / "stops.txt"
SHADE_DATA_PATH = APP_DIR / "shading_data.csv"
APP_TITLE = "Shade Study Builder"
VISUAL_MAP_HEIGHT = 500
METHODS_PREVIEW_HEIGHT = 1220


def timestamp_with_timezone() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")

DEFAULT_PROJECT = {
    "name": "Tampa Bus Stop Shade Study",
    "agency": "Hillsborough Area Regional Transit (HART)",
    "region": "Tampa, Florida",
    "description": (
        "A reusable shade inventory project seeded with Tampa-area GTFS stops, "
        "shade classifications, and heat-context fields."
    ),
    "owners": "Open transit and climate research contributors",
    "visibility": "Public",
    "dataset_version": "0.1.0",
    "methodology_version": "0.1.0",
    "source_name": "HART GTFS feed",
    "source_license": "Agency GTFS terms",
    "source_url": "",
}

DEFAULT_TAXONOMY = [
    {
        "name": "No Shade",
        "description": "No shade visibly reaches the waiting area.",
        "color": "#dc143c",
        "sort_order": 1,
    },
    {
        "name": "Limited Natural Shade",
        "description": "Vegetation shades part of the waiting area, but not most of it.",
        "color": "#d69e2e",
        "sort_order": 2,
    },
    {
        "name": "Significant Natural Shade",
        "description": "Vegetation visibly covers most of the waiting area or seating area.",
        "color": "#228b22",
        "sort_order": 3,
    },
    {
        "name": "Intentional Built Shade",
        "description": "A purpose-built shelter, awning, canopy, or overhang shades riders.",
        "color": "#4682b4",
        "sort_order": 4,
    },
    {
        "name": "Incidental Built Shade",
        "description": "A nearby building or other non-shelter built feature shades riders.",
        "color": "#805aaa",
        "sort_order": 5,
    },
    {
        "name": "Needs Review",
        "description": "The stop needs imagery, review, or disagreement resolution.",
        "color": "#808080",
        "sort_order": 6,
    },
]

DEFAULT_METHODOLOGY = {
    "title": "Bus Stop Shade Study",
    "summary": "Preparing a reproducible, city-wide shade inventory from GTFS bus stop data.",
    "purpose": (
        "This project helps researchers, transit agencies, and municipalities collect, "
        "review, visualize, and publish standardized bus stop shade datasets."
    ),
    "shade_method": (
        "Classifications should describe visible shade reaching the passenger waiting area, "
        "not merely nearby trees or structures. Store raw labels and consensus labels so "
        "future reviewers can reproduce decisions."
    ),
    "data_sources": (
        "- GTFS stops and routes\n"
        "- Expert or crowdsourced shade labels\n"
        "- Optional environmental, demographic, and transportation overlays"
    ),
    "contributors": "Project team, reviewers, and community contributors",
    "citation": (
        "Dataset release:\n"
        "    Author or Organization. (Year). Title of dataset or study release (Version number) [Data set]. Publisher. URL"
    ),
    "bibliography": (
        "Works referenced:\n"
        "    Author, A. A., & Author, B. B. (Year). Title of article. Title of Journal, volume(issue), page range. https://doi.org/xxxxx\n"
        "    Author or Organization. (Year). Title of report. Publisher. URL"
    ),
    "limitations": (
        "Imagery date, time of day, season, and reviewer uncertainty can affect shade labels. "
        "Published releases should document these limitations."
    ),
    "release_history": "- 0.1.0: Draft project configuration and starter dataset",
}

DEFAULT_DISPLAY_COLUMNS = ["stop_id", "stop_name", "routes", "shading", "review_status", "priority_score"]
RECORD_COUNT_FIELD = "Record count"
MAX_CUSTOM_CHARTS = 10
DEFAULT_CUSTOM_CHART = {
    "title": "Custom chart",
    "x": "shading",
    "y": RECORD_COUNT_FIELD,
    "aggregation": "Count",
    "chart_type": "Bar",
}

DEFAULT_VISUALIZATION = {
    "color_by": "Shade category",
    "marker_shape": "Circle",
    "marker_size": 7,
    "marker_opacity": 0.82,
    "marker_stroke_color": "#141414",
    "marker_stroke_width": 1,
    "map_style": "Light",
    "priority_colors": {
        "low": "#34d399",
        "mid": "#facc15",
        "high": "#ef4444",
    },
    "field_color_maps": {},
    "metric_cards": [
        "Shade distribution",
        "Stops without shade",
        "Stops requiring review",
        "Review status",
        "Agreement metrics",
        "Shade by route",
        "Shade by neighborhood",
        "Shade vs ridership",
        "Shade vs heat vulnerability",
        "Priority stops",
    ],
    "overlays": [],
    "gis_overlays": [],
    "priority_weights": {
        "ridership": 0.5,
        "low_shade": 0.5,
    },
    "show_legend": True,
    "show_downloads": True,
    "display_columns": DEFAULT_DISPLAY_COLUMNS,
    "custom_charts": [DEFAULT_CUSTOM_CHART],
}

REVIEW_STATUS_COLORS = {
    "Unlabeled": [148, 163, 184],
    "Needs Review": [234, 179, 8],
    "Crowd Reviewed": [45, 212, 191],
    "Expert Reviewed": [59, 130, 246],
    "Accepted": [34, 197, 94],
    "Disputed": [239, 68, 68],
    "Archived": [107, 114, 128],
}

REVIEW_QUEUE_DEFAULT_STATUSES = ["Needs Review", "Disputed", "Unlabeled"]
REVIEW_ACTION_OPTIONS = [
    "Accept current label",
    "Expert override",
    "Mark disputed",
    "Resolve dispute",
    "Archive",
]
REVIEW_ACTION_STATUS_DEFAULTS = {
    "Accept current label": "Accepted",
    "Expert override": "Expert Reviewed",
    "Mark disputed": "Disputed",
    "Resolve dispute": "Accepted",
    "Archive": "Archived",
}

MARKER_SHAPES = ["Circle", "Pin", "Square", "Diamond", "Triangle"]
DESTINATION_FILTER_COLUMNS = ["nearby_destinations", "destinations", "destination"]
CATEGORICAL_MAP_FILTERS = ["shading", "review_status", "heat_vulnerability_label"]
NUMERIC_MAP_FILTERS = [
    "confidence",
    "ridership",
    "heat_vulnerability_index",
    "tree_canopy_pct",
    "priority_score",
]
GIS_OVERLAY_CATEGORIES = ["Transportation", "Environmental", "Demographic", "Destinations", "Other"]
GIS_OVERLAY_CATEGORIES = ["Transportation", "Environmental", "Demographic", "Destinations", "Other"]

MAP_STYLES = {
    "Light": pdk.map_styles.CARTO_LIGHT,
    "Dark": pdk.map_styles.CARTO_DARK,
    "Road": pdk.map_styles.CARTO_ROAD,
    "Light, no labels": pdk.map_styles.CARTO_LIGHT_NO_LABELS,
    "Dark, no labels": pdk.map_styles.CARTO_DARK_NO_LABELS,
}

COLOR_MODE_FIELDS = {
    "Shade category": "shading",
    "Review status": "review_status",
    "Priority score": "priority_score",
}

FIELD_LABELS = {
    "stop_id": "Stop ID",
    "stop_name": "Stop name",
    "stop_lat": "Latitude",
    "stop_lon": "Longitude",
    "agency": "Agency",
    "routes": "Routes",
    "municipality": "Municipality",
    "shading": "Shade category",
    "shade_coverage": "Shade coverage",
    "shade_sources": "Shade sources",
    "review_status": "Review status",
    "confidence": "Confidence",
    "ridership": "Ridership",
    "heat_vulnerability_index": "Heat vulnerability index",
    "heat_vulnerability_label": "Heat vulnerability label",
    "tree_canopy_pct": "Tree canopy percent",
    "lst_median": "Land surface temperature",
    "nearby_destinations": "Nearby destinations",
    "priority_score": "Priority score",
}

OVERLAY_REQUIREMENTS = {
    "GTFS routes": ["routes"],
    "Ridership": ["ridership"],
    "Existing shelters": ["shelter", "shelter_status", "has_shelter"],
    "Route frequency": ["route_frequency", "trips_per_day", "headway_minutes"],
    "Tree canopy": ["tree_canopy_pct"],
    "Land surface temperature": ["lst_median"],
    "Heat vulnerability": ["heat_vulnerability_index", "heat_vulnerability_label"],
    "NDVI": ["ndvi"],
    "Zero-vehicle households": ["zero_vehicle_households"],
    "Older adult population": ["older_adult_population"],
    "Nearby destinations": ["nearby_destinations"],
}

METRIC_REQUIREMENTS = {
    "Shade distribution": ["shading"],
    "Stops without shade": ["shading"],
    "Stops requiring review": ["shading"],
    "Review status": ["review_status"],
    "Agreement metrics": [],
    "Shade by route": ["routes", "shading"],
    "Shade by neighborhood": ["municipality", "shading"],
    "Shade vs ridership": ["ridership", "shading"],
    "Shade vs heat vulnerability": ["heat_vulnerability_index", "shading"],
    "Priority stops": ["priority_score"],
}

CHART_TYPES = ["Bar", "Line", "Scatter"]
CHART_AGGREGATIONS = ["Count", "Mean", "Sum", "Median", "Min", "Max"]
PRIORITY_FACTOR_DETAILS = {
    "ridership": (
        "Ridership",
        "Higher ridership increases priority when the dataset includes ridership values.",
    ),
    "low_shade": (
        "Low shade",
        "Stops labeled No Shade or Needs Review receive more priority.",
    ),
    "heat_vulnerability_index": (
        "Heat vulnerability",
        "Higher heat vulnerability values increase priority when that field is present.",
    ),
    "low_tree_canopy": (
        "Low tree canopy",
        "Lower tree canopy share increases priority when tree canopy data is present.",
    ),
}

COLOR_PALETTE = [
    "#2563eb",
    "#16a34a",
    "#dc2626",
    "#9333ea",
    "#0891b2",
    "#ea580c",
    "#4f46e5",
    "#65a30d",
    "#db2777",
    "#0f766e",
    "#7c3aed",
    "#ca8a04",
    "#475569",
    "#be123c",
    "#0284c7",
    "#15803d",
]

SHADE_PALETTES = {
    "Default shade study": ["#dc143c", "#d69e2e", "#228b22", "#4682b4", "#805aaa", "#808080"],
    "Colorblind friendly": ["#d55e00", "#e69f00", "#009e73", "#0072b2", "#cc79a7", "#999999"],
    "High contrast": ["#b91c1c", "#f97316", "#15803d", "#2563eb", "#7c3aed", "#475569"],
    "Canopy and shelter": ["#dc2626", "#ca8a04", "#16a34a", "#0ea5e9", "#9333ea", "#71717a"],
    "Civic map": ["#ef4444", "#f59e0b", "#22c55e", "#3b82f6", "#a855f7", "#64748b"],
}

SHADE_ALIASES = {
    "Constructed Shade": "Intentional Built Shade",
    "Manmade Shade": "Incidental Built Shade",
    "Unknown": "Needs Review",
}

REQUIRED_STOP_FIELDS = ["stop_id", "stop_name", "stop_lat", "stop_lon"]
OPTIONAL_FIELDS = [
    "agency",
    "routes",
    "municipality",
    "shading",
    "shade_coverage",
    "shade_sources",
    "review_status",
    "confidence",
    "ridership",
    "heat_vulnerability_index",
    "heat_vulnerability_label",
    "tree_canopy_pct",
    "lst_median",
    "nearby_destinations",
]

MANUAL_ENTRY_COLUMNS = REQUIRED_STOP_FIELDS + [
    "agency",
    "routes",
    "municipality",
    "shading",
    "review_status",
    "confidence",
]

FIELD_ALIASES = {
    "stop_id": ["stop_id", "stopid", "stop_code", "id", "objectid"],
    "stop_name": ["stop_name", "stopname", "name", "stop_desc", "description"],
    "stop_lat": ["stop_lat", "stoplat", "latitude", "lat", "y"],
    "stop_lon": ["stop_lon", "stoplon", "longitude", "lon", "lng", "long", "x"],
    "agency": ["agency", "agency_name", "operator"],
    "routes": ["routes", "route", "route_short_name", "route_ids"],
    "municipality": ["municipality", "city", "jurisdiction", "neighborhood"],
    "shading": ["shading", "shade", "shade_category", "shade_label"],
    "shade_coverage": ["shade_coverage", "coverage"],
    "shade_sources": ["shade_sources", "shade_source", "source"],
    "review_status": ["review_status", "status"],
    "confidence": ["confidence", "score"],
    "ridership": ["ridership", "boardings", "ons", "passengers"],
    "heat_vulnerability_index": ["heat_vulnerability_index", "hvi", "heat_index"],
    "heat_vulnerability_label": ["heat_vulnerability_label", "hvi_label"],
    "tree_canopy_pct": ["tree_canopy_pct", "canopy", "tree_canopy"],
    "lst_median": ["lst_median", "lst", "land_surface_temperature"],
    "nearby_destinations": ["nearby_destinations", "destinations", "destination", "nearby_places", "places"],
}

LABEL_SOURCE_OPTIONS = [
    "Expert review",
    "Crowdsourcing",
    "Field audit",
    "Imported dataset",
    "LLM-assisted suggestion",
    "Manual review",
]

LABELER_ROLE_OPTIONS = [
    "Reviewer",
    "Contributor",
    "Project Admin",
    "Expert",
    "Public",
    "Model",
]

SHADE_SOURCE_OPTIONS = [
    "Natural",
    "Intentional Built",
    "Incidental Built",
    "Other",
]

SHADE_COVERAGE_OPTIONS = [
    "No Shade",
    "Limited",
    "Significant",
    "Unknown",
]


def hex_to_rgb(value: str) -> list[int]:
    text = str(value or "").strip().lstrip("#")
    if len(text) != 6:
        return [128, 128, 128]
    try:
        return [int(text[index : index + 2], 16) for index in (0, 2, 4)]
    except ValueError:
        return [128, 128, 128]


def rgb_to_hex(value: list[int]) -> str:
    rgb = [max(0, min(255, int(channel))) for channel in value[:3]]
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def normalize_hex_color(value: Any, fallback: str = "#808080") -> str:
    text = str(value or "").strip()
    if not text.startswith("#"):
        text = f"#{text}"
    if len(text) != 7:
        return fallback
    try:
        int(text[1:], 16)
    except ValueError:
        return fallback
    return text.lower()


def normalize_category(value: Any, taxonomy: list[dict[str, Any]]) -> str:
    categories = [str(item.get("name", "")).strip() for item in taxonomy if str(item.get("name", "")).strip()]
    fallback = "Needs Review" if "Needs Review" in categories else (categories[-1] if categories else "Needs Review")
    if pd.isna(value):
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    text = SHADE_ALIASES.get(text, text)
    return text if text in categories else fallback


def normalize_review_status(value: Any) -> str:
    if pd.isna(value) or not str(value).strip():
        return "Unlabeled"
    text = str(value).strip()
    return text if text in REVIEW_STATUS_COLORS else "Needs Review"


def read_csv_bytes(contents: bytes) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(contents), dtype=str)


def normalize_column_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def suggest_source_column(target: str, columns: list[str]) -> str:
    normalized_columns = {normalize_column_key(column): column for column in columns}
    for alias in FIELD_ALIASES.get(target, [target]):
        match = normalized_columns.get(normalize_column_key(alias))
        if match:
            return match
    return ""


def geometry_coordinate_pairs(geometry: dict[str, Any] | None) -> list[tuple[float, float]]:
    if not geometry:
        return []
    geometry_type = str(geometry.get("type", "")).lower()
    coordinates = geometry.get("coordinates")
    if geometry_type == "point" and isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
        try:
            return [(float(coordinates[0]), float(coordinates[1]))]
        except (TypeError, ValueError):
            return []
    if geometry_type == "geometrycollection":
        pairs: list[tuple[float, float]] = []
        for child in geometry.get("geometries", []) or []:
            pairs.extend(geometry_coordinate_pairs(child))
        return pairs

    pairs: list[tuple[float, float]] = []

    def collect(value: Any) -> None:
        if isinstance(value, (list, tuple)) and len(value) >= 2 and not isinstance(value[0], (list, tuple)):
            try:
                pairs.append((float(value[0]), float(value[1])))
            except (TypeError, ValueError):
                return
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                collect(item)

    collect(coordinates)
    return pairs


def geometry_centroid(geometry: dict[str, Any] | None) -> tuple[float | None, float | None]:
    pairs = geometry_coordinate_pairs(geometry)
    if not pairs:
        return None, None
    lon = sum(pair[0] for pair in pairs) / len(pairs)
    lat = sum(pair[1] for pair in pairs) / len(pairs)
    return lon, lat


def geojson_features(payload: dict[str, Any]) -> list[dict[str, Any]]:
    payload_type = str(payload.get("type", "")).lower()
    if payload_type == "featurecollection":
        return [feature for feature in payload.get("features", []) if isinstance(feature, dict)]
    if payload_type == "feature":
        return [payload]
    if payload_type in {"point", "multipoint", "linestring", "multilinestring", "polygon", "multipolygon"}:
        return [{"type": "Feature", "properties": {}, "geometry": payload}]
    raise ValueError("GeoJSON must be a FeatureCollection, Feature, or geometry object")


def parse_geojson_bytes(contents: bytes) -> tuple[pd.DataFrame, dict[str, Any]]:
    payload = json.loads(contents.decode("utf-8-sig"))
    features = geojson_features(payload)
    records: list[dict[str, Any]] = []
    geometry_types: set[str] = set()
    missing_geometry = 0
    for index, feature in enumerate(features, start=1):
        properties = feature.get("properties") or {}
        if not isinstance(properties, dict):
            properties = {}
        geometry = feature.get("geometry")
        geometry_types.add(str((geometry or {}).get("type", "None")))
        lon, lat = geometry_centroid(geometry)
        record = {str(key): value for key, value in properties.items()}
        record.setdefault("stop_id", str(feature.get("id") or record.get("stop_id") or index))
        record.setdefault("stop_name", record.get("name") or record.get("stop_name") or f"GeoJSON stop {index}")
        if lon is None or lat is None:
            missing_geometry += 1
        else:
            record.setdefault("stop_lon", lon)
            record.setdefault("stop_lat", lat)
        record["geometry_type"] = str((geometry or {}).get("type", ""))
        records.append(record)
    if not records:
        raise ValueError("GeoJSON did not contain any features")
    return pd.DataFrame(records), {
        "geometry_types": "; ".join(sorted(geometry_types)),
        "features": len(records),
        "missing_geometry": missing_geometry,
    }


def json_safe_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, Path)):
        return str(value)
    return str(value)


def clean_geojson_feature(feature: dict[str, Any]) -> dict[str, Any] | None:
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict) or not geometry_coordinate_pairs(geometry):
        return None
    properties = feature.get("properties") or {}
    if not isinstance(properties, dict):
        properties = {}
    cleaned = {
        "type": "Feature",
        "properties": {str(key): json_safe_value(value) for key, value in properties.items()},
        "geometry": geometry,
    }
    if feature.get("id") is not None:
        cleaned["id"] = json_safe_value(feature.get("id"))
    return cleaned


def parse_geojson_overlay_bytes(contents: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = json.loads(contents.decode("utf-8-sig"))
    features = []
    geometry_types: set[str] = set()
    for feature in geojson_features(payload):
        cleaned = clean_geojson_feature(feature)
        if cleaned is None:
            continue
        geometry_types.add(str(cleaned["geometry"].get("type", "")))
        features.append(cleaned)
    if not features:
        raise ValueError("GIS overlay did not contain any renderable geometries")
    return {"type": "FeatureCollection", "features": features}, {
        "geometry_types": "; ".join(sorted(geometry_types)),
        "features": len(features),
    }


def zip_member_names(contents: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(contents)) as archive:
        return archive.namelist()


def detect_zip_import_format(contents: bytes) -> str:
    names = [Path(name).name.lower() for name in zip_member_names(contents)]
    if "stops.txt" in names:
        return "GTFS"
    if any(name.endswith(".shp") for name in names) and any(name.endswith(".dbf") for name in names):
        return "Shapefile"
    raise ValueError("ZIP upload must contain GTFS stops.txt or a zipped Shapefile with .shp and .dbf files")


def parse_shapefile_zip(contents: bytes) -> tuple[pd.DataFrame, dict[str, Any]]:
    try:
        import shapefile  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError("Install pyshp to import zipped Shapefiles: pip install pyshp") from error

    with zipfile.ZipFile(io.BytesIO(contents)) as archive:
        members = {member.lower(): member for member in archive.namelist()}
        shp_member = next((member for member in members.values() if member.lower().endswith(".shp")), None)
        dbf_member = next((member for member in members.values() if member.lower().endswith(".dbf")), None)
        shx_member = next((member for member in members.values() if member.lower().endswith(".shx")), None)
        if not shp_member or not dbf_member:
            raise ValueError("Shapefile ZIP must include at least .shp and .dbf files")
        shp = io.BytesIO(archive.read(shp_member))
        dbf = io.BytesIO(archive.read(dbf_member))
        shx = io.BytesIO(archive.read(shx_member)) if shx_member else None

    reader_kwargs = {"shp": shp, "dbf": dbf}
    if shx is not None:
        reader_kwargs["shx"] = shx
    reader = shapefile.Reader(**reader_kwargs)
    fields = [field[0] for field in reader.fields if field[0] != "DeletionFlag"]
    records = []
    missing_geometry = 0
    geometry_types: set[str] = set()
    for index, shape_record in enumerate(reader.iterShapeRecords(), start=1):
        record = {field: value for field, value in zip(fields, shape_record.record)}
        geometry = shape_record.shape.__geo_interface__
        geometry_types.add(str(geometry.get("type", "")))
        lon, lat = geometry_centroid(geometry)
        record.setdefault("stop_id", str(record.get("stop_id") or record.get("id") or index))
        record.setdefault("stop_name", record.get("name") or record.get("stop_name") or f"Shapefile stop {index}")
        if lon is None or lat is None:
            missing_geometry += 1
        else:
            record.setdefault("stop_lon", lon)
            record.setdefault("stop_lat", lat)
        record["geometry_type"] = str(geometry.get("type", ""))
        records.append(record)
    if not records:
        raise ValueError("Shapefile did not contain any records")
    return pd.DataFrame(records), {
        "geometry_types": "; ".join(sorted(geometry_types)),
        "features": len(records),
        "missing_geometry": missing_geometry,
    }


def parse_shapefile_overlay_zip(contents: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        import shapefile  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError("Install pyshp to import zipped Shapefiles: pip install pyshp") from error

    with zipfile.ZipFile(io.BytesIO(contents)) as archive:
        members = {member.lower(): member for member in archive.namelist()}
        shp_member = next((member for member in members.values() if member.lower().endswith(".shp")), None)
        dbf_member = next((member for member in members.values() if member.lower().endswith(".dbf")), None)
        shx_member = next((member for member in members.values() if member.lower().endswith(".shx")), None)
        if not shp_member or not dbf_member:
            raise ValueError("Shapefile ZIP must include at least .shp and .dbf files")
        shp = io.BytesIO(archive.read(shp_member))
        dbf = io.BytesIO(archive.read(dbf_member))
        shx = io.BytesIO(archive.read(shx_member)) if shx_member else None

    reader_kwargs = {"shp": shp, "dbf": dbf}
    if shx is not None:
        reader_kwargs["shx"] = shx
    reader = shapefile.Reader(**reader_kwargs)
    fields = [field[0] for field in reader.fields if field[0] != "DeletionFlag"]
    features = []
    geometry_types: set[str] = set()
    for shape_record in reader.iterShapeRecords():
        geometry = shape_record.shape.__geo_interface__
        if not geometry_coordinate_pairs(geometry):
            continue
        geometry_types.add(str(geometry.get("type", "")))
        properties = {
            str(field): json_safe_value(value)
            for field, value in zip(fields, shape_record.record)
        }
        features.append({"type": "Feature", "properties": properties, "geometry": geometry})
    if not features:
        raise ValueError("Shapefile overlay did not contain any renderable geometries")
    return {"type": "FeatureCollection", "features": features}, {
        "geometry_types": "; ".join(sorted(geometry_types)),
        "features": len(features),
    }


def fetch_api_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url.strip(),
        headers={"User-Agent": "Shade-GIS/0.1 (+https://github.com/)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not fetch API URL: {error}") from error


def parse_api_response(contents: bytes, url: str, requested_format: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    if requested_format == "CSV":
        return read_csv_bytes(contents), {"source_url": url}
    if requested_format == "GeoJSON":
        raw, metadata = parse_geojson_bytes(contents)
        metadata["source_url"] = url
        return raw, metadata
    try:
        raw, metadata = parse_geojson_bytes(contents)
        metadata["source_url"] = url
        metadata["detected_format"] = "GeoJSON"
        return raw, metadata
    except Exception:
        raw = read_csv_bytes(contents)
        return raw, {"source_url": url, "detected_format": "CSV"}


def find_gtfs_member(archive: zipfile.ZipFile, filename: str) -> str | None:
    filename = filename.lower()
    for member in archive.namelist():
        if Path(member).name.lower() == filename:
            return member
    return None


def read_gtfs_table(
    archive: zipfile.ZipFile, filename: str, usecols: list[str] | None = None
) -> pd.DataFrame | None:
    member = find_gtfs_member(archive, filename)
    if member is None:
        return None
    with archive.open(member) as handle:
        try:
            return pd.read_csv(handle, dtype=str, usecols=usecols)
        except ValueError:
            handle.seek(0)
            return pd.read_csv(handle, dtype=str)


def parse_gtfs_zip(contents: bytes) -> tuple[pd.DataFrame, dict[str, Any]]:
    with zipfile.ZipFile(io.BytesIO(contents)) as archive:
        stops = read_gtfs_table(archive, "stops.txt")
        if stops is None:
            raise ValueError("GTFS upload must include stops.txt")

        route_map: dict[str, str] = {}
        stop_times = read_gtfs_table(archive, "stop_times.txt", ["trip_id", "stop_id"])
        trips = read_gtfs_table(archive, "trips.txt", ["trip_id", "route_id"])
        routes = read_gtfs_table(archive, "routes.txt")
        if stop_times is not None and trips is not None and routes is not None:
            route_label_col = "route_short_name" if "route_short_name" in routes.columns else "route_long_name"
            if route_label_col in routes.columns and "route_id" in routes.columns:
                route_lookup = routes.loc[:, ["route_id", route_label_col]].dropna().drop_duplicates()
                joined = stop_times.merge(trips, on="trip_id", how="left").merge(route_lookup, on="route_id", how="left")
                joined = joined.dropna(subset=["stop_id", route_label_col])
                route_map = (
                    joined.groupby("stop_id")[route_label_col]
                    .apply(lambda values: "; ".join(sorted({str(value) for value in values if str(value).strip()})))
                    .to_dict()
                )

    if route_map:
        stops["routes"] = stops["stop_id"].map(route_map).fillna("")
    metadata = {
        "format": "GTFS",
        "tables": ["stops.txt"],
        "routes_joined": bool(route_map),
        "imported_at": timestamp_with_timezone(),
    }
    return stops, metadata


def apply_field_mapping(raw: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    mapped = pd.DataFrame(index=raw.index)
    used_sources = set()
    for target, source in mapping.items():
        if source and source in raw.columns:
            mapped[target] = raw[source]
            used_sources.add(source)
    for column in raw.columns:
        if column not in used_sources and column not in mapped.columns:
            mapped[column] = raw[column]
    for field in REQUIRED_STOP_FIELDS:
        if field not in mapped.columns:
            mapped[field] = ""
    return mapped


def clean_import_key(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower() or "import"


def import_stop_dataset(
    raw: pd.DataFrame,
    mapping: dict[str, str],
    *,
    project: dict[str, Any],
    taxonomy: list[dict[str, Any]],
    source_name: str,
    import_format: str,
    metadata: dict[str, Any] | None = None,
) -> pd.DataFrame:
    prepared = prepare_stop_dataset(apply_field_mapping(raw, mapping), project, taxonomy)
    st.session_state["stops"] = prepared
    if source_name:
        project["source_name"] = source_name
    if metadata and metadata.get("source_url"):
        project["source_url"] = str(metadata["source_url"])
    log_entry = {
        "source": source_name,
        "format": import_format,
        "rows": len(prepared),
        "imported_at": timestamp_with_timezone(),
    }
    if metadata:
        log_entry.update(metadata)
    st.session_state["import_log"].append(log_entry)
    return prepared


def render_mapped_import_controls(
    raw: pd.DataFrame,
    *,
    source_name: str,
    import_format: str,
    project: dict[str, Any],
    taxonomy: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    key_prefix: str,
    button_label: str,
) -> None:
    metadata = metadata or {}
    st.dataframe(raw.head(25), use_container_width=True)
    if {"stop_lat", "stop_lon"}.issubset(raw.columns):
        missing_coordinates = raw[["stop_lat", "stop_lon"]].isna().any(axis=1).sum()
        st.caption(f"Geometry validation: {len(raw):,} records, {int(missing_coordinates):,} missing coordinates.")
    elif {"geometry_type", "stop_lat", "stop_lon"}.issubset(raw.columns):
        st.caption(f"Geometry validation: {len(raw):,} records from {metadata.get('geometry_types', 'spatial')} geometries.")

    choices = [""] + list(raw.columns)
    st.markdown("#### Field Mapping")
    mapping: dict[str, str] = {}
    fields = REQUIRED_STOP_FIELDS + OPTIONAL_FIELDS
    grid = st.columns(4)
    for index, field in enumerate(fields):
        suggested = suggest_source_column(field, list(raw.columns))
        default_index = choices.index(suggested) if suggested in choices else 0
        with grid[index % 4]:
            mapping[field] = st.selectbox(
                field,
                choices,
                index=default_index,
                key=f"{key_prefix}_map_{field}",
            )
    if st.button(button_label, type="primary", key=f"{key_prefix}_use"):
        prepared = import_stop_dataset(
            raw,
            mapping,
            project=project,
            taxonomy=taxonomy,
            source_name=source_name,
            import_format=import_format,
            metadata=metadata,
        )
        st.success(f"Imported {len(prepared):,} mapped stops.")


def prepare_stop_dataset(raw: pd.DataFrame, project: dict[str, Any], taxonomy: list[dict[str, Any]]) -> pd.DataFrame:
    df = raw.copy()
    for field in REQUIRED_STOP_FIELDS:
        if field not in df.columns:
            df[field] = ""
    for field in OPTIONAL_FIELDS:
        if field not in df.columns:
            df[field] = ""

    df["stop_id"] = df["stop_id"].astype(str).str.strip()
    df["stop_name"] = df["stop_name"].fillna("").astype(str).str.strip()
    df["stop_name"] = df["stop_name"].where(df["stop_name"] != "", "Unnamed stop")
    df["stop_lat"] = pd.to_numeric(df["stop_lat"], errors="coerce")
    df["stop_lon"] = pd.to_numeric(df["stop_lon"], errors="coerce")
    df["agency"] = df["agency"].fillna("").replace("", project.get("agency", ""))
    df["routes"] = df["routes"].fillna("").astype(str)
    df["municipality"] = df["municipality"].fillna("").astype(str)
    df["shading"] = df["shading"].apply(lambda value: normalize_category(value, taxonomy))
    df["review_status"] = df["review_status"].apply(normalize_review_status)

    numeric_fields = ["confidence", "ridership", "heat_vulnerability_index", "tree_canopy_pct", "lst_median"]
    for field in numeric_fields:
        df[field] = pd.to_numeric(df[field], errors="coerce")

    df = df.dropna(subset=["stop_lat", "stop_lon"])
    df = df[df["stop_id"] != ""].drop_duplicates(subset=["stop_id"], keep="first")
    df["priority_score"] = calculate_priority_scores(df)
    return df.reset_index(drop=True)


def calculate_priority_scores(df: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    weights = weights or DEFAULT_VISUALIZATION["priority_weights"]
    score_parts: list[tuple[float, pd.Series]] = []

    ridership_weight = float(weights.get("ridership", 0.0))
    if ridership_weight > 0 and has_column_data(df, "ridership"):
        ridership = pd.to_numeric(df.get("ridership"), errors="coerce").fillna(0)
        ridership = ridership / ridership.max() if ridership.max() and ridership.max() > 0 else ridership
        score_parts.append((ridership_weight, ridership))

    heat_weight = float(weights.get("heat_vulnerability_index", 0.0))
    if heat_weight > 0 and has_column_data(df, "heat_vulnerability_index"):
        heat = pd.to_numeric(df.get("heat_vulnerability_index"), errors="coerce").fillna(0)
        heat = heat / heat.max() if heat.max() and heat.max() > 0 else heat
        score_parts.append((heat_weight, heat))

    canopy_weight = float(weights.get("low_tree_canopy", 0.0))
    if canopy_weight > 0 and has_column_data(df, "tree_canopy_pct"):
        canopy = pd.to_numeric(df.get("tree_canopy_pct"), errors="coerce").fillna(0)
        canopy = canopy.clip(lower=0, upper=1)
        score_parts.append((canopy_weight, 1 - canopy))

    low_shade_weight = float(weights.get("low_shade", 0.0))
    if low_shade_weight > 0 and "shading" in df.columns:
        low_shade = df.get("shading", pd.Series(index=df.index, dtype=str)).isin(["No Shade", "Needs Review"]).astype(float)
        score_parts.append((low_shade_weight, low_shade))

    total_weight = sum(weight for weight, _series in score_parts)
    if total_weight <= 0:
        return pd.Series(0.0, index=df.index)
    score = sum(series * weight for weight, series in score_parts) / total_weight
    return (score * 100).round(1)


def load_seed_dataset(taxonomy: list[dict[str, Any]], project: dict[str, Any]) -> pd.DataFrame:
    if not DATA_PATH.exists():
        return pd.DataFrame(columns=REQUIRED_STOP_FIELDS)
    stops = pd.read_csv(DATA_PATH, dtype={"stop_id": str})
    if SHADE_DATA_PATH.exists():
        shade = pd.read_csv(SHADE_DATA_PATH, dtype={"stop_id": str})
        keep_cols = [column for column in shade.columns if column != "stop_name"]
        stops = stops.merge(shade.loc[:, keep_cols], on="stop_id", how="left")
    return prepare_stop_dataset(stops, project, taxonomy)


def empty_stop_dataset() -> pd.DataFrame:
    return pd.DataFrame(columns=REQUIRED_STOP_FIELDS + OPTIONAL_FIELDS + ["priority_score"])


def with_default_project_values(project: dict[str, Any]) -> dict[str, Any]:
    merged = DEFAULT_PROJECT.copy()
    merged.update(project or {})
    return merged


def with_default_methodology_values(methodology: dict[str, Any]) -> dict[str, Any]:
    merged = DEFAULT_METHODOLOGY.copy()
    merged.update(methodology or {})
    return merged


def with_default_visualization_values(visualization: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(DEFAULT_VISUALIZATION))
    merged.update(visualization or {})
    return merged


def ensure_visualization_defaults() -> None:
    visualization = st.session_state["visualization"]
    if "custom_charts" not in visualization and isinstance(visualization.get("custom_chart"), dict):
        visualization["custom_charts"] = [visualization["custom_chart"]]
    for key, value in DEFAULT_VISUALIZATION.items():
        visualization.setdefault(key, json.loads(json.dumps(value)))
    metric_cards = visualization.setdefault("metric_cards", [])
    for label in DEFAULT_VISUALIZATION["metric_cards"]:
        if label not in metric_cards:
            metric_cards.append(label)

    review_colors = visualization.setdefault("review_status_colors", {})
    for status, color in REVIEW_STATUS_COLORS.items():
        review_colors.setdefault(status, rgb_to_hex(color))

    priority_colors = visualization.setdefault("priority_colors", {})
    for key, color in DEFAULT_VISUALIZATION["priority_colors"].items():
        priority_colors.setdefault(key, color)

    clean_gis_overlays(visualization)


def create_seed_project() -> str:
    project = DEFAULT_PROJECT.copy()
    taxonomy = [item.copy() for item in DEFAULT_TAXONOMY]
    methodology = DEFAULT_METHODOLOGY.copy()
    visualization = json.loads(json.dumps(DEFAULT_VISUALIZATION))
    stops = load_seed_dataset(taxonomy, project)
    import_log = [
        {
            "source": "Seed Tampa GTFS and shade CSV",
            "format": "CSV",
            "rows": len(stops),
            "imported_at": timestamp_with_timezone(),
        }
    ]
    return create_project(project, taxonomy, methodology, visualization, stops, import_log)


def load_project_into_session(project_id: str) -> None:
    bundle = load_project_bundle(project_id)
    project = with_default_project_values(bundle["project"])
    taxonomy = bundle["taxonomy"] or [item.copy() for item in DEFAULT_TAXONOMY]
    methodology = with_default_methodology_values(bundle["methodology"])
    visualization = with_default_visualization_values(bundle["visualization"])
    stops = bundle["stops"]
    if stops.empty:
        stops = empty_stop_dataset()
    else:
        stops = prepare_stop_dataset(stops, project, taxonomy)

    st.session_state["active_project_id"] = project_id
    st.session_state["loaded_project_id"] = project_id
    st.session_state["project"] = project
    st.session_state["taxonomy"] = taxonomy
    st.session_state["methodology"] = methodology
    st.session_state["visualization"] = visualization
    st.session_state["stops"] = stops
    st.session_state["import_log"] = bundle["import_log"]
    ensure_visualization_defaults()


def save_active_project_to_store() -> None:
    project_id = st.session_state.get("active_project_id")
    if not project_id:
        return
    save_project_bundle(
        project_id,
        st.session_state.get("project", DEFAULT_PROJECT.copy()),
        st.session_state.get("taxonomy", [item.copy() for item in DEFAULT_TAXONOMY]),
        st.session_state.get("methodology", DEFAULT_METHODOLOGY.copy()),
        st.session_state.get("visualization", json.loads(json.dumps(DEFAULT_VISUALIZATION))),
        st.session_state.get("stops", empty_stop_dataset()),
        st.session_state.get("import_log", []),
    )


def create_blank_project(name: str) -> str:
    project = DEFAULT_PROJECT.copy()
    project.update(
        {
            "name": name.strip() or "Untitled Shade Study",
            "agency": "",
            "region": "",
            "description": "A reusable bus stop shade study project.",
            "dataset_version": "draft",
            "methodology_version": "draft",
            "source_name": "",
            "source_license": "",
            "source_url": "",
        }
    )
    return create_project(
        project,
        [item.copy() for item in DEFAULT_TAXONOMY],
        DEFAULT_METHODOLOGY.copy(),
        json.loads(json.dumps(DEFAULT_VISUALIZATION)),
        empty_stop_dataset(),
        [],
    )


def ensure_state() -> None:
    init_database()
    projects = list_projects()
    if not projects:
        create_seed_project()
        projects = list_projects()

    active_project_id = st.session_state.get("active_project_id") or projects[0]["id"]
    known_ids = {project["id"] for project in projects}
    if active_project_id not in known_ids:
        active_project_id = projects[0]["id"]

    if st.session_state.get("loaded_project_id") != active_project_id:
        load_project_into_session(active_project_id)


def get_taxonomy_color_map(taxonomy: list[dict[str, Any]]) -> dict[str, list[int]]:
    return {
        str(item.get("name", "")).strip(): hex_to_rgb(str(item.get("color", "")))
        for item in taxonomy
        if str(item.get("name", "")).strip()
    }


def has_column_data(df: pd.DataFrame, column: str) -> bool:
    if column not in df.columns:
        return False
    series = df[column].dropna()
    if series.empty:
        return False
    return bool(series.astype(str).str.strip().ne("").any())


def has_any_column_data(df: pd.DataFrame, columns: list[str]) -> bool:
    return any(has_column_data(df, column) for column in columns)


def has_all_column_data(df: pd.DataFrame, columns: list[str]) -> bool:
    return all(has_column_data(df, column) for column in columns)


def get_color_options(df: pd.DataFrame) -> dict[str, str]:
    options = COLOR_MODE_FIELDS.copy()
    excluded = {"stop_id", "stop_name", "stop_lat", "stop_lon", "priority_score", "shading", "review_status"}
    for column in df.columns:
        if column in excluded:
            continue
        series = df[column].dropna().astype(str).str.strip()
        unique_count = series[series != ""].nunique()
        if 1 < unique_count <= len(COLOR_PALETTE):
            options[f"Column: {FIELD_LABELS.get(column, column)}"] = column
    return options


def display_label(column: str) -> str:
    return FIELD_LABELS.get(column, column.replace("_", " ").title())


def get_active_data_columns(df: pd.DataFrame) -> list[str]:
    always_show = set(REQUIRED_STOP_FIELDS + ["priority_score"])
    return [column for column in df.columns if column in always_show or has_column_data(df, column)]


def get_display_column_options(df: pd.DataFrame) -> list[str]:
    options = get_active_data_columns(df)
    if "priority_score" not in options:
        options.append("priority_score")
    return options


def get_selected_display_columns(df: pd.DataFrame, visualization: dict[str, Any]) -> list[str]:
    options = get_display_column_options(df)
    selected = [column for column in visualization.get("display_columns", []) if column in options]
    if not selected:
        selected = [column for column in DEFAULT_DISPLAY_COLUMNS if column in options]
    if not selected:
        selected = options[: min(6, len(options))]
    visualization["display_columns"] = selected
    return selected


def build_tooltip_text(df: pd.DataFrame, visualization: dict[str, Any]) -> str:
    columns = get_selected_display_columns(df, visualization)[:8]
    return "\n".join(f"{display_label(column)}: {{{column}}}" for column in columns)


def get_available_overlays(df: pd.DataFrame) -> list[str]:
    return [
        label
        for label, columns in OVERLAY_REQUIREMENTS.items()
        if has_any_column_data(df, columns)
    ]


def get_available_metric_cards(df: pd.DataFrame) -> list[str]:
    return [
        label
        for label, columns in METRIC_REQUIREMENTS.items()
        if has_all_column_data(df, columns)
    ]


def clean_selected_options(selected: list[str], options: list[str]) -> list[str]:
    return [item for item in selected if item in options]


def selected_dashboard_sections(df: pd.DataFrame, visualization: dict[str, Any]) -> list[str]:
    available = get_available_metric_cards(df)
    selected = clean_selected_options(visualization.get("metric_cards", []), available)
    return selected or available


def clean_gis_overlays(visualization: dict[str, Any]) -> list[dict[str, Any]]:
    overlays = []
    for index, overlay in enumerate(visualization.get("gis_overlays") or []):
        if not isinstance(overlay, dict):
            continue
        geojson = overlay.get("geojson")
        if not isinstance(geojson, dict) or str(geojson.get("type", "")).lower() != "featurecollection":
            continue
        features = geojson.get("features")
        if not isinstance(features, list) or not features:
            continue
        cleaned = overlay.copy()
        cleaned.setdefault("id", f"gis_overlay_{index + 1}")
        cleaned.setdefault("name", f"GIS overlay {index + 1}")
        cleaned.setdefault("category", "Other")
        cleaned.setdefault("color", COLOR_PALETTE[index % len(COLOR_PALETTE)])
        cleaned.setdefault("opacity", 0.35)
        cleaned.setdefault("line_width", 2)
        cleaned.setdefault("visible", True)
        cleaned["color"] = normalize_hex_color(cleaned.get("color", COLOR_PALETTE[index % len(COLOR_PALETTE)]))
        cleaned["opacity"] = max(0.05, min(1.0, float(cleaned.get("opacity", 0.35) or 0.35)))
        cleaned["line_width"] = max(1, min(12, int(cleaned.get("line_width", 2) or 2)))
        overlays.append(cleaned)
    visualization["gis_overlays"] = overlays
    return overlays


def rgba_from_hex(value: str, opacity: float) -> list[int]:
    rgb = hex_to_rgb(normalize_hex_color(value))
    alpha = int(max(0.05, min(1.0, float(opacity))) * 255)
    return [rgb[0], rgb[1], rgb[2], alpha]


def build_gis_overlay_layers(visualization: dict[str, Any]) -> list[pdk.Layer]:
    layers = []
    for index, overlay in enumerate(clean_gis_overlays(visualization)):
        if not overlay.get("visible", True):
            continue
        color = rgba_from_hex(str(overlay.get("color", COLOR_PALETTE[index % len(COLOR_PALETTE)])), overlay.get("opacity", 0.35))
        line_color = rgba_from_hex(str(overlay.get("color", COLOR_PALETTE[index % len(COLOR_PALETTE)])), min(1.0, float(overlay.get("opacity", 0.35)) + 0.25))
        layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                data=overlay["geojson"],
                id=f"gis_overlay_{index}",
                pickable=True,
                stroked=True,
                filled=True,
                point_type="circle",
                get_fill_color=color,
                get_line_color=line_color,
                get_line_width=int(overlay.get("line_width", 2)),
                line_width_min_pixels=1,
                get_point_radius=35,
                point_radius_units="meters",
                point_radius_min_pixels=4,
                auto_highlight=True,
            )
        )
    return layers


def get_chart_column_options(df: pd.DataFrame) -> list[str]:
    return get_display_column_options(df)


def ensure_custom_chart_defaults(df: pd.DataFrame, chart: dict[str, Any] | None = None, index: int = 0) -> dict[str, Any]:
    chart = chart if isinstance(chart, dict) else {}
    for key, value in DEFAULT_CUSTOM_CHART.items():
        chart.setdefault(key, json.loads(json.dumps(value)))
    if not str(chart.get("title", "")).strip():
        chart["title"] = f"Custom chart {index + 1}"
    columns = get_chart_column_options(df)
    fallback_x = "shading" if "shading" in columns else (columns[0] if columns else "")
    if chart.get("x") not in columns:
        chart["x"] = fallback_x
    y_options = [RECORD_COUNT_FIELD] + columns
    if chart.get("y") not in y_options:
        chart["y"] = RECORD_COUNT_FIELD
    if chart.get("aggregation") not in CHART_AGGREGATIONS:
        chart["aggregation"] = "Count"
    if chart.get("chart_type") not in CHART_TYPES:
        chart["chart_type"] = "Bar"
    return chart


def get_custom_charts(df: pd.DataFrame, visualization: dict[str, Any]) -> list[dict[str, Any]]:
    charts = visualization.get("custom_charts")
    if not isinstance(charts, list):
        legacy_chart = visualization.get("custom_chart")
        charts = [legacy_chart] if isinstance(legacy_chart, dict) else [json.loads(json.dumps(DEFAULT_CUSTOM_CHART))]
    if not charts:
        charts = [json.loads(json.dumps(DEFAULT_CUSTOM_CHART))]
    charts = [
        ensure_custom_chart_defaults(df, chart if isinstance(chart, dict) else {}, index)
        for index, chart in enumerate(charts[:MAX_CUSTOM_CHARTS])
    ]
    visualization["custom_charts"] = charts
    return charts


def build_custom_chart_data(df: pd.DataFrame, chart: dict[str, Any]) -> tuple[pd.DataFrame, str, str]:
    x_column = chart.get("x", "")
    y_column = chart.get("y", RECORD_COUNT_FIELD)
    chart_type = chart.get("chart_type", "Bar")
    aggregation = chart.get("aggregation", "Count")
    if df.empty or x_column not in df.columns:
        return pd.DataFrame(), "", ""

    working = df.copy()
    working[x_column] = working[x_column].fillna("(blank)").astype(str).str.strip().replace("", "(blank)")
    if y_column == RECORD_COUNT_FIELD or y_column not in working.columns:
        chart_df = working.groupby(x_column, dropna=False).size().reset_index(name="records")
        return chart_df.sort_values("records", ascending=False).head(50), x_column, "records"

    numeric_y = pd.to_numeric(working[y_column], errors="coerce")
    if chart_type == "Scatter":
        chart_df = working.loc[numeric_y.notna(), [x_column]].copy()
        chart_df[y_column] = numeric_y[numeric_y.notna()]
        return chart_df.head(500), x_column, y_column

    if numeric_y.notna().any():
        working[y_column] = numeric_y
        if aggregation == "Sum":
            grouped = working.groupby(x_column, dropna=False)[y_column].sum()
        elif aggregation == "Median":
            grouped = working.groupby(x_column, dropna=False)[y_column].median()
        elif aggregation == "Min":
            grouped = working.groupby(x_column, dropna=False)[y_column].min()
        elif aggregation == "Max":
            grouped = working.groupby(x_column, dropna=False)[y_column].max()
        elif aggregation == "Count":
            grouped = working.groupby(x_column, dropna=False)[y_column].count()
        else:
            grouped = working.groupby(x_column, dropna=False)[y_column].mean()
        chart_df = grouped.reset_index(name=display_label(y_column))
        return chart_df.sort_values(display_label(y_column), ascending=False).head(50), x_column, display_label(y_column)

    working[y_column] = working[y_column].fillna("(blank)").astype(str).str.strip().replace("", "(blank)")
    chart_df = working.groupby([x_column, y_column], dropna=False).size().reset_index(name="records")
    chart_df["pair"] = chart_df[x_column].astype(str) + " / " + chart_df[y_column].astype(str)
    return chart_df.sort_values("records", ascending=False).head(50), "pair", "records"


def render_custom_chart(df: pd.DataFrame, chart: dict[str, Any]) -> None:
    chart_df, x_column, y_column = build_custom_chart_data(df, chart)
    if chart_df.empty or not x_column or not y_column:
        st.info("No data is available for the selected chart columns.")
        return
    if chart.get("chart_type") == "Line":
        st.line_chart(chart_df, x=x_column, y=y_column)
    elif chart.get("chart_type") == "Scatter":
        st.scatter_chart(chart_df, x=x_column, y=y_column)
    else:
        st.bar_chart(chart_df, x=x_column, y=y_column)


def render_custom_charts(df: pd.DataFrame, visualization: dict[str, Any]) -> None:
    for index, chart in enumerate(get_custom_charts(df, visualization)):
        title = str(chart.get("title", "")).strip() or f"Custom chart {index + 1}"
        st.markdown(f"#### {title}")
        render_custom_chart(df, chart)


def normalized_category_series(df: pd.DataFrame, column: str) -> pd.Series:
    return df[column].fillna("(blank)").astype(str).str.strip().replace("", "(blank)")


def count_by_field(df: pd.DataFrame, column: str, count_name: str = "stops") -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return pd.DataFrame(columns=[column, count_name])
    working = df.copy()
    working[column] = normalized_category_series(working, column)
    return working.groupby(column, dropna=False).size().reset_index(name=count_name).sort_values(count_name, ascending=False)


def split_routes_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "routes" not in df.columns:
        return pd.DataFrame()
    rows = []
    for _, row in df.iterrows():
        routes = split_route_values(row.get("routes"))
        if not routes:
            continue
        for route in routes:
            rows.append(
                {
                    "route": route,
                    "shading": str(row.get("shading", "Unknown") or "Unknown"),
                    "stop_id": row.get("stop_id", ""),
                }
            )
    return pd.DataFrame(rows)


def render_grouped_shade_dashboard(df: pd.DataFrame, group_column: str, title: str, top_n: int = 25) -> None:
    if df.empty or group_column not in df.columns or "shading" not in df.columns:
        return
    working = df.loc[:, [group_column, "shading"]].copy()
    working[group_column] = normalized_category_series(working, group_column)
    working["shading"] = normalized_category_series(working, "shading")
    grouped = working.groupby([group_column, "shading"], dropna=False).size().reset_index(name="stops")
    if grouped.empty:
        return
    top_groups = grouped.groupby(group_column)["stops"].sum().sort_values(ascending=False).head(top_n).index
    grouped = grouped[grouped[group_column].isin(top_groups)]
    pivot = grouped.pivot_table(index=group_column, columns="shading", values="stops", fill_value=0, aggfunc="sum")
    st.markdown(f"#### {title}")
    st.bar_chart(pivot)
    st.dataframe(grouped.sort_values(["stops", group_column], ascending=[False, True]), use_container_width=True, hide_index=True)


def render_route_shade_dashboard(df: pd.DataFrame) -> None:
    routes = split_routes_table(df)
    if routes.empty or "shading" not in routes.columns:
        return
    grouped = routes.groupby(["route", "shading"], dropna=False).size().reset_index(name="stops")
    top_routes = grouped.groupby("route")["stops"].sum().sort_values(ascending=False).head(25).index
    grouped = grouped[grouped["route"].isin(top_routes)]
    pivot = grouped.pivot_table(index="route", columns="shading", values="stops", fill_value=0, aggfunc="sum")
    st.markdown("#### Shade By Route")
    st.bar_chart(pivot)
    st.dataframe(grouped.sort_values(["stops", "route"], ascending=[False, True]), use_container_width=True, hide_index=True)


def numeric_by_shade_summary(df: pd.DataFrame, numeric_column: str, value_label: str) -> pd.DataFrame:
    if df.empty or numeric_column not in df.columns or "shading" not in df.columns:
        return pd.DataFrame()
    working = df.loc[:, ["shading", numeric_column]].copy()
    working["shading"] = normalized_category_series(working, "shading")
    working[numeric_column] = pd.to_numeric(working[numeric_column], errors="coerce")
    working = working.dropna(subset=[numeric_column])
    if working.empty:
        return pd.DataFrame()
    return (
        working.groupby("shading", dropna=False)[numeric_column]
        .agg(**{f"Mean {value_label}": "mean", f"Median {value_label}": "median", "Stops": "count"})
        .reset_index()
        .sort_values(f"Mean {value_label}", ascending=False)
    )


def render_numeric_by_shade_dashboard(df: pd.DataFrame, numeric_column: str, value_label: str, title: str) -> None:
    summary = numeric_by_shade_summary(df, numeric_column, value_label)
    if summary.empty:
        return
    st.markdown(f"#### {title}")
    st.bar_chart(summary, x="shading", y=f"Mean {value_label}")
    st.dataframe(summary, use_container_width=True, hide_index=True)


def render_issue_analytics_dashboard(
    df: pd.DataFrame,
    visualization: dict[str, Any],
    raw_labels: pd.DataFrame,
) -> None:
    selected = selected_dashboard_sections(df, visualization)
    if df.empty:
        st.info("No stops match the active filters.")
        return

    st.markdown("#### Summary Statistics")
    render_metric_cards(df)

    summary_cols = st.columns(2)
    if "Shade distribution" in selected and "shading" in df.columns:
        with summary_cols[0]:
            st.markdown("#### Shade Distribution")
            shade_counts = count_by_field(df, "shading")
            st.bar_chart(shade_counts, x="shading", y="stops")
            st.dataframe(shade_counts, use_container_width=True, hide_index=True)
    if "Review status" in selected and "review_status" in df.columns:
        with summary_cols[1]:
            st.markdown("#### Review Status")
            review_counts = count_by_field(df, "review_status")
            st.bar_chart(review_counts, x="review_status", y="stops")
            st.dataframe(review_counts, use_container_width=True, hide_index=True)

    queue_rows = []
    if "Stops without shade" in selected and "shading" in df.columns:
        no_shade = df[normalized_category_series(df, "shading").eq("No Shade")]
        queue_rows.append({"Queue": "Stops without shade", "Stops": len(no_shade)})
    if "Stops requiring review" in selected and "shading" in df.columns:
        needs_review = df[normalized_category_series(df, "shading").eq("Needs Review")]
        queue_rows.append({"Queue": "Stops requiring review", "Stops": len(needs_review)})
    if queue_rows:
        st.markdown("#### Action Queues")
        st.dataframe(pd.DataFrame(queue_rows), use_container_width=True, hide_index=True)

    if "Agreement metrics" in selected:
        render_agreement_metrics(raw_labels, df)
    if "Shade by route" in selected:
        render_route_shade_dashboard(df)
    if "Shade by neighborhood" in selected:
        render_grouped_shade_dashboard(df, "municipality", "Shade By Neighborhood")
    if "Shade vs ridership" in selected:
        render_numeric_by_shade_dashboard(df, "ridership", "Ridership", "Shade Vs Ridership")
    if "Shade vs heat vulnerability" in selected:
        render_numeric_by_shade_dashboard(
            df,
            "heat_vulnerability_index",
            "Heat Vulnerability",
            "Shade Vs Heat Vulnerability",
        )
    if "Priority stops" in selected and "priority_score" in df.columns:
        st.markdown("#### Highest Priority Stops")
        priority = df.sort_values("priority_score", ascending=False).head(20)
        columns = get_selected_display_columns(priority, visualization)
        st.dataframe(priority.loc[:, columns], use_container_width=True, hide_index=True)


def priority_score_used_in_visualization(visualization: dict[str, Any]) -> bool:
    if COLOR_MODE_FIELDS.get(visualization.get("color_by", "")) == "priority_score":
        return True
    if "Priority stops" in visualization.get("metric_cards", []):
        return True
    if "priority_score" in visualization.get("display_columns", []):
        return True
    charts = visualization.get("custom_charts")
    if not isinstance(charts, list) and isinstance(visualization.get("custom_chart"), dict):
        charts = [visualization["custom_chart"]]
    for chart in charts or []:
        if isinstance(chart, dict) and "priority_score" in {chart.get("x"), chart.get("y")}:
            return True
    return False


def priority_formula_for_about(visualization: dict[str, Any]) -> dict[str, Any] | None:
    if not priority_score_used_in_visualization(visualization):
        return None

    weights = visualization.get("priority_weights", {})
    rows = []
    for key, (label, description) in PRIORITY_FACTOR_DETAILS.items():
        weight = float(weights.get(key, 0.0))
        if weight > 0:
            rows.append(
                {
                    "Factor": label,
                    "Weight": f"{weight:.2f}",
                    "Role in score": description,
                }
            )

    if rows:
        summary = (
            "Priority score is calculated from the weighted factors below and normalized to a 0-100 scale. "
            "The score is included here automatically because at least one configured visualization uses "
            "`priority_score`."
        )
    else:
        summary = (
            "Priority score is included in at least one configured visualization, but no weighted priority "
            "factors are currently active or available. Scores will remain 0 until a factor is enabled."
        )

    return {"summary": summary, "weights": rows}


def field_values_for_colors(df: pd.DataFrame, field: str) -> list[str]:
    if field not in df.columns:
        return []
    values = df[field].fillna("Unknown").astype(str).str.strip()
    values = values.where(values != "", "Unknown")
    return sorted(values.unique().tolist())[: len(COLOR_PALETTE)]


def ensure_field_color_map(visualization: dict[str, Any], df: pd.DataFrame, field: str) -> dict[str, str]:
    field_maps = visualization.setdefault("field_color_maps", {})
    color_map = field_maps.setdefault(field, {})
    for index, value in enumerate(field_values_for_colors(df, field)):
        color_map.setdefault(value, COLOR_PALETTE[index % len(COLOR_PALETTE)])
    return color_map


def color_for_priority(value: Any, visualization: dict[str, Any]) -> list[int]:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    score = 0.0 if pd.isna(numeric) else max(0.0, min(100.0, float(numeric)))
    colors = visualization.get("priority_colors", DEFAULT_VISUALIZATION["priority_colors"])
    low = hex_to_rgb(colors.get("low", DEFAULT_VISUALIZATION["priority_colors"]["low"]))
    mid = hex_to_rgb(colors.get("mid", DEFAULT_VISUALIZATION["priority_colors"]["mid"]))
    high = hex_to_rgb(colors.get("high", DEFAULT_VISUALIZATION["priority_colors"]["high"]))
    if score <= 50:
        start, end, fraction = low, mid, score / 50
    else:
        start, end, fraction = mid, high, (score - 50) / 50
    return [int(start[channel] + (end[channel] - start[channel]) * fraction) for channel in range(3)]


def color_dataset(df: pd.DataFrame, taxonomy: list[dict[str, Any]], visualization: dict[str, Any]) -> pd.DataFrame:
    colored = df.copy()
    color_options = get_color_options(colored)
    color_by = visualization.get("color_by", "Shade category")
    field = color_options.get(color_by, "shading")
    if field == "review_status":
        review_colors = visualization.get("review_status_colors", {})
        colored["fill_color"] = colored["review_status"].map(
            {status: hex_to_rgb(color) for status, color in review_colors.items()}
        )
    elif field == "priority_score":
        colored["fill_color"] = colored["priority_score"].apply(lambda value: color_for_priority(value, visualization))
    elif field == "shading":
        color_map = get_taxonomy_color_map(taxonomy)
        colored["fill_color"] = colored["shading"].map(color_map)
    else:
        color_map = ensure_field_color_map(visualization, colored, field)
        values = colored[field].fillna("Unknown").astype(str).str.strip()
        values = values.where(values != "", "Unknown")
        colored["fill_color"] = values.map({value: hex_to_rgb(color) for value, color in color_map.items()})
    colored["fill_color"] = colored["fill_color"].apply(lambda value: value if isinstance(value, list) else [128, 128, 128])
    return colored


def marker_icon_svg(
    shape: str,
    fill_color: list[int],
    stroke_color: list[int],
    opacity: float,
    stroke_width: int,
) -> str:
    fill = f"rgb({fill_color[0]},{fill_color[1]},{fill_color[2]})"
    stroke = f"rgb({stroke_color[0]},{stroke_color[1]},{stroke_color[2]})"
    stroke_width = max(0, int(stroke_width))
    base_attrs = f'fill="{fill}" fill-opacity="{opacity:.2f}" stroke="{stroke}" stroke-width="{stroke_width}"'
    if shape == "Pin":
        body = (
            f'<path {base_attrs} d="M32 4C20.4 4 11 13.4 11 25c0 15.2 21 35 21 35s21-19.8 21-35C53 13.4 43.6 4 32 4z"/>'
            f'<circle cx="32" cy="25" r="8" fill="#ffffff" fill-opacity="0.8" stroke="none"/>'
        )
    elif shape == "Square":
        body = f'<rect {base_attrs} x="12" y="12" width="40" height="40" rx="4"/>'
    elif shape == "Diamond":
        body = f'<polygon {base_attrs} points="32,6 58,32 32,58 6,32"/>'
    elif shape == "Triangle":
        body = f'<polygon {base_attrs} points="32,7 58,55 6,55"/>'
    else:
        body = f'<circle {base_attrs} cx="32" cy="32" r="24"/>'
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">{body}</svg>'
    return f"data:image/svg+xml;charset=utf-8,{urllib.parse.quote(svg)}"


def add_marker_icons(map_df: pd.DataFrame, visualization: dict[str, Any]) -> pd.DataFrame:
    shaped = map_df.copy()
    shape = visualization.get("marker_shape", "Circle")
    if shape not in MARKER_SHAPES:
        shape = "Circle"
    opacity = max(0.1, min(1.0, float(visualization.get("marker_opacity", 0.82))))
    stroke_color = hex_to_rgb(visualization.get("marker_stroke_color", "#141414"))
    stroke_width = int(visualization.get("marker_stroke_width", 1))
    shaped["icon_data"] = shaped["fill_color"].apply(
        lambda color: {
            "url": marker_icon_svg(shape, color, stroke_color, opacity, stroke_width),
            "width": 64,
            "height": 64,
            "anchorY": 64 if shape == "Pin" else 32,
        }
    )
    shaped["marker_size"] = int(visualization.get("marker_size", 18))
    return shaped


def calculate_view_state(df: pd.DataFrame) -> pdk.ViewState:
    if df.empty:
        return pdk.ViewState(latitude=39.5, longitude=-98.35, zoom=3, min_zoom=2, max_zoom=18, pitch=0)
    lat = pd.to_numeric(df["stop_lat"], errors="coerce")
    lon = pd.to_numeric(df["stop_lon"], errors="coerce")
    return pdk.ViewState(
        latitude=float(lat.mean()),
        longitude=float(lon.mean()),
        zoom=10 if max(lat.max() - lat.min(), lon.max() - lon.min()) < 0.8 else 8,
        min_zoom=2,
        max_zoom=18,
        pitch=0,
    )


def build_deck_chart(df: pd.DataFrame, taxonomy: list[dict[str, Any]], visualization: dict[str, Any]) -> pdk.Deck:
    map_df = color_dataset(df, taxonomy, visualization)
    if visualization.get("marker_shape", "Circle") == "Circle":
        marker_size = max(4, min(48, int(visualization.get("marker_size", 7))))
        map_df["marker_size"] = marker_size
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            id="stops_layer",
            get_position="[stop_lon, stop_lat]",
            get_fill_color="fill_color",
            get_radius="marker_size",
            radius_units="pixels",
            radius_min_pixels=4,
            radius_max_pixels=48,
            opacity=max(0.1, min(1.0, float(visualization.get("marker_opacity", 0.82)))),
            stroked=True,
            get_line_color=hex_to_rgb(visualization.get("marker_stroke_color", "#141414")),
            line_width_min_pixels=max(0, int(visualization.get("marker_stroke_width", 1))),
            pickable=True,
            auto_highlight=True,
        )
    else:
        map_df = add_marker_icons(map_df, visualization)
        layer = pdk.Layer(
            "IconLayer",
            data=map_df,
            id="stops_layer",
            get_icon="icon_data",
            get_position="[stop_lon, stop_lat]",
            get_size="marker_size",
            size_units="pixels",
            size_min_pixels=4,
            size_max_pixels=48,
            pickable=True,
            auto_highlight=True,
        )
    return pdk.Deck(
        initial_view_state=calculate_view_state(map_df),
        layers=[*build_gis_overlay_layers(visualization), layer],
        map_style=MAP_STYLES.get(visualization.get("map_style", "Light"), pdk.map_styles.CARTO_LIGHT),
        tooltip={"text": build_tooltip_text(map_df, visualization)},
    )


def dataframe_to_geojson(df: pd.DataFrame) -> str:
    features = []
    for _, row in df.iterrows():
        properties = row.drop(labels=["stop_lat", "stop_lon"], errors="ignore").to_dict()
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(row["stop_lon"]), float(row["stop_lat"])]},
                "properties": {key: (None if pd.isna(value) else value) for key, value in properties.items()},
            }
        )
    return json.dumps({"type": "FeatureCollection", "features": features}, indent=2)


def study_config_json() -> str:
    return json.dumps(study_config_payload(), indent=2, default=str)


def study_config_payload() -> dict[str, Any]:
    return {
        "project": st.session_state["project"],
        "taxonomy": st.session_state["taxonomy"],
        "methodology": st.session_state["methodology"],
        "visualization": st.session_state["visualization"],
        "import_log": st.session_state["import_log"],
    }


def active_raw_labels() -> pd.DataFrame:
    project_id = st.session_state.get("active_project_id")
    if not project_id:
        return pd.DataFrame()
    return list_shade_labels(project_id)


def slugify_repo_name(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", str(value or "").strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip(".-_")
    return slug or "shade-study-app"


def github_new_repo_url(project: dict[str, Any], repo_name: str) -> str:
    params = {
        "name": slugify_repo_name(repo_name),
        "description": f"{project.get('name', 'Shade study')} Streamlit app",
        "visibility": "public" if project.get("visibility") == "Public" else "private",
    }
    return "https://github.com/new?" + urllib.parse.urlencode(params)


def published_app_source() -> str:
    return r'''import base64
import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd
import pydeck as pdk
import streamlit as st


APP_DIR = Path(__file__).parent
CONFIG_PATH = APP_DIR / "shade_study_config.json"
DATA_PATH = APP_DIR / "shade_study_stops.csv"
RAW_LABELS_PATH = APP_DIR / "shade_study_raw_labels.csv"
RECORD_COUNT_FIELD = "Record count"
STOP_DETAIL_PANEL_HEIGHT = 500

MAP_STYLES = {
    "Light": pdk.map_styles.CARTO_LIGHT,
    "Dark": pdk.map_styles.CARTO_DARK,
    "Road": pdk.map_styles.CARTO_ROAD,
    "Light, no labels": pdk.map_styles.CARTO_LIGHT_NO_LABELS,
    "Dark, no labels": pdk.map_styles.CARTO_DARK_NO_LABELS,
}

COLOR_MODE_FIELDS = {
    "Shade category": "shading",
    "Review status": "review_status",
    "Priority score": "priority_score",
}

DEFAULT_DISPLAY_COLUMNS = ["stop_id", "stop_name", "routes", "shading", "review_status", "priority_score"]
DEFAULT_PALETTE = [
    "#2563eb", "#16a34a", "#dc2626", "#9333ea", "#d97706",
    "#0891b2", "#be123c", "#4d7c0f", "#7c3aed", "#0f766e",
]
FILTER_FIELD_LABELS = {
    "shading": "Shade category",
    "review_status": "Review status",
    "confidence": "Confidence",
    "ridership": "Ridership",
    "heat_vulnerability_index": "Heat vulnerability index",
    "heat_vulnerability_label": "Heat vulnerability label",
    "tree_canopy_pct": "Tree canopy percent",
    "priority_score": "Priority score",
}
DESTINATION_FILTER_COLUMNS = ["nearby_destinations", "destinations", "destination"]
CATEGORICAL_MAP_FILTERS = ["shading", "review_status", "heat_vulnerability_label"]
NUMERIC_MAP_FILTERS = [
    "confidence",
    "ridership",
    "heat_vulnerability_index",
    "tree_canopy_pct",
    "priority_score",
]
METRIC_REQUIREMENTS = {
    "Shade distribution": ["shading"],
    "Stops without shade": ["shading"],
    "Stops requiring review": ["shading"],
    "Review status": ["review_status"],
    "Agreement metrics": [],
    "Shade by route": ["routes", "shading"],
    "Shade by neighborhood": ["municipality", "shading"],
    "Shade vs ridership": ["ridership", "shading"],
    "Shade vs heat vulnerability": ["heat_vulnerability_index", "shading"],
    "Priority stops": ["priority_score"],
}


def load_study() -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    stops = pd.read_csv(DATA_PATH)
    raw_labels = pd.read_csv(RAW_LABELS_PATH) if RAW_LABELS_PATH.exists() else pd.DataFrame()
    stops["priority_score"] = calculate_priority_scores(
        stops, config.get("visualization", {}).get("priority_weights", {})
    )
    return config, stops, raw_labels


def normalize_hex_color(value: str, fallback: str = "#808080") -> str:
    text = str(value or "").strip()
    if not text.startswith("#"):
        text = f"#{text}"
    return text if len(text) == 7 else fallback


def hex_to_rgb(value: str) -> list[int]:
    color = normalize_hex_color(value).lstrip("#")
    return [int(color[index : index + 2], 16) for index in (0, 2, 4)]


def calculate_priority_scores(df: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    score = pd.Series(0.0, index=df.index)
    weight_total = 0.0
    ridership_weight = float(weights.get("ridership", 0) or 0)
    if ridership_weight and "ridership" in df:
        ridership = pd.to_numeric(df["ridership"], errors="coerce").fillna(0)
        max_ridership = ridership.max()
        if max_ridership > 0:
            score += ridership_weight * (ridership / max_ridership)
            weight_total += ridership_weight
    low_shade_weight = float(weights.get("low_shade", 0) or 0)
    if low_shade_weight and "shading" in df:
        low_shade = df["shading"].isin(["No Shade", "Limited Natural Shade", "Needs Review"]).astype(float)
        score += low_shade_weight * low_shade
        weight_total += low_shade_weight
    if weight_total == 0:
        return pd.Series(0.0, index=df.index)
    return (score / weight_total).round(4)


def get_selected_display_columns(df: pd.DataFrame, visualization: dict[str, Any]) -> list[str]:
    configured = visualization.get("display_columns") or DEFAULT_DISPLAY_COLUMNS
    columns = [column for column in configured if column in df.columns]
    return columns or [column for column in DEFAULT_DISPLAY_COLUMNS if column in df.columns] or list(df.columns[:8])


def clean_gis_overlays(visualization: dict[str, Any]) -> list[dict[str, Any]]:
    overlays = []
    for index, overlay in enumerate(visualization.get("gis_overlays") or []):
        if not isinstance(overlay, dict):
            continue
        geojson = overlay.get("geojson")
        if not isinstance(geojson, dict) or str(geojson.get("type", "")).lower() != "featurecollection":
            continue
        features = geojson.get("features")
        if not isinstance(features, list) or not features:
            continue
        cleaned = overlay.copy()
        cleaned.setdefault("id", f"gis_overlay_{index + 1}")
        cleaned.setdefault("name", f"GIS overlay {index + 1}")
        cleaned.setdefault("category", "Other")
        cleaned.setdefault("color", DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)])
        cleaned.setdefault("opacity", 0.35)
        cleaned.setdefault("line_width", 2)
        cleaned.setdefault("visible", True)
        cleaned["color"] = normalize_hex_color(cleaned.get("color", DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)]))
        cleaned["opacity"] = max(0.05, min(1.0, float(cleaned.get("opacity", 0.35) or 0.35)))
        cleaned["line_width"] = max(1, min(12, int(cleaned.get("line_width", 2) or 2)))
        overlays.append(cleaned)
    visualization["gis_overlays"] = overlays
    return overlays


def rgba_from_hex(value: str, opacity: float) -> list[int]:
    rgb = hex_to_rgb(normalize_hex_color(value))
    alpha = int(max(0.05, min(1.0, float(opacity))) * 255)
    return [rgb[0], rgb[1], rgb[2], alpha]


def build_gis_overlay_layers(visualization: dict[str, Any]) -> list[pdk.Layer]:
    layers = []
    for index, overlay in enumerate(clean_gis_overlays(visualization)):
        if not overlay.get("visible", True):
            continue
        color = rgba_from_hex(str(overlay.get("color", DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)])), overlay.get("opacity", 0.35))
        line_color = rgba_from_hex(str(overlay.get("color", DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)])), min(1.0, float(overlay.get("opacity", 0.35)) + 0.25))
        layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                data=overlay["geojson"],
                id=f"gis_overlay_{index}",
                pickable=True,
                stroked=True,
                filled=True,
                point_type="circle",
                get_fill_color=color,
                get_line_color=line_color,
                get_line_width=int(overlay.get("line_width", 2)),
                line_width_min_pixels=1,
                get_point_radius=35,
                point_radius_units="meters",
                point_radius_min_pixels=4,
                auto_highlight=True,
            )
        )
    return layers


def color_lookup(df: pd.DataFrame, taxonomy: list[dict[str, Any]], visualization: dict[str, Any]) -> tuple[str, dict[str, list[int]]]:
    label = visualization.get("color_by", "Shade category")
    field = COLOR_MODE_FIELDS.get(label, label)
    if field not in df.columns:
        field = "shading" if "shading" in df.columns else df.columns[0]
    if field == "priority_score":
        colors = visualization.get("priority_colors", {})
        return field, {
            "low": hex_to_rgb(colors.get("low", "#34d399")),
            "mid": hex_to_rgb(colors.get("mid", "#facc15")),
            "high": hex_to_rgb(colors.get("high", "#ef4444")),
        }
    if field == "shading":
        mapping = {
            str(item.get("name", "")): hex_to_rgb(item.get("color", "#808080"))
            for item in taxonomy
        }
    else:
        stored = visualization.get("field_color_maps", {}).get(field, {})
        values = sorted(str(value) for value in df[field].fillna("Unknown").unique())
        mapping = {
            value: hex_to_rgb(stored.get(value, DEFAULT_PALETTE[index % len(DEFAULT_PALETTE)]))
            for index, value in enumerate(values)
        }
    mapping.setdefault("Unknown", [128, 128, 128])
    return field, mapping


def marker_color(row: pd.Series, field: str, mapping: dict[str, list[int]]) -> list[int]:
    if field == "priority_score":
        score = float(row.get("priority_score", 0) or 0)
        if score >= 0.66:
            return mapping["high"]
        if score >= 0.33:
            return mapping["mid"]
        return mapping["low"]
    return mapping.get(str(row.get(field, "Unknown")), mapping.get("Unknown", [128, 128, 128]))


def build_tooltip_text(df: pd.DataFrame, visualization: dict[str, Any]) -> str:
    columns = get_selected_display_columns(df, visualization)[:8]
    return "\n".join([f"{column}: {{{column}}}" for column in columns])


def marker_svg(shape: str, fill: list[int], stroke: str) -> str:
    fill_hex = "#%02x%02x%02x" % tuple(fill)
    stroke_hex = normalize_hex_color(stroke, "#141414")
    if shape == "Square":
        body = f"<rect x='6' y='6' width='52' height='52' rx='6' fill='{fill_hex}' stroke='{stroke_hex}' stroke-width='4'/>"
    elif shape == "Diamond":
        body = f"<path d='M32 4 L60 32 L32 60 L4 32 Z' fill='{fill_hex}' stroke='{stroke_hex}' stroke-width='4'/>"
    elif shape == "Triangle":
        body = f"<path d='M32 5 L60 58 L4 58 Z' fill='{fill_hex}' stroke='{stroke_hex}' stroke-width='4'/>"
    else:
        body = f"<path d='M32 4 C18 4 7 15 7 29 C7 49 32 62 32 62 C32 62 57 49 57 29 C57 15 46 4 32 4 Z' fill='{fill_hex}' stroke='{stroke_hex}' stroke-width='4'/><circle cx='32' cy='29' r='9' fill='white' fill-opacity='0.85'/>"
    svg = f"<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 64 64'>{body}</svg>"
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def calculate_view_state(df: pd.DataFrame) -> pdk.ViewState:
    return pdk.ViewState(
        latitude=float(df["stop_lat"].mean()),
        longitude=float(df["stop_lon"].mean()),
        zoom=10,
        pitch=0,
    )


def build_deck_chart(df: pd.DataFrame, taxonomy: list[dict[str, Any]], visualization: dict[str, Any]) -> pdk.Deck:
    map_df = df.dropna(subset=["stop_lat", "stop_lon"]).copy()
    field, colors = color_lookup(map_df, taxonomy, visualization)
    map_df["marker_color"] = map_df.apply(lambda row: marker_color(row, field, colors), axis=1)
    marker_size = int(visualization.get("marker_size", 7) or 7)
    shape = visualization.get("marker_shape", "Circle")
    if shape == "Circle":
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            id="stops_layer",
            get_position="[stop_lon, stop_lat]",
            get_fill_color="marker_color",
            get_radius=marker_size,
            radius_units="pixels",
            radius_min_pixels=4,
            radius_max_pixels=48,
            opacity=float(visualization.get("marker_opacity", 0.82) or 0.82),
            stroked=True,
            get_line_color=hex_to_rgb(visualization.get("marker_stroke_color", "#141414")),
            line_width_min_pixels=int(visualization.get("marker_stroke_width", 1) or 1),
            pickable=True,
            auto_highlight=True,
        )
    else:
        stroke = visualization.get("marker_stroke_color", "#141414")
        map_df["icon_data"] = map_df["marker_color"].apply(
            lambda color: {"url": marker_svg(shape, color, stroke), "width": 64, "height": 64, "anchorY": 64}
        )
        map_df["icon_size"] = marker_size * 4
        layer = pdk.Layer(
            "IconLayer",
            data=map_df,
            id="stops_layer",
            get_icon="icon_data",
            get_position="[stop_lon, stop_lat]",
            get_size="icon_size",
            size_units="pixels",
            size_min_pixels=16,
            size_max_pixels=96,
            pickable=True,
            auto_highlight=True,
        )
    return pdk.Deck(
        initial_view_state=calculate_view_state(map_df),
        layers=[*build_gis_overlay_layers(visualization), layer],
        map_style=MAP_STYLES.get(visualization.get("map_style", "Light"), pdk.map_styles.CARTO_LIGHT),
        tooltip={"text": build_tooltip_text(map_df, visualization)},
    )


def filter_unlabeled_stops(df: pd.DataFrame, show_unlabeled: bool) -> pd.DataFrame:
    if show_unlabeled or "shading" not in df.columns:
        return df
    return df[df["shading"] != "Needs Review"].copy()


def split_route_values(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none"}:
        return []
    return [route.strip() for route in re.split(r"[;,|]+", text) if route.strip()]


def route_filter_options(df: pd.DataFrame) -> list[str]:
    if "routes" not in df.columns:
        return []
    routes: set[str] = set()
    for value in df["routes"].dropna():
        routes.update(split_route_values(value))
    return sorted(routes, key=lambda route: (len(route), route.lower()))


def filter_label(column: str) -> str:
    return FILTER_FIELD_LABELS.get(column, column.replace("_", " ").title())


def categorical_filter_options(df: pd.DataFrame, column: str) -> list[str]:
    if column not in df.columns:
        return []
    values = df[column].dropna().astype(str).str.strip()
    values = values[(values != "") & (values.str.lower() != "nan")]
    return sorted(values.unique().tolist())


def numeric_filter_bounds(df: pd.DataFrame, column: str) -> tuple[float, float] | None:
    if column not in df.columns:
        return None
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    values = values[values.apply(math.isfinite)]
    if values.empty:
        return None
    low = float(values.min())
    high = float(values.max())
    if math.isclose(low, high):
        return None
    return low, high


def destination_columns(df: pd.DataFrame) -> list[str]:
    return [column for column in DESTINATION_FILTER_COLUMNS if column in df.columns]


def current_map_filters(df: pd.DataFrame, key_prefix: str) -> dict[str, Any]:
    filters: dict[str, Any] = {
        "show_unlabeled": bool(st.session_state.get(f"{key_prefix}_show_unlabeled_stops", True)),
        "search_query": str(st.session_state.get(f"{key_prefix}_stop_search", "") or ""),
        "selected_routes": [
            route
            for route in st.session_state.get(f"{key_prefix}_route_filter", [])
            if route in route_filter_options(df)
        ],
        "categorical": {},
        "numeric": {},
        "destination_query": str(st.session_state.get(f"{key_prefix}_destination_filter", "") or ""),
    }
    for column in CATEGORICAL_MAP_FILTERS:
        options = categorical_filter_options(df, column)
        selected = st.session_state.get(f"{key_prefix}_{column}_filter", [])
        filters["categorical"][column] = [value for value in selected if value in options]
    for column in NUMERIC_MAP_FILTERS:
        bounds = numeric_filter_bounds(df, column)
        if bounds is None:
            continue
        selected = st.session_state.get(f"{key_prefix}_{column}_range", bounds)
        filters["numeric"][column] = {"selected": selected, "bounds": bounds}
    return filters


def render_map_filter_controls(df: pd.DataFrame, key_prefix: str) -> dict[str, Any]:
    with st.expander("Map filters", expanded=True):
        primary_cols = st.columns([1, 2, 2])
        primary_cols[0].toggle(
            "Show unlabeled bus stops",
            value=True,
            key=f"{key_prefix}_show_unlabeled_stops",
        )
        primary_cols[1].text_input(
            "Search stop name or ID",
            placeholder="Stop name or ID",
            key=f"{key_prefix}_stop_search",
        )
        primary_cols[2].multiselect(
            "Filter routes",
            route_filter_options(df),
            key=f"{key_prefix}_route_filter",
        )

        categorical_columns = [
            column for column in CATEGORICAL_MAP_FILTERS if categorical_filter_options(df, column)
        ]
        if categorical_columns:
            category_cols = st.columns(len(categorical_columns))
            for index, column in enumerate(categorical_columns):
                category_cols[index].multiselect(
                    filter_label(column),
                    categorical_filter_options(df, column),
                    key=f"{key_prefix}_{column}_filter",
                )

        numeric_columns = [
            column for column in NUMERIC_MAP_FILTERS if numeric_filter_bounds(df, column) is not None
        ]
        if numeric_columns:
            numeric_cols = st.columns(min(3, len(numeric_columns)))
            for index, column in enumerate(numeric_columns):
                bounds = numeric_filter_bounds(df, column)
                if bounds is None:
                    continue
                low, high = bounds
                step = max((high - low) / 100.0, 0.01)
                numeric_cols[index % len(numeric_cols)].slider(
                    filter_label(column),
                    min_value=low,
                    max_value=high,
                    value=(low, high),
                    step=step,
                    key=f"{key_prefix}_{column}_range",
                )

        if destination_columns(df):
            st.text_input(
                "Filter destinations",
                placeholder="Destination or nearby place",
                key=f"{key_prefix}_destination_filter",
            )
    return current_map_filters(df, key_prefix)


def filter_map_stops(
    df: pd.DataFrame,
    search_query: str = "",
    selected_routes: list[str] | None = None,
    filters: dict[str, Any] | None = None,
) -> pd.DataFrame:
    filtered = df.copy()
    selected_routes = selected_routes or []
    filters = filters or {}
    query = str(search_query or "").strip().lower()
    if query:
        searchable_columns = [column for column in ["stop_id", "stop_name", "routes"] if column in filtered.columns]
        if searchable_columns:
            search_blob = filtered[searchable_columns].fillna("").astype(str).agg(" ".join, axis=1).str.lower()
            filtered = filtered[search_blob.str.contains(re.escape(query), na=False)]
    if selected_routes and "routes" in filtered.columns:
        wanted = set(selected_routes)
        route_mask = filtered["routes"].apply(lambda value: bool(wanted.intersection(split_route_values(value))))
        filtered = filtered[route_mask]
    for column, selected in filters.get("categorical", {}).items():
        if selected and column in filtered.columns:
            values = filtered[column].fillna("").astype(str).str.strip()
            filtered = filtered[values.isin(set(selected))]
    for column, config in filters.get("numeric", {}).items():
        if column not in filtered.columns:
            continue
        selected = config.get("selected")
        bounds = config.get("bounds")
        if not selected or not bounds:
            continue
        low, high = float(selected[0]), float(selected[1])
        bound_low, bound_high = float(bounds[0]), float(bounds[1])
        if math.isclose(low, bound_low) and math.isclose(high, bound_high):
            continue
        values = pd.to_numeric(filtered[column], errors="coerce")
        filtered = filtered[values.between(low, high, inclusive="both")]
    destination_query = str(filters.get("destination_query", "") or "").strip().lower()
    if destination_query and destination_columns(filtered):
        destination_blob = (
            filtered[destination_columns(filtered)]
            .fillna("")
            .astype(str)
            .agg(" ".join, axis=1)
            .str.lower()
        )
        filtered = filtered[destination_blob.str.contains(re.escape(destination_query), na=False)]
    return filtered.copy()


def selected_stop_id_from_map_selection(selection_event: Any, df: pd.DataFrame) -> str | None:
    if selection_event is None:
        return None
    selection = getattr(selection_event, "selection", None)
    if selection is None and isinstance(selection_event, dict):
        selection = selection_event.get("selection")
    if selection is None:
        return None

    objects = getattr(selection, "objects", None)
    if objects is None and isinstance(selection, dict):
        objects = selection.get("objects")
    if isinstance(objects, dict):
        layer_objects = objects.get("stops_layer")
        if layer_objects:
            stop_id = layer_objects[0].get("stop_id")
            if stop_id is not None:
                return str(stop_id)

    indices = getattr(selection, "indices", None)
    if indices is None and isinstance(selection, dict):
        indices = selection.get("indices")
    if isinstance(indices, dict):
        layer_indices = indices.get("stops_layer")
        if layer_indices:
            index = int(layer_indices[0])
            if 0 <= index < len(df):
                return str(df.iloc[index].get("stop_id", ""))
    return None


def stop_picker_label(row: pd.Series) -> str:
    stop_id = str(row.get("stop_id", "")).strip()
    stop_name = str(row.get("stop_name", "")).strip() or "Unnamed stop"
    routes = str(row.get("routes", "")).strip()
    suffix = f" | routes {routes}" if routes else ""
    return f"{stop_name} ({stop_id}){suffix}"


def render_stop_detail_workflow(df: pd.DataFrame, visualization: dict[str, Any], key_prefix: str) -> None:
    if df.empty:
        st.info("No stop is available for the active map filters.")
        return

    options = df.reset_index(drop=True)
    stop_ids = options["stop_id"].astype(str).tolist() if "stop_id" in options.columns else []
    selected_key = f"{key_prefix}_selected_stop_id"
    selected_stop_id = str(st.session_state.get(selected_key, "") or "")
    if selected_stop_id not in stop_ids and stop_ids:
        selected_stop_id = stop_ids[0]
        st.session_state[selected_key] = selected_stop_id

    selected_index = stop_ids.index(selected_stop_id) if selected_stop_id in stop_ids else 0
    picker_key = f"{key_prefix}_stop_picker"
    current_picker = st.session_state.get(picker_key)
    if (
        not isinstance(current_picker, int)
        or current_picker < 0
        or current_picker >= len(options)
        or stop_ids[int(current_picker)] != selected_stop_id
    ):
        st.session_state[picker_key] = selected_index
    picked_index = st.selectbox(
        "Selected stop",
        range(len(options)),
        index=selected_index,
        format_func=lambda index: stop_picker_label(options.iloc[int(index)]),
        key=picker_key,
    )
    selected_stop = options.iloc[int(picked_index)]
    st.session_state[selected_key] = str(selected_stop.get("stop_id", ""))
    st.markdown(f"**{stop_picker_label(selected_stop)}**")

    st.markdown("#### Stop Details")
    priority = pd.to_numeric(pd.Series([selected_stop.get("priority_score")]), errors="coerce").iloc[0]
    summary_rows = [
        ("Shade", str(selected_stop.get("shading", "Unknown") or "Unknown")),
        ("Review", str(selected_stop.get("review_status", "Unknown") or "Unknown")),
        ("Priority", "N/A" if pd.isna(priority) else f"{float(priority):.2f}"),
    ]
    for label, value in summary_rows:
        st.markdown(f"**{label}**  \n{value}")

    detail_columns = []
    for column in get_selected_display_columns(options, visualization) + [
        "shade_coverage",
        "shade_sources",
        "routes",
        "stop_lat",
        "stop_lon",
    ]:
        if column in options.columns and column not in detail_columns:
            detail_columns.append(column)
    detail_rows = [{"Field": column.replace("_", " ").title(), "Value": selected_stop.get(column, "")} for column in detail_columns]
    for row in detail_rows:
        value = str(row["Value"] if pd.notna(row["Value"]) else "")
        st.markdown(f"**{row['Field']}**  \n{value}")


def render_metric_cards(df: pd.DataFrame) -> None:
    no_shade = int((df.get("shading", pd.Series(dtype=str)) == "No Shade").sum()) if not df.empty else 0
    needs_review = int((df.get("shading", pd.Series(dtype=str)) == "Needs Review").sum()) if not df.empty else 0
    accepted = int((df.get("review_status", pd.Series(dtype=str)) == "Accepted").sum()) if not df.empty else 0
    cols = st.columns(4)
    cols[0].metric("Stops", f"{len(df):,}")
    cols[1].metric("No shade", f"{no_shade:,}")
    cols[2].metric("Needs review", f"{needs_review:,}")
    cols[3].metric("Accepted", f"{accepted:,}")


def chart_data(df: pd.DataFrame, chart: dict[str, Any]) -> tuple[pd.DataFrame, str, str]:
    x_field = chart.get("x", "shading")
    y_field = chart.get("y", RECORD_COUNT_FIELD)
    aggregation = chart.get("aggregation", "Count")
    if x_field not in df.columns:
        return pd.DataFrame(), "", ""
    if y_field == RECORD_COUNT_FIELD or aggregation == "Count":
        data = df.groupby(x_field, dropna=False).size().reset_index(name="stops")
        return data, x_field, "stops"
    if y_field not in df.columns:
        return pd.DataFrame(), "", ""
    working = df.loc[:, [x_field, y_field]].copy()
    working[y_field] = pd.to_numeric(working[y_field], errors="coerce")
    grouped = working.groupby(x_field, dropna=False)[y_field]
    if aggregation == "Average":
        data = grouped.mean().reset_index()
    elif aggregation == "Maximum":
        data = grouped.max().reset_index()
    elif aggregation == "Minimum":
        data = grouped.min().reset_index()
    else:
        data = grouped.sum().reset_index()
    return data, x_field, y_field


def render_custom_charts(df: pd.DataFrame, visualization: dict[str, Any]) -> None:
    charts = visualization.get("custom_charts") or []
    if not charts:
        return
    columns = st.columns(2)
    for index, chart in enumerate(charts):
        data, x_field, y_field = chart_data(df, chart)
        if data.empty:
            continue
        with columns[index % 2]:
            st.markdown(f"#### {chart.get('title') or 'Chart'}")
            chart_type = chart.get("chart_type", "Bar")
            if chart_type == "Line":
                st.line_chart(data, x=x_field, y=y_field)
            elif chart_type == "Area":
                st.area_chart(data, x=x_field, y=y_field)
            elif chart_type == "Scatter":
                st.scatter_chart(data, x=x_field, y=y_field)
            else:
                st.bar_chart(data, x=x_field, y=y_field)


def has_column_data(df: pd.DataFrame, column: str) -> bool:
    if column not in df.columns:
        return False
    values = df[column].dropna().astype(str).str.strip()
    return bool(values.ne("").any())


def available_dashboard_sections(df: pd.DataFrame) -> list[str]:
    sections = []
    for label, columns in METRIC_REQUIREMENTS.items():
        if all(has_column_data(df, column) for column in columns):
            sections.append(label)
    return sections


def selected_dashboard_sections(df: pd.DataFrame, visualization: dict[str, Any]) -> list[str]:
    available = available_dashboard_sections(df)
    selected = [label for label in visualization.get("metric_cards", []) if label in available]
    return selected or available


def normalized_category_series(df: pd.DataFrame, column: str) -> pd.Series:
    return df[column].fillna("(blank)").astype(str).str.strip().replace("", "(blank)")


def count_by_field(df: pd.DataFrame, column: str, count_name: str = "stops") -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return pd.DataFrame(columns=[column, count_name])
    working = df.copy()
    working[column] = normalized_category_series(working, column)
    return working.groupby(column, dropna=False).size().reset_index(name=count_name).sort_values(count_name, ascending=False)


def split_routes_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "routes" not in df.columns:
        return pd.DataFrame()
    rows = []
    for _, row in df.iterrows():
        for route in split_route_values(row.get("routes")):
            rows.append({"route": route, "shading": str(row.get("shading", "Unknown") or "Unknown")})
    return pd.DataFrame(rows)


def render_route_shade_dashboard(df: pd.DataFrame) -> None:
    routes = split_routes_table(df)
    if routes.empty:
        return
    grouped = routes.groupby(["route", "shading"], dropna=False).size().reset_index(name="stops")
    top_routes = grouped.groupby("route")["stops"].sum().sort_values(ascending=False).head(25).index
    grouped = grouped[grouped["route"].isin(top_routes)]
    pivot = grouped.pivot_table(index="route", columns="shading", values="stops", fill_value=0, aggfunc="sum")
    st.markdown("#### Shade By Route")
    st.bar_chart(pivot)
    st.dataframe(grouped.sort_values(["stops", "route"], ascending=[False, True]), use_container_width=True, hide_index=True)


def render_grouped_shade_dashboard(df: pd.DataFrame, group_column: str, title: str) -> None:
    if df.empty or group_column not in df.columns or "shading" not in df.columns:
        return
    working = df.loc[:, [group_column, "shading"]].copy()
    working[group_column] = normalized_category_series(working, group_column)
    working["shading"] = normalized_category_series(working, "shading")
    grouped = working.groupby([group_column, "shading"], dropna=False).size().reset_index(name="stops")
    top_groups = grouped.groupby(group_column)["stops"].sum().sort_values(ascending=False).head(25).index
    grouped = grouped[grouped[group_column].isin(top_groups)]
    if grouped.empty:
        return
    pivot = grouped.pivot_table(index=group_column, columns="shading", values="stops", fill_value=0, aggfunc="sum")
    st.markdown(f"#### {title}")
    st.bar_chart(pivot)
    st.dataframe(grouped.sort_values(["stops", group_column], ascending=[False, True]), use_container_width=True, hide_index=True)


def render_numeric_by_shade_dashboard(df: pd.DataFrame, numeric_column: str, value_label: str, title: str) -> None:
    if df.empty or numeric_column not in df.columns or "shading" not in df.columns:
        return
    working = df.loc[:, ["shading", numeric_column]].copy()
    working["shading"] = normalized_category_series(working, "shading")
    working[numeric_column] = pd.to_numeric(working[numeric_column], errors="coerce")
    working = working.dropna(subset=[numeric_column])
    if working.empty:
        return
    summary = (
        working.groupby("shading", dropna=False)[numeric_column]
        .agg(**{f"Mean {value_label}": "mean", f"Median {value_label}": "median", "Stops": "count"})
        .reset_index()
        .sort_values(f"Mean {value_label}", ascending=False)
    )
    st.markdown(f"#### {title}")
    st.bar_chart(summary, x="shading", y=f"Mean {value_label}")
    st.dataframe(summary, use_container_width=True, hide_index=True)


def render_issue_analytics_dashboard(df: pd.DataFrame, visualization: dict[str, Any], raw_labels: pd.DataFrame) -> None:
    selected = selected_dashboard_sections(df, visualization)
    if df.empty:
        st.info("No stops match the active filters.")
        return

    st.markdown("#### Summary Statistics")
    render_metric_cards(df)

    summary_cols = st.columns(2)
    if "Shade distribution" in selected and "shading" in df.columns:
        with summary_cols[0]:
            st.markdown("#### Shade Distribution")
            shade_counts = count_by_field(df, "shading")
            st.bar_chart(shade_counts, x="shading", y="stops")
            st.dataframe(shade_counts, use_container_width=True, hide_index=True)
    if "Review status" in selected and "review_status" in df.columns:
        with summary_cols[1]:
            st.markdown("#### Review Status")
            review_counts = count_by_field(df, "review_status")
            st.bar_chart(review_counts, x="review_status", y="stops")
            st.dataframe(review_counts, use_container_width=True, hide_index=True)

    queue_rows = []
    if "Stops without shade" in selected and "shading" in df.columns:
        queue_rows.append({"Queue": "Stops without shade", "Stops": int(normalized_category_series(df, "shading").eq("No Shade").sum())})
    if "Stops requiring review" in selected and "shading" in df.columns:
        queue_rows.append({"Queue": "Stops requiring review", "Stops": int(normalized_category_series(df, "shading").eq("Needs Review").sum())})
    if queue_rows:
        st.markdown("#### Action Queues")
        st.dataframe(pd.DataFrame(queue_rows), use_container_width=True, hide_index=True)

    if "Agreement metrics" in selected:
        render_agreement_metrics(raw_labels)
    if "Shade by route" in selected:
        render_route_shade_dashboard(df)
    if "Shade by neighborhood" in selected:
        render_grouped_shade_dashboard(df, "municipality", "Shade By Neighborhood")
    if "Shade vs ridership" in selected:
        render_numeric_by_shade_dashboard(df, "ridership", "Ridership", "Shade Vs Ridership")
    if "Shade vs heat vulnerability" in selected:
        render_numeric_by_shade_dashboard(df, "heat_vulnerability_index", "Heat Vulnerability", "Shade Vs Heat Vulnerability")
    if "Priority stops" in selected and "priority_score" in df.columns:
        st.markdown("#### Highest Priority Stops")
        priority = df.sort_values("priority_score", ascending=False).head(20)
        columns = get_selected_display_columns(priority, visualization)
        st.dataframe(priority.loc[:, columns], use_container_width=True, hide_index=True)


def render_methodology(config: dict[str, Any]) -> None:
    project = config.get("project", {})
    methodology = config.get("methodology", {})
    st.title(methodology.get("title") or project.get("name") or "Bus Stop Shade Study")
    st.markdown(f"### {methodology.get('summary', '')}")
    st.caption(
        f"{project.get('agency', 'Transit agency')} | {project.get('region', 'Region')} | "
        f"dataset v{project.get('dataset_version', 'draft')} | methodology v{project.get('methodology_version', 'draft')}"
    )
    sections = [
        ("Rationale", methodology.get("purpose", "")),
        ("Shade Assessment Method", methodology.get("shade_method", "")),
        ("Data Sources", methodology.get("data_sources", "")),
        ("Contributors", methodology.get("contributors", "")),
        ("Known Limitations", methodology.get("limitations", "")),
        ("Bibliography", methodology.get("bibliography", "")),
        ("Release History", methodology.get("release_history", "")),
        ("Citation", methodology.get("citation", "")),
    ]
    for title, body in sections:
        if str(body or "").strip():
            st.markdown(f"## {title}")
            st.markdown(body)
    taxonomy = config.get("taxonomy", [])
    if taxonomy:
        st.markdown("## Shade Taxonomy")
        st.dataframe(pd.DataFrame(taxonomy), use_container_width=True, hide_index=True)


def dataframe_to_geojson(df: pd.DataFrame) -> str:
    features = []
    for _, row in df.iterrows():
        properties = row.drop(labels=["stop_lat", "stop_lon"], errors="ignore").to_dict()
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(row["stop_lon"]), float(row["stop_lat"])]},
                "properties": {key: (None if pd.isna(value) else value) for key, value in properties.items()},
            }
        )
    return json.dumps({"type": "FeatureCollection", "features": features}, indent=2)


def clean_label_values(labels: pd.DataFrame, label_column: str = "shade_category") -> pd.DataFrame:
    if labels.empty or label_column not in labels.columns or "stop_id" not in labels.columns:
        return pd.DataFrame(columns=["stop_id", label_column])
    clean = labels.copy()
    clean["stop_id"] = clean["stop_id"].fillna("").astype(str).str.strip()
    clean[label_column] = clean[label_column].fillna("").astype(str).str.strip()
    return clean[(clean["stop_id"] != "") & (clean[label_column] != "")]


def majority_label_table(labels: pd.DataFrame, label_column: str = "shade_category") -> pd.DataFrame:
    clean = clean_label_values(labels, label_column)
    rows = []
    for stop_id, group in clean.groupby("stop_id", sort=True):
        counts = group[label_column].value_counts()
        max_count = int(counts.max())
        winners = sorted(counts[counts == max_count].index.astype(str).tolist())
        total = int(counts.sum())
        rows.append({
            "stop_id": stop_id,
            "majority_label": "; ".join(winners),
            "label_count": total,
            "majority_count": max_count,
            "agreement_pct": round(max_count / total * 100, 1) if total else 0.0,
            "disagreement_flag": len(counts) > 1,
            "tied_majority": len(winners) > 1,
        })
    return pd.DataFrame(rows)


def label_rater_key(row: pd.Series) -> str:
    labeler_id = str(row.get("labeler_id", "") or "").strip()
    if labeler_id:
        return labeler_id
    role = str(row.get("labeler_role", "") or "").strip()
    source = str(row.get("source", "") or "").strip()
    return f"{role or 'unknown'}:{source or 'manual'}"


def latest_labels_by_rater(labels: pd.DataFrame, label_column: str = "shade_category") -> pd.DataFrame:
    clean = clean_label_values(labels, label_column)
    if clean.empty:
        return pd.DataFrame(columns=["stop_id", "rater", label_column])
    clean = clean.copy()
    clean["rater"] = clean.apply(label_rater_key, axis=1)
    if "created_at" in clean.columns:
        clean = clean.sort_values("created_at")
    return clean.drop_duplicates(subset=["stop_id", "rater"], keep="last")


def cohen_kappa_for_pair(left: pd.Series, right: pd.Series, categories: list[str]) -> float | None:
    paired = pd.DataFrame({"left": left, "right": right}).dropna()
    if paired.empty:
        return None
    observed = float((paired["left"] == paired["right"]).mean())
    total = len(paired)
    expected = sum((paired["left"].eq(category).sum() / total) * (paired["right"].eq(category).sum() / total) for category in categories)
    if math.isclose(1.0 - expected, 0.0):
        return 1.0 if math.isclose(observed, 1.0) else None
    return (observed - expected) / (1.0 - expected)


def average_pairwise_cohen_kappa(labels: pd.DataFrame) -> tuple[float | None, int]:
    latest = latest_labels_by_rater(labels)
    if latest.empty or latest["rater"].nunique() < 2:
        return None, 0
    matrix = latest.pivot(index="stop_id", columns="rater", values="shade_category")
    categories = sorted(latest["shade_category"].dropna().astype(str).unique().tolist())
    kappas = []
    raters = list(matrix.columns)
    for left_index, left_rater in enumerate(raters):
        for right_rater in raters[left_index + 1:]:
            paired = matrix[[left_rater, right_rater]].dropna()
            if len(paired) < 2:
                continue
            kappa = cohen_kappa_for_pair(paired[left_rater], paired[right_rater], categories)
            if kappa is not None:
                kappas.append(kappa)
    return (float(sum(kappas) / len(kappas)), len(kappas)) if kappas else (None, 0)


def category_count_matrix(labels: pd.DataFrame) -> pd.DataFrame:
    clean = clean_label_values(labels)
    return pd.crosstab(clean["stop_id"], clean["shade_category"]) if not clean.empty else pd.DataFrame()


def fleiss_kappa(labels: pd.DataFrame) -> float | None:
    counts = category_count_matrix(labels)
    if counts.empty:
        return None
    counts = counts[counts.sum(axis=1) >= 2]
    if counts.empty:
        return None
    item_totals = counts.sum(axis=1)
    total_assignments = float(item_totals.sum())
    p_i = ((counts.pow(2).sum(axis=1) - item_totals) / (item_totals * (item_totals - 1))).fillna(0)
    p_bar = float((p_i * item_totals / total_assignments).sum())
    p_e = float((counts.sum(axis=0) / total_assignments).pow(2).sum())
    if math.isclose(1.0 - p_e, 0.0):
        return 1.0 if math.isclose(p_bar, 1.0) else None
    return (p_bar - p_e) / (1.0 - p_e)


def krippendorff_alpha_nominal(labels: pd.DataFrame) -> float | None:
    counts = category_count_matrix(labels)
    if counts.empty:
        return None
    counts = counts[counts.sum(axis=1) >= 2]
    if counts.empty:
        return None
    item_totals = counts.sum(axis=1)
    observed = sum(float((row * (float(item_totals.loc[stop_id]) - row)).sum() / (float(item_totals.loc[stop_id]) - 1)) for stop_id, row in counts.iterrows()) / float(item_totals.sum())
    category_totals = counts.sum(axis=0)
    total = float(category_totals.sum())
    if total <= 1:
        return None
    expected = float((category_totals * (total - category_totals)).sum() / (total - 1) / total)
    if math.isclose(expected, 0.0):
        return 1.0 if math.isclose(observed, 0.0) else None
    return 1.0 - (observed / expected)


def format_metric_value(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "Not enough data"
    return f"{float(value):.3f}"


def render_agreement_metrics(labels: pd.DataFrame) -> None:
    st.markdown("#### Agreement Metrics")
    if labels.empty:
        st.info("No raw labels were included with this published study.")
        return
    majority = majority_label_table(labels)
    cohen, cohen_pairs = average_pairwise_cohen_kappa(labels)
    summary = pd.DataFrame([
        ("Stops with labels", int(majority["stop_id"].nunique()) if not majority.empty else 0),
        ("Stops with 2+ labels", int((majority["label_count"] >= 2).sum()) if not majority.empty else 0),
        ("Stops with disagreement", int(majority["disagreement_flag"].sum()) if not majority.empty else 0),
        ("Mean majority agreement", f"{float(majority['agreement_pct'].mean()):.1f}%" if not majority.empty else "Not enough data"),
        ("Average pairwise Cohen kappa", format_metric_value(cohen)),
        ("Cohen rater pairs compared", cohen_pairs),
        ("Fleiss kappa", format_metric_value(fleiss_kappa(labels))),
        ("Krippendorff alpha", format_metric_value(krippendorff_alpha_nominal(labels))),
    ], columns=["Metric", "Value"])
    st.dataframe(summary, use_container_width=True, hide_index=True)
    if not majority.empty:
        st.dataframe(majority.sort_values(["disagreement_flag", "agreement_pct", "stop_id"], ascending=[False, True, True]), use_container_width=True, hide_index=True)


def main() -> None:
    config, stops, raw_labels = load_study()
    project = config.get("project", {})
    methodology = config.get("methodology", {})
    visualization = config.get("visualization", {})
    taxonomy = config.get("taxonomy", [])

    st.set_page_config(page_title=project.get("name", "Shade Study"), layout="wide")
    st.title(project.get("name", "Shade Study"))
    st.markdown(f"### {methodology.get('summary', '')}")
    st.caption(f"{project.get('agency', '')} | {project.get('region', '')} | dataset v{project.get('dataset_version', 'draft')}")

    filters = current_map_filters(stops, "published")
    visible_stops = filter_map_stops(
        filter_unlabeled_stops(stops, filters["show_unlabeled"]),
        filters["search_query"],
        filters["selected_routes"],
        filters,
    )
    render_metric_cards(visible_stops)

    tabs = st.tabs(["Map", "Analytics", "Methodology", "Downloads"])
    with tabs[0]:
        if visible_stops.empty:
            st.info("No stops match the current visibility settings.")
        else:
            map_cols = st.columns([2, 1])
            with map_cols[0]:
                map_selection = st.pydeck_chart(
                    build_deck_chart(visible_stops, taxonomy, visualization),
                    use_container_width=True,
                    on_select="rerun",
                    selection_mode="single-object",
                    key="published_stops_map",
                )
                selected_stop_id = selected_stop_id_from_map_selection(map_selection, visible_stops)
                if selected_stop_id:
                    st.session_state["published_selected_stop_id"] = selected_stop_id
            with map_cols[1]:
                with st.container(height=STOP_DETAIL_PANEL_HEIGHT, border=False):
                    render_stop_detail_workflow(visible_stops, visualization, "published")
        st.caption(f"{len(visible_stops):,} of {len(stops):,} stops match the active map filters.")
        render_map_filter_controls(stops, "published")
        if visualization.get("show_legend", True) and taxonomy:
            legend = pd.DataFrame(taxonomy)
            columns = [column for column in ["name", "description", "color"] if column in legend.columns]
            st.dataframe(legend.loc[:, columns], use_container_width=True, hide_index=True)
    with tabs[1]:
        render_issue_analytics_dashboard(visible_stops, visualization, raw_labels)
        render_custom_charts(visible_stops, visualization)
    with tabs[2]:
        render_methodology(config)
    with tabs[3]:
        if visualization.get("show_downloads", True):
            st.download_button("Download stops CSV", stops.to_csv(index=False).encode("utf-8"), "shade_study_stops.csv", "text/csv")
            st.download_button("Download stops GeoJSON", dataframe_to_geojson(stops).encode("utf-8"), "shade_study_stops.geojson", "application/geo+json")
            st.download_button("Download study configuration", json.dumps(config, indent=2).encode("utf-8"), "shade_study_config.json", "application/json")
            if not raw_labels.empty:
                st.download_button("Download raw labels CSV", raw_labels.to_csv(index=False).encode("utf-8"), "shade_study_raw_labels.csv", "text/csv")


if __name__ == "__main__":
    main()
'''


def deploy_readme(repo_name: str, project: dict[str, Any]) -> str:
    app_name = project.get("name", "Shade Study")
    return f"""# {app_name}

This repository was generated by Shade Study Builder. It contains a public Streamlit app rendered from the builder state at export time.

## Files

- `app.py`: public Streamlit app.
- `shade_study_stops.csv`: published stop dataset.
- `shade_study_raw_labels.csv`: raw submitted labels, included when labels have been collected.
- `shade_study_config.json`: project metadata, methodology, taxonomy, visualization settings, uploaded GIS overlays, and import log.
- `requirements.txt`: Python dependencies for Streamlit deployment.

## Publish To GitHub

Either create a new GitHub repository named `{repo_name}` and upload these files, or run:

```powershell
./deploy_to_github.ps1 -RepositoryName "{repo_name}"
```

The script requires Git and the GitHub CLI (`gh`) with an authenticated account.

## Run Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud

After the repository is on GitHub, create a Streamlit Community Cloud app with:

- repository: `{repo_name}`
- branch: `main`
- main file path: `app.py`
"""


def deploy_script(repo_name: str) -> str:
    return f"""param(
    [string]$RepositoryName = "{repo_name}",
    [ValidateSet("public", "private")]
    [string]$Visibility = "public"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {{
    throw "Git is required before publishing."
}}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {{
    throw "GitHub CLI is required before publishing. Install gh and run gh auth login."
}}

if (-not (Test-Path ".git")) {{
    git init
    git branch -M main
}}

git add .
git commit -m "Publish shade study app"
gh repo create $RepositoryName --$Visibility --source=. --remote=origin --push
"""


def build_github_deploy_bundle(repo_name: str) -> bytes:
    stops = st.session_state["stops"].copy()
    stops["priority_score"] = calculate_priority_scores(stops, st.session_state["visualization"]["priority_weights"])
    config_json = study_config_json()
    raw_labels = active_raw_labels()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("app.py", published_app_source())
        bundle.writestr("shade_study_stops.csv", stops.to_csv(index=False))
        bundle.writestr("shade_study_config.json", config_json)
        if not raw_labels.empty:
            bundle.writestr("shade_study_raw_labels.csv", raw_labels.to_csv(index=False))
        bundle.writestr("requirements.txt", "streamlit>=1.57,<2\npandas>=2,<4\npydeck>=0.8,<1\n")
        bundle.writestr(".streamlit/config.toml", "[server]\nheadless = true\n\n[browser]\ngatherUsageStats = false\n")
        bundle.writestr(".gitignore", "__pycache__/\n*.pyc\n.streamlit/secrets.toml\n")
        bundle.writestr("README.md", deploy_readme(repo_name, st.session_state["project"]))
        bundle.writestr("deploy_to_github.ps1", deploy_script(repo_name))
    return buffer.getvalue()


def validation_summary(df: pd.DataFrame) -> pd.DataFrame:
    checks = [
        ("Stops ready for mapping", len(df)),
        ("Duplicate stop IDs removed", int(df["stop_id"].duplicated().sum()) if "stop_id" in df else 0),
        ("Missing coordinates", int(df[["stop_lat", "stop_lon"]].isna().any(axis=1).sum()) if not df.empty else 0),
        ("Stops needing review", int((df.get("shading") == "Needs Review").sum()) if not df.empty else 0),
        ("Stops with route metadata", int((df.get("routes", "") != "").sum()) if not df.empty else 0),
    ]
    return pd.DataFrame(checks, columns=["Check", "Value"])


def stop_picker_label(row: pd.Series) -> str:
    stop_id = str(row.get("stop_id", "")).strip()
    stop_name = str(row.get("stop_name", "")).strip() or "Unnamed stop"
    routes = str(row.get("routes", "")).strip()
    suffix = f" | routes {routes}" if routes else ""
    return f"{stop_name} ({stop_id}){suffix}"


def taxonomy_names(taxonomy: list[dict[str, Any]]) -> list[str]:
    names = [str(item.get("name", "")).strip() for item in taxonomy if str(item.get("name", "")).strip()]
    return names or ["Needs Review"]


def label_source_code(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "manual").strip().lower()).strip("_") or "manual"


def raw_label_summary(labels: pd.DataFrame, stops: pd.DataFrame) -> pd.DataFrame:
    labeled_stop_count = labels["stop_id"].nunique() if not labels.empty and "stop_id" in labels.columns else 0
    conflicting_stops = 0
    if not labels.empty and {"stop_id", "shade_category"}.issubset(labels.columns):
        category_counts = labels.dropna(subset=["shade_category"]).groupby("stop_id")["shade_category"].nunique()
        conflicting_stops = int((category_counts > 1).sum())
    checks = [
        ("Raw labels stored", len(labels)),
        ("Stops with raw labels", int(labeled_stop_count)),
        ("Stops without raw labels", max(len(stops) - int(labeled_stop_count), 0)),
        ("Stops with conflicting raw labels", conflicting_stops),
    ]
    return pd.DataFrame(checks, columns=["Check", "Value"])


def clean_label_values(labels: pd.DataFrame, label_column: str = "shade_category") -> pd.DataFrame:
    if labels.empty or label_column not in labels.columns or "stop_id" not in labels.columns:
        return pd.DataFrame(columns=list(labels.columns) if not labels.empty else ["stop_id", label_column])
    clean = labels.copy()
    clean["stop_id"] = clean["stop_id"].fillna("").astype(str).str.strip()
    clean[label_column] = clean[label_column].fillna("").astype(str).str.strip()
    clean = clean[(clean["stop_id"] != "") & (clean[label_column] != "")]
    return clean


def majority_label_table(labels: pd.DataFrame, label_column: str = "shade_category") -> pd.DataFrame:
    clean = clean_label_values(labels, label_column)
    if clean.empty:
        return pd.DataFrame(
            columns=[
                "stop_id",
                "majority_label",
                "label_count",
                "majority_count",
                "agreement_pct",
                "disagreement_flag",
                "tied_majority",
            ]
        )
    rows = []
    for stop_id, group in clean.groupby("stop_id", sort=True):
        counts = group[label_column].value_counts()
        max_count = int(counts.max())
        winners = sorted(counts[counts == max_count].index.astype(str).tolist())
        total = int(counts.sum())
        rows.append(
            {
                "stop_id": stop_id,
                "majority_label": "; ".join(winners),
                "label_count": total,
                "majority_count": max_count,
                "agreement_pct": round(max_count / total * 100, 1) if total else 0.0,
                "disagreement_flag": len(counts) > 1,
                "tied_majority": len(winners) > 1,
            }
        )
    return pd.DataFrame(rows)


def label_rater_key(row: pd.Series) -> str:
    labeler_id = str(row.get("labeler_id", "") or "").strip()
    if labeler_id:
        return labeler_id
    role = str(row.get("labeler_role", "") or "").strip()
    source = str(row.get("source", "") or "").strip()
    return f"{role or 'unknown'}:{source or 'manual'}"


def latest_labels_by_rater(labels: pd.DataFrame, label_column: str = "shade_category") -> pd.DataFrame:
    clean = clean_label_values(labels, label_column)
    if clean.empty:
        return pd.DataFrame(columns=["stop_id", "rater", label_column])
    clean = clean.copy()
    clean["rater"] = clean.apply(label_rater_key, axis=1)
    if "created_at" in clean.columns:
        clean = clean.sort_values("created_at")
    return clean.drop_duplicates(subset=["stop_id", "rater"], keep="last")


def cohen_kappa_for_pair(left: pd.Series, right: pd.Series, categories: list[str]) -> float | None:
    paired = pd.DataFrame({"left": left, "right": right}).dropna()
    if paired.empty:
        return None
    observed = float((paired["left"] == paired["right"]).mean())
    total = len(paired)
    expected = 0.0
    for category in categories:
        expected += (paired["left"].eq(category).sum() / total) * (paired["right"].eq(category).sum() / total)
    if math.isclose(1.0 - expected, 0.0):
        return 1.0 if math.isclose(observed, 1.0) else None
    return (observed - expected) / (1.0 - expected)


def average_pairwise_cohen_kappa(labels: pd.DataFrame, label_column: str = "shade_category") -> tuple[float | None, int]:
    latest = latest_labels_by_rater(labels, label_column)
    if latest.empty or latest["rater"].nunique() < 2:
        return None, 0
    matrix = latest.pivot(index="stop_id", columns="rater", values=label_column)
    categories = sorted(latest[label_column].dropna().astype(str).unique().tolist())
    kappas = []
    raters = list(matrix.columns)
    for left_index, left_rater in enumerate(raters):
        for right_rater in raters[left_index + 1 :]:
            paired = matrix[[left_rater, right_rater]].dropna()
            if len(paired) < 2:
                continue
            kappa = cohen_kappa_for_pair(paired[left_rater], paired[right_rater], categories)
            if kappa is not None:
                kappas.append(kappa)
    if not kappas:
        return None, 0
    return float(sum(kappas) / len(kappas)), len(kappas)


def category_count_matrix(labels: pd.DataFrame, label_column: str = "shade_category") -> pd.DataFrame:
    clean = clean_label_values(labels, label_column)
    if clean.empty:
        return pd.DataFrame()
    return pd.crosstab(clean["stop_id"], clean[label_column])


def fleiss_kappa(labels: pd.DataFrame, label_column: str = "shade_category") -> float | None:
    counts = category_count_matrix(labels, label_column)
    if counts.empty:
        return None
    counts = counts[counts.sum(axis=1) >= 2]
    if counts.empty:
        return None
    item_totals = counts.sum(axis=1)
    total_assignments = float(item_totals.sum())
    p_i = ((counts.pow(2).sum(axis=1) - item_totals) / (item_totals * (item_totals - 1))).fillna(0)
    p_bar = float((p_i * item_totals / total_assignments).sum())
    category_props = counts.sum(axis=0) / total_assignments
    p_e = float(category_props.pow(2).sum())
    if math.isclose(1.0 - p_e, 0.0):
        return 1.0 if math.isclose(p_bar, 1.0) else None
    return (p_bar - p_e) / (1.0 - p_e)


def krippendorff_alpha_nominal(labels: pd.DataFrame, label_column: str = "shade_category") -> float | None:
    counts = category_count_matrix(labels, label_column)
    if counts.empty:
        return None
    counts = counts[counts.sum(axis=1) >= 2]
    if counts.empty:
        return None
    item_totals = counts.sum(axis=1)
    observed_terms = []
    for stop_id, row in counts.iterrows():
        n_i = float(item_totals.loc[stop_id])
        observed_terms.append(float((row * (n_i - row)).sum() / (n_i - 1)))
    observed = sum(observed_terms) / float(item_totals.sum())
    category_totals = counts.sum(axis=0)
    total = float(category_totals.sum())
    if total <= 1:
        return None
    expected = float((category_totals * (total - category_totals)).sum() / (total - 1) / total)
    if math.isclose(expected, 0.0):
        return 1.0 if math.isclose(observed, 0.0) else None
    return 1.0 - (observed / expected)


def format_metric_value(value: float | None, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return "Not enough data"
    return f"{float(value):.{digits}f}"


def agreement_metric_summary(labels: pd.DataFrame, stops: pd.DataFrame) -> pd.DataFrame:
    majority = majority_label_table(labels)
    labeled_stops = int(majority["stop_id"].nunique()) if not majority.empty else 0
    multi_label_stops = int((majority["label_count"] >= 2).sum()) if not majority.empty else 0
    disagreement_stops = int(majority["disagreement_flag"].sum()) if not majority.empty else 0
    average_agreement = (
        float(majority["agreement_pct"].mean()) if not majority.empty and "agreement_pct" in majority else None
    )
    cohen, cohen_pairs = average_pairwise_cohen_kappa(labels)
    return pd.DataFrame(
        [
            ("Stops with labels", labeled_stops),
            ("Stops with 2+ labels", multi_label_stops),
            ("Stops with disagreement", disagreement_stops),
            ("Mean majority agreement", f"{average_agreement:.1f}%" if average_agreement is not None else "Not enough data"),
            ("Average pairwise Cohen kappa", format_metric_value(cohen)),
            ("Cohen rater pairs compared", cohen_pairs),
            ("Fleiss kappa", format_metric_value(fleiss_kappa(labels))),
            ("Krippendorff alpha", format_metric_value(krippendorff_alpha_nominal(labels))),
        ],
        columns=["Metric", "Value"],
    )


def render_agreement_metrics(labels: pd.DataFrame, stops: pd.DataFrame) -> None:
    st.markdown("#### Agreement Metrics")
    if labels.empty:
        st.info("Submit raw labels from at least two assessments to compute agreement metrics.")
        return
    st.dataframe(agreement_metric_summary(labels, stops), use_container_width=True, hide_index=True)
    majority = majority_label_table(labels)
    if not majority.empty:
        display = majority.sort_values(["disagreement_flag", "agreement_pct", "stop_id"], ascending=[False, True, True])
        st.dataframe(display, use_container_width=True, hide_index=True)


def split_list_field(value: Any) -> list[str]:
    if value is None:
        return []
    try:
        if pd.isna(value):
            return []
    except (TypeError, ValueError):
        pass
    pieces = re.split(r"[;,]", str(value))
    return [piece.strip() for piece in pieces if piece.strip()]


def stop_review_snapshot(stop: pd.Series | dict[str, Any]) -> dict[str, Any]:
    return {
        "shade_category": str(stop.get("shading", "") or ""),
        "shade_coverage": str(stop.get("shade_coverage", "") or ""),
        "shade_sources": str(stop.get("shade_sources", "") or ""),
        "confidence": stop.get("confidence", None),
        "review_status": str(stop.get("review_status", "Unlabeled") or "Unlabeled"),
    }


def review_queue_table(stops: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    if stops.empty or "stop_id" not in stops.columns:
        return pd.DataFrame()
    queue = stops.copy()
    queue["stop_id"] = queue["stop_id"].astype(str)
    if "review_status" not in queue.columns:
        queue["review_status"] = "Unlabeled"
    queue["review_status"] = queue["review_status"].apply(normalize_review_status)
    for column in ["shading", "stop_name", "routes", "municipality"]:
        if column not in queue.columns:
            queue[column] = ""

    majority = majority_label_table(labels)
    if not majority.empty:
        majority["stop_id"] = majority["stop_id"].astype(str)
        queue = queue.merge(majority, on="stop_id", how="left")
    for column, fallback in [
        ("majority_label", ""),
        ("label_count", 0),
        ("majority_count", 0),
        ("agreement_pct", 0.0),
        ("disagreement_flag", False),
        ("tied_majority", False),
    ]:
        if column not in queue.columns:
            queue[column] = fallback
        queue[column] = queue[column].fillna(fallback)

    priority_rank = {status: index for index, status in enumerate(["Disputed", "Needs Review", "Unlabeled"])}
    queue["queue_rank"] = queue["review_status"].map(priority_rank).fillna(10)
    priority_score = pd.to_numeric(queue.get("priority_score", 0), errors="coerce").fillna(0)
    agreement_gap = 100 - pd.to_numeric(queue["agreement_pct"], errors="coerce").fillna(100)
    queue["queue_score"] = (
        (10 - queue["queue_rank"]).clip(lower=0) * 100
        + queue["disagreement_flag"].astype(bool).astype(int) * 60
        + agreement_gap
        + priority_score.clip(lower=0)
    )
    return queue.sort_values(["queue_score", "priority_score", "stop_name"], ascending=[False, False, True])


def apply_review_decision_to_stop(
    stop_id: str,
    shade_category: str,
    shade_coverage: str,
    shade_sources: str,
    confidence: float,
    review_status: str,
) -> None:
    stops = st.session_state.get("stops", pd.DataFrame()).copy()
    if stops.empty or "stop_id" not in stops.columns:
        return
    mask = stops["stop_id"].astype(str) == str(stop_id)
    if not mask.any():
        return
    stops.loc[mask, "shading"] = shade_category
    stops.loc[mask, "shade_coverage"] = shade_coverage
    stops.loc[mask, "shade_sources"] = shade_sources
    stops.loc[mask, "confidence"] = confidence
    stops.loc[mask, "review_status"] = review_status
    st.session_state["stops"] = stops


def review_queue_label(row: pd.Series) -> str:
    status = str(row.get("review_status", "Unlabeled") or "Unlabeled")
    label_count = int(float(row.get("label_count", 0) or 0))
    disagreement = "disputed labels" if bool(row.get("disagreement_flag", False)) else f"{label_count} label(s)"
    return f"{stop_picker_label(row)} - {status} - {disagreement}"


def render_review_queue(project_id: str, stops: pd.DataFrame, labels: pd.DataFrame, taxonomy: list[dict[str, Any]]) -> str | None:
    st.subheader("Admin Review Queue")
    queue = review_queue_table(stops, labels)
    if queue.empty:
        st.info("Import stops before reviewing labels.")
        return None

    filter_cols = st.columns([1.2, 1.1, 1.1], vertical_alignment="bottom")
    status_options = list(REVIEW_STATUS_COLORS)
    default_statuses = [status for status in REVIEW_QUEUE_DEFAULT_STATUSES if status in status_options]
    with filter_cols[0]:
        selected_statuses = st.multiselect(
            "Queue statuses",
            status_options,
            default=default_statuses,
            key="review_queue_statuses",
        )
    with filter_cols[1]:
        queue_search = st.text_input("Search queue", key="review_queue_search")
    with filter_cols[2]:
        only_conflicts = st.checkbox("Only disagreements", value=False, key="review_queue_conflicts_only")

    filtered = queue
    if selected_statuses:
        filtered = filtered[filtered["review_status"].isin(selected_statuses)]
    if queue_search.strip():
        haystack = (
            filtered["stop_id"].fillna("").astype(str)
            + " "
            + filtered["stop_name"].fillna("").astype(str)
            + " "
            + filtered["routes"].fillna("").astype(str)
        ).str.lower()
        filtered = filtered[haystack.str.contains(re.escape(queue_search.strip().lower()), na=False)]
    if only_conflicts:
        filtered = filtered[filtered["disagreement_flag"].astype(bool)]

    display_columns = [
        column
        for column in [
            "stop_id",
            "stop_name",
            "routes",
            "municipality",
            "shading",
            "review_status",
            "priority_score",
            "majority_label",
            "label_count",
            "agreement_pct",
            "disagreement_flag",
            "tied_majority",
        ]
        if column in filtered.columns
    ]
    if filtered.empty:
        st.info("No stops match the review queue filters.")
        return None
    st.dataframe(filtered.loc[:, display_columns].head(200), use_container_width=True, hide_index=True)

    queue_records = filtered.reset_index(drop=True)
    queue_labels = [review_queue_label(row) for _, row in queue_records.iterrows()]
    selected_index = st.selectbox(
        "Queue stop",
        range(len(queue_records)),
        format_func=lambda index: queue_labels[index],
        key="review_queue_stop_index",
    )
    selected_stop = queue_records.iloc[int(selected_index)]
    selected_stop_id = str(selected_stop.get("stop_id", ""))

    stop_labels = labels[labels["stop_id"].astype(str) == selected_stop_id] if not labels.empty else pd.DataFrame()
    detail_cols = st.columns([1, 1, 1, 1])
    detail_cols[0].metric("Current label", str(selected_stop.get("shading", "Needs Review") or "Needs Review"))
    detail_cols[1].metric("Review status", str(selected_stop.get("review_status", "Unlabeled") or "Unlabeled"))
    detail_cols[2].metric("Agreement", f"{float(selected_stop.get('agreement_pct', 0) or 0):.1f}%")
    detail_cols[3].metric("Raw labels", int(float(selected_stop.get("label_count", 0) or 0)))

    if stop_labels.empty:
        st.info("No raw labels are attached to this stop yet.")
    else:
        visible_label_columns = [
            column
            for column in [
                "created_at",
                "shade_category",
                "shade_coverage",
                "shade_sources",
                "confidence",
                "labeler_role",
                "labeler_id",
                "source",
                "notes",
            ]
            if column in stop_labels.columns
        ]
        st.dataframe(stop_labels.loc[:, visible_label_columns], use_container_width=True, hide_index=True)

    previous = stop_review_snapshot(selected_stop)
    category_options = taxonomy_names(taxonomy)
    current_category = previous["shade_category"]
    category_index = category_options.index(current_category) if current_category in category_options else 0
    coverage_options = SHADE_COVERAGE_OPTIONS
    current_coverage = previous["shade_coverage"]
    coverage_index = coverage_options.index(current_coverage) if current_coverage in coverage_options else len(coverage_options) - 1
    current_sources = [source for source in split_list_field(previous["shade_sources"]) if source in SHADE_SOURCE_OPTIONS]
    current_confidence = previous["confidence"]
    try:
        confidence_default = float(current_confidence)
    except (TypeError, ValueError):
        confidence_default = 0.85
    confidence_default = max(0.0, min(1.0, confidence_default))

    with st.form("admin_review_decision_form", clear_on_submit=False):
        st.markdown("#### Admin Review Decision")
        top_cols = st.columns([1, 1, 1])
        with top_cols[0]:
            action = st.selectbox("Decision type", REVIEW_ACTION_OPTIONS, key="review_action")
        default_status = REVIEW_ACTION_STATUS_DEFAULTS.get(action, "Needs Review")
        with top_cols[1]:
            actor_id = st.text_input("Reviewer or admin ID", key="review_actor_id")
        with top_cols[2]:
            actor_role = st.selectbox(
                "Reviewer role",
                LABELER_ROLE_OPTIONS,
                index=LABELER_ROLE_OPTIONS.index("Project Admin") if "Project Admin" in LABELER_ROLE_OPTIONS else 0,
                key="review_actor_role",
            )

        decision_cols = st.columns([1, 1, 1])
        with decision_cols[0]:
            final_status = st.selectbox(
                "Final review status",
                list(REVIEW_STATUS_COLORS),
                index=list(REVIEW_STATUS_COLORS).index(default_status),
                key="review_final_status",
            )
        with decision_cols[1]:
            final_category = st.selectbox("Final shade category", category_options, index=category_index, key="review_final_category")
        with decision_cols[2]:
            final_confidence = st.slider("Decision confidence", 0.0, 1.0, confidence_default, 0.05, key="review_final_confidence")

        lower_cols = st.columns([1, 1])
        with lower_cols[0]:
            final_coverage = st.selectbox("Final shade coverage", coverage_options, index=coverage_index, key="review_final_coverage")
        with lower_cols[1]:
            final_sources = st.multiselect("Final shade source(s)", SHADE_SOURCE_OPTIONS, default=current_sources, key="review_final_sources")
        notes = st.text_area("Decision notes", key="review_notes", height=110)
        decision_submitted = st.form_submit_button("Apply review decision", type="primary")

    if decision_submitted:
        if not selected_stop_id.strip():
            st.error("Selected stop is missing a stop ID.")
        else:
            final_sources_text = "; ".join(final_sources)
            apply_review_decision_to_stop(
                selected_stop_id,
                final_category,
                final_coverage,
                final_sources_text,
                final_confidence,
                final_status,
            )
            save_active_project_to_store()
            event_id = add_review_event(
                project_id,
                {
                    "stop_id": selected_stop_id,
                    "actor_id": actor_id,
                    "actor_role": actor_role,
                    "action": action,
                    "from_status": previous["review_status"],
                    "to_status": final_status,
                    "from_label": previous["shade_category"],
                    "to_label": final_category,
                    "from_coverage": previous["shade_coverage"],
                    "to_coverage": final_coverage,
                    "from_sources": previous["shade_sources"],
                    "to_sources": final_sources_text,
                    "from_confidence": previous["confidence"],
                    "to_confidence": final_confidence,
                    "majority_label": selected_stop.get("majority_label", ""),
                    "agreement_pct": selected_stop.get("agreement_pct", ""),
                    "label_count": selected_stop.get("label_count", 0),
                    "notes": notes,
                },
            )
            st.success(f"Applied review decision and saved audit event {event_id}.")
            st.rerun()

    return selected_stop_id


def render_review_audit_history(project_id: str, selected_stop_id: str | None) -> None:
    st.subheader("Review Audit History")
    show_selected = st.checkbox(
        "Show queue-selected stop only",
        value=bool(selected_stop_id),
        key="show_selected_review_history",
        disabled=not bool(selected_stop_id),
    )
    history = list_review_history(project_id, selected_stop_id if show_selected and selected_stop_id else None)
    if history.empty:
        st.info("No review decisions have been recorded yet.")
        return
    visible_columns = [
        column
        for column in [
            "created_at",
            "stop_id",
            "action",
            "from_status",
            "to_status",
            "metadata_from_label",
            "metadata_to_label",
            "metadata_actor_role",
            "actor_id",
            "notes",
        ]
        if column in history.columns
    ]
    st.dataframe(history.loc[:, visible_columns], use_container_width=True, hide_index=True)
    st.download_button(
        "Download review audit CSV",
        history.to_csv(index=False).encode("utf-8"),
        "shade_study_review_audit.csv",
        "text/csv",
    )


def apply_label_to_current_stop(
    stop_id: str,
    shade_category: str,
    shade_coverage: str,
    shade_sources: str,
    confidence: float,
) -> None:
    stops = st.session_state.get("stops", pd.DataFrame()).copy()
    if stops.empty or "stop_id" not in stops.columns:
        return
    mask = stops["stop_id"].astype(str) == str(stop_id)
    if not mask.any():
        return
    stops.loc[mask, "shading"] = shade_category
    stops.loc[mask, "shade_coverage"] = shade_coverage
    stops.loc[mask, "shade_sources"] = shade_sources
    stops.loc[mask, "confidence"] = confidence
    stops.loc[mask, "review_status"] = "Needs Review"
    st.session_state["stops"] = stops


def set_page(page: str) -> None:
    st.session_state["page"] = page


def render_header() -> str:
    pages = ["Data", "Labels", "Visuals", "Docs", "Preview", "Deploy"]
    if st.session_state.get("page") not in pages:
        st.session_state["page"] = "Data"
    st.markdown(
        """
        <style>
        .builder-topbar {
            border-bottom: 1px solid #e5e7eb;
            margin: -1rem -1rem 1.2rem;
            padding: 0.9rem 1.4rem 1.1rem;
        }
        .builder-brand {
            color: #14532d;
            font-size: 2.85rem;
            font-weight: 800;
            letter-spacing: 0;
            line-height: 1.08;
            white-space: nowrap;
        }
        .builder-topbar .stButton button {
            border-radius: 999px;
            font-size: 1.2rem;
            min-height: 3.05rem;
            font-weight: 680;
            padding: 0.5rem 1rem;
            white-space: nowrap;
            width: 100%;
        }
        .builder-topbar .stButton button p {
            white-space: nowrap;
        }
        .builder-topbar .stButton button[kind="primary"] {
            background: #ff4b4b;
            border-color: #ff4b4b;
            color: white;
        }
        .builder-topbar .stButton button[kind="secondary"] {
            background: white;
            border-color: #d1d5db;
            color: #31333f;
        }
        h1 {
            font-size: 1.85rem;
            line-height: 1.15;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div class='builder-topbar'>", unsafe_allow_html=True)
    cols = st.columns([3.3, 0.9, 0.9, 1, 1, 1, 1, 1], gap="small", vertical_alignment="center")
    with cols[0]:
        st.markdown("<div class='builder-brand'>Shade-GIS</div>", unsafe_allow_html=True)
    for index, page in enumerate(pages, start=2):
        with cols[index]:
            st.button(
                page,
                key=f"nav_{page}",
                type="primary" if st.session_state["page"] == page else "secondary",
                use_container_width=True,
                on_click=set_page,
                args=(page,),
            )
    st.markdown("</div>", unsafe_allow_html=True)
    return st.session_state["page"]


def render_project_storage_controls() -> None:
    projects = list_projects()
    project_ids = [project["id"] for project in projects]
    active_project_id = st.session_state.get("active_project_id")
    if active_project_id not in project_ids and project_ids:
        active_project_id = project_ids[0]

    def project_label(project_id: str) -> str:
        project = next((item for item in projects if item["id"] == project_id), {})
        name = project.get("name") or "Untitled Shade Study"
        region = project.get("region") or "No region"
        version = project.get("dataset_version") or "draft"
        return f"{name} - {region} - v{version}"

    st.subheader("Project Store")
    cols = st.columns([1.5, 0.55, 0.95], vertical_alignment="bottom")
    with cols[0]:
        if project_ids:
            selected_project_id = st.selectbox(
                "Active saved project",
                project_ids,
                index=project_ids.index(active_project_id),
                format_func=project_label,
            )
            if selected_project_id != active_project_id:
                save_active_project_to_store()
                load_project_into_session(selected_project_id)
                st.rerun()
    with cols[1]:
        if st.button("Save now", use_container_width=True):
            save_active_project_to_store()
            st.success("Project saved.")
    with cols[2]:
        status = database_status()
        if status["using_fallback"]:
            st.caption(f"Database fallback: `{status['active_path']}`")
        else:
            st.caption(f"Database: `{status['active_path']}`")

    create_cols = st.columns([1.5, 0.65], vertical_alignment="bottom")
    with create_cols[0]:
        new_project_name = st.text_input("New blank project name", key="new_project_name")
    with create_cols[1]:
        if st.button("Create blank project", use_container_width=True):
            new_project_id = create_blank_project(new_project_name)
            load_project_into_session(new_project_id)
            st.rerun()


def render_data_page() -> None:
    st.title("Project Data")
    render_project_storage_controls()
    project = st.session_state["project"]
    taxonomy = st.session_state["taxonomy"]

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Project")
        project["name"] = st.text_input("Project name", project["name"])
        project["agency"] = st.text_input("Transit agency", project["agency"])
        project["region"] = st.text_input("Geographic region", project["region"])
        project["owners"] = st.text_input("Owner(s)", project["owners"])
    with right:
        st.subheader("Publication")
        project["visibility"] = st.selectbox("Visibility", ["Public", "Private"], index=0 if project["visibility"] == "Public" else 1)
        project["dataset_version"] = st.text_input("Dataset version", project["dataset_version"])
        project["methodology_version"] = st.text_input("Methodology version", project["methodology_version"])
        project["description"] = st.text_area("Description", project["description"], height=118)

    st.subheader("Upload Or Map A Dataset")
    file_tab, api_tab, manual_tab = st.tabs(["File Upload", "API URL", "Manual Entry"])
    with file_tab:
        uploaded = st.file_uploader(
            "Upload GTFS, CSV, GeoJSON, or a zipped Shapefile",
            type=["zip", "txt", "csv", "geojson", "json"],
        )
        if uploaded is not None:
            contents = uploaded.getvalue()
            filename = uploaded.name
            key_prefix = f"file_{clean_import_key(filename)}"
            try:
                if filename.lower().endswith(".zip"):
                    zip_format = detect_zip_import_format(contents)
                    if zip_format == "GTFS":
                        raw, metadata = parse_gtfs_zip(contents)
                        st.dataframe(raw.head(25), use_container_width=True)
                        if st.button("Use uploaded GTFS stops", type="primary", key=f"{key_prefix}_gtfs"):
                            mapping = {field: field for field in REQUIRED_STOP_FIELDS + OPTIONAL_FIELDS if field in raw.columns}
                            metadata.update({"original_filename": filename})
                            prepared = import_stop_dataset(
                                raw,
                                mapping,
                                project=project,
                                taxonomy=taxonomy,
                                source_name=filename,
                                import_format="GTFS",
                                metadata=metadata,
                            )
                            st.success(f"Imported {len(prepared):,} mapped stops.")
                    else:
                        raw, metadata = parse_shapefile_zip(contents)
                        metadata.update({"original_filename": filename})
                        render_mapped_import_controls(
                            raw,
                            source_name=filename,
                            import_format="Shapefile",
                            project=project,
                            taxonomy=taxonomy,
                            metadata=metadata,
                            key_prefix=key_prefix,
                            button_label="Use mapped Shapefile",
                        )
                elif filename.lower().endswith((".geojson", ".json")):
                    raw, metadata = parse_geojson_bytes(contents)
                    metadata.update({"original_filename": filename})
                    render_mapped_import_controls(
                        raw,
                        source_name=filename,
                        import_format="GeoJSON",
                        project=project,
                        taxonomy=taxonomy,
                        metadata=metadata,
                        key_prefix=key_prefix,
                        button_label="Use mapped GeoJSON",
                    )
                else:
                    raw = read_csv_bytes(contents)
                    render_mapped_import_controls(
                        raw,
                        source_name=filename,
                        import_format="CSV",
                        project=project,
                        taxonomy=taxonomy,
                        metadata={"original_filename": filename},
                        key_prefix=key_prefix,
                        button_label="Use mapped CSV",
                    )
            except Exception as error:
                st.error(f"Could not import this file: {error}")

    with api_tab:
        api_url = st.text_input("Dataset API or file URL", key="api_import_url")
        api_format = st.selectbox("Response format", ["Auto detect", "CSV", "GeoJSON"], key="api_import_format")
        if st.button("Fetch API dataset", key="fetch_api_dataset"):
            if not api_url.strip():
                st.warning("Enter a URL before fetching.")
            else:
                try:
                    contents = fetch_api_bytes(api_url)
                    requested = "Auto" if api_format == "Auto detect" else api_format
                    raw, metadata = parse_api_response(contents, api_url, requested)
                    st.session_state["api_import_raw"] = raw
                    st.session_state["api_import_metadata"] = metadata
                    st.session_state["api_import_source"] = api_url
                    st.success(f"Fetched {len(raw):,} records.")
                except Exception as error:
                    st.error(f"Could not fetch this API dataset: {error}")
        api_raw = st.session_state.get("api_import_raw")
        if isinstance(api_raw, pd.DataFrame):
            api_metadata = st.session_state.get("api_import_metadata", {})
            detected = api_metadata.get("detected_format") or api_format.replace("Auto detect", "API")
            render_mapped_import_controls(
                api_raw,
                source_name=st.session_state.get("api_import_source", api_url),
                import_format=str(detected),
                project=project,
                taxonomy=taxonomy,
                metadata=api_metadata,
                key_prefix="api_import",
                button_label="Use mapped API dataset",
            )

    with manual_tab:
        st.caption("Add one stop per row. Rows without a stop ID or valid coordinates are ignored on import.")
        manual_template = pd.DataFrame([{column: "" for column in MANUAL_ENTRY_COLUMNS}])
        manual_rows = st.data_editor(
            manual_template,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="manual_import_rows",
        )
        manual_source = st.text_input("Manual import source label", "Manual entry", key="manual_import_source")
        if st.button("Use manual entries", type="primary", key="use_manual_entries"):
            mapping = {field: field for field in REQUIRED_STOP_FIELDS + OPTIONAL_FIELDS if field in manual_rows.columns}
            prepared = import_stop_dataset(
                manual_rows,
                mapping,
                project=project,
                taxonomy=taxonomy,
                source_name=manual_source,
                import_format="Manual",
                metadata={"entry_method": "manual"},
            )
            st.success(f"Imported {len(prepared):,} manually entered stops.")

    source_cols = st.columns(3)
    with source_cols[0]:
        project["source_name"] = st.text_input("Data source name", project["source_name"])
    with source_cols[1]:
        project["source_license"] = st.text_input("Source license", project["source_license"])
    with source_cols[2]:
        project["source_url"] = st.text_input("Source URL", project["source_url"])

    st.subheader("Shade Taxonomy")
    edited_taxonomy = st.data_editor(
        pd.DataFrame(taxonomy),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "name": st.column_config.TextColumn("Category"),
            "description": st.column_config.TextColumn("Definition"),
            "color": st.column_config.TextColumn("Hex color"),
            "sort_order": st.column_config.NumberColumn("Sort order", min_value=1, step=1),
        },
    )
    if st.button(
        "Apply taxonomy",
        help=(
            "Save the edited shade categories and reapply them to the active dataset "
            "so maps, legends, previews, and exports use the latest taxonomy."
        ),
    ):
        st.session_state["taxonomy"] = edited_taxonomy.fillna("").to_dict("records")
        st.session_state["stops"] = prepare_stop_dataset(st.session_state["stops"], project, st.session_state["taxonomy"])
        st.success("Taxonomy applied to the active dataset.")

    st.subheader("Dataset Health")
    st.dataframe(validation_summary(st.session_state["stops"]), use_container_width=True, hide_index=True)
    st.dataframe(st.session_state["stops"].head(50), use_container_width=True, hide_index=True)


def render_labels_page() -> None:
    st.title("Labeling")
    project_id = st.session_state.get("active_project_id")
    stops = st.session_state.get("stops", pd.DataFrame())
    taxonomy = st.session_state.get("taxonomy", [])
    if not project_id:
        st.warning("Save or load a project before collecting labels.")
        return
    if stops.empty:
        st.warning("Import a stop dataset before collecting labels.")
        return

    labels = list_shade_labels(project_id)
    st.dataframe(raw_label_summary(labels, stops), use_container_width=True, hide_index=True)
    render_agreement_metrics(labels, stops)
    queue_stop_id = render_review_queue(project_id, stops, labels, taxonomy)
    render_review_audit_history(project_id, queue_stop_id)

    st.subheader("Raw Label Collection")
    stop_options = stops.reset_index(drop=True)
    stop_labels = [stop_picker_label(row) for _, row in stop_options.iterrows()]
    selected_index = st.selectbox(
        "Stop to label",
        range(len(stop_options)),
        format_func=lambda index: stop_labels[index],
        key="label_stop_index",
    )
    selected_stop = stop_options.iloc[int(selected_index)]
    selected_stop_id = str(selected_stop.get("stop_id", ""))

    detail_cols = st.columns([1, 1, 1])
    detail_cols[0].metric("Current label", str(selected_stop.get("shading", "Needs Review") or "Needs Review"))
    detail_cols[1].metric("Review status", str(selected_stop.get("review_status", "Unlabeled") or "Unlabeled"))
    detail_cols[2].metric("Raw labels for stop", len(list_shade_labels(project_id, selected_stop_id)))

    with st.form("raw_label_form", clear_on_submit=False):
        st.subheader("Submit Raw Shade Label")
        form_cols = st.columns([1, 1, 1])
        with form_cols[0]:
            labeler_id = st.text_input("Reviewer or contributor ID", key="labeler_id")
            labeler_role = st.selectbox("Reviewer role", LABELER_ROLE_OPTIONS, key="labeler_role")
        with form_cols[1]:
            source_label = st.selectbox("Label source", LABEL_SOURCE_OPTIONS, key="label_source")
            image_id = st.text_input("Image ID or reference", key="label_image_id")
        with form_cols[2]:
            confidence = st.slider("Confidence", 0.0, 1.0, 0.75, 0.05, key="label_confidence")
            apply_current = st.checkbox(
                "Also update current map label",
                value=False,
                help="The raw label is always saved. This additionally updates the current stop fields used by maps and exports.",
            )

        category_options = taxonomy_names(taxonomy)
        current_category = str(selected_stop.get("shading", "")).strip()
        category_index = category_options.index(current_category) if current_category in category_options else 0
        shade_category = st.selectbox("Shade category", category_options, index=category_index, key="label_category")
        coverage_cols = st.columns([1, 1])
        with coverage_cols[0]:
            shade_coverage = st.selectbox("Shade coverage", SHADE_COVERAGE_OPTIONS, key="label_coverage")
        with coverage_cols[1]:
            shade_sources = st.multiselect("Shade source(s)", SHADE_SOURCE_OPTIONS, key="label_sources")
        notes = st.text_area("Notes", key="label_notes", height=120)
        submitted = st.form_submit_button("Save raw label", type="primary")

    if submitted:
        if not selected_stop_id.strip():
            st.error("Selected stop is missing a stop ID.")
        else:
            shade_sources_text = "; ".join(shade_sources)
            label_id = add_shade_label(
                project_id,
                {
                    "stop_id": selected_stop_id,
                    "image_id": image_id,
                    "labeler_id": labeler_id,
                    "labeler_role": labeler_role,
                    "shade_category": shade_category,
                    "shade_coverage": shade_coverage,
                    "shade_sources": shade_sources_text,
                    "confidence": confidence,
                    "notes": notes,
                    "source": label_source_code(source_label),
                    "source_label": source_label,
                    "stop_name": selected_stop.get("stop_name", ""),
                },
            )
            if apply_current:
                previous = stop_review_snapshot(selected_stop)
                apply_label_to_current_stop(selected_stop_id, shade_category, shade_coverage, shade_sources_text, confidence)
                save_active_project_to_store()
                add_review_event(
                    project_id,
                    {
                        "stop_id": selected_stop_id,
                        "actor_id": labeler_id,
                        "actor_role": labeler_role,
                        "action": "Raw label applied to map",
                        "from_status": previous["review_status"],
                        "to_status": "Needs Review",
                        "from_label": previous["shade_category"],
                        "to_label": shade_category,
                        "from_coverage": previous["shade_coverage"],
                        "to_coverage": shade_coverage,
                        "from_sources": previous["shade_sources"],
                        "to_sources": shade_sources_text,
                        "from_confidence": previous["confidence"],
                        "to_confidence": confidence,
                        "source": source_label,
                        "label_id": label_id,
                        "notes": notes,
                    },
                )
            st.success(f"Saved raw label {label_id}.")
            st.rerun()

    st.subheader("Raw Label History")
    show_selected_only = st.checkbox("Show selected stop only", value=False, key="show_selected_label_history")
    history = list_shade_labels(project_id, selected_stop_id if show_selected_only else None)
    if history.empty:
        st.info("No raw labels have been submitted yet.")
    else:
        visible_columns = [
            column
            for column in [
                "created_at",
                "stop_id",
                "shade_category",
                "shade_coverage",
                "shade_sources",
                "confidence",
                "labeler_role",
                "labeler_id",
                "source",
                "notes",
            ]
            if column in history.columns
        ]
        st.dataframe(history.loc[:, visible_columns], use_container_width=True, hide_index=True)
        st.download_button(
            "Download raw labels CSV",
            history.to_csv(index=False).encode("utf-8"),
            "shade_study_raw_labels.csv",
            "text/csv",
        )


def render_palette_controls(
    visualization: dict[str, Any],
    stops: pd.DataFrame,
    taxonomy: list[dict[str, Any]],
    color_options: dict[str, str],
) -> None:
    field = color_options.get(visualization.get("color_by", "Shade category"), "shading")
    st.markdown("#### Color Palette")
    if field == "shading":
        previous_palette = visualization.get("shade_palette", "Custom")
        palette_options = ["Custom"] + list(SHADE_PALETTES)
        if previous_palette not in palette_options:
            previous_palette = "Custom"
        selected_palette = st.selectbox(
            "Premade shade palette",
            palette_options,
            index=palette_options.index(previous_palette),
        )
        if selected_palette != "Custom" and selected_palette != previous_palette:
            palette = SHADE_PALETTES[selected_palette]
            for index, item in enumerate(taxonomy):
                color = palette[index % len(palette)]
                item["color"] = color
                st.session_state[f"shade_color_{index}"] = color
        visualization["shade_palette"] = selected_palette

        grid = st.columns(2)
        for index, item in enumerate(taxonomy):
            name = str(item.get("name", "")).strip() or f"Category {index + 1}"
            with grid[index % 2]:
                item["color"] = st.color_picker(
                    name,
                    normalize_hex_color(item.get("color", "#808080")),
                    key=f"shade_color_{index}",
                )
        return

    if field == "review_status":
        review_colors = visualization.setdefault("review_status_colors", {})
        grid = st.columns(2)
        for index, status in enumerate(REVIEW_STATUS_COLORS):
            review_colors.setdefault(status, rgb_to_hex(REVIEW_STATUS_COLORS[status]))
            with grid[index % 2]:
                review_colors[status] = st.color_picker(
                    status,
                    normalize_hex_color(review_colors[status]),
                    key=f"review_color_{status}",
                )
        return

    if field == "priority_score":
        priority_colors = visualization.setdefault("priority_colors", DEFAULT_VISUALIZATION["priority_colors"].copy())
        grid = st.columns(3)
        with grid[0]:
            priority_colors["low"] = st.color_picker(
                "Low score",
                normalize_hex_color(priority_colors.get("low"), DEFAULT_VISUALIZATION["priority_colors"]["low"]),
                key="priority_color_low",
            )
        with grid[1]:
            priority_colors["mid"] = st.color_picker(
                "Mid score",
                normalize_hex_color(priority_colors.get("mid"), DEFAULT_VISUALIZATION["priority_colors"]["mid"]),
                key="priority_color_mid",
            )
        with grid[2]:
            priority_colors["high"] = st.color_picker(
                "High score",
                normalize_hex_color(priority_colors.get("high"), DEFAULT_VISUALIZATION["priority_colors"]["high"]),
                key="priority_color_high",
            )
        return

    color_map = ensure_field_color_map(visualization, stops, field)
    values = field_values_for_colors(stops, field)
    if not values:
        st.caption("No values are available for the selected column.")
        return
    total_unique = stops[field].fillna("Unknown").astype(str).str.strip().replace("", "Unknown").nunique()
    if total_unique > len(values):
        st.caption(f"Showing colors for the first {len(values)} values in this column.")
    grid = st.columns(2)
    for index, value in enumerate(values):
        with grid[index % 2]:
            color_map[value] = st.color_picker(
                value[:80],
                normalize_hex_color(color_map.get(value, COLOR_PALETTE[index % len(COLOR_PALETTE)])),
                key=f"field_color_{field}_{index}",
            )


def gis_overlay_id(name: str, index: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "gis-overlay").lower()).strip("-")
    return f"{slug or 'gis-overlay'}-{index + 1}"


def parse_uploaded_gis_overlay(contents: bytes, filename: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".zip":
        geojson, metadata = parse_shapefile_overlay_zip(contents)
        return "Shapefile", geojson, metadata
    geojson, metadata = parse_geojson_overlay_bytes(contents)
    return "GeoJSON", geojson, metadata


def append_import_log(entry: dict[str, Any]) -> None:
    import_log = st.session_state.setdefault("import_log", [])
    import_log.append(entry)


def render_gis_overlay_controls(visualization: dict[str, Any]) -> None:
    st.subheader("GIS Overlays")
    overlays = clean_gis_overlays(visualization)
    uploaded = st.file_uploader(
        "Upload GeoJSON or zipped Shapefile overlay",
        type=["geojson", "json", "zip"],
        key="gis_overlay_upload",
        help="Use this for real map layers such as routes, shelters, canopy, NDVI, Census geographies, or destinations.",
    )
    overlay_cols = st.columns([1.2, 1, 1])
    overlay_name = overlay_cols[0].text_input("Overlay name", key="gis_overlay_name", placeholder="Tree canopy")
    overlay_category = overlay_cols[1].selectbox("Overlay category", GIS_OVERLAY_CATEGORIES, key="gis_overlay_category")
    overlay_color = overlay_cols[2].color_picker("Overlay color", "#2563eb", key="gis_overlay_color")
    source_cols = st.columns([1, 1])
    overlay_source = source_cols[0].text_input("Source", key="gis_overlay_source", placeholder="Agency, dataset, or URL")
    overlay_license = source_cols[1].text_input("License", key="gis_overlay_license", placeholder="Optional")
    style_cols = st.columns([1, 1, 1])
    overlay_opacity = style_cols[0].slider("Overlay opacity", 0.05, 1.0, 0.35, 0.05, key="gis_overlay_opacity")
    overlay_line_width = style_cols[1].slider("Line width", 1, 12, 2, 1, key="gis_overlay_line_width")
    overlay_visible = style_cols[2].checkbox("Visible by default", value=True, key="gis_overlay_visible")

    if st.button("Add GIS overlay", type="primary", disabled=uploaded is None):
        if uploaded is None:
            st.warning("Upload a GeoJSON file or zipped Shapefile first.")
        else:
            try:
                overlay_format, geojson, metadata = parse_uploaded_gis_overlay(uploaded.getvalue(), uploaded.name)
                name = overlay_name.strip() or Path(uploaded.name).stem.replace("_", " ").title()
                overlay = {
                    "id": gis_overlay_id(name, len(overlays)),
                    "name": name,
                    "category": overlay_category,
                    "source": overlay_source.strip(),
                    "license": overlay_license.strip(),
                    "filename": uploaded.name,
                    "format": overlay_format,
                    "color": normalize_hex_color(overlay_color),
                    "opacity": overlay_opacity,
                    "line_width": overlay_line_width,
                    "visible": overlay_visible,
                    "metadata": metadata,
                    "imported_at": timestamp_with_timezone(),
                    "geojson": geojson,
                }
                overlays.append(overlay)
                visualization["gis_overlays"] = overlays
                append_import_log(
                    {
                        "source": name,
                        "format": f"GIS overlay: {overlay_format}",
                        "rows": int(metadata.get("features", 0)),
                        "imported_at": overlay["imported_at"],
                        "original_filename": uploaded.name,
                        "metadata": {
                            "category": overlay_category,
                            "geometry_types": metadata.get("geometry_types", ""),
                            "source": overlay_source.strip(),
                            "license": overlay_license.strip(),
                        },
                    }
                )
                st.success(f"Added {name} with {metadata.get('features', 0)} feature(s).")
                st.rerun()
            except Exception as error:
                st.error(f"Could not import GIS overlay: {error}")

    if not overlays:
        st.caption("No uploaded GIS overlays yet.")
        return

    delete_index: int | None = None
    for index, overlay in enumerate(overlays):
        label = f"{overlay.get('name', f'GIS overlay {index + 1}')} ({overlay.get('category', 'Other')})"
        with st.expander(label, expanded=False):
            edit_cols = st.columns([1, 1, 1])
            overlay["visible"] = edit_cols[0].checkbox("Visible", value=bool(overlay.get("visible", True)), key=f"gis_overlay_visible_{index}")
            overlay["color"] = edit_cols[1].color_picker(
                "Color",
                normalize_hex_color(overlay.get("color", COLOR_PALETTE[index % len(COLOR_PALETTE)])),
                key=f"gis_overlay_color_{index}",
            )
            overlay["opacity"] = edit_cols[2].slider(
                "Opacity",
                0.05,
                1.0,
                float(overlay.get("opacity", 0.35)),
                0.05,
                key=f"gis_overlay_opacity_{index}",
            )
            overlay["line_width"] = st.slider(
                "Line width",
                1,
                12,
                int(overlay.get("line_width", 2)),
                1,
                key=f"gis_overlay_width_{index}",
            )
            overlay["name"] = st.text_input("Name", str(overlay.get("name", "")), key=f"gis_overlay_name_{index}")
            category = str(overlay.get("category", "Other"))
            if category not in GIS_OVERLAY_CATEGORIES:
                category = "Other"
            overlay["category"] = st.selectbox(
                "Category",
                GIS_OVERLAY_CATEGORIES,
                index=GIS_OVERLAY_CATEGORIES.index(category),
                key=f"gis_overlay_category_{index}",
            )
            meta = overlay.get("metadata", {})
            st.caption(
                f"{overlay.get('format', 'GIS')} | {meta.get('features', 0)} feature(s) | "
                f"{meta.get('geometry_types', 'Unknown geometry')}"
            )
            if st.button("Remove overlay", key=f"remove_gis_overlay_{index}"):
                delete_index = index

    if delete_index is not None:
        overlays.pop(delete_index)
        visualization["gis_overlays"] = overlays
        st.rerun()
    else:
        visualization["gis_overlays"] = overlays


def render_visuals_page() -> None:
    st.title("Metrics And Visualizations")
    visualization = st.session_state["visualization"]
    stops = st.session_state["stops"]
    taxonomy = st.session_state["taxonomy"]

    controls, preview = st.columns([0.85, 1.15])
    with controls:
        with st.expander("Visualization Controls", expanded=True):
            with st.container(height=VISUAL_MAP_HEIGHT, border=False):
                color_options = get_color_options(stops)
                if visualization.get("color_by") not in color_options:
                    visualization["color_by"] = "Shade category"
                color_labels = list(color_options)
                visualization["color_by"] = st.selectbox(
                    "Color stops by",
                    color_labels,
                    index=color_labels.index(visualization["color_by"]),
                )
                marker_shape = visualization.get("marker_shape", "Circle")
                if marker_shape not in MARKER_SHAPES:
                    marker_shape = "Circle"
                visualization["marker_shape"] = st.selectbox(
                    "Marker shape",
                    MARKER_SHAPES,
                    index=MARKER_SHAPES.index(marker_shape),
                )
                visualization["marker_size"] = st.slider(
                    "Marker size",
                    4,
                    48,
                    int(visualization.get("marker_size", 7)),
                    1,
                )
                visualization["marker_opacity"] = st.slider(
                    "Marker opacity",
                    0.1,
                    1.0,
                    float(visualization.get("marker_opacity", 0.82)),
                    0.05,
                )
                visualization["marker_stroke_color"] = st.color_picker(
                    "Marker outline",
                    normalize_hex_color(visualization.get("marker_stroke_color", "#141414"), "#141414"),
                )
                visualization["marker_stroke_width"] = st.slider(
                    "Outline width",
                    0,
                    6,
                    int(visualization.get("marker_stroke_width", 1)),
                    1,
                )
                map_style = visualization.get("map_style", "Light")
                if map_style not in MAP_STYLES:
                    map_style = "Light"
                visualization["map_style"] = st.selectbox(
                    "Base map style",
                    list(MAP_STYLES),
                    index=list(MAP_STYLES).index(map_style),
                )
                overlay_options = get_available_overlays(stops)
                visualization["overlays"] = clean_selected_options(visualization.get("overlays", []), overlay_options)
                if overlay_options:
                    visualization["overlays"] = st.multiselect(
                        "Dataset-backed context fields",
                        overlay_options,
                        default=visualization["overlays"],
                        help=(
                            "These options expose contextual fields that are already attached to stop rows, "
                            "such as routes, ridership, shelters, heat vulnerability, or canopy. They only appear "
                            "when those columns have usable values: at least one non-null cell with text or data "
                            "after blank spaces are trimmed."
                        ),
                    )
                else:
                    visualization["overlays"] = []
                    st.caption("No optional context layers are available in the active dataset.")

                st.divider()
                render_gis_overlay_controls(visualization)

                metric_options = get_available_metric_cards(stops)
                visualization["metric_cards"] = clean_selected_options(
                    visualization.get("metric_cards", []), metric_options
                )
                if metric_options:
                    visualization["metric_cards"] = st.multiselect(
                        "Dashboard summaries",
                        metric_options,
                        default=visualization["metric_cards"],
                    )
                else:
                    visualization["metric_cards"] = []
                    st.caption("No dashboard summaries are available for the active dataset yet.")

                st.subheader("Custom Chart")
                charts = get_custom_charts(stops, visualization)
                chart_columns = get_chart_column_options(stops)
                if chart_columns:
                    chart_count = st.number_input(
                        "Number of custom charts",
                        min_value=1,
                        max_value=MAX_CUSTOM_CHARTS,
                        value=len(charts),
                        step=1,
                        help="Configure up to 10 charts for the public Analytics tab.",
                    )
                    chart_count = int(chart_count)
                    while len(charts) < chart_count:
                        charts.append(
                            ensure_custom_chart_defaults(
                                stops,
                                json.loads(json.dumps(DEFAULT_CUSTOM_CHART)),
                                len(charts),
                            )
                        )
                    charts = charts[:chart_count]
                    for index, chart in enumerate(charts):
                        chart = ensure_custom_chart_defaults(stops, chart, index)
                        with st.expander(chart.get("title", f"Custom chart {index + 1}"), expanded=index == 0):
                            chart["title"] = st.text_input(
                                "Chart title",
                                chart.get("title", f"Custom chart {index + 1}"),
                                key=f"custom_chart_title_{index}",
                            )
                            chart["x"] = st.selectbox(
                                "X column",
                                chart_columns,
                                index=chart_columns.index(chart["x"]),
                                format_func=display_label,
                                key=f"custom_chart_x_{index}",
                            )
                            y_options = [RECORD_COUNT_FIELD] + chart_columns
                            chart["y"] = st.selectbox(
                                "Y column",
                                y_options,
                                index=y_options.index(chart["y"]),
                                format_func=lambda value: value if value == RECORD_COUNT_FIELD else display_label(value),
                                key=f"custom_chart_y_{index}",
                            )
                            chart["aggregation"] = st.selectbox(
                                "Y aggregation",
                                CHART_AGGREGATIONS,
                                index=CHART_AGGREGATIONS.index(chart["aggregation"]),
                                key=f"custom_chart_aggregation_{index}",
                            )
                            chart["chart_type"] = st.selectbox(
                                "Chart type",
                                CHART_TYPES,
                                index=CHART_TYPES.index(chart["chart_type"]),
                                key=f"custom_chart_type_{index}",
                            )
                    visualization["custom_charts"] = charts
                else:
                    st.caption("Import a dataset before configuring a custom chart.")

                current_display_columns = get_selected_display_columns(stops, visualization)
                display_columns = st.multiselect(
                    "Published data columns",
                    get_display_column_options(stops),
                    default=current_display_columns,
                    format_func=display_label,
                    help="Choose which stop fields appear in the public analytics data table and map hover details.",
                )
                if display_columns:
                    visualization["display_columns"] = display_columns
                else:
                    st.warning("Select at least one column for the public data table.")
                    visualization["display_columns"] = current_display_columns
                visualization["show_legend"] = st.checkbox("Show legend", value=visualization["show_legend"])
                visualization["show_downloads"] = st.checkbox(
                    "Show public downloads", value=visualization["show_downloads"]
                )

                st.divider()
                render_palette_controls(visualization, stops, taxonomy, color_options)
                st.divider()
                st.subheader("Priority Formula")
                weights = visualization["priority_weights"]
                priority_factors = []
                if has_column_data(stops, "ridership"):
                    priority_factors.append(("ridership", "Ridership weight"))
                if "shading" in stops.columns:
                    priority_factors.append(("low_shade", "Low shade weight"))
                if has_column_data(stops, "heat_vulnerability_index"):
                    priority_factors.append(("heat_vulnerability_index", "Heat vulnerability weight"))
                if has_column_data(stops, "tree_canopy_pct"):
                    priority_factors.append(("low_tree_canopy", "Low tree canopy weight"))

                if priority_factors:
                    for key, label in priority_factors:
                        weights[key] = st.slider(label, 0.0, 1.0, float(weights.get(key, 0.0)), 0.05)
                else:
                    st.caption("No priority factors are available in the active dataset.")
                st.caption("The preview stores the selected formula version with exported configuration.")

    st.session_state["stops"]["priority_score"] = calculate_priority_scores(stops, visualization["priority_weights"])
    display_columns = get_selected_display_columns(st.session_state["stops"], visualization)

    with preview:
        st.subheader("Map Preview")
        if stops.empty:
            st.warning("Import a dataset before configuring the map.")
        else:
            st.pydeck_chart(
                build_deck_chart(stops, st.session_state["taxonomy"], visualization),
                use_container_width=True,
                height=VISUAL_MAP_HEIGHT,
            )

    st.subheader("Custom Chart Preview")
    if stops.empty:
        st.info("Import a dataset to preview a custom chart.")
    else:
        render_custom_charts(st.session_state["stops"], visualization)

    st.subheader("Data Table Preview")
    if stops.empty:
        st.info("Import a dataset to preview selected data columns.")
    else:
        st.dataframe(
            st.session_state["stops"].loc[:, display_columns].head(20),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Available Fields")
    active_columns = get_active_data_columns(stops)
    field_summary = pd.DataFrame(
        [{"field": column, "non_null_values": int(stops[column].notna().sum())} for column in active_columns]
    )
    st.dataframe(field_summary, use_container_width=True, hide_index=True)


def render_methodology_page() -> None:
    st.title("Project Documentation")
    methodology = st.session_state["methodology"]

    edit, preview = st.columns([1, 1])
    with edit:
        methodology["title"] = st.text_input("About page title", methodology["title"])
        methodology["summary"] = st.text_area("Summary", methodology["summary"], height=85)
        methodology["purpose"] = st.text_area("Rationale", methodology["purpose"], height=130)
        methodology["shade_method"] = st.text_area("Shade assessment method", methodology["shade_method"], height=130)
        methodology["data_sources"] = st.text_area("Data sources", methodology["data_sources"], height=135)
        methodology["contributors"] = st.text_area("Contributors", methodology["contributors"], height=85)
        methodology["limitations"] = st.text_area("Known limitations", methodology["limitations"], height=110)
        methodology.setdefault("bibliography", DEFAULT_METHODOLOGY["bibliography"])
        methodology["bibliography"] = st.text_area(
            "Bibliography",
            methodology["bibliography"],
            height=170,
            help=(
                "Use the same grouped APA format as citations: unindented lines are group labels, "
                "and indented lines render as hanging-indent bibliography entries."
            ),
            placeholder=(
                "Works referenced:\n"
                "    Author, A. A., & Author, B. B. (Year). Title of article. Title of Journal, volume(issue), page range. https://doi.org/xxxxx\n"
                "    Author or Organization. (Year). Title of report. Publisher. URL\n\n"
                "Data and software:\n"
                "    Author or Organization. (Year). Title of software or dataset (Version number) [Software or data set]. Publisher. URL"
            ),
        )
        methodology["release_history"] = st.text_area("Release history", methodology["release_history"], height=95)
        methodology["citation"] = st.text_area(
            "Citation",
            methodology["citation"],
            height=150,
            help=(
                "Use unindented lines as citation group labels. Put each citation on an indented line "
                "under its group to render a hanging indent on the public methodology page. The examples use APA style."
            ),
            placeholder=(
                "Transit data:\n"
                "    Author or Organization. (Year). Title of dataset (Version number) [Data set]. Publisher. URL\n\n"
                "Methods and references:\n"
                "    Author, A. A., & Author, B. B. (Year). Title of article. Title of Journal, volume(issue), page range. https://doi.org/xxxxx\n"
                "    Author or Organization. (Year). Title of report. Publisher. URL"
            ),
        )
    with preview:
        with st.container(height=METHODS_PREVIEW_HEIGHT, border=False):
            render_builder_about_page(
                project=st.session_state["project"],
                methodology=methodology,
                taxonomy=st.session_state["taxonomy"],
                import_log=st.session_state["import_log"],
                priority_formula=priority_formula_for_about(st.session_state["visualization"]),
            )


def render_metric_cards(df: pd.DataFrame) -> None:
    no_shade = int((df["shading"] == "No Shade").sum()) if not df.empty else 0
    needs_review = int((df["shading"] == "Needs Review").sum()) if not df.empty else 0
    accepted = int((df["review_status"] == "Accepted").sum()) if not df.empty else 0
    cols = st.columns(4)
    cols[0].metric("Stops", f"{len(df):,}")
    cols[1].metric("No shade", f"{no_shade:,}")
    cols[2].metric("Needs review", f"{needs_review:,}")
    cols[3].metric("Accepted", f"{accepted:,}")


def filter_unlabeled_stops(df: pd.DataFrame, show_unlabeled: bool) -> pd.DataFrame:
    if show_unlabeled or "shading" not in df.columns:
        return df
    return df[df["shading"] != "Needs Review"].copy()


def split_route_values(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none"}:
        return []
    return [route.strip() for route in re.split(r"[;,|]+", text) if route.strip()]


def route_filter_options(df: pd.DataFrame) -> list[str]:
    if "routes" not in df.columns:
        return []
    routes: set[str] = set()
    for value in df["routes"].dropna():
        routes.update(split_route_values(value))
    return sorted(routes, key=lambda route: (len(route), route.lower()))


def categorical_filter_options(df: pd.DataFrame, column: str) -> list[str]:
    if column not in df.columns:
        return []
    values = df[column].dropna().astype(str).str.strip()
    values = values[(values != "") & (values.str.lower() != "nan")]
    return sorted(values.unique().tolist())


def numeric_filter_bounds(df: pd.DataFrame, column: str) -> tuple[float, float] | None:
    if column not in df.columns:
        return None
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    values = values[values.apply(math.isfinite)]
    if values.empty:
        return None
    low = float(values.min())
    high = float(values.max())
    if math.isclose(low, high):
        return None
    return low, high


def destination_columns(df: pd.DataFrame) -> list[str]:
    return [column for column in DESTINATION_FILTER_COLUMNS if column in df.columns]


def current_map_filters(df: pd.DataFrame, key_prefix: str) -> dict[str, Any]:
    filters: dict[str, Any] = {
        "show_unlabeled": bool(st.session_state.get(f"{key_prefix}_show_unlabeled_stops", True)),
        "search_query": str(st.session_state.get(f"{key_prefix}_stop_search", "") or ""),
        "selected_routes": [
            route
            for route in st.session_state.get(f"{key_prefix}_route_filter", [])
            if route in route_filter_options(df)
        ],
        "categorical": {},
        "numeric": {},
        "destination_query": str(st.session_state.get(f"{key_prefix}_destination_filter", "") or ""),
    }
    for column in CATEGORICAL_MAP_FILTERS:
        options = categorical_filter_options(df, column)
        selected = st.session_state.get(f"{key_prefix}_{column}_filter", [])
        filters["categorical"][column] = [value for value in selected if value in options]
    for column in NUMERIC_MAP_FILTERS:
        bounds = numeric_filter_bounds(df, column)
        if bounds is None:
            continue
        selected = st.session_state.get(f"{key_prefix}_{column}_range", bounds)
        filters["numeric"][column] = {"selected": selected, "bounds": bounds}
    return filters


def render_map_filter_controls(df: pd.DataFrame, key_prefix: str) -> dict[str, Any]:
    with st.expander("Map filters", expanded=True):
        primary_cols = st.columns([1, 2, 2])
        primary_cols[0].toggle(
            "Show unlabeled bus stops",
            value=True,
            key=f"{key_prefix}_show_unlabeled_stops",
        )
        primary_cols[1].text_input(
            "Search stop name or ID",
            placeholder="Stop name or ID",
            key=f"{key_prefix}_stop_search",
        )
        primary_cols[2].multiselect(
            "Filter routes",
            route_filter_options(df),
            key=f"{key_prefix}_route_filter",
        )

        categorical_columns = [
            column for column in CATEGORICAL_MAP_FILTERS if categorical_filter_options(df, column)
        ]
        if categorical_columns:
            category_cols = st.columns(len(categorical_columns))
            for index, column in enumerate(categorical_columns):
                category_cols[index].multiselect(
                    display_label(column),
                    categorical_filter_options(df, column),
                    key=f"{key_prefix}_{column}_filter",
                )

        numeric_columns = [
            column for column in NUMERIC_MAP_FILTERS if numeric_filter_bounds(df, column) is not None
        ]
        if numeric_columns:
            numeric_cols = st.columns(min(3, len(numeric_columns)))
            for index, column in enumerate(numeric_columns):
                bounds = numeric_filter_bounds(df, column)
                if bounds is None:
                    continue
                low, high = bounds
                step = max((high - low) / 100.0, 0.01)
                numeric_cols[index % len(numeric_cols)].slider(
                    display_label(column),
                    min_value=low,
                    max_value=high,
                    value=(low, high),
                    step=step,
                    key=f"{key_prefix}_{column}_range",
                )

        if destination_columns(df):
            st.text_input(
                "Filter destinations",
                placeholder="Destination or nearby place",
                key=f"{key_prefix}_destination_filter",
            )
    return current_map_filters(df, key_prefix)


def filter_map_stops(
    df: pd.DataFrame,
    search_query: str = "",
    selected_routes: list[str] | None = None,
    filters: dict[str, Any] | None = None,
) -> pd.DataFrame:
    filtered = df.copy()
    selected_routes = selected_routes or []
    filters = filters or {}
    query = str(search_query or "").strip().lower()
    if query:
        searchable_columns = [column for column in ["stop_id", "stop_name", "routes"] if column in filtered.columns]
        if searchable_columns:
            search_blob = filtered[searchable_columns].fillna("").astype(str).agg(" ".join, axis=1).str.lower()
            filtered = filtered[search_blob.str.contains(re.escape(query), na=False)]
    if selected_routes and "routes" in filtered.columns:
        wanted = set(selected_routes)
        route_mask = filtered["routes"].apply(lambda value: bool(wanted.intersection(split_route_values(value))))
        filtered = filtered[route_mask]
    for column, selected in filters.get("categorical", {}).items():
        if selected and column in filtered.columns:
            values = filtered[column].fillna("").astype(str).str.strip()
            filtered = filtered[values.isin(set(selected))]
    for column, config in filters.get("numeric", {}).items():
        if column not in filtered.columns:
            continue
        selected = config.get("selected")
        bounds = config.get("bounds")
        if not selected or not bounds:
            continue
        low, high = float(selected[0]), float(selected[1])
        bound_low, bound_high = float(bounds[0]), float(bounds[1])
        if math.isclose(low, bound_low) and math.isclose(high, bound_high):
            continue
        values = pd.to_numeric(filtered[column], errors="coerce")
        filtered = filtered[values.between(low, high, inclusive="both")]
    destination_query = str(filters.get("destination_query", "") or "").strip().lower()
    if destination_query and destination_columns(filtered):
        destination_blob = (
            filtered[destination_columns(filtered)]
            .fillna("")
            .astype(str)
            .agg(" ".join, axis=1)
            .str.lower()
        )
        filtered = filtered[destination_blob.str.contains(re.escape(destination_query), na=False)]
    return filtered.copy()


def selected_stop_id_from_map_selection(selection_event: Any, df: pd.DataFrame) -> str | None:
    if selection_event is None:
        return None
    selection = getattr(selection_event, "selection", None)
    if selection is None and isinstance(selection_event, dict):
        selection = selection_event.get("selection")
    if selection is None:
        return None

    objects = getattr(selection, "objects", None)
    if objects is None and isinstance(selection, dict):
        objects = selection.get("objects")
    if isinstance(objects, dict):
        layer_objects = objects.get("stops_layer")
        if layer_objects:
            stop_id = layer_objects[0].get("stop_id")
            if stop_id is not None:
                return str(stop_id)

    indices = getattr(selection, "indices", None)
    if indices is None and isinstance(selection, dict):
        indices = selection.get("indices")
    if isinstance(indices, dict):
        layer_indices = indices.get("stops_layer")
        if layer_indices:
            index = int(layer_indices[0])
            if 0 <= index < len(df):
                return str(df.iloc[index].get("stop_id", ""))
    return None


def render_stop_detail_workflow(df: pd.DataFrame, visualization: dict[str, Any], key_prefix: str) -> None:
    if df.empty:
        st.info("No stop is available for the active map filters.")
        return

    options = df.reset_index(drop=True)
    stop_ids = options["stop_id"].astype(str).tolist() if "stop_id" in options.columns else []
    selected_key = f"{key_prefix}_selected_stop_id"
    selected_stop_id = str(st.session_state.get(selected_key, "") or "")
    if selected_stop_id not in stop_ids and stop_ids:
        selected_stop_id = stop_ids[0]
        st.session_state[selected_key] = selected_stop_id

    selected_index = stop_ids.index(selected_stop_id) if selected_stop_id in stop_ids else 0
    picker_key = f"{key_prefix}_stop_picker"
    current_picker = st.session_state.get(picker_key)
    if (
        not isinstance(current_picker, int)
        or current_picker < 0
        or current_picker >= len(options)
        or stop_ids[int(current_picker)] != selected_stop_id
    ):
        st.session_state[picker_key] = selected_index
    picked_index = st.selectbox(
        "Selected stop",
        range(len(options)),
        index=selected_index,
        format_func=lambda index: stop_picker_label(options.iloc[int(index)]),
        key=picker_key,
    )
    selected_stop = options.iloc[int(picked_index)]
    st.session_state[selected_key] = str(selected_stop.get("stop_id", ""))
    st.markdown(f"**{stop_picker_label(selected_stop)}**")

    st.markdown("#### Stop Details")
    priority = pd.to_numeric(pd.Series([selected_stop.get("priority_score")]), errors="coerce").iloc[0]
    summary_rows = [
        ("Shade", str(selected_stop.get("shading", "Unknown") or "Unknown")),
        ("Review", str(selected_stop.get("review_status", "Unknown") or "Unknown")),
        ("Priority", "N/A" if pd.isna(priority) else f"{float(priority):.2f}"),
    ]
    for label, value in summary_rows:
        st.markdown(f"**{label}**  \n{value}")

    detail_columns = []
    for column in get_selected_display_columns(options, visualization) + [
        "shade_coverage",
        "shade_sources",
        "routes",
        "stop_lat",
        "stop_lon",
    ]:
        if column in options.columns and column not in detail_columns:
            detail_columns.append(column)
    detail_rows = [
        {"Field": display_label(column), "Value": selected_stop.get(column, "")}
        for column in detail_columns
    ]
    for row in detail_rows:
        value = str(row["Value"] if pd.notna(row["Value"]) else "")
        st.markdown(f"**{row['Field']}**  \n{value}")


def render_preview_page() -> None:
    project = st.session_state["project"]
    methodology = st.session_state["methodology"]
    visualization = st.session_state["visualization"]
    taxonomy = st.session_state["taxonomy"]
    stops = st.session_state["stops"]
    stops["priority_score"] = calculate_priority_scores(stops, visualization["priority_weights"])

    st.title(project["name"])
    st.markdown(f"### {methodology['summary']}")
    st.caption(f"{project['agency']} | {project['region']} | dataset v{project['dataset_version']}")

    if stops.empty:
        st.warning("Import a stop dataset before previewing the public app.")
        return

    filters = current_map_filters(stops, "preview")
    visible_stops = filter_map_stops(
        filter_unlabeled_stops(stops, filters["show_unlabeled"]),
        filters["search_query"],
        filters["selected_routes"],
        filters,
    )

    render_metric_cards(visible_stops)
    tabs = st.tabs(["Map", "Analytics", "Methodology", "Exports"])
    with tabs[0]:
        if visible_stops.empty:
            st.info("No stops match the current visibility settings.")
        else:
            map_cols = st.columns([2, 1])
            with map_cols[0]:
                map_selection = st.pydeck_chart(
                    build_deck_chart(visible_stops, taxonomy, visualization),
                    use_container_width=True,
                    on_select="rerun",
                    selection_mode="single-object",
                    key="preview_stops_map",
                )
                selected_stop_id = selected_stop_id_from_map_selection(map_selection, visible_stops)
                if selected_stop_id:
                    st.session_state["preview_selected_stop_id"] = selected_stop_id
            with map_cols[1]:
                with st.container(height=VISUAL_MAP_HEIGHT, border=False):
                    render_stop_detail_workflow(visible_stops, visualization, "preview")
        st.caption(f"{len(visible_stops):,} of {len(stops):,} stops match the active map filters.")
        render_map_filter_controls(stops, "preview")
        if visualization.get("show_legend", True):
            legend = pd.DataFrame(taxonomy).sort_values("sort_order")
            st.dataframe(legend.loc[:, ["name", "description", "color"]], use_container_width=True, hide_index=True)
    with tabs[1]:
        render_issue_analytics_dashboard(visible_stops, visualization, active_raw_labels())
        render_custom_charts(visible_stops, visualization)
    with tabs[2]:
        render_builder_about_page(
            project=project,
            methodology=methodology,
            taxonomy=taxonomy,
            import_log=st.session_state["import_log"],
            priority_formula=priority_formula_for_about(visualization),
        )
    with tabs[3]:
        if visualization.get("show_downloads", True):
            st.download_button(
                "Download stops CSV",
                data=stops.to_csv(index=False).encode("utf-8"),
                file_name="shade_study_stops.csv",
                mime="text/csv",
            )
            st.download_button(
                "Download stops GeoJSON",
                data=dataframe_to_geojson(stops).encode("utf-8"),
                file_name="shade_study_stops.geojson",
                mime="application/geo+json",
            )
            st.download_button(
                "Download study configuration",
                data=study_config_json().encode("utf-8"),
                file_name="shade_study_config.json",
                mime="application/json",
            )
            raw_labels = active_raw_labels()
            if not raw_labels.empty:
                st.download_button(
                    "Download raw labels CSV",
                    data=raw_labels.to_csv(index=False).encode("utf-8"),
                    file_name="shade_study_raw_labels.csv",
                    mime="text/csv",
                )
        st.dataframe(pd.DataFrame(st.session_state["import_log"]), use_container_width=True, hide_index=True)


def render_deploy_page() -> None:
    project = st.session_state["project"]
    visualization = st.session_state["visualization"]
    stops = st.session_state["stops"]
    default_repo_name = slugify_repo_name(project.get("name", "shade-study-app"))

    st.title("Deploy")
    st.markdown(f"### Publish {project.get('name', 'this shade study')} as a GitHub-backed Streamlit app")

    if stops.empty:
        st.warning("Import a stop dataset before creating a deployment bundle.")
        return

    stops_for_export = stops.copy()
    stops_for_export["priority_score"] = calculate_priority_scores(stops_for_export, visualization["priority_weights"])

    left, right = st.columns([1, 1])
    with left:
        repo_name = st.text_input("GitHub repository name", default_repo_name)
        repo_name = slugify_repo_name(repo_name)
        st.link_button("Create GitHub repository", github_new_repo_url(project, repo_name))
    with right:
        st.metric("Stops included", f"{len(stops_for_export):,}")
        st.metric("Dataset version", project.get("dataset_version", "draft"))

    bundle_name = f"{repo_name}.zip"
    st.download_button(
        "Download GitHub deploy bundle",
        data=build_github_deploy_bundle(repo_name),
        file_name=bundle_name,
        mime="application/zip",
        type="primary",
    )

    st.markdown("#### Bundle Contents")
    st.dataframe(
        pd.DataFrame(
            [
                ("app.py", "Public Streamlit app rendered from the current builder state"),
                ("shade_study_stops.csv", "Published stop dataset"),
                ("shade_study_raw_labels.csv", "Raw label submissions, included when labels have been collected"),
                ("shade_study_config.json", "Project, methodology, taxonomy, visualization, and import-log settings"),
                ("requirements.txt", "Runtime dependencies for Streamlit Community Cloud"),
                ("README.md", "GitHub and Streamlit deployment notes"),
                ("deploy_to_github.ps1", "Optional GitHub CLI publishing helper"),
            ],
            columns=["File", "Purpose"],
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("#### Command-Line Publish")
    st.code(
        f'Expand-Archive .\\{bundle_name} -DestinationPath .\\{repo_name}\n'
        f"Set-Location .\\{repo_name}\n"
        f'.\\deploy_to_github.ps1 -RepositoryName "{repo_name}"',
        language="powershell",
    )


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    ensure_state()
    if st.session_state.get("page") in {"Methodology", "Methods"}:
        st.session_state["page"] = "Docs"
    page = render_header()
    if page == "Labels":
        render_labels_page()
    elif page == "Visuals":
        render_visuals_page()
    elif page == "Docs":
        render_methodology_page()
    elif page == "Preview":
        render_preview_page()
    elif page == "Deploy":
        render_deploy_page()
    else:
        render_data_page()
    save_active_project_to_store()
