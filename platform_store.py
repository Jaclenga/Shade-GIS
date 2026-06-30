"""Durable storage helpers for the Shade Study Builder platform."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


APP_DIR = Path(__file__).parent
_ACTIVE_DATABASE_PATH: Path | None = None
_UNUSABLE_DATABASE_PATHS: set[Path] = set()
_DATABASE_FALLBACK_REASON = ""


def default_database_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Shade-GIS" / "shade_study_builder.sqlite3"
    return APP_DIR / "platform_data" / "shade_study_builder.sqlite3"


def fallback_database_paths() -> list[Path]:
    return [
        Path.home() / ".shade-gis" / "shade_study_builder.sqlite3",
        Path(tempfile.gettempdir()) / "Shade-GIS" / "shade_study_builder.sqlite3",
    ]


def candidate_database_paths() -> list[Path]:
    candidates = []
    configured = os.environ.get("SHADE_GIS_DB_PATH")
    if configured:
        candidates.append(Path(configured))
    candidates.append(default_database_path())
    candidates.extend(fallback_database_paths())

    unique = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def is_readonly_database_error(error: BaseException) -> bool:
    return "readonly database" in str(error).lower()


def probe_database_writable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SQLITE_SCHEMA)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS storage_healthcheck (
                id INTEGER PRIMARY KEY,
                checked_at TEXT NOT NULL
            )
            """
        )
        conn.execute("INSERT INTO storage_healthcheck (checked_at) VALUES (?)", (utc_timestamp(),))
        conn.execute(
            """
            DELETE FROM storage_healthcheck
            WHERE id NOT IN (SELECT id FROM storage_healthcheck ORDER BY id DESC LIMIT 3)
            """
        )
        conn.commit()


def mark_database_path_unusable(path: Path, reason: BaseException | str) -> None:
    global _ACTIVE_DATABASE_PATH, _DATABASE_FALLBACK_REASON
    resolved = path.expanduser().resolve()
    _UNUSABLE_DATABASE_PATHS.add(resolved)
    if _ACTIVE_DATABASE_PATH == resolved:
        _ACTIVE_DATABASE_PATH = None
    _DATABASE_FALLBACK_REASON = str(reason)


def choose_database_path() -> Path:
    global _ACTIVE_DATABASE_PATH, _DATABASE_FALLBACK_REASON
    if _ACTIVE_DATABASE_PATH and _ACTIVE_DATABASE_PATH not in _UNUSABLE_DATABASE_PATHS:
        return _ACTIVE_DATABASE_PATH

    last_error: BaseException | None = None
    for candidate in candidate_database_paths():
        if candidate in _UNUSABLE_DATABASE_PATHS:
            continue
        try:
            probe_database_writable(candidate)
        except (OSError, sqlite3.Error) as error:
            last_error = error
            _UNUSABLE_DATABASE_PATHS.add(candidate)
            _DATABASE_FALLBACK_REASON = str(error)
            continue
        _ACTIVE_DATABASE_PATH = candidate
        return candidate

    if last_error:
        raise sqlite3.OperationalError(f"No writable Shade-GIS database path is available: {last_error}") from last_error
    raise sqlite3.OperationalError("No writable Shade-GIS database path is available")


def database_status() -> dict[str, Any]:
    active = database_path()
    preferred = candidate_database_paths()[0]
    return {
        "active_path": str(active),
        "preferred_path": str(preferred),
        "using_fallback": active != preferred,
        "fallback_reason": _DATABASE_FALLBACK_REASON,
    }


PROJECT_FIELDS = [
    "name",
    "agency",
    "region",
    "description",
    "owners",
    "visibility",
    "dataset_version",
    "methodology_version",
    "source_name",
    "source_license",
    "source_url",
]

STOP_FIELDS = [
    "stop_id",
    "stop_name",
    "stop_lat",
    "stop_lon",
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
    "priority_score",
]

LABEL_FIELDS = [
    "id",
    "project_id",
    "stop_id",
    "image_id",
    "labeler_id",
    "labeler_role",
    "shade_category",
    "shade_coverage",
    "shade_sources",
    "confidence",
    "notes",
    "source",
    "metadata_json",
    "created_at",
]

NUMERIC_STOP_FIELDS = {
    "stop_lat",
    "stop_lon",
    "confidence",
    "ridership",
    "heat_vulnerability_index",
    "tree_canopy_pct",
    "lst_median",
    "priority_score",
}


def utc_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def database_path() -> Path:
    return choose_database_path()


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = Path(path) if path is not None else database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database(path: Path | None = None) -> Path:
    db_path = Path(path) if path is not None else database_path()
    with connect(db_path) as conn:
        conn.executescript(SQLITE_SCHEMA)
    return db_path


