import io
import ipaddress
import json
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_API_BYTES = 15 * 1024 * 1024
DEFAULT_MAX_ZIP_MEMBERS = 256
DEFAULT_MAX_ZIP_MEMBER_BYTES = 80 * 1024 * 1024
DEFAULT_MAX_ZIP_UNCOMPRESSED_BYTES = 150 * 1024 * 1024
DEFAULT_PRIORITY_WEIGHTS = {"ridership": 0.5, "low_shade": 0.5}
API_FETCH_TIMEOUT_SECONDS = 30

SHADE_ALIASES = {
    "Constructed Shade": "Intentional Built Shade",
    "Manmade Shade": "Incidental Built Shade",
    "Unknown": "Needs Review",
}
REVIEW_STATUS_NAMES = {
    "Unlabeled",
    "Needs Review",
    "Crowd Reviewed",
    "Expert Reviewed",
    "Accepted",
    "Disputed",
    "Archived",
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
    "nearby_destinations",
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
    "nearby_destinations": ["nearby_destinations", "destinations", "destination", "nearby_places", "places"],
}


def timestamp_with_timezone() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def hex_to_rgb(value: str) -> list[int]:
    text = str(value or "").strip().lstrip("#")
    if len(text) != 6:
        return [128, 128, 128]
    try:
        return [int(text[index : index + 2], 16) for index in (0, 2, 4)]
    except ValueError:
        return [128, 128, 128]


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
    return text if text in REVIEW_STATUS_NAMES else "Needs Review"


