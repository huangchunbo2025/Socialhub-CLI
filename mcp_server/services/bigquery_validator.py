"""BigQuery credentials validator."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from google.cloud import bigquery
from google.oauth2 import service_account

logger = logging.getLogger(__name__)

_REQUIRED_SA_FIELDS = {"type", "project_id", "private_key", "client_email"}
_SCOPES = ["https://www.googleapis.com/auth/bigquery.readonly"]


@dataclass
class ValidationResult:
    success: bool
    datasets_found: list[str] = field(default_factory=list)  # auto-discovered emarsys_* dataset IDs
    tables_found: list[str] = field(default_factory=list)
    account_ids_found: list[str] = field(default_factory=list)  # suite account IDs from email_sends_* tables
    error: str | None = None


def validate_credentials(
    sa_json: dict[str, Any],
    gcp_project_id: str,
    dataset_id: str | None = None,
    customer_id: str | None = None,
) -> ValidationResult:
    """Validate BigQuery Service Account credentials.

    If dataset_id is provided: validate that single dataset (existing behavior).
    If dataset_id is None: auto-discover all emarsys_* datasets in the GCP project.

    If customer_id is provided: verify email_sends_{customer_id} table exists.
    If customer_id is None: scan for all email_sends_* tables, extract suffixes.

    Args:
        sa_json: Service Account JSON dict.
        gcp_project_id: GCP project ID.
        dataset_id: BigQuery dataset ID to validate. If None, auto-discovers emarsys_* datasets.
        customer_id: Emarsys customer ID (optional). If omitted, auto-detected from table names.

    Returns:
        ValidationResult with success=True and tables_found on success,
        or success=False and error message on failure.
    """
    # Step 1: SA JSON format check
    missing = _REQUIRED_SA_FIELDS - set(sa_json.keys())
    if missing:
        return ValidationResult(
            success=False,
            error=f"service_account_json 格式无效：缺少字段 {', '.join(sorted(missing))}",
        )
    if sa_json.get("type") != "service_account":
        return ValidationResult(
            success=False,
            error="service_account_json 格式无效：type 必须为 'service_account'",
        )

    try:
        credentials = service_account.Credentials.from_service_account_info(
            sa_json, scopes=_SCOPES
        )
        client = bigquery.Client(credentials=credentials, project=gcp_project_id)

        if dataset_id is None:
            # Auto-discover all emarsys_* datasets
            datasets = list(client.list_datasets())
            emarsys_datasets = [ds for ds in datasets if ds.dataset_id.startswith("emarsys_")]
            if not emarsys_datasets:
                return ValidationResult(
                    success=False,
                    error="No emarsys_* datasets found in project",
                )

            all_tables: list[Any] = []
            dataset_ids: list[str] = []
            for ds in emarsys_datasets:
                dataset_ref = client.dataset(ds.dataset_id)
                ds_tables = list(client.list_tables(dataset_ref))
                all_tables.extend(ds_tables)
                dataset_ids.append(ds.dataset_id)
                logger.info(
                    "BigQuery list_tables: dataset=%s found=%d tables",
                    ds.dataset_id,
                    len(ds_tables),
                )

            customer_ids = list({
                t.table_id.removeprefix("email_sends_")
                for t in all_tables
                if t.table_id.startswith("email_sends_")
            })

            return ValidationResult(
                success=True,
                datasets_found=dataset_ids,
                tables_found=[t.table_id for t in all_tables],
                account_ids_found=customer_ids,
            )

        # Single dataset validation (existing behavior)
        tables = list(client.list_tables(dataset_id))
        table_names = [t.table_id for t in tables]
        logger.info("BigQuery list_tables: dataset=%s found=%d tables", dataset_id, len(table_names))

        if not table_names:
            return ValidationResult(
                success=False,
                error=f"数据集 {dataset_id} 中未发现任何表，请检查权限或 Dataset ID",
            )

        # Extract account_ids from email_sends_* tables
        account_ids_found = [
            t.removeprefix("email_sends_")
            for t in table_names
            if t.startswith("email_sends_")
        ]

        if customer_id:
            # Specific customer_id check
            core_table = f"email_sends_{customer_id}"
            if core_table not in table_names:
                return ValidationResult(
                    success=False,
                    error=(
                        f"数据集 {dataset_id} 中未找到核心表 {core_table}。"
                        f"已发现的表：{', '.join(table_names[:10]) or '(空)'}"
                    ),
                )
        else:
            # No customer_id: just need at least one table
            pass

        return ValidationResult(
            success=True,
            tables_found=table_names,
            account_ids_found=account_ids_found,
        )

    except Exception as exc:
        logger.error("BigQuery validation failed: %s", exc)
        return ValidationResult(success=False, error=str(exc))
