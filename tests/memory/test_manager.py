"""Integration tests for cli/memory/manager.py."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cli.memory.manager import MemoryManager
from cli.config import MemoryConfig
from cli.memory.models import ExtractionResult, InsightData, MemoryContext


@pytest.fixture
def tmp_config(tmp_path):
    return MemoryConfig(
        memory_dir=str(tmp_path / "memory"),
        max_insights=100,
        max_summaries=30,
        extractor_timeout_s=5,
    )


@pytest.fixture
def manager(tmp_config):
    return MemoryManager(config=tmp_config)


class TestLoad:
    def test_load_empty_returns_context(self, manager):
        ctx = manager.load()
        assert isinstance(ctx, MemoryContext)

    def test_load_with_corrupt_profile_does_not_raise(self, tmp_config, tmp_path):
        mem_dir = Path(tmp_config.memory_dir)
        mem_dir.mkdir(parents=True, exist_ok=True)
        (mem_dir / "user_profile.yaml").write_text("{bad: yaml: !!!", encoding="utf-8")
        mm = MemoryManager(config=tmp_config)
        ctx = mm.load()
        assert ctx is not None

    def test_disabled_returns_empty_context(self, tmp_config):
        tmp_config.enabled = False
        mm = MemoryManager(config=tmp_config)
        ctx = mm.load()
        assert ctx.is_empty


class TestBuildSystemPrompt:
    def test_fallback_on_empty_context(self, manager):
        ctx = MemoryContext()
        result = manager.build_system_prompt(ctx)
        from cli.ai.prompt import BASE_SYSTEM_PROMPT
        assert result == BASE_SYSTEM_PROMPT

    def test_disabled_returns_base(self, tmp_config):
        tmp_config.enabled = False
        mm = MemoryManager(config=tmp_config)
        ctx = MemoryContext()
        result = mm.build_system_prompt(ctx)
        from cli.ai.prompt import BASE_SYSTEM_PROMPT
        assert result == BASE_SYSTEM_PROMPT


class TestSaveSessionMemory:
    def _make_session(self, messages=None):
        from cli.ai.session import Session
        import time
        session = Session(
            session_id="test-session-001",
            created_at=time.time(),
            messages=messages or [
                {"role": "user", "content": "分析渠道 GMV"},
                {"role": "assistant", "content": "天猫渠道本月 GMV 占比 60%"},
            ],
            last_active=time.time(),
        )
        return session

    def test_no_memory_flag_skips_write(self, manager):
        session = self._make_session()
        result = manager.save_session_memory(session, no_memory=True)
        assert result is None
        # No files should be created
        insights = list(manager._store._insights_dir.glob("*.json"))
        summaries = list(manager._store._summaries_dir.glob("*.json"))
        assert len(insights) == 0
        assert len(summaries) == 0

    def test_extractor_timeout_returns_none(self, manager):
        session = self._make_session()

        # Mock extractor to return skipped result
        mock_result = ExtractionResult(skipped=True, skip_reason="extractor_timeout")
        with patch.object(manager._extractor, "extract", return_value=mock_result):
            result = manager.save_session_memory(session)
        assert result is None

    def test_nothing_to_save_returns_none(self, manager):
        session = self._make_session()
        mock_result = ExtractionResult(nothing_to_save=True)
        with patch.object(manager._extractor, "extract", return_value=mock_result):
            result = manager.save_session_memory(session)
        assert result is None

    def test_pii_in_insight_skipped(self, manager):
        session = self._make_session()
        mock_result = ExtractionResult(
            business_insights=[
                InsightData(topic="Test", conclusion="联系电话 13812345678 的客户流失了")
            ],
            session_summary="test",
        )
        with patch.object(manager._extractor, "extract", return_value=mock_result):
            manager.save_session_memory(session)
        insights = list(manager._store._insights_dir.glob("*.json"))
        assert len(insights) == 0

    def test_valid_insight_written(self, manager):
        session = self._make_session()
        mock_result = ExtractionResult(
            business_insights=[
                InsightData(
                    topic="渠道GMV",
                    conclusion="天猫渠道本月 GMV 占比 60%",
                    confidence="high",
                )
            ],
            session_summary="分析了渠道 GMV",
        )
        with patch.object(manager._extractor, "extract", return_value=mock_result):
            summary_id = manager.save_session_memory(session)
        assert summary_id is not None
        insights = list(manager._store._insights_dir.glob("*.json"))
        assert len(insights) == 1

    def test_roundtrip_load_after_save(self, manager):
        session = self._make_session()
        mock_result = ExtractionResult(
            business_insights=[
                InsightData(topic="渠道分析", conclusion="渠道 A 增长 20%", confidence="high")
            ],
            session_summary="分析渠道",
        )
        with patch.object(manager._extractor, "extract", return_value=mock_result):
            manager.save_session_memory(session)

        ctx = manager.load()
        assert len(ctx.recent_insights) == 1
        assert "渠道 A 增长 20%" in ctx.recent_insights[0].conclusion


class TestGetStatus:
    def test_returns_dict_with_expected_keys(self, manager):
        status = manager.get_status()
        assert "enabled" in status
        assert "insight_count" in status
        assert "summary_count" in status
        assert "campaign_count" in status
        assert "memory_dir" in status

    def test_counts_reflect_saved_files(self, manager):
        from unittest.mock import patch
        from cli.memory.models import ExtractionResult, InsightData
        mock_result = ExtractionResult(
            business_insights=[InsightData(topic="T", conclusion="C", confidence="high")],
            session_summary="s",
        )
        session = TestSaveSessionMemory()._make_session()
        with patch.object(manager._extractor, "extract", return_value=mock_result):
            manager.save_session_memory(session)

        status = manager.get_status()
        assert status["insight_count"] == 1
        assert status["summary_count"] == 1


class TestSaveInsightFromAi:
    def test_writes_insight(self, manager):
        result = manager.save_insight_from_ai(
            raw_content="天猫渠道 GMV 占比 60%",
            topic="渠道分析",
            tags=["channel", "gmv"],
        )
        assert result is True
        insights = list(manager._store._insights_dir.glob("*.json"))
        assert len(insights) == 1

    def test_pii_returns_false(self, manager):
        result = manager.save_insight_from_ai(
            raw_content="用户手机 13812345678 已流失",
            topic="流失分析",
            tags=[],
        )
        assert result is False

    def test_no_memory_returns_false(self, manager):
        result = manager.save_insight_from_ai(
            raw_content="GMV 增长",
            topic="增长分析",
            tags=[],
            no_memory=True,
        )
        assert result is False