def list_projects(path: Path | None = None) -> list[dict[str, Any]]:
    init_database(path)
    with connect(path) as conn:
        rows = conn.execute(
            """
            SELECT id, name, agency, region, visibility, dataset_version, updated_at
            FROM projects
            ORDER BY updated_at DESC, name COLLATE NOCASE
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_shade_labels(
    project_id: str,
    stop_id: str | None = None,
    path: Path | None = None,
) -> pd.DataFrame:
    init_database(path)
    filters = ["project_id = ?"]
    params: list[Any] = [project_id]
    if stop_id:
        filters.append("stop_id = ?")
        params.append(stop_id)
    where_clause = " AND ".join(filters)
    with connect(path) as conn:
        rows = conn.execute(
            f"""
            SELECT id, project_id, stop_id, image_id, labeler_id, labeler_role,
                   shade_category, shade_coverage, shade_sources, confidence,
                   notes, source, metadata_json, created_at
            FROM shade_labels
            WHERE {where_clause}
            ORDER BY created_at DESC, id DESC
            """,
            params,
        ).fetchall()
    records = []
    for row in rows:
        record = {field: row[field] for field in LABEL_FIELDS}
        metadata = json.loads(record.pop("metadata_json") or "{}")
        for key, value in metadata.items():
            record[f"metadata_{key}"] = value
        records.append(record)
    if not records:
        return pd.DataFrame(columns=[field for field in LABEL_FIELDS if field != "metadata_json"])
    return pd.DataFrame(records)


def add_shade_label(
    project_id: str,
    label: dict[str, Any],
    path: Path | None = None,
) -> str:
    db_path = Path(path) if path is not None else database_path()
    for attempt in range(2):
        try:
            return _add_shade_label_once(project_id, label, db_path)
        except sqlite3.OperationalError as error:
            if path is None and attempt == 0 and is_readonly_database_error(error):
                mark_database_path_unusable(db_path, error)
                db_path = database_path()
                continue
            raise
    raise sqlite3.OperationalError("Could not write shade label")


def _add_shade_label_once(
    project_id: str,
    label: dict[str, Any],
    path: Path,
) -> str:
    init_database(path)
    label_id = str(uuid.uuid4())
    now = utc_timestamp()
    metadata = {
        key: clean_scalar(value)
        for key, value in label.items()
        if key
        not in {
            "stop_id",
            "image_id",
            "labeler_id",
            "labeler_role",
            "shade_category",
            "shade_coverage",
            "shade_sources",
            "confidence",
            "notes",
            "source",
        }
    }
    with connect(path) as conn:
        conn.execute(
            """
            INSERT INTO shade_labels (
                id, project_id, stop_id, image_id, labeler_id, labeler_role,
                shade_category, shade_coverage, shade_sources, confidence,
                notes, source, metadata_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                label_id,
                project_id,
                clean_scalar(label.get("stop_id", "")),
                clean_optional_text(label.get("image_id", "")),
                clean_scalar(label.get("labeler_id", "")),
                clean_scalar(label.get("labeler_role", "")),
                clean_scalar(label.get("shade_category", "")),
                clean_scalar(label.get("shade_coverage", "")),
                clean_scalar(label.get("shade_sources", "")),
                clean_number(label.get("confidence")),
                clean_scalar(label.get("notes", "")),
                clean_scalar(label.get("source", "manual")),
                json.dumps(metadata, ensure_ascii=True),
                now,
            ),
        )
        conn.commit()
    return label_id


def create_project(
    project: dict[str, Any],
    taxonomy: list[dict[str, Any]],
    methodology: dict[str, Any],
    visualization: dict[str, Any],
    stops: pd.DataFrame,
    import_log: list[dict[str, Any]],
    path: Path | None = None,
) -> str:
    project_id = str(uuid.uuid4())
    save_project_bundle(project_id, project, taxonomy, methodology, visualization, stops, import_log, path)
    return project_id


def load_project_bundle(project_id: str, path: Path | None = None) -> dict[str, Any]:
    init_database(path)
    with connect(path) as conn:
        project_row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if project_row is None:
            raise KeyError(f"Project {project_id} was not found")

        settings_row = conn.execute(
            "SELECT methodology_json, visualization_json FROM project_settings WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        taxonomy_rows = conn.execute(
            """
            SELECT name, description, color, sort_order
            FROM shade_taxonomy
            WHERE project_id = ?
            ORDER BY sort_order, name COLLATE NOCASE
            """,
            (project_id,),
        ).fetchall()
        stop_rows = conn.execute(
            """
            SELECT *
            FROM stops
            WHERE project_id = ?
            ORDER BY stop_name COLLATE NOCASE, stop_id COLLATE NOCASE
            """,
            (project_id,),
        ).fetchall()
        import_rows = conn.execute(
            """
            SELECT source, format, rows, imported_at, metadata_json
            FROM import_logs
            WHERE project_id = ?
            ORDER BY id
            """,
            (project_id,),
        ).fetchall()

    project = {field: project_row[field] for field in PROJECT_FIELDS}
    methodology = json.loads(settings_row["methodology_json"]) if settings_row else {}
    visualization = json.loads(settings_row["visualization_json"]) if settings_row else {}
    taxonomy = [dict(row) for row in taxonomy_rows]
    import_log = []
    for row in import_rows:
        entry = {
            "source": row["source"],
            "format": row["format"],
            "rows": row["rows"],
            "imported_at": row["imported_at"],
        }
        entry.update(json.loads(row["metadata_json"] or "{}"))
        import_log.append(entry)

    return {
        "project_id": project_id,
        "project": project,
        "taxonomy": taxonomy,
        "methodology": methodology,
        "visualization": visualization,
        "stops": stops_dataframe(stop_rows),
        "import_log": import_log,
    }


