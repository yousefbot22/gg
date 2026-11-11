# ==============================================================
# Qureo Solution Bot — Production Dockerfile
# ==============================================================
# Multi-stage build:
#   1. builder  — installs Python deps into a venv
#   2. runtime  — slim image with only runtime deps + venv
# ==============================================================

FROM python:3.11-slim AS builder

WORKDIR /build

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Create venv and install Python deps
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


# ==============================================================
# Runtime
# ==============================================================

FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HEADLESS=true \
    PYTHONPATH=/app \
    PORT=8080

WORKDIR /app

# Chromium runtime dependencies only (no compilers)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        fonts-liberation \
        fonts-noto-color-emoji \
        fonts-noto-core \
        libnss3 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libatspi2.0-0 \
        libcups2 \
        libdbus-1-3 \
        libdrm2 \
        libgbm1 \
        libgtk-3-0 \
        libnspr4 \
        libpango-1.0-0 \
        libx11-6 \
        libxcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxkbcommon0 \
        libxrandr2 \
        libxshmfence1 \
        libasound2 \
        libpangoft2-1.0-0 \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Playwright Chromium as the app user (before we switch users)
RUN playwright install --with-deps chromium \
    && rm -rf /root/.cache/ms-playwright/chromium-*/chrome-linux/meipreload 2>/dev/null || true

# Create non-root user
RUN groupadd -r botuser && useradd -r -g botuser -d /app -s /sbin/nologin botuser

# Copy app code
COPY --chown=botuser:botuser . .

# Ensure writable dirs
RUN mkdir -p /app/data /app/logs /app/screenshots \
    && chown -R botuser:botuser /app

USER botuser

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/ping" || exit 1

# Use tini as PID 1 to handle signals correctly
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "main.py"]