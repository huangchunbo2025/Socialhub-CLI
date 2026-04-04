"""Tests for cli/memory/store.py."""

import json
import os
import time
from pathlib import Path

import pytest
import yaml

from cli.config import MemoryConfig
from cli.memory.models import (
    BusinessContext,
    Campaign,
    CampaignPeriod,
    Insight,
    SessionSummary,
    UserProfile,
)
from cli.memory.store import MemoryStore


@pytest.fixture
def tmp_config(tmp_path):
    return MemoryConfig(
        memory_dir=str(tmp_path / "memory"),
        max_insights=5,
        max_summaries=3,
        insight_ttl_days=90,
        summary_ttl_days=30,
    )


@pytest.fixture
def store(tmp_config):
    return MemoryStore(tmp_config)


class TestUserProfile:
    def test_save_and_load(self, store):
        profile = UserProfile()
        profile.analysis.default_period = "30d"
        profile.analysis.preferred_dimensions = ["channel"]
        store.save_user_profile(profile)
        loaded = store.load_user_profile()
        assert loaded.analysis.default_period == "30d"
        assert loaded.analysis.preferred_dimensions == ["channel"]

    def test_load_missing_returns_default(self, store):
        profile = store.load_user_profile()
        assert isinstance(profile, UserProfile)
        assert profile.analysis.default_period == "7d"

    def test_load_corrupt_yaml_returns_default(self, store, tmp_path):
        store._profile_path.parent.mkdir(parents=True, exist_ok=True)
        store._profile_path.write_text("{not: valid: yaml: !!!", encoding="utf-8")
        result = store.load_user_profile()
        assert isinstance(result, UserProfile)

    def test_atomic_write_leaves_no_tmp_on_success(self, store):
        profile = UserProfile()
        store.save_user_profile(profile)
        tmp = store._profile_path.with_suffix(".tmp")
        assert not tmp.exists()

    def test_file_permission_600(self, store):
        if os.name == "nt":
            pytest.skip("POSIX permissions not enforced on Windows")
        profile = UserProfile()
        store.save_user_profile(profile)
        mode = oct(store._profile_path.stat().st_mode)[-3:]
        assert mode == "600"


class TestInsights:
    def _make_insight(self, idx: int) -> Insight:
        return Insight(
            id=f"2026-04-0{idx}-test",
            date=f"2026-04-0{idx}",
            topic=f"Topic {idx}",
            conclusion=f"Conclusion {idx}",
        )

    def test_save_and_load(self, store):
        ins = self._make_insight(1)
        store.save_insight(ins)
        loaded = store.load_recent_insights(n=5)
        assert len(loaded) == 1
        assert loaded[0].id == ins.id

    def test_count_limit_prunes_oldest(self, store):
        for i in range(1, 8):
            ins = self._make_insight(i)
            store.save_insight(ins)
            time.sleep(0.01)  # ensure distinct mtime
        # max_insights=5 in fixture
        store.purge_expired()
        remaining = list(store._insights_dir.glob("*.json"))
        assert len(remaining) <= 5

    def test_same_day_same_topic_gets_unique_id(self, store):
        """Same-day same-topic insights must NOT overwrite each other."""
        date_str = "2026-04-04"
        id1 = store.make_insight_id("渠道GMV", date_str=date_str)
        ins1 = Insight(id=id1, date=date_str, topic="渠道GMV", conclusion="Result 1")
        store.save_insight(ins1)

        id2 = store.make_insight_id("渠道GMV", date_str=date_str)
        assert id2 != id1, "Second ID should differ to avoid overwrite"
        ins2 = Insight(id=id2, date=date_str, topic="渠道GMV", conclusion="Result 2")
        store.save_insight(ins2)

        # Both files should exist
        loaded = store.load_recent_insights(n=10)
        conclusions = {i.conclusion for i in loaded}
        assert "Result 1" in conclusions
        assert "Result 2" in conclusions

    def test_path_traversal_rejected(self, store):
        with pytest.raises(Exception):
            Insight(id="../../../etc/passwd", date="2026-04-01", topic="x", conclusion="y")


