"""Asda scraper using Playwright with API interception technique.

Mirrors the Tesco approach:
- Intercepts JSON responses from ASDA's internal APIs for structured data
- Real Chrome browser (channel="chrome") for genuine fingerprint
- Retry with exponential backoff
- Falls back to HTML parsing if API interception yields nothing

Key fix (v3): ASDA uses Algolia for product search. The batch query endpoint
  https://8i6wskccnv-dsn.algolia.net/1/indexes/*/queries
returns { "results": [ { "hits": [...], "nbHits": N, ... } ] }
"hits" is Algolia's standard product array key — added to URL patterns and
_find_product_arrays. objectID is Algolia's standard record identifier.
"""

from playwright.sync_api import sync_playwright, Page, Response as PWResponse

try:
    from playwright_stealth import Stealth
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False

from typing import List, Dict, Any, Optional
import time
import random
import re
import json
import os
from datetime import datetime, timezone


class AsdaPlaywrightScraper:
    """Advanced Asda scraper using API interception."""

    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    ]

    MAX_RETRIES = 3
    MIN_DELAY = 1.5
    MAX_DELAY = 3.5

    # ---------------------------------------------------------------------------
    # Known ASDA product search API patterns.
    # Confirmed: ASDA uses Algolia — batch endpoint is:
    #   https://<app-id>-dsn.algolia.net/1/indexes/*/queries
    # Also keep broad patterns as fallback in case ASDA changes provider.
    # ---------------------------------------------------------------------------
    PRODUCT_API_PATTERNS = (
        # Confirmed Algolia endpoints
        "algolia.net/1/indexes",
        "algolianet.com/1/indexes",
        # Broad fallback patterns
        "/api/products",
        "/api/search",
        "/api/cms/page",
        "/api/shelf",
        "/api/browse",
        "graphql",
        "page-summary",
        "uber-page",
        "wcs/resources",
        "/items",
        "/product",
    )

    # Endpoints we know are NOT product data — skip to reduce noise
    SKIP_URL_FRAGMENTS = (
        "token-manager",
        "nr-data.net",
        "analytics",
        "tracking",
        "adobedtm",
        "doubleclick",
        "facebook",
        "google-analytics",
        # Algolia non-product endpoints
        "query_suggestions",   # autocomplete index, not products
        "set-consent",
        ".css",
        ".js",
        "fonts.googleapis",
    )

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.retailer = "asda"
        self.base_url = "https://groceries.asda.com"
        self.debug = True
        self._api_responses: List[Dict] = []
        self._all_json_urls: List[str] = []  # for discovery logging

    # ------------------------------------------------------------------
    # Response interception
    # ------------------------------------------------------------------

    def _on_response(self, response: PWResponse) -> None:
        """Capture JSON payloads from ASDA's internal APIs.

        Strategy:
        1. Log EVERY JSON response URL to asda_api_debug.json for discovery.
        2. Skip known noise endpoints.
        3. For URLs matching PRODUCT_API_PATTERNS, store the parsed body.
        4. As a safety net, also store any JSON response whose parsed body
           looks like it contains product arrays — regardless of URL.
        """
        url = response.url
        try:
            ct = response.headers.get("content-type", "")
            if "json" not in ct or response.status != 200:
                return

            body = response.json()

            # --- Skip known non-product noise ---
            if any(skip in url for skip in self.SKIP_URL_FRAGMENTS):
                return

            # --- Always log the URL for discovery ---
            self._all_json_urls.append(url)
            self._write_debug(url, body)

            # --- Check if URL matches known product patterns ---
            url_match = any(p in url for p in self.PRODUCT_API_PATTERNS)

            # --- Safety net: does the body LOOK like it has products? ---
            body_match = self._body_looks_like_products(body)

            if url_match or body_match:
                self._api_responses.append(body)
                if self.debug:
                    reason = []
                    if url_match:
                        reason.append("url-pattern")
                    if body_match:
                        reason.append("body-heuristic")
                    print(f"  📡 Captured [{', '.join(reason)}]: {url[:100]}")

        except Exception:
            pass

    @staticmethod
    def _body_looks_like_products(body) -> bool:
        """Heuristic: return True if the JSON body likely contains product data."""
        if not isinstance(body, dict):
            return False

        def _scan(obj, depth=0):
            if depth > 6:
                return False
            if isinstance(obj, list) and len(obj) >= 2:
                first = obj[0] if obj else {}
                if isinstance(first, dict):
                    keys = set(first.keys())
                    product_keys = {
                        # ASDA Algolia (ALL-CAPS)
                        "NAME", "PRICES", "ID", "BRAND",
                        # Generic providers
                        "name", "title", "displayName", "description",
                        "price", "priceInfo", "basePrice", "listPrice",
                        "gtin", "skuId", "itemId", "productId",
                    }
                    if keys & product_keys:
                        return True
            if isinstance(obj, dict):
                for v in obj.values():
                    if _scan(v, depth + 1):
                        return True
            elif isinstance(obj, list):
                for item in obj:
                    if _scan(item, depth + 1):
                        return True
            return False

        return _scan(body)

    def _write_debug(self, url: str, body) -> None:
        """Append a JSON response to the debug file (non-destructively)."""
        try:
            with open("asda_api_debug.json", "a", encoding="utf-8") as f:
                f.write(f"\n\n=== URL: {url} ===\n")
                json.dump(body, f, indent=2)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _random_delay(self, min_seconds: Optional[float] = None, max_seconds: Optional[float] = None):
        min_s = min_seconds if min_seconds is not None else self.MIN_DELAY
        max_s = max_seconds if max_seconds is not None else self.MAX_DELAY
        time.sleep(random.uniform(min_s, max_s))

    def _human_like_scroll(self, page: Page, steps: int = 4):
        """Scroll down in increments to trigger lazy-loaded API calls."""
        try:
            total_height = page.evaluate("document.body.scrollHeight") or 3000
            step_px = total_height // steps
            for i in range(1, steps + 1):
                page.evaluate(f"window.scrollTo(0, {step_px * i})")
                time.sleep(random.uniform(0.4, 0.8))
            # Scroll back up slightly (mimics human behaviour)
            page.evaluate("window.scrollTo(0, 300)")
            time.sleep(0.3)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Product extraction from API payloads
    # ------------------------------------------------------------------

    def _parse_api_products(self) -> List[Dict[str, Any]]:
        products: List[Dict[str, Any]] = []
        seen_gtins: set = set()

        for payload in self._api_responses:
            candidates = self._find_product_arrays(payload)
            for arr in candidates:
                for item in arr:
                    product = self._api_item_to_product(item)
                    if not product:
                        continue
                    if not (product.get("name") or product.get("gtin")):
                        continue
                    # Deduplicate
                    dedup_key = product.get("gtin") or product.get("name", "")
                    if dedup_key and dedup_key in seen_gtins:
                        continue
                    if dedup_key:
                        seen_gtins.add(dedup_key)
                    products.append(product)

        if products and self.debug:
            print(f"  📦 Extracted {len(products)} products from API responses")
        return products

    @staticmethod
    def _find_product_arrays(obj, depth: int = 0) -> List[List]:
        results: List[List] = []
        if depth > 10:
            return results
        if isinstance(obj, dict):
            for key in (
                # Algolia standard: hits array inside each result object
                "hits",
                # Generic / other provider keys
                "items", "products", "searchResults", "results",
                "productItems", "data", "uber", "shelf",
                "categories", "tiles", "entries",
            ):
                if key in obj and isinstance(obj[key], list) and obj[key]:
                    first = obj[key][0]
                    if isinstance(first, dict) and (
                        # ASDA Algolia uses ALL-CAPS field names
                        "ID" in first or "NAME" in first
                        # Generic / other providers
                        or "objectID" in first
                        or "id" in first or "itemId" in first
                        or "name" in first or "displayName" in first
                        or "title" in first or "skuId" in first
                        or "gtin" in first
                    ):
                        results.append(obj[key])
                    else:
                        # May be a list of Algolia result objects each containing hits
                        results.extend(AsdaPlaywrightScraper._find_product_arrays(obj[key], depth + 1))
            for v in obj.values():
                results.extend(AsdaPlaywrightScraper._find_product_arrays(v, depth + 1))
        elif isinstance(obj, list):
            for item in obj:
                results.extend(AsdaPlaywrightScraper._find_product_arrays(item, depth + 1))
        return results

    @staticmethod
    def _api_item_to_product(item: dict) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict):
            return None

        product: Dict[str, Any] = {}

        # ASDA's Algolia index does not expose real GTINs/EANs.
        # ID and CIN are internal ASDA product numbers — not suitable as GTINs
        # because they would cause false cross-retailer matches in the normalizer.
        # Leave gtin as None; fuzzy name matching handles ASDA deduplication.
        product["gtin"] = None

        # NAME is the product name; BRAND is the brand (e.g. "ASDA", "Anchor")
        name = (
            item.get("NAME", "") or item.get("name", "")
            or item.get("displayName", "") or item.get("title", "")
            or item.get("description", "")
        )
        brand = item.get("BRAND", "") or item.get("brandName", "") or item.get("brand", "")
        if brand and name and brand.lower() not in name.lower():
            name = f"{brand} {name}"
        product["name"] = name

        # PRICES.EN.PRICE        → current shelf price
        # PRICES.EN.WASPRICE     → previous price (for rollback/offer display)
        # PRICES.EN.PRICEPERUOMFORMATTED → formatted unit price e.g. "72.6p/LT"
        price_val = None
        unit_price_val = None
        was_price_val = None

        prices_obj = item.get("PRICES", {})
        if isinstance(prices_obj, dict):
            # ASDA Algolia always uses the "EN" locale sub-key
            en_prices = prices_obj.get("EN", prices_obj)
            if isinstance(en_prices, dict):
                price_val = en_prices.get("PRICE")
                unit_price_val = en_prices.get("PRICEPERUOMFORMATTED") or en_prices.get("PRICEPERUOM")
                was_price = en_prices.get("WASPRICE")
                # Only treat WASPRICE as a "was" price if it differs from current price
                if was_price and price_val and float(was_price) != float(price_val):
                    was_price_val = was_price

        # Fallback to generic lowercase price fields (other providers)
        if price_val is None:
            price_obj = item.get("price", {}) or item.get("priceInfo", {}) or {}
            if isinstance(price_obj, dict):
                price_val = (
                    price_obj.get("price") or price_obj.get("actual")
                    or price_obj.get("current") or price_obj.get("NOW")
                    or price_obj.get("now")
                )
                if not unit_price_val:
                    unit_price_val = price_obj.get("unitPrice") or price_obj.get("pricePerUnit")
                    uom = price_obj.get("unitOfMeasure", "")
                    if unit_price_val and uom:
                        unit_price_val = f"{unit_price_val}/{uom}"
            if price_val is None:
                price_val = item.get("basePrice") or item.get("currentPrice") or item.get("listPrice")

        if price_val is not None:
            product["price"] = str(price_val)
        if unit_price_val:
            product["unit_price"] = str(unit_price_val)
        if was_price_val:
            product["normal_price"] = str(was_price_val)

        # Require both a name and a non-zero price to consider this a valid product
        if not product.get("name"):
            return None
        price_float = float(product.get("price", 0) or 0)
        if price_float == 0:
            return None

        return product

    # ------------------------------------------------------------------
    # HTML fallback
    # ------------------------------------------------------------------

    def _parse_html_fallback(self, page: Page) -> List[Dict[str, Any]]:
        products: List[Dict[str, Any]] = []
        product_selectors = [
            '[data-auto-id="productTile"]',
            '[data-auto-id*="product"]',
            'article[class*="product"]',
            'li[class*="product"]',
            '[class*="productTile"]',
            '[class*="product-tile"]',
            '[class*="product"][class*="card"]',
            '[class*="product"][class*="item"]',
            ".co-product",
            'article[class*="card"]',
            '[data-testid*="product-tile"]:not([data-testid*="recall"])',
            '[data-testid*="product"]:not([data-testid*="recall"])',
        ]

        product_elements = None
        for selector in product_selectors:
            elements = page.locator(selector)
            count = elements.count()
            if count > 1:   # require at least 2 — single match is usually a wrapper
                product_elements = elements
                if self.debug:
                    print(f"  ✓ HTML fallback: selector '{selector}' ({count} elements)")
                break

        if not product_elements or product_elements.count() <= 1:
            if self.debug:
                print("  ⚠ HTML fallback: no product grid found")
            return products

        for i in range(min(product_elements.count(), 50)):
            try:
                tile = product_elements.nth(i)
                full_text = tile.inner_text()
                lines = [l.strip() for l in full_text.split("\n") if l.strip()]

                name = None
                for sel in (
                    '[data-auto-id="linkProductTitle"]',
                    ".co-product__title",
                    'a[href*="/product/"]',
                    "h2", "h3", "a",
                    '[class*="title"]',
                ):
                    try:
                        loc = tile.locator(sel).first
                        if loc.count() > 0:
                            name = loc.inner_text().strip()
                            if name:
                                break
                    except Exception:
                        continue

                if not name:
                    for line in lines:
                        if len(line) > 10 and "£" not in line and not line.replace(".", "").isdigit():
                            name = line
                            break

                price = None
                for line in lines:
                    m = re.search(r"£\d+\.?\d*", line)
                    if m:
                        price = m.group(0)
                        break

                unit_price = None
                for line in lines:
                    if re.search(r"(£\d+\.?\d*|[\d.]+p)\s*(\/|per)\s*\w+", line, re.I):
                        unit_price = line.strip("()")
                        break

                if name and price:
                    products.append({
                        "name": name,
                        "price": price.replace("£", ""),
                        "unit_price": unit_price,
                        "gtin": None,
                    })
            except Exception:
                continue

        return products

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _navigate_with_retry(self, page: Page, url: str) -> bool:
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                if self.debug:
                    print(f"  🌐 Navigating to {url} (attempt {attempt}/{self.MAX_RETRIES})")
                self._api_responses.clear()
                self._all_json_urls.clear()

                response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                status = response.status if response else 0

                if status in (403, 429):
                    wait = (3 ** attempt) + random.uniform(2, 5)
                    if self.debug:
                        print(f"  ⚠ HTTP {status} - backing off {wait:.1f}s")
                    time.sleep(wait)
                    continue

                # Wait for network to settle
                try:
                    page.wait_for_load_state("networkidle", timeout=25000)
                except Exception:
                    pass

                return True

            except Exception as exc:
                wait = (3 ** attempt) + random.uniform(2, 5)
                if self.debug:
                    print(f"  ⚠ Error: {exc} - retrying in {wait:.1f}s")
                time.sleep(wait)

        # Fallback: try using the search bar from the homepage
        if self.debug:
            print(f"  🔍 Trying search bar fallback...")
        try:
            # Extract search term from URL
            search_term = url.split("/search/")[-1] if "/search/" in url else ""
            if not search_term:
                return False

            search_input = page.locator(
                'input[type="search"], input[name="searchTerm"], '
                'input[placeholder*="Search"], input[id*="search"]'
            ).first
            if search_input.count() > 0:
                search_input.click()
                self._random_delay(0.5, 1)
                search_input.fill(search_term)
                self._random_delay(0.5, 1)
                search_input.press("Enter")
                self._random_delay(3, 5)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except:
                    pass
                if self.debug:
                    print(f"  ✓ Search bar navigation succeeded")
                return True
        except Exception as e:
            if self.debug:
                print(f"  ⚠ Search bar fallback failed: {e}")

        if self.debug:
            print(f"  ❌ All {self.MAX_RETRIES} attempts + fallback failed")
        return False

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def scrape_search_results(self, search_query: str, max_items: int = 100) -> List[Dict[str, Any]]:
        products: List[Dict[str, Any]] = []

        # Clear debug file at start (not mid-run)
        try:
            if os.path.exists("asda_api_debug.json"):
                os.remove("asda_api_debug.json")
        except Exception:
            pass

        with sync_playwright() as playwright:
            try:
                # Launch browser — cloud CDP or local
                from scrapers.browser import get_browser
                browser = get_browser(playwright, headless=self.headless)

                context = browser.new_context(
                    user_agent=random.choice(self.USER_AGENTS),
                    viewport={"width": 1920, "height": 1080},
                    locale="en-GB",
                    timezone_id="Europe/London",
                    color_scheme="light",
                    extra_http_headers={"Accept-Language": "en-GB,en;q=0.9"},
                )

                page = context.new_page()

                if STEALTH_AVAILABLE:
                    stealth = Stealth(
                        navigator_platform_override="MacIntel",
                        navigator_languages_override=("en-GB", "en"),
                    )
                    stealth.apply_stealth_sync(page)

                # Wire up interception BEFORE navigation
                page.on("response", self._on_response)

                print(f"🔄 Scraping Asda: {search_query}")

                # Visit homepage first to establish cookies/session — avoids
                # immediate 403 on search pages from cloud browser IPs.
                print(f"  🏠 Visiting homepage first...")
                try:
                    page.goto(self.base_url, wait_until="domcontentloaded", timeout=30000)
                    self._random_delay(2, 4)

                    # Dismiss cookie banner
                    for selector in (
                        "#onetrust-accept-btn-handler",
                        "button:has-text('Accept All Cookies')",
                        "button:has-text('Accept all cookies')",
                        "button:has-text('Accept All')",
                        "button:has-text('Accept')",
                    ):
                        try:
                            page.click(selector, timeout=3000)
                            self._random_delay(0.5, 1)
                            break
                        except Exception:
                            continue
                    print(f"  ✓ Homepage loaded")
                except Exception as e:
                    print(f"  ⚠ Homepage visit failed: {e}")

                search_url = f"{self.base_url}/search/{search_query}"
                success = self._navigate_with_retry(page, search_url)

                if not success:
                    if self.debug:
                        print("  ❌ Failed to load search page")
                    return products

                if self.debug:
                    print(f"  📄 Page title: {page.title()}")
                    print(f"  🔗 URL: {page.url}")

                # Give React time to fire its search API calls.
                # Scroll in steps — ASDA lazy-loads product cards which
                # triggers additional Algolia requests.
                self._random_delay(3, 5)
                self._human_like_scroll(page, steps=5)
                self._random_delay(2, 4)

                # Second scroll pass in case of paginated lazy loading
                self._human_like_scroll(page, steps=3)
                self._random_delay(1, 2)

                # Print all captured JSON URLs for diagnostics
                if self.debug and self._all_json_urls:
                    print(f"\n  📋 All JSON URLs captured ({len(self._all_json_urls)}):")
                    for u in self._all_json_urls:
                        print(f"     {u[:120]}")
                    print()

                # Strategy 1: API interception
                products = self._parse_api_products()

                # Strategy 2: HTML fallback
                if not products:
                    if self.debug:
                        print("  ℹ️ No API data captured, falling back to HTML parsing...")
                    products = self._parse_html_fallback(page)

                if self.debug:
                    try:
                        page.screenshot(path="asda_debug_screenshot.png")
                        print("  📸 Screenshot saved: asda_debug_screenshot.png")
                    except Exception:
                        pass

                products = products[:max_items]
                print(f"✓ Scraped {len(products)} products from Asda")

            except Exception as e:
                print(f"❌ Error scraping Asda: {e}")
            finally:
                try:
                    browser.close()
                except Exception:
                    pass

        return products


def main():
    """Example usage."""
    scraper = AsdaPlaywrightScraper(headless=False)
    products = scraper.scrape_search_results("milk", max_items=10)

    print(f"\nFound {len(products)} products:")
    for product in products:
        print(f"  - {product.get('name')}: £{product.get('price')}")


if __name__ == "__main__":
    main()
