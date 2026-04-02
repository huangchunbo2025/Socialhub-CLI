"""BigQuery credentials management endpoints.

Routes:
    POST   /credentials/bigquery  — Upload and validate credentials
    GET    /credentials/bigquery  — Get credential status (no SA JSON)
    DELETE /credentials/bigquery  — Delete credentials
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_server.auth import resolve_tenant_id
from mcp_server.db import get_session
from mcp_server.models import TenantBigQueryCredential
from mcp_server.services.bigquery_validator import validate_credentials
from mcp_server.services.crypto import encrypt, decrypt  # noqa: F401

logger = logging.getLogger(__name__)


class UploadRequest(BaseModel):
    """Request body for uploading BigQuery credentials."""

    customer_id: str | None = Field(None, description="Emarsys Customer ID (optional, auto-detected if omitted)")
    gcp_project_id: str = Field(..., description="SAP-hosted GCP project ID")
    dataset_id: str | None = Field(None, description="BigQuery dataset ID (optional, auto-discovers emarsys_* if omitted)")
    service_account_json: dict[str, Any] = Field(..., description="Google Service Account JSON")


async def upload_credentials(request: Request) -> JSONResponse:
    """POST /credentials/bigquery — upload and validate BQ credentials."""
    try:
        body = await request.json()
        req = UploadRequest(**body)
    except Exception as e:
        return JSONResponse(
            status_code=422,
            content={"status": "error", "message": f"请求格式错误: {e}"},
        )

    # Get tenant_id from API Key middleware state or JWT portal token
    tenant_id = await resolve_tenant_id(request)
    if tenant_id is None:
        return JSONResponse(status_code=401, content={"status": "error", "message": "未认证"})

    # Validate BigQuery credentials
    result = validate_credentials(
        sa_json=req.service_account_json,
        gcp_project_id=req.gcp_project_id,
        dataset_id=req.dataset_id,
        customer_id=req.customer_id,
    )
    if not result.success:
        return JSONResponse(
            status_code=422,
            content={"status": "error", "message": f"BigQuery 校验失败：{result.error}"},
        )

    # Encrypt and store
    encrypted_sa = encrypt(json.dumps(req.service_account_json))
    tables_json = json.dumps(result.tables_found)
    # If single-dataset path, datasets_found is empty but we know the dataset
    effective_datasets = result.datasets_found if result.datasets_found else (
        [req.dataset_id] if req.dataset_id else []
    )
    datasets_found_str = json.dumps(effective_datasets) if effective_datasets else None
    now = datetime.now(timezone.utc)

    session = await get_session()
    async with session:
        stmt = select(TenantBigQueryCredential).where(
            TenantBigQueryCredential.tenant_id == tenant_id
        )
        row = (await session.execute(stmt)).scalar_one_or_none()

        resolved_customer_id = req.customer_id or (result.account_ids_found[0] if result.account_ids_found else None)

        if row is None:
            row = TenantBigQueryCredential(
                tenant_id=tenant_id,
                credential_type="bigquery_emarsys",
                customer_id=resolved_customer_id,
                gcp_project_id=req.gcp_project_id,
                dataset_id=req.dataset_id,
                service_account_json=encrypted_sa,
                tables_found=tables_json,
                datasets_found=datasets_found_str,
                validated_at=now,
            )
            session.add(row)
        else:
            row.credential_type = "bigquery_emarsys"
            row.customer_id = resolved_customer_id
            row.gcp_project_id = req.gcp_project_id
            row.dataset_id = req.dataset_id
            row.service_account_json = encrypted_sa
            row.tables_found = tables_json
            row.datasets_found = datasets_found_str
            row.validated_at = now

        await session.commit()
        await session.refresh(row)

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "tenant_id": tenant_id,
            "customer_id": resolved_customer_id,
            "account_ids_found": result.account_ids_found,
            "datasets_found": effective_datasets,
            "tables_found": result.tables_found,
            "validated_at": now.isoformat(),
        },
    )


async def get_credentials(request: Request) -> JSONResponse:
    """GET /credentials/bigquery — get credential status (no SA JSON returned)."""
    tenant_id = await resolve_tenant_id(request)
    if tenant_id is None:
        return JSONResponse(status_code=401, content={"status": "error", "message": "未认证"})

    session = await get_session()
    async with session:
        stmt = select(TenantBigQueryCredential).where(
            TenantBigQueryCredential.tenant_id == tenant_id
        )
        row = (await session.execute(stmt)).scalar_one_or_none()

    if row is None:
        return JSONResponse(status_code=200, content={"status": "ok", "configured": False})

    tables = json.loads(row.tables_found) if row.tables_found else []
    datasets = json.loads(row.datasets_found) if row.datasets_found else []
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "configured": True,
            "credential_type": row.credential_type,
            "customer_id": row.customer_id,
            "gcp_project_id": row.gcp_project_id,
            "dataset_id": row.dataset_id,
            "tables_found": tables,
            "datasets_found": datasets,
            "validated_at": row.validated_at.isoformat() if row.validated_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        },
    )


async def delete_credentials(request: Request) -> JSONResponse:
    """DELETE /credentials/bigquery — delete credentials for current tenant."""
    tenant_id = await resolve_tenant_id(request)
    if tenant_id is None:
        return JSONResponse(status_code=401, content={"status": "error", "message": "未认证"})

    session = await get_session()
    async with session:
        stmt = select(TenantBigQueryCredential).where(
            TenantBigQueryCredential.tenant_id == tenant_id
        )
        row = (await session.execute(stmt)).scalar_one_or_none()

        if row is None:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "凭据不存在"},
            )

        await session.delete(row)
        await session.commit()

    return JSONResponse(status_code=200, content={"status": "ok"})
