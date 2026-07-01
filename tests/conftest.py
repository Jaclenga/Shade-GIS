from __future__ import annotations

import copy
import gc
import sys
import time
import uuid
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from builder_app import DEFAULT_METHODOLOGY, DEFAULT_PROJECT, DEFAULT_TAXONOMY, DEFAULT_VISUALIZATION


@pytest.fixture
def db_path() -> Path:
    directory = Path(".test_dbs")
    directory.mkdir(exist_ok=True)
    path = directory / f"shade-gis-test-{uuid.uuid4().hex}.sqlite3"
    yield path
    for candidate in [path, path.with_name(f"{path.name}-journal")]:
        for _attempt in range(3):
            try:
                gc.collect()
                candidate.unlink(missing_ok=True)
                break
            except PermissionError:
                time.sleep(0.1)


@pytest.fixture
def project() -> dict:
    data = copy.deepcopy(DEFAULT_PROJECT)
    data.update(
        {
            "name": "Test Shade Study",
            "agency": "Test Transit",
            "region": "Test City",
            "dataset_version": "test-1",
            "methodology_version": "test-1",
            "source_name": "pytest fixture",
        }
    )
    return data


@pytest.fixture
def taxonomy() -> list[dict]:
    return copy.deepcopy(DEFAULT_TAXONOMY)


@pytest.fixture
def methodology() -> dict:
    data = copy.deepcopy(DEFAULT_METHODOLOGY)
    data["summary"] = "Pytest methodology summary"
    return data


@pytest.fixture
def visualization() -> dict:
    return copy.deepcopy(DEFAULT_VISUALIZATION)


@pytest.fixture
def minimal_stops() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "stop_id": "1001",
                "stop_name": "Main St & 1st Ave",
                "stop_lat": 27.9506,
                "stop_lon": -82.4572,
                "agency": "Test Transit",
                "routes": "10",
                "municipality": "Test City",
                "shading": "No Shade",
                "review_status": "Needs Review",
                "confidence": 0.7,
                "ridership": 120,
                "heat_vulnerability_index": 0.9,
                "tree_canopy_pct": 0.1,
                "nearby_destinations": "Hospital",
            },
            {
                "stop_id": "1002",
                "stop_name": "Central Ave",
                "stop_lat": 27.9510,
                "stop_lon": -82.4590,
                "agency": "Test Transit",
                "routes": "10",
                "municipality": "Test City",
                "shading": "Limited Natural Shade",
                "review_status": "Unlabeled",
                "confidence": 0.9,
                "ridership": 80,
                "heat_vulnerability_index": 0.3,
                "tree_canopy_pct": 0.6,
                "nearby_destinations": "School",
            },
        ]
    )
