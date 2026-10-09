# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libgomp1: OpenMP runtime required by LightGBM (not present in the slim image)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# non-root user
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# /data = SQLite volume; /app/artifacts/hf_model = model folder from Hugging Face (mounted read-only by compose, never baked in)
RUN mkdir -p /data /app/artifacts && chown -R app:app /data /app
ENV DB_PATH=/data/tenders.db \
    ARTIFACT_PATH=/app/artifacts/hf_model
VOLUME ["/data"]
USER app
EXPOSE 8000

# /api/health answers 200 as soon as the server is up; the model loads in the background (~1 min)
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1

# ONE worker on purpose: the model + history indexes (~1.3 GB) live in process memory and SQLite
# has a single writer. Scale vertically or run separate instances behind a proxy if needed.
CMD ["uvicorn", "app.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
