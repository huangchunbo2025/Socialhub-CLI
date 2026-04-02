"""Tests for cli/ai/trace.py — TraceLogger PII masking and lifecycle."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from cli.ai.trace import TraceLogger, _build_pii_patterns, _mask_pii
from cli.config import TraceConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**kwargs) -> TraceConfig:
    """Create a TraceConfig backed by a temp directory unless overridden."""
    defaults = dict(
        enabled=True,
        pii_masking=True,
        order_id_min_digits=16,
        max_file_size_mb=10,
    )
    defaults.update(kwargs)
    return TraceConfig(**defaults)


def _make_logger(tmp_path: Path, **config_kwargs) -> TraceLogger:
    cfg = _make_config(trace_dir=str(tmp_path), **config_kwargs)
    return TraceLogger(cfg)


def _read_events(tmp_path: Path) -> list[dict]:
    """Read all NDJSON events from ai_trace.jsonl in tmp_path."""
    trace_file = tmp_path / "ai_trace.jsonl"
    if not trace_file.exists():
        return []
    lines = trace_file.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


# ---------------------------------------------------------------------------
# PII masking unit tests (test the module-level helpers directly)
# ---------------------------------------------------------------------------


class TestPiiMaskingPhone:
    """test_pii_masking_phone: 手机号被脱敏。"""

    def test_phone_replaced(self):
        patterns = _build_pii_patterns(16)
        result = _mask_pii("联系人手机号：13812345678，请回电", patterns)
        assert "[PHONE_MASKED]" in result
        assert "13812345678" not in result

    def test_phone_boundary_digits(self):
        """所有 1[3-9] 开头的 11 位手机号格式均被脱敏。"""
        patterns = _build_pii_patterns(16)
        for prefix in ("130", "150", "170", "189", "199"):
            number = prefix + "12345678"
            result = _mask_pii(number, patterns)
            assert "[PHONE_MASKED]" in result, f"号码 {number} 未被脱敏"
            assert number not in result

    def test_short_number_not_replaced(self):
        """10 位或更短的数字串不应被当作手机号脱敏。"""
        patterns = _build_pii_patterns(16)
        result = _mask_pii("1381234567", patterns)  # 10 位，不足 11 位
        assert "[PHONE_MASKED]" not in result


class TestPiiMaskingEmail:
    """test_pii_masking_email: 邮箱被脱敏。"""

    def test_simple_email(self):
        patterns = _build_pii_patterns(16)
        result = _mask_pii("发送到 user@example.com 地址", patterns)
        assert "[EMAIL_MASKED]" in result
        assert "user@example.com" not in result

    def test_complex_email(self):
        patterns = _build_pii_patterns(16)
        result = _mask_pii("john.doe+tag@mail.company.org", patterns)
        assert "[EMAIL_MASKED]" in result

    def test_multiple_emails(self):
        patterns = _build_pii_patterns(16)
        result = _mask_pii("a@b.com 和 c@d.net", patterns)
        assert result.count("[EMAIL_MASKED]") == 2


class TestPiiMaskingIdCard:
    """test_pii_masking_id_card: 身份证被脱敏。"""

    def test_id_card_digits_only(self):
        patterns = _build_pii_patterns(16)
        result = _mask_pii("身份证号 110101199001011234 已核实", patterns)
        assert "[ID_MASKED]" in result
        assert "110101199001011234" not in result

    def test_id_card_with_x(self):
        patterns = _build_pii_patterns(16)
        result = _mask_pii("证件号 11010119900101123X", patterns)
        assert "[ID_MASKED]" in result
        assert "11010119900101123X" not in result

    def test_id_card_with_lowercase_x(self):
        """校验位小写 x 同样应被脱敏（re.IGNORECASE）。"""
        patterns = _build_pii_patterns(16)
        result = _mask_pii("11010119900101123x", patterns)
        assert "[ID_MASKED]" in result

    def test_id_card_masked_before_order_id(self):
        """身份证（18 位）应先于订单号正则被匹配，不被误标为 ORDER_ID。"""
        patterns = _build_pii_patterns(16)
        result = _mask_pii("110101199001011234", patterns)
        assert "[ID_MASKED]" in result
        assert "[ORDER_ID]" not in result


class TestPiiMaskingDisabled:
    """test_pii_masking_disabled: pii_masking=False 时不脱敏。"""

    def test_phone_not_masked_when_disabled(self, tmp_path):
        logger = _make_logger(tmp_path, pii_masking=False)
        original = "手机 13812345678"
        trace_id = logger.log_plan_start("sess1", original, "gpt-4o")
        events = _read_events(tmp_path)
        assert len(events) == 1
        assert events[0]["user_input"] == original

    def test_email_not_masked_when_disabled(self, tmp_path):
        logger = _make_logger(tmp_path, pii_masking=False)
        original = "邮箱 user@example.com"
        logger.log_plan_start("sess1", original, "gpt-4o")
        events = _read_events(tmp_path)
        assert events[0]["user_input"] == original

    def test_id_card_not_masked_when_disabled(self, tmp_path):
        logger = _make_logger(tmp_path, pii_masking=False)
        original = "身份证 110101199001011234"
        logger.log_plan_start("sess1", original, "gpt-4o")
        events = _read_events(tmp_path)
        assert events[0]["user_input"] == original


# ---------------------------------------------------------------------------
# TraceLogger disabled mode
# ---------------------------------------------------------------------------


class TestTraceDisabled:
    """test_trace_disabled: enabled=False 时不写文件。"""

    def test_no_file_created_when_disabled(self, tmp_path):
        logger = _make_logger(tmp_path, enabled=False)
        trace_id = logger.log_plan_start("sess1", "查询订单", "gpt-4o")
        logger.log_step(trace_id, 1, "sh analytics overview", True, 500, 200)
        logger.log_plan_end(trace_id, 1, 1, 100, 50)

        trace_file = tmp_path / "ai_trace.jsonl"
        assert not trace_file.exists(), "enabled=False 时不应创建 trace 文件"

    def test_returns_valid_trace_id_when_disabled(self, tmp_path):
        """即使 disabled，log_plan_start 也应返回有效的非空字符串。"""
        logger = _make_logger(tmp_path, enabled=False)
        trace_id = logger.log_plan_start("sess1", "test", "gpt-4o")
        assert isinstance(trace_id, str)
        assert len(trace_id) > 0


# ---------------------------------------------------------------------------
# Full lifecycle integration test
# ---------------------------------------------------------------------------


class TestLogPlanLifecycle:
    """test_log_plan_lifecycle: 完整 start/step/end 流程写入有效 NDJSON。"""

    def test_three_events_written(self, tmp_path):
        logger = _make_logger(tmp_path)
        trace_id = logger.log_plan_start("session-abc", "查询本月留存率", "gpt-4o")
        logger.log_step(trace_id, 1, "sh analytics retention", True, 1200, 450)
        logger.log_plan_end(trace_id, 1, 1, 1200, 340)

        events = _read_events(tmp_path)
        assert len(events) == 3

    def test_event_types(self, tmp_path):
        logger = _make_logger(tmp_path)
        trace_id = logger.log_plan_start("session-abc", "查询本月留存率", "gpt-4o")
        logger.log_step(trace_id, 1, "sh analytics retention", True, 1200, 450)
        logger.log_plan_end(trace_id, 1, 1, 1200, 340)

        events = _read_events(tmp_path)
        assert events[0]["type"] == "plan_start"
        assert events[1]["type"] == "step"
        assert events[2]["type"] == "plan_end"

    def test_trace_id_consistent(self, tmp_path):
        """三条事件的 trace_id 必须相同。"""
        logger = _make_logger(tmp_path)
        trace_id = logger.log_plan_start("session-abc", "查询", "gpt-4o")
        logger.log_step(trace_id, 1, "sh analytics overview", True, 800, 300)
        logger.log_plan_end(trace_id, 1, 1, 500, 200)

        events = _read_events(tmp_path)
        assert events[0]["trace_id"] == trace_id
        assert events[1]["trace_id"] == trace_id
        assert events[2]["trace_id"] == trace_id

    def test_plan_start_fields(self, tmp_path):
        logger = _make_logger(tmp_path)
        trace_id = logger.log_plan_start("sess-xyz", "查询客户 RFM", "gpt-4o")

        events = _read_events(tmp_path)
        ev = events[0]
        assert ev["type"] == "plan_start"
        assert ev["trace_id"] == trace_id
        assert ev["session_id"] == "sess-xyz"
        assert ev["model"] == "gpt-4o"
        assert "ts" in ev
        assert "user_input" in ev

    def test_step_fields(self, tmp_path):
        logger = _make_logger(tmp_path)
        trace_id = logger.log_plan_start("sess1", "test", "gpt-4o")
        logger.log_step(trace_id, 2, "sh analytics orders --limit 10", False, 350, 0)

        events = _read_events(tmp_path)
        step_ev = events[1]
        assert step_ev["type"] == "step"
        assert step_ev["step"] == 2
        assert step_ev["command"] == "sh analytics orders --limit 10"
        assert step_ev["success"] is False
        assert step_ev["duration_ms"] == 350
        assert step_ev["output_chars"] == 0

    def test_plan_end_fields(self, tmp_path):
        logger = _make_logger(tmp_path)
        trace_id = logger.log_plan_start("sess1", "test", "gpt-4o")
        logger.log_plan_end(trace_id, 3, 2, 1200, 340)

        events = _read_events(tmp_path)
        end_ev = events[1]
        assert end_ev["type"] == "plan_end"
        assert end_ev["total"] == 3
        assert end_ev["succeeded"] == 2
        assert end_ev["prompt_tokens"] == 1200
        assert end_ev["completion_tokens"] == 340

    def test_each_line_is_valid_json(self, tmp_path):
        """文件中的每一行都必须是可独立解析的合法 JSON（NDJSON 格式）。"""
        logger = _make_logger(tmp_path)
        trace_id = logger.log_plan_start("sess1", "查询", "gpt-4o")
        logger.log_step(trace_id, 1, "sh analytics overview", True, 100, 50)
        logger.log_plan_end(trace_id, 1, 1, 100, 50)

        trace_file = tmp_path / "ai_trace.jsonl"
        raw_lines = trace_file.read_text(encoding="utf-8").splitlines()
        assert len(raw_lines) == 3
        for line in raw_lines:
            obj = json.loads(line)  # 抛出 JSONDecodeError 则测试失败
            assert isinstance(obj, dict)

    def test_pii_masked_in_plan_start(self, tmp_path):
        """pii_masking=True 时 user_input 中的手机号在文件中被脱敏。"""
        logger = _make_logger(tmp_path, pii_masking=True)
        logger.log_plan_start("sess1", "查询手机号 13812345678 的客户", "gpt-4o")

        events = _read_events(tmp_path)
        assert "13812345678" not in events[0]["user_input"]
        assert "[PHONE_MASKED]" in events[0]["user_input"]

    def test_multiple_traces_appended(self, tmp_path):
        """多次调用 log_plan_start 应追加到同一文件，而非覆盖。"""
        logger = _make_logger(tmp_path)
        for i in range(3):
            tid = logger.log_plan_start(f"sess{i}", f"查询 {i}", "gpt-4o")
            logger.log_plan_end(tid, 1, 1, 100, 50)

        events = _read_events(tmp_path)
        assert len(events) == 6  # 3 × (plan_start + plan_end)

    @pytest.mark.skipif(os.name == "nt", reason="文件权限检查不适用于 Windows")
    def test_file_permissions_600(self, tmp_path):
        """ai_trace.jsonl 创建后权限应为 0o600（POSIX 平台）。"""
        logger = _make_logger(tmp_path)
        logger.log_plan_start("sess1", "test", "gpt-4o")

        trace_file = tmp_path / "ai_trace.jsonl"
        assert trace_file.exists()
        mode = oct(trace_file.stat().st_mode & 0o777)
        assert mode == "0o600", f"期望 0o600，实际 {mode}"
