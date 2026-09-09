# Replay/API unit you would replicate. Headless Chromium — human handoff
# still wants a headed browser on the host (see DEMO.md).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_HEADLESS=true \
    APP_HOST=0.0.0.0 \
    APP_PORT=8787

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e . \
    && playwright install --with-deps chromium

COPY frontend ./frontend
EXPOSE 8787
CMD ["capability-forge", "api"]
