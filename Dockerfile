ARG PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.14-slim
ARG NODE_IMAGE=docker.m.daocloud.io/library/node:24-alpine
FROM ${NODE_IMAGE} AS frontend-build
WORKDIR /frontend-src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
COPY pyproject.toml /pyproject.toml
RUN npm run build

FROM ${PYTHON_IMAGE}

COPY --from=ghcr.io/astral-sh/uv:0.11.12 /uv /uvx /bin/

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    DATA_DIR=/data \
    FRONTEND_DIR=/frontend

RUN mkdir -p /data /frontend

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY backend/app ./app
COPY --from=frontend-build /frontend-src/dist /frontend

VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
