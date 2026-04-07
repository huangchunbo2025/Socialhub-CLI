"""Single-tenant sync orchestrator: BQ → dts_ + datanow_ + views."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pymysql

from emarsys_sync.bq_reader import BqReader, TableNotFoundError
from emarsys_sync.datanow_writer import DatanowWriter
from emarsys_sync.dts_writer import DtsWriter
from emarsys_sync.mapping.datanow_mappings import DATANOW_TABLES
from emarsys_sync.mapping.dts_mappings import DTS_TABLES
from emarsys_sync.view_manager import ViewManager
from mcp_server.sync.models import SyncStateStore, TenantSyncConfig

logger = logging.getLogger(__name__)

# All 29 Emarsys BQ table names (without account suffix)
ALL_EMARSYS_TABLES: list[str] = [
    "email_campaigns_v2",
    "email_sends",
    "email_opens",
    "email_clicks",
    "email_bounces",
    "email_cancels",
    "email_complaints",
    "email_unsubscribes",
    "web_push_campaigns",
    "web_push_sends",
    "web_push_clicks",
    "web_push_not_sends",
    "web_push_custom_events",
    "sms_sends",
    "sms_deliveries",
    "sms_clicks",
    "sms_bounces",
    "mobile_push_sends",
    "mobile_push_deliveries",
    "mobile_push_opens",
    "engagement_events",
    "predict_clicks",
    "loyalty_contact_points_state_latest",
    "loyalty_points_earned_redeemed",
    "conversation_opens",
    "conversation_deliveries",
    "conversation_clicks",
    "conversation_sends",
    "products_latest_state",
]


@dataclass
class TableResult:
    """Result of syncing one table for one tenant."""

    table_name: str
    rows_read: int = 0
    rows_written_dts: int = 0
    rows_written_datanow: int = 0
    error: str | None = None
    skipped: bool = False  # True = BQ table not found, normal skip

    @property
    def success(self) -> bool:
        """Return True if no error occurred."""
        return self.error is None


@dataclass
class TenantResult:
    """Aggregated result for a full tenant sync."""

    tenant_id: str
    table_results: list[TableResult] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        """Return number of successfully synced tables."""
        return sum(1 for t in self.table_results if t.success)

    @property
    def failed_count(self) -> int:
        """Return number of failed tables."""
        return sum(1 for t in self.table_results if not t.success)

    @property
    def failed_tables(self) -> list[str]:
        """Return list of failed table names."""
        return [t.table_name for t in self.table_results if not t.success]

    @property
    def skipped_count(self) -> int:
        """Return number of skipped tables (BQ table not found)."""
        return sum(1 for t in self.table_results if t.skipped)

    @property
    def rows_read(self) -> int:
        """Return total rows read across all tables."""
        return sum(t.rows_read for t in self.table_results)

    @property
    def rows_written_dts(self) -> int:
        """Return total rows written to dts_ tables."""
        return sum(t.rows_written_dts for t in self.table_results)

    @property
    def rows_written_datanow(self) -> int:
        """Return total rows written to datanow_.t_retailevent."""
        return sum(t.rows_written_datanow for t in self.table_results)


class TenantSyncer:
    """Orchestrates a full sync cycle for one tenant.

    Args:
        config: Tenant sync configuration (databases, credentials).
        sr_host: StarRocks FE host.
        sr_port: StarRocks MySQL protocol port (for DDL).
        sr_http_port: StarRocks HTTP port (for Stream Load).
        sr_user: StarRocks username.
        sr_password: StarRocks password.
        state_store: Watermark persistence store.
        batch_size: Max BQ rows per table read.
    """

    def __init__(
        self,
        config: TenantSyncConfig,
        sr_host: str,
        sr_port: int,
        sr_http_port: int,
        sr_user: str,
        sr_password: str,
        state_store: SyncStateStore,
        batch_size: int = 10_000,
    ) -> None:
        self._config = config
        self._sr_host = sr_host
        self._sr_port = sr_port
        self._sr_http_port = sr_http_port
        self._sr_user = sr_user
        self._sr_password = sr_password
        self._state_store = state_store
        self._batch_size = batch_size

    def _make_sr_conn(self) -> pymysql.Connection:
        return pymysql.connect(
            host=self._sr_host,
            port=self._sr_port,
            user=self._sr_user,
            password=self._sr_password,
            connect_timeout=10,
        )

    def _resolve_datasets(self) -> list[str]:
        """Resolve dataset IDs to sync.

        If ``dataset_id`` is set, return it as a single-element list.
        Otherwise, discover all ``emarsys_*`` datasets in the BQ project.

        Returns:
            List of dataset IDs.
        """
        cfg = self._config
        if cfg.dataset_id:
            return [cfg.dataset_id]

        logger.info(
            "Tenant %s: dataset_id is empty, discovering emarsys_* datasets in project %s",
            cfg.tenant_id,
            cfg.gcp_project_id,
        )
        datasets = BqReader.list_emarsys_datasets(
            sa_json=cfg.sa_json, project=cfg.gcp_project_id
        )
        logger.info("Tenant %s: found %d datasets: %s", cfg.tenant_id, len(datasets), datasets)
        return datasets

    async def sync(self) -> TenantResult:
        """Run a full incremental sync for this tenant.

        When ``dataset_id`` is empty, automatically discovers all ``emarsys_*``
        datasets in the BQ project and syncs each one.

        Returns:
            TenantResult with per-table outcomes.
        """
        cfg = self._config
        result = TenantResult(tenant_id=cfg.tenant_id)

        datasets = self._resolve_datasets()
        if not datasets:
            logger.warning("Tenant %s: no emarsys_* datasets found, skipping", cfg.tenant_id)
            return result

        dts_writer = DtsWriter(
            host=self._sr_host,
            http_port=self._sr_http_port,
            user=self._sr_user,
            password=self._sr_password,
            database=cfg.dts_database,
        )
        datanow_writer = DatanowWriter(
            host=self._sr_host,
            http_port=self._sr_http_port,
            user=self._sr_user,
            password=self._sr_password,
            database=cfg.datanow_database,
        )
        # ViewManager uses MySQL protocol for DDL
        sr_conn = self._make_sr_conn()
        view_manager = ViewManager(conn=sr_conn, database=cfg.datanow_database)

        try:
            for dataset_id in datasets:
                bq_reader = BqReader.from_sa_json(
                    sa_json=cfg.sa_json,
                    project=cfg.gcp_project_id,
                    dataset=dataset_id,
                    batch_size=self._batch_size,
                )
                for table_name in ALL_EMARSYS_TABLES:
                    table_result = await self._sync_table(
                        table_name=table_name,
                        account_id=cfg.account_id or "",
                        dataset_id=dataset_id,
                        bq_reader=bq_reader,
                        dts_writer=dts_writer,
                        datanow_writer=datanow_writer,
                    )
                    result.table_results.append(table_result)

            # Refresh views after all tables done
            try:
                view_manager.refresh_all_views()
            except Exception as exc:
                logger.error("View refresh failed for %s: %s", cfg.tenant_id, exc)

        finally:
            sr_conn.close()

        logger.info(
            "Tenant %s sync done: %d ok, %d failed",
            cfg.tenant_id,
            result.success_count,
            result.failed_count,
        )
        return result

    async def _sync_table(
        self,
        *,
        table_name: str,
        account_id: str,
        dataset_id: str,
        bq_reader: BqReader,
        dts_writer: DtsWriter,
        datanow_writer: DatanowWriter,
    ) -> TableResult:
        """Sync a single BQ table for this tenant.

        Args:
            table_name: BQ table name without account suffix.
            account_id: Emarsys account ID (table name suffix).
            dataset_id: BigQuery dataset ID for this sync iteration.
            bq_reader: Configured BigQuery reader.
            dts_writer: Configured dts_ stream load writer.
            datanow_writer: Configured datanow_ stream load writer.

        Returns:
            TableResult with row counts and error info.
        """
        cfg = self._config
        tr = TableResult(table_name=table_name)

        watermark = await self._state_store.get_watermark(cfg.tenant_id, dataset_id, table_name)

        try:
            rows = bq_reader.read_incremental(
                table_name, account_id=account_id, watermark=watermark
            )
            tr.rows_read = len(rows)
            if not rows:
                return tr

            # Determine max event_time for watermark update
            event_times = [r.get("event_time") for r in rows if r.get("event_time")]
            new_watermark: datetime | None = None
            if event_times:
                max_ts = max(event_times)
                if isinstance(max_ts, str):
                    from dateutil.parser import parse as dtparse  # noqa: PLC0415

                    new_watermark = dtparse(max_ts).replace(tzinfo=timezone.utc)
                elif isinstance(max_ts, datetime):
                    new_watermark = max_ts

            dts_ok = True
            datanow_ok = True

            if table_name in DTS_TABLES:
                try:
                    tr.rows_written_dts = dts_writer.write(
                        table_name, rows, tenant_id=cfg.tenant_id
                    )
                except Exception as exc:
                    logger.error("dts write failed %s/%s: %s", cfg.tenant_id, table_name, exc)
                    dts_ok = False
                    tr.error = f"dts: {exc}"

            if table_name in DATANOW_TABLES:
                try:
                    tr.rows_written_datanow = datanow_writer.write(
                        table_name,
                        rows,
                        tenant_id=cfg.tenant_id,
                        customer_code=cfg.account_id or cfg.tenant_id,
                    )
                except Exception as exc:
                    logger.error("datanow write failed %s/%s: %s", cfg.tenant_id, table_name, exc)
                    datanow_ok = False
                    tr.error = (tr.error or "") + f" datanow: {exc}"

            # Update watermark only if all applicable writes succeeded
            if dts_ok and datanow_ok and new_watermark:
                await self._state_store.update_watermark(
                    cfg.tenant_id,
                    dataset_id,
                    table_name,
                    new_watermark,
                    rows_delta=tr.rows_read,
                )

        except TableNotFoundError:
            logger.debug(
                "BQ table not found, skipped: %s/%s", cfg.tenant_id, table_name
            )
            tr.skipped = True
            return tr
        except Exception as exc:
            logger.error("BQ read failed %s/%s: %s", cfg.tenant_id, table_name, exc)
            tr.error = f"bq: {exc}"

        return tr
