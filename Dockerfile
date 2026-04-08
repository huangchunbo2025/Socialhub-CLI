FROM python:3.12-slim AS builder

WORKDIR /app

COPY pyproject.toml README.md ./
COPY cli/ cli/
COPY mcp_server/ mcp_server/

RUN pip install --no-cache-dir -e ".[http]"


FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

ENV PYTHONUNBUFFERED=1
ENV PORT=8090

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; r=httpx.get('http://localhost:8090/health'); exit(0 if r.status_code==200 else 1)"

CMD ["uvicorn", "mcp_server.http_app:app", \
     "--host", "0.0.0.0", "--port", "8090", \
     "--workers", "1", "--log-level", "info"]
