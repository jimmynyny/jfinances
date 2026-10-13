# syntax=docker/dockerfile:1.7
# One image, three services (web / hooks / worker) selected by SERVICE_ROLE.
# Stage 1 builds the SPA so no build artefacts live in git.

# ---------------------------------------------------------------- frontend --
FROM node:22-alpine AS frontend
WORKDIR /build
COPY package.json ./
COPY package-lock.json* ./
COPY packages ./packages
COPY frontend ./frontend
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
RUN npm run build

# ---------------------------------------------------------------- python ----
FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY server ./server
COPY start.sh index.html ./
COPY --from=frontend /build/frontend/dist ./frontend/dist
RUN uv sync --frozen --no-dev && chmod +x start.sh && chown -R app:app /app
ENV PATH="/app/.venv/bin:$PATH" SPA_DIR=/app/frontend/dist
USER app
EXPOSE 8000
CMD ["./start.sh"]
