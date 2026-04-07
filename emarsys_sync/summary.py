"""Run summary writer — persists last-run stats to run_summary.json."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from emarsys_sync.tenant_syncer import TenantResult

logger = logging.getLogger(__name__)


class SummaryWriter:
    """Writes sync run statistics to a JSON file.

    Args:
        state_path: Directory to write ``run_summary.json`` into.
    """

    def __init__(self, state_path: str | Path = "/data/emarsys_sync") -> None:
        self._path = Path(state_path) / "run_summary.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        tenant_results: list[TenantResult],
        duration_seconds: float,
    ) -> None:
        """Persist a summary of the sync cycle.

        Args:
            tenant_results: Per-tenant results from the run.
            duration_seconds: Total elapsed seconds for the cycle.
        """
        summary: dict = {
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(duration_seconds, 2),
            "tenants": {},
        }
        for tr in tenant_results:
            summary["tenants"][tr.tenant_id] = {
                "success": tr.success_count,
                "skipped": tr.skipped_count,
                "failed": tr.failed_count,
                "failed_tables": tr.failed_tables,
                "rows_read": tr.rows_read,
                "rows_written_dts": tr.rows_written_dts,
                "rows_written_datanow": tr.rows_written_datanow,
            }

        with self._path.open("w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, ensure_ascii=False)

        logger.info("Summary written to %s", self._path)
