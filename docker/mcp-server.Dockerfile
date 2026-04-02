FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[http,snowflake]" \
    && pip install --no-cache-dir psycopg2-binary

COPY mcp_server/ ./mcp_server/
COPY cli/ ./cli/
COPY alembic_mcp/ ./alembic_mcp/

EXPOSE 8090

CMD ["python", "-m", "mcp_server", "--transport", "http", "--port", "8090"]
