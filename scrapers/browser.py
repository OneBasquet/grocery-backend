"""
Shared browser launcher for all scrapers.
Supports:
  1. Remote cloud browser (Browserless.io) via CDP WebSocket
  2. Residential proxy for anti-bot bypass (applied at context level)
  3. Local Chrome/Chromium fallback

Environment variables:
  BROWSERLESS_URL  — wss://chrome.browserless.io?token=YOUR_TOKEN
  PROXY_URL        — http://user:pass@proxy.example.com:port (residential proxy)
"""
import os
import re

BROWSERLESS_URL = os.environ.get("BROWSERLESS_URL", "")
PROXY_URL = os.environ.get("PROXY_URL", "")

LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-crash-reporter",
    "--disable-breakpad",
]


def _parse_proxy_url(url: str) -> dict:
    """Parse http://user:pass@host:port into a Playwright proxy dict."""
    m = re.match(r'https?://(?:([^:]+):([^@]+)@)?([^:]+):(\d+)', url)
    if not m:
        return {}
    result = {"server": f"http://{m.group(3)}:{m.group(4)}"}
    if m.group(1):
        result["username"] = m.group(1)
    if m.group(2):
        result["password"] = m.group(2)
    return result


def get_browser(playwright, headless: bool = True):
    """Launch a browser — remote CDP if BROWSERLESS_URL is set, local otherwise.

    Returns a Browser instance. Caller is responsible for browser.close().
    """
    if BROWSERLESS_URL:
        print(f"  🌐 Connecting to cloud browser...")
        browser = playwright.chromium.connect_over_cdp(BROWSERLESS_URL)
        print(f"  ✓ Connected to cloud browser")
        if PROXY_URL:
            print(f"  🔀 Proxy will be applied at context level")
        return browser

    # Local with proxy in launch args
    args = list(LAUNCH_ARGS)
    if PROXY_URL:
        args.append(f"--proxy-server={PROXY_URL}")
        print(f"  🔀 Using residential proxy (launch arg)")

    try:
        browser = playwright.chromium.launch(
            channel="chrome",
            headless=headless,
            args=args,
        )
        print("  ✓ Using local Chrome")
        return browser
    except Exception:
        pass

    browser = playwright.chromium.launch(
        headless=headless,
        args=args,
    )
    print("  ✓ Using local Chromium")
    return browser


def create_context(browser, **kwargs):
    """Create a browser context with proxy injected if PROXY_URL is set.

    This is the correct way to use a proxy with a remote CDP browser —
    proxy is applied per-context, not at browser launch.

    Args:
        browser: Playwright Browser instance
        **kwargs: additional args passed to browser.new_context()
    """
    context_opts = dict(kwargs)

    if PROXY_URL:
        proxy_dict = _parse_proxy_url(PROXY_URL)
        if proxy_dict:
            context_opts["proxy"] = proxy_dict
            print(f"  🔀 Proxy applied to context: {proxy_dict['server']}")

    return browser.new_context(**context_opts)
