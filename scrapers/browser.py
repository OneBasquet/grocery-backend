"""
Shared browser launcher for all scrapers.
Supports local Playwright and remote cloud browsers (Browserless.io, etc.)
via CDP (Chrome DevTools Protocol) WebSocket connection.

Usage:
    with launch_browser(playwright) as browser:
        context = browser.new_context(...)

Set BROWSERLESS_URL env var to use a cloud browser:
    BROWSERLESS_URL=wss://chrome.browserless.io?token=YOUR_TOKEN

If not set, falls back to local chromium.launch().
"""
import os


BROWSERLESS_URL = os.environ.get("BROWSERLESS_URL", "")

LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-crash-reporter",
    "--disable-breakpad",
]


def get_browser(playwright, headless: bool = True):
    """Launch a browser — remote CDP if BROWSERLESS_URL is set, local otherwise.

    Returns a Browser instance. Caller is responsible for browser.close().
    """
    if BROWSERLESS_URL:
        print(f"  🌐 Connecting to cloud browser...")
        browser = playwright.chromium.connect_over_cdp(BROWSERLESS_URL)
        print(f"  ✓ Connected to cloud browser")
        return browser

    # Local fallback — try real Chrome first, then Chromium
    try:
        browser = playwright.chromium.launch(
            channel="chrome",
            headless=headless,
            args=LAUNCH_ARGS,
        )
        print("  ✓ Using local Chrome")
        return browser
    except Exception:
        pass

    browser = playwright.chromium.launch(
        headless=headless,
        args=LAUNCH_ARGS,
    )
    print("  ✓ Using local Chromium")
    return browser
