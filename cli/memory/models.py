"""Memory system data models (Pydantic v2)."""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# L4 — Procedural Memory (permanent)
# ---------------------------------------------------------------------------


class AnalysisPreferences(BaseModel):
    default_period: str = Field(default="7d", description="Default time period (7d/30d/90d/all)")
    preferred_dimensions: list[str] = Field(default_factory=list, description="e.g. ['channel', 'category']")
    key_metrics: list[str] = Field(default_factory=list, description="e.g. ['gmv', 'orders']")
    rfm_focus: list[str] = Field(default_factory=list, description="RFM segments to highlight")


class OutputPreferences(BaseModel):
    format: str = Field(default="table", description="table|json|csv")
    precision: int = Field(default=1, description="Decimal places")
    show_yoy: bool = Field(default=False, description="Show year-over-year comparison")


class ScopeConfig(BaseModel):
    channels: list[str] = Field(default_factory=list, description="[] = all channels")
    provinces: list[str] = Field(default_factory=list, description="[] = all provinces")


class UserProfile(BaseModel):
    version: str = Field(default="1.0")
    updated_at: str | None = None
    role: str = Field(default="operations", description="operations|analyst|marketing")
    analysis: AnalysisPreferences = Field(default_factory=AnalysisPreferences)
    output: OutputPreferences = Field(default_factory=OutputPreferences)
    scope: ScopeConfig = Field(default_factory=ScopeConfig)


class BusinessContext(BaseModel):
    version: str = Field(default="1.0")
    updated_at: str | None = None
    industry: str = Field(default="", description="e.g. fashion, electronics")
    peak_seasons: list[str] = Field(default_factory=list, description="e.g. ['Q4', 'June 618']")
    kpi_baselines: dict[str, float] = Field(default_factory=dict, description="e.g. {'gmv_daily': 500000}")
    open_questions: list[str] = Field(default_factory=list, description="Unresolved business questions")


# ---------------------------------------------------------------------------
# Campaign (part of BusinessContext, but tracked separately)
# ---------------------------------------------------------------------------


class CampaignPeriod(BaseModel):
    start: str = Field(description="YYYY-MM-DD")
    end: str = Field(description="YYYY-MM-DD")


class Campaign(BaseModel):
    id: str
    name: str
    period: CampaignPeriod
    channel: str = ""
    effect_summary: str = Field(default="", description="e.g. '+15% GMV, +8% new buyers'")
    notes: str = ""

    @property
    def status(self) -> Literal["active", "archived"]:
        """BR-01: campaign is archived when period.end < today."""
        try:
            end = date.fromisoformat(self.period.end)
            return "archived" if end < date.today() else "active"
        except (ValueError, AttributeError):
            return "archived"


# ---------------------------------------------------------------------------
# L3 — Semantic Memory (TTL 90 days)
# ---------------------------------------------------------------------------

_INSIGHT_ID_RE = re.compile(r"^[\w\-]{1,80}$")


class Insight(BaseModel):
    schema_version: str = Field(default="v1", description="Schema version for forward-compatible migration")
    id: str
    date: str = Field(description="YYYY-MM-DD")
    topic: str
    tags: list[str] = Field(default_factory=list)
    conclusion: str
    data_period: str = Field(default="", description="e.g. '2026-03-01~2026-03-31'")
    confidence: str = Field(default="medium", description="high|medium|low")
    source_session: str = ""
    source_trace: str = ""

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not _INSIGHT_ID_RE.match(v):
            raise ValueError(f"Invalid insight ID (must match [\\w\\-]{{1,80}}): {v!r}")
        return v


# ---------------------------------------------------------------------------
# L2 — Episodic Memory (TTL 30 days)
# ---------------------------------------------------------------------------


class SessionSummary(BaseModel):
    schema_version: str = Field(default="v1", description="Schema version for forward-compatible migration")
    session_id: str
    date: str = Field(description="YYYY-MM-DD")
    summary: str = Field(description="One-sentence summary, max 100 chars")
    commands_used: list[str] = Field(default_factory=list)
    insights_generated: list[str] = Field(default_factory=list, description="Insight IDs written this session")


# ---------------------------------------------------------------------------
# MemoryContext — assembled from all layers, injected into SYSTEM_PROMPT
# ---------------------------------------------------------------------------


class MemoryContext(BaseModel):
    user_profile: UserProfile = Field(default_factory=UserProfile)
    business_context: BusinessContext = Field(default_factory=BusinessContext)
    campaigns: list[Campaign] = Field(default_factory=list)
    recent_insights: list[Insight] = Field(default_factory=list)
    recent_summaries: list[SessionSummary] = Field(default_factory=list)

    @property
    def active_campaigns(self) -> list[Campaign]:
        """BR-02: only active (non-archived) campaigns for prompt injection."""
        return [c for c in self.campaigns if c.status == "active"]

    @property
    def is_empty(self) -> bool:
        """True when all layers are at defaults (cold-start / no memory yet)."""
        has_preferences = (
            self.user_profile.analysis.default_period != "7d"
            or self.user_profile.analysis.preferred_dimensions
            or self.user_profile.analysis.key_metrics
        )
        return not has_preferences and not self.recent_insights and not self.recent_summaries


# ---------------------------------------------------------------------------
# Extractor output schema
# ---------------------------------------------------------------------------


class UserPreferencesUpdate(BaseModel):
    default_period: str | None = None
    preferred_dimensions: list[str] | None = None
    key_metrics: list[str] | None = None
    rfm_focus: list[str] | None = None
    output_format: str | None = None
    show_yoy: bool | None = None


class InsightData(BaseModel):
    topic: str
    conclusion: str
    tags: list[str] = Field(default_factory=list)
    data_period: str = ""
    confidence: str = "medium"


class ExtractionResult(BaseModel):
    skipped: bool = False
    skip_reason: str = ""
    nothing_to_save: bool = False
    user_preferences_update: UserPreferencesUpdate = Field(default_factory=UserPreferencesUpdate)
    business_insights: list[InsightData] = Field(default_factory=list)
    session_summary: str = ""
