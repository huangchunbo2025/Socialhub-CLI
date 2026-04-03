"""MemoryManager — unified entry point for the memory system.

Every CLI invocation creates a fresh MemoryManager instance (non-singleton).
All public methods catch exceptions internally and degrade gracefully so that
a memory subsystem failure never interrupts the main AI call flow.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ..config import MemoryConfig, load_config
from .extractor import SessionExtractor
from .injector import build_system_prompt as _build_prompt
from .models import (
    ExtractionResult,
    Insight,
    MemoryContext,
    SessionSummary,
)
from .pii import scan_and_mask
from .store import MemoryStore

if TYPE_CHECKING:
    from ..ai.session import Session
    from ..ai.trace import TraceLogger

logger = logging.getLogger(__name__)


def _utcdate() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class MemoryManager:
    """Unified memory management entry point.

    All methods catch internal exceptions and degrade gracefully.
    """

    def __init__(
        self,
        config: MemoryConfig | None = None,
        trace_logger: TraceLogger | None = None,
    ) -> None:
        if config is None:
            config = load_config().memory
        self._config = config
        self._store = MemoryStore(config)
        self._extractor = SessionExtractor(timeout_s=config.extractor_timeout_s)
        self._trace: TraceLogger | None = trace_logger

    # ------------------------------------------------------------------
    # Read path — called at session start
    # ------------------------------------------------------------------

    def load(self) -> MemoryContext:
        """Load all memory layers and assemble MemoryContext.

        Any layer that fails to load returns an empty default.
        Never raises.
        """
        if not self._config.enabled:
            return MemoryContext()

        try:
            profile = self._store.load_user_profile()
        except Exception:
            from .models import UserProfile
            profile = UserProfile()

        try:
            context = self._store.load_business_context()
        except Exception:
            from .models import BusinessContext
            context = BusinessContext()

        try:
            campaigns = self._store.load_campaigns()
        except Exception:
            campaigns = []

        try:
            insights = self._store.load_recent_insights(n=self._config.inject_recent_insights)
        except Exception:
            insights = []

        try:
            summaries = self._store.load_recent_summaries(n=self._config.inject_recent_summaries)
        except Exception:
            summaries = []

        # Lazy TTL cleanup — run in background daemon thread so load() returns faster
        threading.Thread(target=self._store.purge_expired, daemon=True).start()

        return MemoryContext(
            user_profile=profile,
            business_context=context,
            campaigns=campaigns,
            recent_insights=insights,
            recent_summaries=summaries,
        )

    def build_system_prompt(
        self,
        context: MemoryContext,
        session_id: str = "",
        trace_id: str = "",
    ) -> str:
        """Build the final SYSTEM_PROMPT with memory context injected.

        Falls back to BASE_SYSTEM_PROMPT on any error.
        """
        from ..ai.prompt import BASE_SYSTEM_PROMPT

        if not self._config.enabled:
            return BASE_SYSTEM_PROMPT

        try:
            def _on_inject(layers, token_count, insight_ids, summary_ids):
                if self._trace and layers:
                    self._trace.log_memory_injection(
                        session_id=session_id,
                        trace_id=trace_id,
                        injected_layers=layers,
                        token_count=token_count,
                        insight_ids=insight_ids,
                        summary_ids=summary_ids,
                    )

            return _build_prompt(
                context=context,
                base_prompt=BASE_SYSTEM_PROMPT,
                max_tokens=self._config.inject_max_tokens,
                inject_recent_insights=self._config.inject_recent_insights,
                inject_recent_summaries=self._config.inject_recent_summaries,
                on_inject=_on_inject,
            )
        except Exception as exc:
            logger.debug("Memory: build_system_prompt failed (%s), using base prompt", exc)
            return BASE_SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # Write path — called at session end
    # ------------------------------------------------------------------

    def save_session_memory(
        self,
        session: Session,
        trace_id: str = "",
        no_memory: bool = False,
    ) -> str | None:
        """Extract and persist memory from a completed session.

        Args:
            session: The completed AI session
            trace_id: Trace ID for audit linking
            no_memory: If True, skip all writes (BR-13: --no-memory flag)

        Returns:
            summary_id if a summary was written, else None.
        """
        if no_memory or not self._config.enabled:
            return None

        try:
            result: ExtractionResult = self._extractor.extract(session)
        except Exception as exc:
            logger.debug("Memory: extractor raised unexpectedly (%s)", exc)
            result = ExtractionResult(skipped=True, skip_reason="extractor_exception")

        if result.skipped:
            if self._trace:
                self._trace.log_memory_write(
                    memory_type="summary",
                    file_path="",
                    content_hash="",
                    pii_masked=False,
                    session_id=session.session_id,
                    trace_id=trace_id,
                    skipped=True,
                    skip_reason=result.skip_reason,
                )
            return None

        if result.nothing_to_save:
            return None

        session_id = session.session_id
        summary_id: str | None = None

        # Write business insights (L3)
        for insight_data in result.business_insights:
            try:
                raw_conclusion = insight_data.conclusion
                masked_conclusion, pii_found = scan_and_mask(raw_conclusion)
                if pii_found:
                    from rich.console import Console
                    Console().print(
                        "[dim]Memory: PII detected in insight — content skipped[/dim]"
                    )
                    continue

                insight_id = self._store.make_insight_id(insight_data.topic)
                insight = Insight(
                    id=insight_id,
                    date=_utcdate(),
                    topic=insight_data.topic,
                    tags=insight_data.tags,
                    conclusion=masked_conclusion,
                    data_period=insight_data.data_period,
                    confidence=insight_data.confidence,
                    source_session=session_id,
                    source_trace=trace_id,
                )
                content_hash = self._store.save_insight(insight)

                if self._trace:
                    self._trace.log_memory_write(
                        memory_type="insight",
                        file_path=f"analysis_insights/{insight_id}.json",
                        content_hash=content_hash,
                        pii_masked=pii_found,
                        session_id=session_id,
                        trace_id=trace_id,
                    )
            except Exception as exc:
                logger.debug("Memory: failed to write insight (%s)", exc)

        # Write session summary (L2)
        if result.session_summary:
            try:
                raw_summary = result.session_summary
                masked_summary, pii_found = scan_and_mask(raw_summary)
                if pii_found:
                    masked_summary = "[summary contained PII — masked]"

                summary = SessionSummary(
                    session_id=session_id,
                    date=_utcdate(),
                    summary=masked_summary,
                    commands_used=[],
                    insights_generated=[],
                )
                content_hash = self._store.save_summary(summary)
                summary_id = session_id

                if self._trace:
                    self._trace.log_memory_write(
                        memory_type="summary",
                        file_path=f"session_summaries/{session_id}.json",
                        content_hash=content_hash,
                        pii_masked=pii_found,
                        session_id=session_id,
                        trace_id=trace_id,
                    )
            except Exception as exc:
                logger.debug("Memory: failed to write summary (%s)", exc)

        # Merge user preference updates (L4)
        if result.user_preferences_update:
            try:
                upd = result.user_preferences_update
                if upd.model_dump(exclude_none=True):
                    self._store.merge_user_profile(upd)
            except Exception as exc:
                logger.debug("Memory: failed to merge preferences (%s)", exc)

        return summary_id

    def save_insight_from_ai(
        self,
        raw_content: str,
        topic: str,
        tags: list[str],
        session_id: str = "",
        trace_id: str = "",
        no_memory: bool = False,
    ) -> bool:
        """Hook for insights.py — persist a single AI-generated insight.

        Returns True if written, False if skipped (PII / disabled / error).
        """
        if no_memory or not self._config.enabled:
            return False

        try:
            masked_content, pii_found = scan_and_mask(raw_content)
            if pii_found:
                from rich.console import Console
                Console().print(
                    "[dim]Memory: PII detected in insight — content skipped[/dim]"
                )
                return False

            insight_id = self._store.make_insight_id(topic)
            insight = Insight(
                id=insight_id,
                date=_utcdate(),
                topic=topic,
                tags=tags,
                conclusion=masked_content[:500],
                source_session=session_id,
                source_trace=trace_id,
            )
            content_hash = self._store.save_insight(insight)

            if self._trace:
                self._trace.log_memory_write(
                    memory_type="insight",
                    file_path=f"analysis_insights/{insight_id}.json",
                    content_hash=content_hash,
                    pii_masked=False,
                    session_id=session_id,
                    trace_id=trace_id,
                )
            return True
        except Exception as exc:
            logger.debug("Memory: save_insight_from_ai failed (%s)", exc)
            return False

    # ------------------------------------------------------------------
    # Query helpers (for sh memory commands)
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """Return a summary of current memory state for sh memory status."""
        try:
            profile = self._store.load_user_profile()
            campaigns = self._store.load_campaigns()
            return {
                "enabled": self._config.enabled,
                "profile_updated": profile.updated_at,
                "insight_count": self._store.count_insights(),
                "summary_count": self._store.count_summaries(),
                "campaign_count": len(campaigns),
                "memory_dir": str(self._config.memory_dir),
            }
        except Exception:
            return {"enabled": self._config.enabled, "error": "could not read memory state"}
