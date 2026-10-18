FROM node:24.22.0-bookworm-slim AS frontend
WORKDIR /build/frontend
RUN npm install --global pnpm@10.34.7
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM ghcr.io/astral-sh/uv:0.13.1 AS uv
FROM python:3.12-slim-bookworm AS backend
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
COPY backend/ backend/
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm AS runtime
ARG VCS_REF=development
LABEL org.opencontainers.image.title="SeekBell" \
      org.opencontainers.image.revision="$VCS_REF"
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SEEKBELL_DATA_DIR=/data \
    SEEKBELL_STATIC_DIR=/app/frontend/dist \
    SEEKBELL_BUILD_REVISION=$VCS_REF
WORKDIR /app
RUN groupadd --gid 10001 seekbell \
    && useradd --uid 10001 --gid seekbell --no-create-home seekbell \
    && mkdir /data && chown seekbell:seekbell /data
COPY --from=backend /app/.venv /app/.venv
COPY --from=frontend /build/frontend/dist /app/frontend/dist
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"
CMD ["uvicorn", "seekbell.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers"]
