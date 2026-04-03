"""BigQuery incremental reader for Emarsys Open Data tables."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from google.cloud import bigquery
from google.oauth2 import service_account

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/bigquery.readonly"]


def build_incremental_query(
    *,
    project: str,
    dataset: str,
    table_full: str,
    watermark: datetime | None,
    batch_size: int,
) -> str:
    """Build a BigQuery SQL query for incremental read.

    Args:
        project: GCP project ID.
        dataset: BigQuery dataset ID.
        table_full: Full table name including account_id suffix.
        watermark: Last synced event_time; None means read from beginning.
        batch_size: Maximum rows to return.

    Returns:
        SQL string.
    """
    table_ref = f"`{project}.{dataset}.{table_full}`"
    base = f"SELECT * FROM {table_ref}"

    is_engagement = table_full.startswith("engagement_events")

    if watermark and is_engagement:
        date_str = watermark.date().isoformat()
        base += (
            f" WHERE event_time > '{watermark.isoformat()}' AND partitiontime = DATE('{date_str}')"
        )
    elif watermark:
        base += f" WHERE event_time > '{watermark.isoformat()}'"

    base += " ORDER BY event_time"
    base += f" LIMIT {batch_size}"
    return base


class BqReader:
    """Reads rows incrementally from a BigQuery Emarsys dataset.

    Args:
        client: BigQuery client.
        project: GCP project ID.
        dataset: BigQuery dataset ID (e.g. ``emarsys_12345``).
        batch_size: Max rows per read call.
    """

    def __init__(
        self,
        client: bigquery.Client,
        project: str,
        dataset: str,
        batch_size: int = 10_000,
    ) -> None:
        self._client = client
        self._project = project
        self._dataset = dataset
        self._batch_size = batch_size

    @classmethod
    def from_sa_json(
        cls,
        sa_json: dict[str, Any],
        project: str,
        dataset: str,
        batch_size: int = 10_000,
    ) -> BqReader:
        """Construct a BqReader from a Service Account JSON dict.

        Args:
            sa_json: Decrypted Service Account JSON.
            project: GCP project ID.
            dataset: BigQuery dataset ID.
            batch_size: Max rows per read call.

        Returns:
            Configured BqReader instance.
        """
        creds = service_account.Credentials.from_service_account_info(sa_json, scopes=_SCOPES)
        client = bigquery.Client(project=project, credentials=creds)
        return cls(client=client, project=project, dataset=dataset, batch_size=batch_size)

    def read_incremental(
        self,
        table_name: str,
        *,
        account_id: str,
        watermark: datetime | None,
    ) -> list[dict[str, Any]]:
        """Read a batch of rows from a BQ table newer than watermark.

        Args:
            table_name: Table name without account_id suffix (e.g. ``email_sends``).
            account_id: Emarsys account/customer ID (table name suffix).
            watermark: Last synced event_time; None reads from the beginning.

        Returns:
            List of rows as dicts.

        Raises:
            Exception: Re-raises any BigQuery exception after logging.
        """
        table_full = f"{table_name}_{account_id}"
        sql = build_incremental_query(
            project=self._project,
            dataset=self._dataset,
            table_full=table_full,
            watermark=watermark,
            batch_size=self._batch_size,
        )
        logger.debug("BQ query: %s", sql)
        try:
            result = self._client.query(sql).result()
            return [dict(row) for row in result]
        except Exception as exc:
            logger.error("BQ read failed for %s.%s: %s", self._dataset, table_full, exc)
            raise
