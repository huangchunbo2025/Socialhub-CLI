#FROM python:3.11-slim-bookworm
FROM registry.easesaas.com/myron/python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[http,snowflake]" \
    && pip install --no-cache-dir psycopg2-binary

COPY mcp_server/ ./mcp_server/
COPY cli/ ./cli/
COPY alembic_mcp/ ./alembic_mcp/

EXPOSE 8090

CMD ["python", "-m", "mcp_server", "--transport", "http", "--port", "8090"]
