"""ORM models for MCP Server."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from mcp_server.db import Base


class TenantBigQueryCredential(Base):
    """Stores encrypted BigQuery Service Account credentials per tenant."""

    __tablename__ = "tenant_bigquery_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    credential_type: Mapped[str] = mapped_column(String(50), nullable=False, default="bigquery_emarsys")
    customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gcp_project_id: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    service_account_json: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet encrypted
    tables_found: Mapped[str | None] = mapped_column(Text, nullable=True)    # JSON array string
    datasets_found: Mapped[str | None] = mapped_column(Text, nullable=True)  # comma-separated dataset IDs
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
