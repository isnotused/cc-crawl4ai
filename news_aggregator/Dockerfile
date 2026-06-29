FROM python:3.11-slim

# System libraries required by Playwright/Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    gnupg \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxcb1 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install crawl4ai from local source (build context = repo root)
COPY . /tmp/crawl4ai_src/
RUN pip install --no-cache-dir /tmp/crawl4ai_src/ && rm -rf /tmp/crawl4ai_src/

# Install Playwright and download Chromium
RUN playwright install chromium --with-deps

# Install news_aggregator extra dependencies
COPY news_aggregator/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY news_aggregator/ /app/news_aggregator/
RUN mkdir -p /app/news_aggregator/output

# Hourly schedule: run once immediately, then every 3600s
CMD ["sh", "-c", \
     "while true; do \
        python -m news_aggregator.main \
          --llm ${LLM_MODE:-mock} \
          --max ${MAX_ITEMS:-20} \
          --top ${TOP_N:-40} \
          --save; \
        echo '[scheduler] next run in 3600s...'; \
        sleep 3600; \
      done"]
