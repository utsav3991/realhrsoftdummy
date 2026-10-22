# Build context: the codebase directory (the parent of this project), because the
# employee screens are built from ../realhrsoft-marketplace-employee-vue:
#   docker build -f realhrsoftdummy/Dockerfile -t realhrsoftdummy .

# --- The Marketplace employee screens: the package, then this host app ---------------
FROM node:24-alpine AS screens

WORKDIR /src/realhrsoft-marketplace-employee-vue
COPY realhrsoft-marketplace-employee-vue/package.json realhrsoft-marketplace-employee-vue/package-lock.json ./
RUN npm ci
COPY realhrsoft-marketplace-employee-vue/ ./
RUN npm run build

WORKDIR /src/realhrsoftdummy/frontend
COPY realhrsoftdummy/frontend/package.json realhrsoftdummy/frontend/package-lock.json ./
RUN npm ci
COPY realhrsoftdummy/frontend/ ./
# Writes ../portal/static/marketplace (vite.config.ts).
RUN npm run build

# --- Python dependencies ------------------------------------------------------------
FROM python:3.14-slim AS builder

WORKDIR /app

ARG POETRY_VERSION=2.4.1

ENV POETRY_VERSION=${POETRY_VERSION} \
    POETRY_NO_INTERACTION=1 \
    POETRY_NO_ANSI=1 \
    POETRY_VIRTUALENVS_CREATE=0 \
    VIRTUAL_ENV="/venv" \
    PATH="/venv/bin:$PATH"

RUN pip install --no-cache-dir poetry==${POETRY_VERSION} && \
    python -m venv /venv

COPY realhrsoftdummy/pyproject.toml realhrsoftdummy/poetry.lock ./

RUN poetry install --only main --no-root

# --- Runtime ------------------------------------------------------------------------
FROM python:3.14-slim AS final

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    VIRTUAL_ENV="/venv" \
    PATH="/venv/bin:$PATH"

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --system --gid 1001 appuser && \
    useradd --system --uid 1001 --gid appuser --no-create-home appuser

COPY --from=builder /venv /venv
COPY --chown=appuser:appuser realhrsoftdummy/ .
COPY --from=screens --chown=appuser:appuser /src/realhrsoftdummy/portal/static/marketplace portal/static/marketplace

# Static files are part of the image (whitenoise serves them); no database is needed.
RUN python manage.py collectstatic --noinput && \
    chown -R appuser:appuser /app/staticfiles && \
    chmod +x /app/docker-entrypoint.sh

USER appuser

EXPOSE 8100

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8100", "--workers", "2", "--threads", "4", "--timeout", "60"]
