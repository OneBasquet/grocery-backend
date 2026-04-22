"""
Shared browser launcher for all scrapers.
Supports:
  1. Remote cloud browser (Browserless.io) via CDP WebSocket
  2. Residential proxy for anti-bot bypass
  3. Local Chrome/Chromium fallback

Environment variables:
  BROWSERLESS_URL  — wss://chrome.browserless.io?token=YOUR_TOKEN
  PROXY_URL        — http://user:pass@proxy.example.com:port (residential proxy)
"""
import os


BROWSERLESS_URL = os.environ.get("BROWSERLESS_URL", "")
PROXY_URL = os.environ.get("PROXY_URL", "")

LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-crash-reporter",
    "--disable-breakpad",
]


def get_browser(playwright, headless: bool = True):
    """Launch a browser — remote CDP if BROWSERLESS_URL is set, local otherwise.

    If PROXY_URL is set, it's passed to the browser so all traffic routes
    through a residential proxy (bypasses datacenter IP bans).

    Returns a Browser instance. Caller is responsible for browser.close().
    """
    args = list(LAUNCH_ARGS)
    if PROXY_URL:
        args.append(f"--proxy-server={PROXY_URL}")
        print(f"  🔀 Using residential proxy")

    if BROWSERLESS_URL:
        # Append proxy arg to the WebSocket URL if needed
        ws_url = BROWSERLESS_URL
        if PROXY_URL and "&" in ws_url:
            # Some cloud providers accept launch args via URL params
            ws_url += f"&--proxy-server={PROXY_URL}"

        print(f"  🌐 Connecting to cloud browser...")
        browser = playwright.chromium.connect_over_cdp(ws_url)
        print(f"  ✓ Connected to cloud browser")
        return browser

    # Local fallback
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


def get_browser_context(browser, proxy_auth: dict = None, **kwargs):
    """Create a browser context, optionally with proxy authentication.

    Args:
        browser: Playwright Browser instance
        proxy_auth: dict with 'username' and 'password' for proxy auth
        **kwargs: additional args passed to browser.new_context()
    """
    context_opts = dict(kwargs)

    # If using proxy with auth and creating context on a local browser,
    # inject proxy credentials at the context level.
    if PROXY_URL and proxy_auth:
        context_opts["proxy"] = {
            "server": PROXY_URL,
            "username": proxy_auth.get("username", ""),
            "password": proxy_auth.get("password", ""),
        }

    return browser.new_context(**context_opts)
