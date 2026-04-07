FROM python:3.11-slim-bookworm

WORKDIR /app

# 修复基础镜像 OS 层漏洞（apt 安全更新），保持 slim 体积
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 先复制业务代码，再安装，确保 setuptools 能扫描到 emarsys_sync 包
COPY pyproject.toml ./
COPY emarsys_sync/ ./emarsys_sync/
COPY mcp_server/__init__.py ./mcp_server/__init__.py
COPY mcp_server/models.py ./mcp_server/models.py
COPY mcp_server/db.py ./mcp_server/db.py
COPY mcp_server/sync/ ./mcp_server/sync/
COPY alembic_mcp/ ./alembic_mcp/

# 安装 sync 依赖（pymysql + google-cloud-bigquery + httpx + asyncpg）
RUN pip install --no-cache-dir -e ".[http,sync]" \
    && pip install --no-cache-dir psycopg2-binary

# 状态文件目录（挂载 volume 持久化 run_summary.json）
RUN mkdir -p /data/emarsys_sync

CMD ["socialhub-sync-emarsys"]
