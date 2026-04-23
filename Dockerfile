FROM python:3.11-slim-bookworm

# System deps: Chromium + Xvfb + fonts + Chinese support
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    xvfb \
    fonts-noto-cjk \
    fonts-liberation \
    fonts-noto-color-emoji \
    dbus \
    && rm -rf /var/lib/apt/lists/*

# Python deps
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Entrypoint: start Xvfb, then run the script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Data dirs
RUN mkdir -p /app/logs /app/sso

# Default: run 1 registration per container invocation
ENV COUNT=1
ENV EXTRACT_NUMBERS=true

ENTRYPOINT ["/entrypoint.sh"]
CMD ["--count", "1", "--extract-numbers"]
