"""StarRocks datanow_ writer — stream-loads into t_retailevent."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from emarsys_sync.mapping.datanow_mappings import apply_datanow_mapping

logger = logging.getLogger(__name__)

_STREAM_LOAD_TIMEOUT = 120
_FIXED_COLUMNS = [
    "event_key",
    "event_type",
    "event_time",
    "customer_code",
    "tenant_id",
]
_ALL_SLOT_COLUMNS = (
    [f"text{i}" for i in range(1, 31)]
    + [f"dimension{i}" for i in range(1, 26)]
    + [f"bigint{i}" for i in range(1, 16)]
    + [f"decimal{i}" for i in range(1, 6)]
    + [f"datetime{i}" for i in range(1, 6)]
    + [f"date{i}" for i in range(1, 6)]
    + ["context"]
)
_ALL_COLUMNS = _FIXED_COLUMNS + _ALL_SLOT_COLUMNS


class DatanowWriter:
    """Writes event rows into StarRocks datanow_.t_retailevent via Stream Load.

    Args:
        host: StarRocks FE host.
        http_port: StarRocks HTTP API port (default 8030).
        user: StarRocks username.
        password: StarRocks password.
        database: Target datanow_ database name.
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

    def write(
        self,
        table_name: str,
        rows: list[dict[str, Any]],
        *,
        tenant_id: str,
        customer_code: str,
    ) -> int:
        """Stream-load BQ rows as t_retailevent records.

        Args:
            table_name: BQ source table name (without account suffix).
            rows: List of raw BQ row dicts.
            tenant_id: Tenant identifier.
            customer_code: Customer code for t_retailevent.customer_code.

        Returns:
            Number of rows loaded.

        Raises:
            RuntimeError: If StarRocks returns a non-Success status.
        """
        if not rows:
            return 0

        mapped = [
            apply_datanow_mapping(table_name, row, tenant_id=tenant_id, customer_code=customer_code)
            for row in rows
        ]
        mapped = [m for m in mapped if m is not None]
        if not mapped:
            return 0

        # Normalise: include only columns present (omit None slots)
        param_rows = [
            {col: m[col] for col in _ALL_COLUMNS if m.get(col) is not None} for m in mapped
        ]

        url = (
            f"http://{self._host}:{self._http_port}/api/{self._database}/t_retailevent/_stream_load"
        )
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
            content=json.dumps(param_rows, default=str).encode(),
            timeout=_STREAM_LOAD_TIMEOUT + 10,
        )
        result = resp.json()
        if result.get("Status") not in ("Success", "Publish Timeout"):
            raise RuntimeError(
                f"Stream Load failed for {self._database}.t_retailevent: "
                f"{result.get('Message', result)}"
            )

        loaded = result.get("NumberLoadedRows", len(param_rows))
        logger.debug(
            "datanow_writer: stream-loaded %d rows into %s.t_retailevent",
            loaded,
            self._database,
        )
        return loaded
