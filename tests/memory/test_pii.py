"""Tests for cli/memory/pii.py."""

import pytest
from cli.memory.pii import scan_and_mask


class TestScanAndMask:
    def test_phone_masked(self):
        text = "联系电话 13812345678"
        result, found = scan_and_mask(text)
        assert "[PHONE_MASKED]" in result
        assert found is True

    def test_id_card_masked(self):
        text = "身份证 110101199001011234"
        result, found = scan_and_mask(text)
        assert "[ID_MASKED]" in result
        assert found is True

    def test_email_masked(self):
        text = "邮箱 user@example.com"
        result, found = scan_and_mask(text)
        assert "[EMAIL_MASKED]" in result
        assert found is True

    def test_order_id_masked(self):
        text = "订单号 1234567890123456"
        result, found = scan_and_mask(text)
        assert "[ORDER_ID]" in result
        assert found is True

    def test_aggregate_data_not_masked(self):
        text = "GMV 占比 60%，渠道 A 增长 15%"
        result, found = scan_and_mask(text)
        assert result == text
        assert found is False

    def test_percentage_not_mistaken_for_pii(self):
        text = "转化率提升 26%"
        result, found = scan_and_mask(text)
        assert found is False

    def test_empty_string(self):
        result, found = scan_and_mask("")
        assert result == ""
        assert found is False

    def test_multiple_pii_types(self):
        text = "手机 13800138000，邮箱 a@b.com"
        result, found = scan_and_mask(text)
        assert "[PHONE_MASKED]" in result
        assert "[EMAIL_MASKED]" in result
        assert found is True
