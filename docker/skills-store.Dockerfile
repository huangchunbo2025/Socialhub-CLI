FROM python:3.11-slim

WORKDIR /app

# 先复制全部源码（setuptools editable install 需要 backend/ 包存在）
COPY pyproject.toml ./
COPY backend/ ./backend/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY start.sh ./

RUN pip install --no-cache-dir -e . \
    && chmod +x start.sh

EXPOSE 10000

CMD ["bash", "start.sh"]