class TestSummaries:
    def test_save_and_load(self, store):
        summary = SessionSummary(
            session_id="20260401T200000-abc1",
            date="2026-04-01",
            summary="分析了渠道 GMV",
        )
        store.save_summary(summary)
        loaded = store.load_recent_summaries(n=5)
        assert len(loaded) == 1
        assert loaded[0].summary == "分析了渠道 GMV"

    def test_count_limit(self, store):
        for i in range(5):
            s = SessionSummary(
                session_id=f"session-{i:04d}",
                date="2026-04-01",
                summary=f"summary {i}",
            )
            store.save_summary(s)
            time.sleep(0.01)
        store.purge_expired()
        remaining = list(store._summaries_dir.glob("*.json"))
        assert len(remaining) <= 3  # max_summaries=3


class TestBusinessContext:
    def test_save_and_load(self, store):
        from cli.memory.models import BusinessContext
        bc = BusinessContext(industry="ecommerce", peak_seasons=["11.11", "618"])
        store.save_business_context(bc)
        loaded = store.load_business_context()
        assert loaded.industry == "ecommerce"
        assert "11.11" in loaded.peak_seasons

    def test_load_missing_returns_default(self, store):
        bc = store.load_business_context()
        assert isinstance(bc, BusinessContext)

    def test_updated_at_is_set(self, store):
        from cli.memory.models import BusinessContext
        bc = BusinessContext()
        store.save_business_context(bc)
        loaded = store.load_business_context()
        assert loaded.updated_at is not None


class TestMergeUserProfile:
    def test_merge_updates_field(self, store):
        from cli.memory.models import UserPreferencesUpdate
        store.save_user_profile(store.load_user_profile())  # initialise with defaults
        update = UserPreferencesUpdate(default_period="30d", preferred_dimensions=["channel"])
        store.merge_user_profile(update)
        loaded = store.load_user_profile()
        assert loaded.analysis.default_period == "30d"
        assert loaded.analysis.preferred_dimensions == ["channel"]

    def test_merge_partial_update_preserves_other_fields(self, store):
        from cli.memory.models import UserPreferencesUpdate
        # Set initial state
        initial = store.load_user_profile()
        initial.analysis.default_period = "90d"
        store.save_user_profile(initial)
        # Partial update — only preferred_dimensions
        store.merge_user_profile(UserPreferencesUpdate(preferred_dimensions=["city"]))
        loaded = store.load_user_profile()
        assert loaded.analysis.default_period == "90d"
        assert loaded.analysis.preferred_dimensions == ["city"]


class TestPurgeExpired:
    def test_ttl_prunes_old_insight(self, store, tmp_path):
        """Insights older than ttl_days should be removed."""
        import os
        from cli.memory.models import Insight
        ins = Insight(id="2026-04-01-old", date="2026-04-01", topic="T", conclusion="C")
        store.save_insight(ins)
        # Backdate the file mtime by 200 days (> insight_ttl_days=90)
        p = store._insights_dir / f"{ins.id}.json"
        old_time = time.time() - 200 * 86400
        os.utime(str(p), (old_time, old_time))

        removed = store.purge_expired()
        assert removed >= 1
        assert not p.exists()

    def test_count_limit_removes_oldest(self, store):
        """After saving max_insights+2 files, purge should reduce to max_insights."""
        for i in range(7):  # max_insights=5 in fixture
            ins = Insight(
                id=f"2026-04-0{i+1}-c{i}",
                date=f"2026-04-0{i+1}",
                topic=f"T{i}",
                conclusion=f"C{i}",
            )
            store.save_insight(ins)
            time.sleep(0.01)
        store.purge_expired()
        remaining = list(store._insights_dir.glob("*.json"))
        assert len(remaining) <= 5


class TestCampaigns:
    def test_save_and_load(self, store):
        c = Campaign(
            id="ACT001",
            name="Test Campaign",
            period=CampaignPeriod(start="2026-04-01", end="2026-04-07"),
        )
        store.save_campaign(c)
        loaded = store.load_campaigns()
        assert len(loaded) == 1
        assert loaded[0].id == "ACT001"

    def test_update_replaces_existing(self, store):
        c = Campaign(
            id="ACT001",
            name="Test",
            period=CampaignPeriod(start="2026-04-01", end="2026-04-07"),
        )
        store.save_campaign(c)
        c.effect_summary = "+20% GMV"
        store.save_campaign(c)
        loaded = store.load_campaigns()
        assert len(loaded) == 1
        assert loaded[0].effect_summary == "+20% GMV"
