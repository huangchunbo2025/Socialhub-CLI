"""Tests for Snowflake sync helpers."""

import shutil
from pathlib import Path

import pandas as pd

from cli.snowflake_sync import load_state, map_identity_type, normalize_customer_frame, quote_identifier


def test_quote_identifier_escapes_double_quotes() -> None:
    assert quote_identifier('bad"name') == '"bad""name"'


def test_map_identity_type() -> None:
    assert map_identity_type(1) == "member"
    assert map_identity_type("2") == "identity_2"


def test_normalize_customer_frame() -> None:
    frame = pd.DataFrame(
        [
            {
                "CUSTOMER_CODE": "C001",
                "CUSTOMER_NAME": "Alice",
                "CREATE_TIME": "2026-03-26 10:00:00",
                "IDENTITY_TYPE": 1,
                "SOURCE_NAME": "H5",
                "SOURCE_CODE": "1001",
                "GENDER": "F",
                "BITMAP_ID": 8,
            }
        ]
    )

    normalized = normalize_customer_frame(frame)

    assert list(normalized.columns[:4]) == ["id", "name", "customer_type", "created_at"]
    assert normalized.loc[0, "id"] == "C001"
    assert normalized.loc[0, "customer_type"] == "member"
    assert str(normalized.loc[0, "created_at"]) == "2026-03-26 10:00:00"


def test_load_state_returns_none_for_missing_or_invalid_file() -> None:
    temp_path = Path(__file__).parent / "_snowflake_sync_tmp"
    temp_path.mkdir(exist_ok=True)
    try:
        missing = temp_path / "missing.json"
        assert load_state(missing) is None

        invalid = temp_path / "invalid.json"
        invalid.write_text("{bad json", encoding="utf-8")
        assert load_state(invalid) is None
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)