def env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def max_upload_bytes() -> int:
    return env_int("SHADE_GIS_MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES)


def max_api_bytes() -> int:
    return env_int("SHADE_GIS_MAX_API_BYTES", DEFAULT_MAX_API_BYTES)


def max_zip_members() -> int:
    return env_int("SHADE_GIS_MAX_ZIP_MEMBERS", DEFAULT_MAX_ZIP_MEMBERS)


def max_zip_member_bytes() -> int:
    return env_int("SHADE_GIS_MAX_ZIP_MEMBER_BYTES", DEFAULT_MAX_ZIP_MEMBER_BYTES)


def max_zip_uncompressed_bytes() -> int:
    return env_int("SHADE_GIS_MAX_ZIP_UNCOMPRESSED_BYTES", DEFAULT_MAX_ZIP_UNCOMPRESSED_BYTES)


def format_bytes(value: int) -> str:
    if value >= 1024 * 1024:
        return f"{value / (1024 * 1024):.1f} MB"
    if value >= 1024:
        return f"{value / 1024:.1f} KB"
    return f"{value} bytes"


def validate_bytes_size(contents: bytes, limit: int, label: str) -> None:
    if len(contents) > limit:
        raise ValueError(f"{label} is {format_bytes(len(contents))}; the limit is {format_bytes(limit)}")


def allowed_api_hosts() -> list[str]:
    return [
        host.strip().lower().rstrip(".")
        for host in os.environ.get("SHADE_GIS_ALLOWED_API_HOSTS", "").split(",")
        if host.strip()
    ]


def api_host_matches(host: str, allowed_host: str) -> bool:
    allowed_host = allowed_host.lstrip(".")
    return host == allowed_host or host.endswith(f".{allowed_host}")


def is_private_network_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def validate_api_url(url: str) -> str:
    clean_url = url.strip()
    parsed = urllib.parse.urlparse(clean_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("API URL must use http or https")
    if parsed.username or parsed.password:
        raise ValueError("API URL must not include embedded credentials")
    if not parsed.hostname:
        raise ValueError("API URL must include a host")

    host = parsed.hostname.lower().rstrip(".")
    allowed_hosts = allowed_api_hosts()
    if allowed_hosts and not any(api_host_matches(host, allowed_host) for allowed_host in allowed_hosts):
        raise ValueError("API URL host is not in SHADE_GIS_ALLOWED_API_HOSTS")

    if not env_flag("SHADE_GIS_ALLOW_PRIVATE_API_URLS"):
        if host == "localhost" or host.endswith(".localhost"):
            raise ValueError("Private or localhost API URLs are disabled by default")
        try:
            if is_private_network_address(host):
                raise ValueError("Private or localhost API URLs are disabled by default")
        except ValueError as error:
            if "disabled by default" in str(error):
                raise
        try:
            addresses = {
                result[4][0]
                for result in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
            }
        except socket.gaierror as error:
            raise ValueError(f"Could not resolve API URL host: {host}") from error
        for address in addresses:
            try:
                if is_private_network_address(address):
                    raise ValueError("Private or localhost API URLs are disabled by default")
            except ValueError as error:
                if "disabled by default" in str(error):
                    raise

    return clean_url


def read_limited_response(response: Any, limit: int) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = 0
        if declared_size > limit:
            raise ValueError(f"API response declares {format_bytes(declared_size)}; the limit is {format_bytes(limit)}")

    buffer = io.BytesIO()
    while True:
        chunk = response.read(64 * 1024)
        if not chunk:
            break
        buffer.write(chunk)
        if buffer.tell() > limit:
            raise ValueError(f"API response exceeded the {format_bytes(limit)} limit")
    return buffer.getvalue()


def validate_zip_bytes(contents: bytes, label: str = "ZIP upload") -> None:
    validate_bytes_size(contents, max_upload_bytes(), label)
    with zipfile.ZipFile(io.BytesIO(contents)) as archive:
        members = archive.infolist()
        if len(members) > max_zip_members():
            raise ValueError(f"{label} contains {len(members)} files; the limit is {max_zip_members()}")
        total_uncompressed = sum(member.file_size for member in members)
        if total_uncompressed > max_zip_uncompressed_bytes():
            raise ValueError(
                f"{label} expands to {format_bytes(total_uncompressed)}; "
                f"the limit is {format_bytes(max_zip_uncompressed_bytes())}"
            )
        for member in members:
            if member.file_size > max_zip_member_bytes():
                raise ValueError(
                    f"{label} member {member.filename!r} expands to {format_bytes(member.file_size)}; "
                    f"the per-file limit is {format_bytes(max_zip_member_bytes())}"
                )


def read_csv_bytes(contents: bytes, *, limit: int | None = None, label: str = "CSV upload") -> pd.DataFrame:
    validate_bytes_size(contents, limit or max_upload_bytes(), label)
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


def parse_geojson_bytes(
    contents: bytes,
    *,
    limit: int | None = None,
    label: str = "GeoJSON upload",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    validate_bytes_size(contents, limit or max_upload_bytes(), label)
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
    validate_bytes_size(contents, max_upload_bytes(), "GeoJSON overlay upload")
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
    validate_zip_bytes(contents)
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
    validate_zip_bytes(contents, "Shapefile ZIP upload")
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
    validate_zip_bytes(contents, "Shapefile overlay ZIP upload")
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
    clean_url = validate_api_url(url)
    request = urllib.request.Request(
        clean_url,
        headers={"User-Agent": "Shade-GIS/0.1 (+https://github.com/)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=API_FETCH_TIMEOUT_SECONDS) as response:
            return read_limited_response(response, max_api_bytes())
    except (urllib.error.URLError, ValueError) as error:
        raise RuntimeError(f"Could not fetch API URL: {error}") from error


def parse_api_response(contents: bytes, url: str, requested_format: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    validate_bytes_size(contents, max_api_bytes(), "API response")
    if requested_format == "CSV":
        return read_csv_bytes(contents, limit=max_api_bytes(), label="API CSV response"), {"source_url": url}
    if requested_format == "GeoJSON":
        raw, metadata = parse_geojson_bytes(contents, limit=max_api_bytes(), label="API GeoJSON response")
        metadata["source_url"] = url
        return raw, metadata
    try:
        raw, metadata = parse_geojson_bytes(contents, limit=max_api_bytes(), label="API GeoJSON response")
        metadata["source_url"] = url
        metadata["detected_format"] = "GeoJSON"
        return raw, metadata
    except Exception:
        raw = read_csv_bytes(contents, limit=max_api_bytes(), label="API CSV response")
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
    validate_zip_bytes(contents, "GTFS ZIP upload")
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


def calculate_priority_scores(df: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    weights = weights or DEFAULT_PRIORITY_WEIGHTS
    score_parts: list[tuple[float, pd.Series]] = []

    ridership_weight = float(weights.get("ridership", 0.0))
    if ridership_weight > 0 and "ridership" in df.columns:
        ridership = pd.to_numeric(df.get("ridership"), errors="coerce").fillna(0)
        ridership = ridership / ridership.max() if ridership.max() and ridership.max() > 0 else ridership
        score_parts.append((ridership_weight, ridership))

    low_shade_weight = float(weights.get("low_shade", 0.0))
    if low_shade_weight > 0 and "shading" in df.columns:
        low_shade = df.get("shading", pd.Series(index=df.index, dtype=str)).isin(["No Shade", "Needs Review"]).astype(float)
        score_parts.append((low_shade_weight, low_shade))

    total_weight = sum(weight for weight, _ in score_parts)
    if total_weight <= 0:
        return pd.Series(0.0, index=df.index)
    score = sum(series * weight for weight, series in score_parts) / total_weight
    return (score * 100).round(1)


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

    numeric_fields = ["confidence", "ridership"]
    for field in numeric_fields:
        df[field] = pd.to_numeric(df[field], errors="coerce")

    df = df.dropna(subset=["stop_lat", "stop_lon"])
    df = df[df["stop_id"] != ""].drop_duplicates(subset=["stop_id"], keep="first")
    df["priority_score"] = calculate_priority_scores(df)
    return df.reset_index(drop=True)


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
    st.dataframe(raw.head(25), width="stretch")
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

