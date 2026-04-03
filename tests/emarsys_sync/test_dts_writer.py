"""Tests for StarRocks dts_ Stream Load writer."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from emarsys_sync.dts_writer import DtsWriter, build_stream_load_url


def test_build_stream_load_url():
    url = build_stream_load_url(
        host="sr.example.com", http_port=8030,
        database="dts_uat", table="vdm_t_message_record"
    )
    assert url == "http://sr.example.com:8030/api/dts_uat/vdm_t_message_record/_stream_load"


def test_write_skips_unmapped_table():
    writer = DtsWriter(
        host="localhost", http_port=8030, user="root", password="",
        database="dts_uat"
    )
    with patch("httpx.put") as mock_put:
        result = writer.write("engagement_events", [{"contact_id": 1}], tenant_id="uat")
        mock_put.assert_not_called()
    assert result == 0


def test_write_calls_stream_load_for_email_sends():
    writer = DtsWriter(
        host="localhost", http_port=8030, user="root", password="",
        database="dts_uat"
    )
    rows = [{
        "customer_id": "12345", "contact_id": 1, "event_time": "2026-01-01T00:00:00Z",
        "loaded_at": "2026-01-01", "message_id": 10, "campaign_id": 20,
        "launch_id": 1, "domain": "x.com", "campaign_type": "batch",
    }]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"Status": "Success", "NumberLoadedRows": 1}

    with patch("httpx.put", return_value=mock_resp) as mock_put:
        count = writer.write("email_sends", rows, tenant_id="uat")

    mock_put.assert_called_once()
    call_kwargs = mock_put.call_args
    assert "dts_uat" in call_kwargs[0][0]
    assert "vdm_t_message_record" in call_kwargs[0][0]
    assert count == 1


def test_write_raises_on_stream_load_failure():
    writer = DtsWriter(
        host="localhost", http_port=8030, user="root", password="",
        database="dts_uat"
    )
    rows = [{
        "customer_id": "12345", "contact_id": 1, "event_time": "2026-01-01T00:00:00Z",
        "loaded_at": "2026-01-01", "message_id": 10, "campaign_id": 20,
        "launch_id": 1, "domain": "x.com", "campaign_type": "batch",
    }]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"Status": "Fail", "Message": "schema error"}

    with patch("httpx.put", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="Stream Load failed"):
            writer.write("email_sends", rows, tenant_id="uat")
