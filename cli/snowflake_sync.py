"""Sync customer data from Snowflake into SocialHub local data files."""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import typer
from dotenv import load_dotenv
from rich.console import Console

app = typer.Typer(help="Sync Snowflake customer data into SocialHub local files.")
console = Console()


@dataclass
class SyncState:
    row_count: int
    table_hash: str
    synced_at: str
    source_table: str
    output_csv: str


@dataclass
class SnowflakeSyncConfig:
    account: str
    user: str
    warehouse: str
    database: str
    schema: str
    table: str
    role: str
    output_csv: Path
    state_file: Path
    interval_seconds: int
    authenticator: str | None = None
    password: str | None = None
    host: str | None = None
    account_locator: str | None = None
    sort_by: str | None = None

    @property
    def qualified_table(self) -> str:
        return ".".join(
            quote_identifier(part) for part in (self.database, self.schema, self.table)
        )


def quote_identifier(value: str) -> str:
    escaped = value.replace('"', '""')
    return f'"{escaped}"'


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=path.parent,
        prefix=f"{path.stem}.",
        suffix=".tmp",
        encoding="utf-8",
    ) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def write_csv_atomic(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=path.parent,
        prefix=f"{path.stem}.",
        suffix=".tmp",
        encoding="utf-8-sig",
        newline="",
    ) as tmp:
        frame.to_csv(tmp.name, index=False, encoding="utf-8-sig")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def build_config(
    output_csv: str,
    interval_seconds: int,
    state_file: str | None,
    sort_by: str | None,
) -> SnowflakeSyncConfig:
    from cli.config import load_config
    sf = load_config().snowflake

    output_path = Path(output_csv).resolve()
    state_path = Path(state_file).resolve() if state_file else output_path.with_suffix(".sync_state.json")

    # Validate required fields (loaded from SnowflakeConfig / env vars via load_config)
    if not sf.account:
        raise ValueError("Missing required environment variable: SNOWFLAKE_ACCOUNT")
    if not sf.user:
        raise ValueError("Missing required environment variable: SNOWFLAKE_USER")
    if not sf.warehouse:
        raise ValueError("Missing required environment variable: SNOWFLAKE_WAREHOUSE")
    if not sf.database:
        raise ValueError("Missing required environment variable: SNOWFLAKE_DATABASE")
    if not sf.schema_name:
        raise ValueError("Missing required environment variable: SNOWFLAKE_SCHEMA")
    if not sf.role:
        raise ValueError("Missing required environment variable: SNOWFLAKE_ROLE")

    return SnowflakeSyncConfig(
        account=sf.account,
        account_locator=sf.account_locator or None,
        host=sf.host or None,
        user=sf.user,
        password=sf.password or None,
        authenticator=sf.authenticator or None,
        warehouse=sf.warehouse,
        database=sf.database,
        schema=sf.schema_name,
        table=sf.table,
        role=sf.role,
        output_csv=output_path,
        state_file=state_path,
        interval_seconds=max(5, interval_seconds),
        sort_by=sort_by or sf.sort_by or None,
    )


def connect_snowflake(config: SnowflakeSyncConfig):
    import snowflake.connector

    connect_kwargs: dict[str, Any] = {
        "user": config.user,
        "warehouse": config.warehouse,
        "database": config.database,
        "schema": config.schema,
        "role": config.role,
    }
    if config.authenticator:
        connect_kwargs["authenticator"] = config.authenticator
    elif config.password:
        connect_kwargs["password"] = config.password
    else:
        raise ValueError("Missing Snowflake authentication: set SNOWFLAKE_PASSWORD or SNOWFLAKE_AUTHENTICATOR")

    attempts: list[dict[str, str]] = [{"account": config.account}]
    if config.account_locator and config.account_locator != config.account:
        attempts.append({"account": config.account_locator})
    if config.host:
        attempts.append({"account": config.account, "host": config.host})

    last_error: Exception | None = None
    for variant in attempts:
        try:
            return snowflake.connector.connect(**connect_kwargs, **variant)
        except Exception as exc:
            last_error = exc
            console.print(f"[yellow]Snowflake connect attempt failed with {variant}: {exc}[/yellow]")

    assert last_error is not None
    raise last_error


def fetch_fingerprint(conn, config: SnowflakeSyncConfig) -> tuple[int, str]:
    sql = f"SELECT COUNT(*) AS row_count, HASH_AGG(*) AS table_hash FROM {config.qualified_table}"
    cursor = conn.cursor()
    try:
        row = cursor.execute(sql).fetchone()
        if not row:
            return 0, "0"
        return int(row[0] or 0), str(row[1] or "0")
    finally:
        cursor.close()


