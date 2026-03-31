"""BigQuery credentials validator.

Validates a Service Account JSON by listing tables in the specified dataset
and checking that the core Emarsys table (email_sends_{customer_id}) exists.
"""

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
    tables_found: list[str] = field(default_factory=list)
    error: str | None = None


def validate_credentials(
    sa_json: dict[str, Any],
    gcp_project_id: str,
    dataset_id: str,
    customer_id: str,
) -> ValidationResult:
    """Validate BigQuery Service Account credentials.

    Steps:
    1. Check SA JSON has required fields.
    2. Build BigQuery client with the SA credentials.
    3. List tables in dataset_id.
    4. Verify email_sends_{customer_id} is present.

    Args:
        sa_json: Service Account JSON dict.
        gcp_project_id: GCP project ID.
        dataset_id: BigQuery dataset ID to validate.
        customer_id: Emarsys customer ID used to check core table existence.

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
        # Step 2: Build BQ client
        credentials = service_account.Credentials.from_service_account_info(
            sa_json, scopes=_SCOPES
        )
        client = bigquery.Client(credentials=credentials, project=gcp_project_id)

        # Step 3: List tables
        tables = list(client.list_tables(dataset_id))
        table_names = [t.table_id for t in tables]
        logger.info(
            "BigQuery list_tables: dataset=%s found=%d tables",
            dataset_id,
            len(table_names),
        )

        # Step 4: Check core table
        core_table = f"email_sends_{customer_id}"
        if core_table not in table_names:
            return ValidationResult(
                success=False,
                error=(
                    f"数据集 {dataset_id} 中未找到核心表 {core_table}。"
                    f"已发现的表：{', '.join(table_names[:10]) or '(空)'}"
                ),
            )

        return ValidationResult(success=True, tables_found=table_names)

    except Exception as exc:
        logger.error("BigQuery validation failed: %s", exc)
        return ValidationResult(success=False, error=str(exc))
