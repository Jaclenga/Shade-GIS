from __future__ import annotations

import logging
import subprocess
import sys

import pandas as pd
import pyarrow as pa
import pytest

from shade_gis.data_quality import evaluate_data_quality
from shade_gis.pages.data_page import (
    dataframe_diagnostics,
    log_dataframe_diagnostics,
    streamlit_safe_dataframe,
)


def exact_data_quality_summary() -> pd.DataFrame:
    """Construct the exact frame rendered by render_data_quality_dashboard."""
    return evaluate_data_quality(pd.DataFrame(), pd.DataFrame()).summary_table()


def test_exact_data_quality_summary_converts_to_arrow_outside_streamlit():
    summary = exact_data_quality_summary()

    table = pa.Table.from_pandas(summary, preserve_index=False)

    assert summary.shape == (5, 3)
    assert summary.columns.tolist() == ["Validation issue", "Affected records", "Status"]
    assert table.num_rows == 5


@pytest.mark.parametrize(
    "column",
    ["Validation issue", "Affected records", "Status"],
)
def test_each_data_quality_summary_column_converts_in_its_own_subprocess(column: str):
    script = """
import sys
import pandas as pd
import pyarrow as pa
from shade_gis.data_quality import evaluate_data_quality

summary = evaluate_data_quality(pd.DataFrame(), pd.DataFrame()).summary_table()
for name in ["Validation issue", "Status"]:
    summary[name] = pd.Series(summary[name].tolist(), dtype=pd.StringDtype(storage="python"))
pa.Table.from_pandas(summary[[sys.argv[1]]], preserve_index=False)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, column],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, (
        f"Arrow conversion failed for data-quality column {column!r} "
        f"with return code {completed.returncode}.\n{completed.stdout}{completed.stderr}"
    )


def test_data_quality_summary_diagnostics_include_required_metadata(caplog):
    summary = exact_data_quality_summary()

    details = dataframe_diagnostics(summary)
    with caplog.at_level(logging.WARNING, logger="shade_gis.pages.data_page"):
        log_dataframe_diagnostics("data_quality_summary", summary)

    assert details["shape"] == [5, 3]
    assert details["column_names"] == ["Validation issue", "Affected records", "Status"]
    assert details["dtypes"] == [str(dtype) for dtype in summary.dtypes]
    assert details["has_duplicate_columns"] is False
    assert details["has_string_dtype"] is any(
        isinstance(dtype, pd.StringDtype) for dtype in summary.dtypes
    )
    assert all(item["python_types"] for item in details["columns"])
    assert "DataFrame diagnostics [data_quality_summary]" in caplog.text


def test_normalizer_converts_string_dtype_missing_and_mixed_values():
    frame = pd.DataFrame(
        {
            "text": pd.Series(["shade", pd.NA, None], dtype=pd.StringDtype(storage="python")),
            "number": [1, 2, 3],
            "flag": [True, False, True],
        }
    )

    display = streamlit_safe_dataframe(frame)

    assert display["text"].dtype == object
    assert display["text"].tolist() == ["shade", None, None]
    assert display["number"].dtype == frame["number"].dtype
    assert display["flag"].dtype == frame["flag"].dtype


def test_normalizer_serializes_nested_containers_as_json_strings():
    frame = pd.DataFrame(
        {
            "value": [
                ["tree", 1],
                {"source": "canopy"},
                ("awning", 2),
                {"b", "a"},
            ]
        },
        dtype=object,
    )

    display = streamlit_safe_dataframe(frame)

    assert display["value"].tolist() == [
        '["tree", 1]',
        '{"source": "canopy"}',
        '["awning", 2]',
        '["a", "b"]',
    ]


def test_normalizer_stringifies_unsupported_custom_objects():
    class CustomValue:
        def __str__(self) -> str:
            return "custom-value"

    display = streamlit_safe_dataframe(pd.DataFrame({"value": [CustomValue()]}, dtype=object))

    assert display["value"].tolist() == ["custom-value"]


def test_normalizer_rejects_duplicate_columns():
    frame = pd.DataFrame([[1, 2]], columns=["duplicate", "duplicate"])

    with pytest.raises(ValueError, match="duplicate columns"):
        streamlit_safe_dataframe(frame)


def test_normalized_complex_frame_converts_to_arrow():
    frame = pd.DataFrame(
        {
            "text": pd.Series(["shade", pd.NA], dtype=pd.StringDtype(storage="python")),
            "nested": [{"source": "tree"}, ["awning"]],
            "count": [1, 2],
            "usable": [True, False],
        }
    )

    display = streamlit_safe_dataframe(frame)
    table = pa.Table.from_pandas(display, preserve_index=False)

    assert table.num_rows == 2
    assert str(table.schema.field("text").type) == "string"
    assert str(table.schema.field("nested").type) == "string"
    assert str(table.schema.field("count").type) == "int64"
    assert str(table.schema.field("usable").type) == "bool"