def fetch_table_frame(conn, config: SnowflakeSyncConfig) -> pd.DataFrame:
    order_clause = ""
    if config.sort_by:
        order_clause = f" ORDER BY {quote_identifier(config.sort_by)}"

    sql = f"SELECT * FROM {config.qualified_table}{order_clause}"
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        return cursor.fetch_pandas_all()
    finally:
        cursor.close()


def normalize_customer_frame(frame: pd.DataFrame) -> pd.DataFrame:
    renamed = frame.rename(
        columns={
            "CUSTOMER_CODE": "id",
            "CUSTOMER_NAME": "name",
            "CREATE_TIME": "created_at",
            "IDENTITY_TYPE": "identity_type",
            "SOURCE_NAME": "channels",
            "SOURCE_CODE": "source_code",
            "GENDER": "gender",
            "BITMAP_ID": "bitmap_id",
        }
    ).copy()

    if "identity_type" in renamed.columns:
        renamed["customer_type"] = renamed["identity_type"].apply(map_identity_type)

    if "created_at" in renamed.columns:
        renamed["created_at"] = pd.to_datetime(renamed["created_at"], errors="coerce")

    preferred_columns = [
        "id",
        "name",
        "customer_type",
        "created_at",
        "channels",
        "source_code",
        "gender",
        "bitmap_id",
        "identity_type",
    ]
    ordered = [column for column in preferred_columns if column in renamed.columns]
    remainder = [column for column in renamed.columns if column not in ordered]
    return renamed[ordered + remainder]


def map_identity_type(value: Any) -> str:
    if pd.isna(value):
        return "unknown"
    if str(value) == "1":
        return "member"
    return f"identity_{value}"


def sync_once(config: SnowflakeSyncConfig) -> bool:
    conn = connect_snowflake(config)
    try:
        row_count, table_hash = fetch_fingerprint(conn, config)
        previous_state = load_state(config.state_file)
        if (
            previous_state
            and int(previous_state.get("row_count", -1)) == row_count
            and str(previous_state.get("table_hash", "")) == table_hash
        ):
            console.print(
                f"[dim]No Snowflake changes detected for {config.qualified_table}. "
                f"rows={row_count} hash={table_hash}[/dim]"
            )
            return False

        frame = fetch_table_frame(conn, config)
        normalized = normalize_customer_frame(frame)
        write_csv_atomic(config.output_csv, normalized)

        state = SyncState(
            row_count=len(normalized),
            table_hash=table_hash,
            synced_at=utc_now_iso(),
            source_table=config.qualified_table,
            output_csv=str(config.output_csv),
        )
        write_json_atomic(config.state_file, asdict(state))

        console.print(
            f"[green]Synced {len(normalized)} rows from {config.qualified_table} "
            f"to {config.output_csv}[/green]"
        )
        return True
    finally:
        conn.close()


@app.command()
def run(
    output_csv: str = typer.Option(
        "data/customers.csv",
        "--output-csv",
        help="Local CSV path to refresh when Snowflake data changes.",
    ),
    interval_seconds: int = typer.Option(
        60,
        "--interval",
        min=5,
        help="Polling interval in seconds for watch mode.",
    ),
    once: bool = typer.Option(
        False,
        "--once",
        help="Run a single sync check and exit.",
    ),
    state_file: str | None = typer.Option(
        None,
        "--state-file",
        help="Optional JSON file for sync state. Defaults next to the output CSV.",
    ),
    sort_by: str | None = typer.Option(
        "CUSTOMER_CODE",
        "--sort-by",
        help="Optional Snowflake column used for stable export ordering.",
    ),
) -> None:
    """Poll Snowflake and refresh local customer CSV when the table changes."""
    load_dotenv()
    config = build_config(output_csv, interval_seconds, state_file, sort_by)

    if once:
        changed = sync_once(config)
        raise typer.Exit(0 if changed else 0)

    console.print(
        f"[cyan]Watching {config.qualified_table} every {config.interval_seconds}s -> "
        f"{config.output_csv}[/cyan]"
    )
    while True:
        try:
            sync_once(config)
        except KeyboardInterrupt:
            console.print("[yellow]Stopped Snowflake sync watcher[/yellow]")
            raise typer.Exit(0)
        except Exception as exc:
            console.print(f"[red]Snowflake sync failed: {exc}[/red]")
        time.sleep(config.interval_seconds)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