def save_project_bundle(
    project_id: str,
    project: dict[str, Any],
    taxonomy: list[dict[str, Any]],
    methodology: dict[str, Any],
    visualization: dict[str, Any],
    stops: pd.DataFrame,
    import_log: list[dict[str, Any]],
    path: Path | None = None,
) -> None:
    db_path = Path(path) if path is not None else database_path()
    for attempt in range(2):
        try:
            _save_project_bundle_once(project_id, project, taxonomy, methodology, visualization, stops, import_log, db_path)
            return
        except sqlite3.OperationalError as error:
            if path is None and attempt == 0 and is_readonly_database_error(error):
                mark_database_path_unusable(db_path, error)
                db_path = database_path()
                continue
            raise


def _save_project_bundle_once(
    project_id: str,
    project: dict[str, Any],
    taxonomy: list[dict[str, Any]],
    methodology: dict[str, Any],
    visualization: dict[str, Any],
    stops: pd.DataFrame,
    import_log: list[dict[str, Any]],
    path: Path,
) -> None:
    init_database(path)
    now = utc_timestamp()
    project_values = {field: clean_scalar(project.get(field, "")) for field in PROJECT_FIELDS}
    if not project_values.get("name"):
        project_values["name"] = "Untitled Shade Study"
    if not project_values.get("visibility"):
        project_values["visibility"] = "Private"

    with connect(path) as conn:
        conn.execute(
            """
            INSERT INTO projects (
                id, name, agency, region, description, owners, visibility,
                dataset_version, methodology_version, source_name, source_license,
                source_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                agency = excluded.agency,
                region = excluded.region,
                description = excluded.description,
                owners = excluded.owners,
                visibility = excluded.visibility,
                dataset_version = excluded.dataset_version,
                methodology_version = excluded.methodology_version,
                source_name = excluded.source_name,
                source_license = excluded.source_license,
                source_url = excluded.source_url,
                updated_at = excluded.updated_at
            """,
            (
                project_id,
                project_values["name"],
                project_values["agency"],
                project_values["region"],
                project_values["description"],
                project_values["owners"],
                project_values["visibility"],
                project_values["dataset_version"],
                project_values["methodology_version"],
                project_values["source_name"],
                project_values["source_license"],
                project_values["source_url"],
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO project_settings (project_id, methodology_json, visualization_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                methodology_json = excluded.methodology_json,
                visualization_json = excluded.visualization_json,
                updated_at = excluded.updated_at
            """,
            (
                project_id,
                json.dumps(methodology, ensure_ascii=True),
                json.dumps(visualization, ensure_ascii=True),
                now,
            ),
        )

        conn.execute("DELETE FROM shade_taxonomy WHERE project_id = ?", (project_id,))
        conn.executemany(
            """
            INSERT INTO shade_taxonomy (project_id, name, description, color, sort_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    project_id,
                    clean_scalar(item.get("name", "")),
                    clean_scalar(item.get("description", "")),
                    clean_scalar(item.get("color", "")),
                    int(float(item.get("sort_order") or index + 1)),
                )
                for index, item in enumerate(taxonomy)
            ],
        )

        conn.execute("DELETE FROM stops WHERE project_id = ?", (project_id,))
        conn.executemany(
            """
            INSERT INTO stops (
                project_id, stop_id, stop_name, stop_lat, stop_lon, agency, routes,
                municipality, shading, shade_coverage, shade_sources, review_status,
                confidence, ridership, heat_vulnerability_index, heat_vulnerability_label,
                tree_canopy_pct, lst_median, priority_score, extra_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [stop_record(project_id, row, now) for row in dataframe_records(stops)],
        )

        conn.execute("DELETE FROM import_logs WHERE project_id = ?", (project_id,))
        conn.executemany(
            """
            INSERT INTO import_logs (project_id, source, format, rows, imported_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [import_log_record(project_id, entry) for entry in import_log],
        )
        conn.commit()


def stops_dataframe(rows: list[sqlite3.Row]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for row in rows:
        record = {field: row[field] for field in STOP_FIELDS}
        record.update(json.loads(row["extra_json"] or "{}"))
        records.append(record)
    if not records:
        return pd.DataFrame(columns=STOP_FIELDS)
    return pd.DataFrame(records)


def dataframe_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    records = df.where(pd.notna(df), None).to_dict("records")
    return [{str(key): clean_scalar(value) for key, value in record.items()} for record in records]


def stop_record(project_id: str, row: dict[str, Any], now: str) -> tuple[Any, ...]:
    extra = {key: value for key, value in row.items() if key not in STOP_FIELDS}
    values = [row.get(field) for field in STOP_FIELDS]
    return (
        project_id,
        clean_scalar(values[0]),
        clean_scalar(values[1]),
        clean_number(values[2]),
        clean_number(values[3]),
        clean_scalar(values[4]),
        clean_scalar(values[5]),
        clean_scalar(values[6]),
        clean_scalar(values[7]),
        clean_scalar(values[8]),
        clean_scalar(values[9]),
        clean_scalar(values[10]),
        clean_number(values[11]),
        clean_number(values[12]),
        clean_number(values[13]),
        clean_scalar(values[14]),
        clean_number(values[15]),
        clean_number(values[16]),
        clean_number(values[17]),
        json.dumps(extra, ensure_ascii=True),
        now,
        now,
    )


def import_log_record(project_id: str, entry: dict[str, Any]) -> tuple[Any, ...]:
    metadata = {
        key: clean_scalar(value)
        for key, value in entry.items()
        if key not in {"source", "format", "rows", "imported_at"}
    }
    return (
        project_id,
        clean_scalar(entry.get("source", "")),
        clean_scalar(entry.get("format", "")),
        int(entry.get("rows") or 0),
        clean_scalar(entry.get("imported_at", "")),
        json.dumps(metadata, ensure_ascii=True),
    )


def clean_scalar(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=True)
    return value


def clean_optional_text(value: Any) -> str | None:
    value = clean_scalar(value)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def clean_number(value: Any) -> float | None:
    value = clean_scalar(value)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    agency TEXT,
    region TEXT,
    description TEXT,
    owners TEXT,
    visibility TEXT NOT NULL DEFAULT 'Private',
    dataset_version TEXT,
    methodology_version TEXT,
    source_name TEXT,
    source_license TEXT,
    source_url TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_settings (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    methodology_json TEXT NOT NULL DEFAULT '{}',
    visualization_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shade_taxonomy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    color TEXT,
    sort_order INTEGER NOT NULL DEFAULT 1,
    UNIQUE(project_id, name)
);

CREATE TABLE IF NOT EXISTS stops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    stop_id TEXT NOT NULL,
    stop_name TEXT NOT NULL,
    stop_lat REAL,
    stop_lon REAL,
    agency TEXT,
    routes TEXT,
    municipality TEXT,
    shading TEXT,
    shade_coverage TEXT,
    shade_sources TEXT,
    review_status TEXT,
    confidence REAL,
    ridership REAL,
    heat_vulnerability_index REAL,
    heat_vulnerability_label TEXT,
    tree_canopy_pct REAL,
    lst_median REAL,
    priority_score REAL,
    extra_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, stop_id)
);

CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    stop_id TEXT,
    uri TEXT NOT NULL,
    storage_path TEXT,
    image_type TEXT,
    source TEXT,
    captured_at TEXT,
    attribution TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shade_labels (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    stop_id TEXT NOT NULL,
    image_id TEXT REFERENCES images(id) ON DELETE SET NULL,
    labeler_id TEXT,
    labeler_role TEXT,
    shade_category TEXT,
    shade_coverage TEXT,
    shade_sources TEXT,
    confidence REAL,
    notes TEXT,
    source TEXT NOT NULL DEFAULT 'manual',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_history (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    stop_id TEXT NOT NULL,
    actor_id TEXT,
    action TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    notes TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS releases (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    version TEXT NOT NULL,
    dataset_version TEXT,
    methodology_version TEXT,
    taxonomy_version TEXT,
    import_version TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    released_at TEXT,
    artifact_manifest_json TEXT NOT NULL DEFAULT '{}',
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, version)
);

CREATE TABLE IF NOT EXISTS import_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source TEXT,
    format TEXT,
    rows INTEGER,
    imported_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_stops_project ON stops(project_id);
CREATE INDEX IF NOT EXISTS idx_images_project_stop ON images(project_id, stop_id);
CREATE INDEX IF NOT EXISTS idx_labels_project_stop ON shade_labels(project_id, stop_id);
CREATE INDEX IF NOT EXISTS idx_review_project_stop ON review_history(project_id, stop_id);
CREATE INDEX IF NOT EXISTS idx_releases_project ON releases(project_id);
"""
