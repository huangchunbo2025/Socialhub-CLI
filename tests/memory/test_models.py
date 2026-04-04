"""Tests for cli/memory/models.py."""

import pytest
from cli.config import MemoryConfig
from cli.memory.models import (
    Campaign,
    CampaignPeriod,
    ExtractionResult,
    Insight,
    MemoryContext,
    UserProfile,
)
from datetime import date


class TestCampaignStatus:
    def test_future_campaign_is_active(self):
        c = Campaign(
            id="c1",
            name="Test",
            period=CampaignPeriod(start="2099-01-01", end="2099-12-31"),
        )
        assert c.status == "active"

    def test_past_campaign_is_archived(self):
        c = Campaign(
            id="c2",
            name="Old",
            period=CampaignPeriod(start="2020-01-01", end="2020-01-31"),
        )
        assert c.status == "archived"

    def test_today_end_is_active(self):
        today = date.today().isoformat()
        c = Campaign(
            id="c3",
            name="Today",
            period=CampaignPeriod(start=today, end=today),
        )
        # today >= today → not archived (archived only when end < today)
        assert c.status == "active"


class TestMemoryContext:
    def test_active_campaigns_excludes_archived(self):
        ctx = MemoryContext(
            campaigns=[
                Campaign(id="a", name="Active", period=CampaignPeriod(start="2099-01-01", end="2099-12-31")),
                Campaign(id="b", name="Old", period=CampaignPeriod(start="2020-01-01", end="2020-12-31")),
            ]
        )
        assert len(ctx.active_campaigns) == 1
        assert ctx.active_campaigns[0].id == "a"

    def test_is_empty_with_defaults(self):
        ctx = MemoryContext()
        assert ctx.is_empty is True

    def test_not_empty_with_preferences(self):
        ctx = MemoryContext()
        ctx.user_profile.analysis.preferred_dimensions = ["channel"]
        assert ctx.is_empty is False

    def test_not_empty_with_business_context_industry(self):
        from cli.memory.models import BusinessContext
        ctx = MemoryContext()
        ctx.business_context = BusinessContext(industry="fashion")
        assert ctx.is_empty is False

    def test_not_empty_with_business_context_kpi(self):
        from cli.memory.models import BusinessContext
        ctx = MemoryContext()
        ctx.business_context = BusinessContext(kpi_baselines={"gmv_daily": 500000})
        assert ctx.is_empty is False

    def test_not_empty_with_active_campaigns(self):
        ctx = MemoryContext(
            campaigns=[
                Campaign(
                    id="c1", name="Active",
                    period=CampaignPeriod(start="2099-01-01", end="2099-12-31"),
                ),
            ]
        )
        assert ctx.is_empty is False

    def test_empty_with_only_archived_campaigns(self):
        ctx = MemoryContext(
            campaigns=[
                Campaign(
                    id="c1", name="Old",
                    period=CampaignPeriod(start="2020-01-01", end="2020-12-31"),
                ),
            ]
        )
        # Only archived campaigns → still considered empty (no active context)
        assert ctx.is_empty is True


class TestInsightValidation:
    def test_valid_id(self):
        ins = Insight(id="2026-04-01-gmv", date="2026-04-01", topic="GMV", conclusion="ok")
        assert ins.id == "2026-04-01-gmv"

    def test_invalid_id_raises(self):
        with pytest.raises(Exception):
            Insight(id="../evil", date="2026-04-01", topic="x", conclusion="y")


class TestMemoryConfig:
    def test_default_memory_dir_is_under_home(self):
        cfg = MemoryConfig()
        assert ".socialhub" in cfg.memory_dir
        assert "memory" in cfg.memory_dir
