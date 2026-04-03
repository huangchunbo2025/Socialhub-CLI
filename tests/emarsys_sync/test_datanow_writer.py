"""Tests for StarRocks datanow_ t_retailevent Stream Load writer."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from emarsys_sync.datanow_writer import DatanowWriter


def test_write_skips_unmapped_table():
    writer = DatanowWriter(
        host="localhost", http_port=8030, user="root", password="",
        database="datanow_uat"
    )
    with patch("httpx.put") as mock_put:
        result = writer.write("revenue_attribution", [], tenant_id="uat", customer_code="uat")
        mock_put.assert_not_called()
    assert result == 0


def test_write_calls_stream_load_for_email_sends():
    writer = DatanowWriter(
        host="localhost", http_port=8030, user="root", password="",
        database="datanow_uat"
    )
    rows = [{
        "contact_id": 1, "event_time": "2026-01-01T00:00:00Z",
        "message_id": 10, "campaign_id": 5, "customer_id": "12345",
        "launch_id": 1, "domain": "x.com", "campaign_type": "batch",
        "loaded_at": "2026-01-01",
    }]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"Status": "Success", "NumberLoadedRows": 1}

    with patch("httpx.put", return_value=mock_resp) as mock_put:
        count = writer.write("email_sends", rows, tenant_id="uat", customer_code="uat")

    mock_put.assert_called_once()
    call_kwargs = mock_put.call_args
    assert "t_retailevent" in call_kwargs[0][0]
    assert count == 1

    # Verify payload has correct event fields
    payload = json.loads(mock_put.call_args[1]["content"])
    assert payload[0]["event_key"] == "$emarsys_email_send"
    assert payload[0]["event_type"] == "trace"
