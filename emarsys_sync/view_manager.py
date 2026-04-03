"""Semantic view manager — CREATE OR REPLACE VIEW per event_key."""

from __future__ import annotations

import logging

import pymysql

from emarsys_sync.mapping.datanow_mappings import SLOT_MAPS, build_view_ddl

logger = logging.getLogger(__name__)


class ViewManager:
    """Refreshes semantic views in a datanow_ database.

    Views are generated from SLOT_MAPS and are idempotent (CREATE OR REPLACE).
    Run after every sync cycle so mapping changes take effect immediately.

    Args:
        conn: Active pymysql connection.
        database: StarRocks datanow_ database name.
    """

    def __init__(self, conn: pymysql.Connection, database: str) -> None:
        self._conn = conn
        self._database = database

    def refresh_all_views(self) -> None:
        """Execute CREATE OR REPLACE VIEW for every event_key in SLOT_MAPS."""
        with self._conn.cursor() as cursor:
            cursor.execute(f"USE `{self._database}`")
            for event_key, slot_map in SLOT_MAPS.items():
                ddl = build_view_ddl(event_key, slot_map)
                # Prefix table reference with database for clarity
                ddl = ddl.replace(
                    "FROM t_retailevent",
                    f"FROM `{self._database}`.t_retailevent",
                )
                ddl = ddl.replace(
                    "CREATE OR REPLACE VIEW",
                    f"CREATE OR REPLACE VIEW `{self._database}`.",
                )
                logger.debug("ViewManager: executing DDL for %s", event_key)
                cursor.execute(ddl)
        self._conn.commit()
        logger.info("ViewManager: refreshed %d views in %s", len(SLOT_MAPS), self._database)
