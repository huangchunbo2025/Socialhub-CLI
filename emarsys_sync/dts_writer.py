"""StarRocks dts_ writer — uses Stream Load HTTP API for bulk insert."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from emarsys_sync.mapping.dts_mappings import apply_dts_mapping

logger = logging.getLogger(__name__)

_STREAM_LOAD_TIMEOUT = 120  # seconds


def build_stream_load_url(host: str, http_port: int, database: str, table: str) -> str:
    """Build the StarRocks Stream Load endpoint URL.

    Args:
        host: StarRocks FE host.
        http_port: StarRocks HTTP port (default 8030).
        database: Target database name.
        table: Target table name.

    Returns:
        Stream Load URL string.
    """
    return f"http://{host}:{http_port}/api/{database}/{table}/_stream_load"


class DtsWriter:
    """Writes transformed rows into StarRocks dts_ tables via Stream Load.

    Args:
        host: StarRocks FE host.
        http_port: StarRocks HTTP API port (default 8030).
        user: StarRocks username.
        password: StarRocks password.
        database: Target dts_ database name.
    """

    def __init__(
        self,
        host: str,
        http_port: int,
        user: str,
        password: str,
        database: str,
    ) -> None:
        self._host = host
        self._http_port = http_port
        self._auth = (user, password)
        self._database = database

    def write(self, table_name: str, rows: list[dict[str, Any]], *, tenant_id: str) -> int:
        """Stream-load BQ rows into the corresponding dts_ target table.

        Args:
            table_name: BQ source table name (without account suffix).
            rows: List of raw BQ row dicts.
            tenant_id: Tenant identifier for field transformation.

        Returns:
            Number of rows loaded.

        Raises:
            RuntimeError: If StarRocks returns a non-Success status.
        """
        if not rows:
            return 0

        mapped = [apply_dts_mapping(table_name, row, tenant_id=tenant_id) for row in rows]
        mapped = [m for m in mapped if m is not None]
        if not mapped:
            return 0

        target_table = mapped[0]["target_table"]
        param_rows = [m["row"] for m in mapped]

        url = build_stream_load_url(self._host, self._http_port, self._database, target_table)
        headers = {
            "format": "json",
            "strip_outer_array": "true",
            "timeout": str(_STREAM_LOAD_TIMEOUT),
        }

        resp = httpx.put(
            url,
            auth=self._auth,
            headers=headers,
            content=json.dumps(param_rows, default=str).encode(),
            timeout=_STREAM_LOAD_TIMEOUT + 10,
        )
        result = resp.json()
        if result.get("Status") not in ("Success", "Publish Timeout"):
            raise RuntimeError(
                f"Stream Load failed for {self._database}.{target_table}: "
                f"{result.get('Message', result)}"
            )

        loaded = result.get("NumberLoadedRows", len(param_rows))
        logger.debug(
            "dts_writer: stream-loaded %d rows into %s.%s",
            loaded,
            self._database,
            target_table,
        )
        return loaded
