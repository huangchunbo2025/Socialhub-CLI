#FROM python:3.11-slim-bookworm
FROM registry.easesaas.com/myron/python:3.11-slim-bookworm

WORKDIR /app

# 安装所有依赖（http + sync + dev）
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[http,sync,dev]" \
    && pip install --no-cache-dir psycopg2-binary

# 复制业务代码
COPY emarsys_sync/ ./emarsys_sync/
COPY mcp_server/ ./mcp_server/
COPY cli/ ./cli/
COPY alembic_mcp/ ./alembic_mcp/

# 复制测试代码
COPY tests/ ./tests/

CMD ["pytest", "tests/integration/", "-v", "--tb=short", "--no-cov"]
