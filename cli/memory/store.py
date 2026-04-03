"""MemoryStore — file-based CRUD for all memory layers.

Storage layout:
    ~/.socialhub/memory/                   0o700
    ├── user_profile.yaml                  0o600
    ├── business_context.yaml              0o600
    ├── campaigns.yaml                     0o600
    ├── analysis_insights/                 0o700
    │   └── {date}-{slug}.json             0o600
    └── session_summaries/                 0o700
        └── {session_id}.json              0o600

All writes use atomic rename (tmp → target) with TOCTOU-safe os.open(0o600).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..config import MemoryConfig
from .models import (
    BusinessContext,
    Campaign,
    Insight,
    SessionSummary,
    UserPreferencesUpdate,
    UserProfile,
)

logger = logging.getLogger(__name__)

_INSIGHT_SLUG_RE = re.compile(r"[^\w\-]")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _safe_load_yaml(path: Path, default_factory):
    """Load YAML, returning default on any error."""
    if not path.exists():
        return default_factory()
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return default_factory(**data) if data else default_factory()
    except Exception as exc:
        logger.warning("Memory: failed to load %s (%s), using defaults", path.name, exc)
        return default_factory()


def _atomic_tmp_path(path: Path) -> Path:
    """Return a unique per-process temp path alongside target, avoiding same-name collisions
    when concurrent daemon threads write to the same directory."""
    suffix = f".{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp"
    return path.with_name(path.name + suffix)


def _atomic_write_json(path: Path, data: dict) -> None:
    """Atomically write JSON to path with 0o600 permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _atomic_tmp_path(path)
    try:
        fd = os.open(str(tmp_path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        tmp_path.replace(path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


def _atomic_write_yaml(path: Path, data: dict) -> None:
    """Atomically write YAML to path with 0o600 permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _atomic_tmp_path(path)
    try:
        fd = os.open(str(tmp_path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)
        tmp_path.replace(path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class MemoryStore:
    """File-based CRUD for all four memory layers."""

    def __init__(self, config: MemoryConfig) -> None:
        self._config = config
        self._root = Path(config.memory_dir)
        self._insights_dir = self._root / "analysis_insights"
        self._summaries_dir = self._root / "session_summaries"
        self._profile_path = self._root / "user_profile.yaml"
        self._context_path = self._root / "business_context.yaml"
        self._campaigns_path = self._root / "campaigns.yaml"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for d in (self._root, self._insights_dir, self._summaries_dir):
            try:
                d.mkdir(parents=True, exist_ok=True)
                # Best-effort 0o700 on POSIX; silently ignored on Windows
                d.chmod(0o700)
            except OSError as exc:
                logger.warning("Memory: could not create directory %s (%s)", d, exc)

    # ------------------------------------------------------------------
    # L4 — UserProfile
    # ------------------------------------------------------------------

    def load_user_profile(self) -> UserProfile:
        try:
            return _safe_load_yaml(self._profile_path, UserProfile)
        except Exception:
            return UserProfile()

    def save_user_profile(self, profile: UserProfile) -> None:
        profile.updated_at = _utcnow_iso()
        _atomic_write_yaml(self._profile_path, profile.model_dump())

    def merge_user_profile(self, updates: UserPreferencesUpdate) -> None:
        """Deep-merge preference updates into the existing user_profile.yaml."""
        profile = self.load_user_profile()
        d = updates.model_dump(exclude_none=True)
        if "default_period" in d:
            profile.analysis.default_period = d["default_period"]
        if "preferred_dimensions" in d:
            profile.analysis.preferred_dimensions = d["preferred_dimensions"]
        if "key_metrics" in d:
            profile.analysis.key_metrics = d["key_metrics"]
        if "rfm_focus" in d:
            profile.analysis.rfm_focus = d["rfm_focus"]
        if "output_format" in d:
            profile.output.format = d["output_format"]
        if "show_yoy" in d:
            profile.output.show_yoy = d["show_yoy"]
        self.save_user_profile(profile)

    # ------------------------------------------------------------------
    # L4 — BusinessContext
    # ------------------------------------------------------------------

    def load_business_context(self) -> BusinessContext:
        try:
            return _safe_load_yaml(self._context_path, BusinessContext)
        except Exception:
            return BusinessContext()

    def save_business_context(self, context: BusinessContext) -> None:
        context.updated_at = _utcnow_iso()
        _atomic_write_yaml(self._context_path, context.model_dump())

    # ------------------------------------------------------------------
    # L4 — Campaigns
    # ------------------------------------------------------------------

    def load_campaigns(self) -> list[Campaign]:
        try:
            if not self._campaigns_path.exists():
                return []
            with open(self._campaigns_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            raw_list = data.get("campaigns", [])
            return [Campaign(**c) for c in raw_list]
        except Exception as exc:
            logger.warning("Memory: failed to load campaigns (%s)", exc)
            return []

    def save_campaign(self, campaign: Campaign) -> None:
        campaigns = self.load_campaigns()
        # Replace if same ID exists
        campaigns = [c for c in campaigns if c.id != campaign.id]
        campaigns.append(campaign)
        _atomic_write_yaml(
            self._campaigns_path,
            {"campaigns": [c.model_dump() for c in campaigns]},
        )

    # ------------------------------------------------------------------
    # L3 — Insights
    # ------------------------------------------------------------------

    def _insight_path(self, insight_id: str) -> Path:
        return self._insights_dir / f"{insight_id}.json"

    def save_insight(self, insight: Insight) -> str:
        """Write insight to disk. Returns content hash for audit logging."""
        content = insight.model_dump_json()
        _atomic_write_json(self._insight_path(insight.id), insight.model_dump())
        return _content_hash(content)

    def load_recent_insights(self, n: int = 5) -> list[Insight]:
        """Load the n most recent insight files by modification time."""
        try:
            files = sorted(
                self._insights_dir.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:n * 2]  # read a few extra to allow for parse failures
            results = []
            for f in files:
                if len(results) >= n:
                    break
                try:
                    with open(f, encoding="utf-8") as fh:
                        data = json.load(fh)
                    results.append(Insight(**data))
                except Exception as exc:
                    logger.debug("Memory: skipping corrupt insight file %s (%s)", f.name, exc)
                    continue
            return results
        except Exception:
            return []

    # ------------------------------------------------------------------
    # L2 — Session Summaries
    # ------------------------------------------------------------------

    def _summary_path(self, session_id: str) -> Path:
        # Sanitize session_id to prevent path traversal
        safe_id = re.sub(r"[^\w\-]", "_", session_id)[:80]
        return self._summaries_dir / f"{safe_id}.json"

    def save_summary(self, summary: SessionSummary) -> str:
        """Write session summary to disk. Returns content hash."""
        content = summary.model_dump_json()
        _atomic_write_json(self._summary_path(summary.session_id), summary.model_dump())
        return _content_hash(content)

    def load_recent_summaries(self, n: int = 3) -> list[SessionSummary]:
        """Load the n most recent summary files by modification time."""
        try:
            files = sorted(
                self._summaries_dir.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:n * 2]
            results = []
            for f in files:
                if len(results) >= n:
                    break
                try:
                    with open(f, encoding="utf-8") as fh:
                        data = json.load(fh)
                    results.append(SessionSummary(**data))
                except Exception as exc:
                    logger.debug("Memory: skipping corrupt summary file %s (%s)", f.name, exc)
                    continue
            return results
        except Exception:
            return []

    # ------------------------------------------------------------------
    # TTL + count-based pruning
    # ------------------------------------------------------------------

    def purge_expired(self) -> int:
        """Remove expired files and enforce count limits. Returns files removed."""
        count = 0
        now = time.time()

        # L2 summaries — TTL
        ttl_s = self._config.summary_ttl_days * 86400
        for p in list(self._summaries_dir.glob("*.json")):
            try:
                if (now - p.stat().st_mtime) > ttl_s:
                    p.unlink(missing_ok=True)
                    count += 1
            except OSError:
                pass

        # L3 insights — TTL
        insight_ttl_s = self._config.insight_ttl_days * 86400
        for p in list(self._insights_dir.glob("*.json")):
            try:
                if (now - p.stat().st_mtime) > insight_ttl_s:
                    p.unlink(missing_ok=True)
                    count += 1
            except OSError:
                pass

        # Count-based pruning — keep only the newest N
        count += self._prune_by_count(self._summaries_dir, self._config.max_summaries)
        count += self._prune_by_count(self._insights_dir, self._config.max_insights)
        return count

    def _prune_by_count(self, directory: Path, max_count: int) -> int:
        try:
            files = sorted(
                directory.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except FileNotFoundError:
            return 0
        to_delete = files[max_count:]
        deleted = 0
        for p in to_delete:
            try:
                p.unlink(missing_ok=True)
                deleted += 1
            except OSError:
                pass
        return deleted

    def count_insights(self) -> int:
        """Return the number of stored insight files."""
        try:
            return sum(1 for _ in self._insights_dir.glob("*.json"))
        except OSError:
            return 0

    def count_summaries(self) -> int:
        """Return the number of stored summary files."""
        try:
            return sum(1 for _ in self._summaries_dir.glob("*.json"))
        except OSError:
            return 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def make_insight_id(topic: str, date_str: str | None = None) -> str:
        """Generate a filesystem-safe insight ID from topic + date."""
        if date_str is None:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        slug = _INSIGHT_SLUG_RE.sub("-", topic.lower())[:40].strip("-")
        return f"{date_str}-{slug}"
