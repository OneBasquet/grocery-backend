# Grocery backend — FastAPI + Playwright (headless Chromium scrapers).
# Built on the EC2 box by user_data.sh and run as a single container on :80.
FROM python:3.11-slim

# Playwright/Chromium system deps are installed by `playwright install --with-deps`.
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Install Python deps first for layer caching.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Install the Chromium browser + its OS dependencies.
RUN playwright install --with-deps chromium

# Xvfb: the scrapers launch Chromium *headed* (headless=False) for anti-bot
# stealth, which needs an X display. Xvfb gives the container a virtual one.
RUN apt-get update \
    && apt-get install -y --no-install-recommends xvfb \
    && rm -rf /var/lib/apt/lists/*

# App source.
COPY . .

# FastAPI listens on :80 inside the container; CloudFront origins to the EC2 host on :80.
EXPOSE 80

# Wrap uvicorn in a virtual display so headed Chromium can launch.
# Single worker keeps memory down on a 1GB t3.micro. Scrapers run sequentially.
CMD ["xvfb-run", "-a", "--server-args=-screen 0 1920x1080x24", \
     "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "80", "--workers", "1"]
