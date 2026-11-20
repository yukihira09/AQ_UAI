FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY apps/api/pyproject.toml /app/pyproject.toml
COPY apps/api/src /app/src
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 appuser
COPY apps/api/alembic.ini /app/alembic.ini
COPY apps/api/migrations /app/migrations
USER appuser

CMD ["uvicorn", "aq_uai_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers"]
