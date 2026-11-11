FROM --platform=$TARGETPLATFORM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PLAYWRIGHT_SKIP_BROWSER_GC=1 \
    USER=container \
    HOME=/home/container

WORKDIR /home/container

# System dependencies for Chromium + Playwright runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    iproute2 \
    tzdata \
    fonts-liberation \
    fonts-noto-color-emoji \
    fonts-noto-core \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libcairo2 \
    libfontconfig1 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    libxshmfence1 \
    libatomic1 \
    libstdc++6 \
    libxcb-shm0 \
    libxcb-render0 \
    libxcb-shape0 \
    libxcb-xfixes0 \
    libxcb-randr0 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-icccm4 \
    libxcb-sync1 \
    libxcb-xinerama0 \
    libxcb-cursor0 \
    && rm -rf /var/lib/apt/lists/*

# Create Pterodactyl user
RUN useradd -m -d /home/container container

# Install Python packages
COPY requirements.txt /tmp/requirements.txt

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /tmp/requirements.txt

# Install Chromium in a shared directory
RUN mkdir -p /ms-playwright \
    && python -m playwright install chromium \
    && chmod -R a+rX /ms-playwright

# Pterodactyl entrypoint
COPY --chmod=755 entrypoint.sh /entrypoint.sh

ENV USER=container
ENV HOME=/home/container

WORKDIR /home/container

CMD ["/bin/bash", "/entrypoint.sh"]
