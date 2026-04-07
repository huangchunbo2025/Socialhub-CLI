"""StarRocks dts_ writer — uses Stream Load HTTP API for bulk insert."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import httpx

from emarsys_sync.mapping.dts_mappings import apply_dts_mapping

logger = logging.getLogger(__name__)

_STREAM_LOAD_TIMEOUT = 120  # seconds


def _sr_default(obj: Any) -> str:
    """JSON serializer for StarRocks stream load.

    StarRocks datetime columns require 'YYYY-MM-DD HH:MM:SS' format.
    ISO-format strings with timezone offset (e.g. '+00:00') are rejected.
    """
    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    return str(obj)


def _normalize_dt(value: Any) -> Any:
    """Convert ISO datetime strings to StarRocks-compatible format."""
    if not isinstance(value, str):
        return value
    # Detect ISO-format datetime strings (contain 'T' and a date part)
    if "T" in value and len(value) >= 19:
        try:
            from dateutil.parser import parse as _dtparse  # noqa: PLC0415
            return _dtparse(value).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    return value


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize datetime string values in a mapped row for StarRocks."""
    return {k: _normalize_dt(v) for k, v in row.items()}


def build_stream_load_url(host: str, http_port: int, database: str, table: str) -> str:
    """Build the StarRocks Stream Load endpoint URL.

    Args:
        host: StarRocks FE host.
        http_port: StarRocks HTTP port (default 8040 BE port).
        database: Target database name.
        table: Target table name.

    Returns:
        Stream Load URL string.
    """
    return f"http://{host}:{http_port}/api/{database}/{table}/_stream_load"


class DtsWriter:
    """Writes transformed rows into StarRocks dts_ tables via Stream Load.

    Args:
        host: StarRocks BE host.
        http_port: StarRocks HTTP API port (default 8040).
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
        param_rows = [_normalize_row(m["row"]) for m in mapped]

        url = build_stream_load_url(self._host, self._http_port, self._database, target_table)
        headers = {
            "format": "json",
            "strip_outer_array": "true",
            "timeout": str(_STREAM_LOAD_TIMEOUT),
            "Expect": "100-continue",
        }

        resp = httpx.put(
            url,
            auth=self._auth,
            headers=headers,
            content=json.dumps(param_rows, default=_sr_default).encode(),
            timeout=_STREAM_LOAD_TIMEOUT + 10,
            follow_redirects=True,
        )
        try:
            result = resp.json()
        except Exception as exc:
            raise RuntimeError(
                f"Stream Load non-JSON response (HTTP {resp.status_code}) "
                f"for {self._database}.{target_table}: {resp.text[:200]}"
            ) from exc
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
