"""
Sainsbury's scraper using Playwright with API response interception.
Instead of parsing HTML selectors (which break when the frontend changes),
this scraper intercepts JSON API responses that Sainsbury's React app fetches
internally — the same approach that works reliably for Asda and Tesco.
"""
from playwright.sync_api import sync_playwright, Page, Response as PWResponse
from typing import List, Dict, Any, Optional
import json
import time
import random
import re


class SainsburysPlaywrightScraper:
    """Scraper for Sainsbury's using Playwright + API interception."""

    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    ]

    # URL fragments that indicate product-related API endpoints
    PRODUCT_API_PATTERNS = (
        "/gol-services/product/",
        "/groceries-api/",
        "/gol-ui/api/",
        "/product-details/",
        "/search/",
        "SearchResults",
        "productsByCategory",
        "products",
    )

    # URL fragments to skip (non-product noise)
    SKIP_URL_FRAGMENTS = (
        "analytics",
        "tracking",
        "consent",
        "onetrust",
        "contentsquare",
        "citrusad",
        "geolocation",
        ".css",
        ".js",
        "fonts",
        "favicon",
        "images",
        "svg",
    )

    def __init__(self, headless: bool = True, fetch_gtin: bool = False):
        self.headless = headless
        self.fetch_gtin = fetch_gtin
        self.retailer = "sainsburys"
        self.base_url = "https://www.sainsburys.co.uk"
        self.debug = True
        self._api_responses: List[Dict] = []
        self._all_json_urls: List[str] = []

    # ------------------------------------------------------------------
    # Response interception
    # ------------------------------------------------------------------

    def _on_response(self, response: PWResponse) -> None:
        """Capture JSON payloads from Sainsbury's internal APIs."""
        url = response.url
        try:
            ct = response.headers.get("content-type", "")
            if "json" not in ct or response.status != 200:
                return

            # Skip known noise
            if any(skip in url.lower() for skip in self.SKIP_URL_FRAGMENTS):
                return

            body = response.json()
            self._all_json_urls.append(url)

            # Check if URL matches known product patterns
            url_match = any(p in url for p in self.PRODUCT_API_PATTERNS)

            # Heuristic: does the body look like product data?
            body_match = self._body_looks_like_products(body)

            if url_match or body_match:
                self._api_responses.append(body)
                if self.debug:
                    reason = []
                    if url_match:
                        reason.append("url-pattern")
                    if body_match:
                        reason.append("body-heuristic")
                    print(f"  📡 Captured [{', '.join(reason)}]: {url[:120]}")
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
                        "name", "title", "displayName", "description",
                        "price", "priceInfo", "retail_price", "unit_price",
                        "gtin", "ean", "skuId", "itemId", "productId",
                        "product_uid", "product_image_url",
                        "nectar_price", "base_price", "retail_price",
                    }
                    if len(keys & product_keys) >= 2:
                        return True
            if isinstance(obj, dict):
                for v in obj.values():
                    if _scan(v, depth + 1):
                        return True
            elif isinstance(obj, list):
                for item in obj[:5]:
                    if _scan(item, depth + 1):
                        return True
            return False

        return _scan(body)

    # ------------------------------------------------------------------
    # Product extraction from API payloads
    # ------------------------------------------------------------------

    def _parse_api_products(self, max_items: int) -> List[Dict[str, Any]]:
        """Parse all captured API responses into product dicts."""
        products: List[Dict[str, Any]] = []
        seen: set = set()

        for payload in self._api_responses:
            candidates = self._find_product_arrays(payload)
            for arr in candidates:
                for item in arr:
                    product = self._api_item_to_product(item)
                    if not product or not product.get("name"):
                        continue

                    dedup_key = product.get("gtin") or product["name"]
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    products.append(product)

                    if len(products) >= max_items:
                        return products

        if products and self.debug:
            print(f"  📦 Extracted {len(products)} products from API responses")
        return products

    def _find_product_arrays(self, obj, depth: int = 0) -> List[List]:
        """Recursively find arrays that look like product lists."""
        results: List[List] = []
        if depth > 10:
            return results

        if isinstance(obj, dict):
            # Check known keys
            for key in ("products", "items", "results", "searchResults",
                        "hits", "entries", "data", "product_items",
                        "productItems", "productLister"):
                if key in obj and isinstance(obj[key], list) and obj[key]:
                    first = obj[key][0]
                    if isinstance(first, dict) and self._looks_like_product(first):
                        results.append(obj[key])

            for v in obj.values():
                results.extend(self._find_product_arrays(v, depth + 1))

        elif isinstance(obj, list):
            if len(obj) >= 2 and isinstance(obj[0], dict) and self._looks_like_product(obj[0]):
                results.append(obj)
            for item in obj[:3]:
                if isinstance(item, dict):
                    results.extend(self._find_product_arrays(item, depth + 1))

        return results

    @staticmethod
    def _looks_like_product(item: dict) -> bool:
        """Check if a dict looks like a product."""
        keys = set(item.keys())
        indicators = {
            "name", "title", "displayName", "product_uid",
            "price", "retail_price", "unit_price",
            "gtin", "ean", "image", "product_image_url",
        }
        return len(keys & indicators) >= 2

    def _api_item_to_product(self, item: dict) -> Optional[Dict[str, Any]]:
        """Convert a single API item to our standard product dict."""
        if not isinstance(item, dict):
            return None

        # Name — try multiple keys
        name = (
            item.get("name")
            or item.get("title")
            or item.get("displayName")
            or item.get("product_name")
            or ""
        ).strip()
        if not name:
            return None

        # Price — try multiple structures
        price = self._extract_price(item)
        if not price or price <= 0:
            return None

        # Unit price
        unit_price = (
            item.get("unit_price")
            or item.get("unitPrice")
            or item.get("unitPriceNote")
            or item.get("price_per_unit")
            or None
        )
        if isinstance(unit_price, dict):
            unit_price = unit_price.get("label") or unit_price.get("value")

        # GTIN/EAN
        gtin = (
            item.get("gtin")
            or item.get("ean")
            or item.get("gtin13")
            or item.get("product_uid")
            or None
        )
        if gtin:
            gtin = str(gtin).strip()
            if not gtin.isdigit() or len(gtin) < 8:
                gtin = None

        # Nectar / member price
        nectar_price = self._extract_nectar_price(item)

        # Product URL
        url = item.get("url") or item.get("href") or item.get("full_url") or None
        if url and not url.startswith("http"):
            url = f"https://www.sainsburys.co.uk{url}"

        return {
            "name": name,
            "price": str(price),
            "unit_price": str(unit_price) if unit_price else None,
            "gtin": gtin,
            "url": url,
            "member_price": nectar_price,
            "is_clubcard_price": bool(nectar_price),
        }

    @staticmethod
    def _extract_price(item: dict) -> Optional[float]:
        """Extract the shelf price from various API response formats."""
        # Direct price field
        for key in ("retail_price", "price", "base_price", "listPrice"):
            val = item.get(key)
            if val is not None:
                if isinstance(val, (int, float)) and val > 0:
                    return float(val)
                if isinstance(val, str):
                    m = re.search(r'[\d.]+', val.replace("£", ""))
                    if m:
                        return float(m.group())

        # Nested price object
        price_info = item.get("priceInfo") or item.get("price_info") or item.get("prices") or {}
        if isinstance(price_info, dict):
            for key in ("price", "now", "retail", "selling_price", "actual_price"):
                val = price_info.get(key)
                if isinstance(val, (int, float)) and val > 0:
                    return float(val)
                if isinstance(val, str):
                    m = re.search(r'[\d.]+', val.replace("£", ""))
                    if m:
                        return float(m.group())

        return None

    @staticmethod
    def _extract_nectar_price(item: dict) -> Optional[str]:
        """Extract Nectar/member price if present."""
        for key in ("nectar_price", "nectarPrice", "member_price",
                     "loyalty_price", "promotionPrice"):
            val = item.get(key)
            if val is not None:
                if isinstance(val, (int, float)) and val > 0:
                    return str(val)
                if isinstance(val, str):
                    m = re.search(r'[\d.]+', val.replace("£", ""))
                    if m:
                        return m.group()

        # Check nested promotions
        promos = item.get("promotions") or item.get("offers") or []
        if isinstance(promos, list):
            for p in promos:
                if isinstance(p, dict):
                    desc = str(p.get("description", "") or p.get("text", "")).lower()
                    if "nectar" in desc:
                        m = re.search(r'£\s*([\d.]+)', desc)
                        if m:
                            return m.group(1)

        return None

    # ------------------------------------------------------------------
    # HTML fallback (kept as a backup)
    # ------------------------------------------------------------------

    def _extract_products_html(self, page: Page, max_items: int) -> List[Dict[str, Any]]:
        """Fallback: parse product data from HTML if API interception found nothing."""
        products = []
        selectors = [
            '[data-testid="product-tile"]',
            'li[data-testid="product-tile"]',
            '[data-testid="search-product-tile"]',
            'li[data-testid*="product"]',
            '[class*="pt-grid__item"]',
            '[class*="productTile"]',
            '[class*="product-tile"]',
            '[class*="ProductCard"]',
            'article[class*="product"]',
        ]

        elements = None
        for sel in selectors:
            loc = page.locator(sel)
            if loc.count() > 0:
                elements = loc
                if self.debug:
                    print(f"  ✓ HTML fallback using '{sel}' ({loc.count()} elements)")
                break

        if not elements or elements.count() == 0:
            return products

        count = min(elements.count(), max_items)
        for i in range(count):
            try:
                el = elements.nth(i)
                text = el.inner_text()
                lines = [l.strip() for l in text.split("\n") if l.strip()]

                name = None
                price = None

                # Name: first line > 10 chars that isn't a price
                for line in lines:
                    if len(line) > 10 and "£" not in line and not line.isdigit():
                        name = line
                        break

                # Price: first line with £
                for line in lines:
                    m = re.search(r"£(\d+\.?\d*)", line)
                    if m:
                        price = m.group(0)
                        break

                if name and price:
                    products.append({"name": name.strip(), "price": price.strip()})
            except Exception:
                continue

        return products

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _configure_stealth(self, page: Page):
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
            window.chrome = { runtime: {} };
            const origQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (p) => (
                p.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    origQuery(p)
            );
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-GB','en'] });
        """)

    def _random_delay(self, min_s: float = 1.0, max_s: float = 3.0):
        time.sleep(random.uniform(min_s, max_s))

    def _human_like_scroll(self, page: Page, steps: int = 4):
        try:
            total = page.evaluate("document.body.scrollHeight") or 3000
            step_px = total // steps
            for i in range(1, steps + 1):
                page.evaluate(f"window.scrollTo(0, {step_px * i})")
                time.sleep(random.uniform(0.3, 0.7))
            page.evaluate("window.scrollTo(0, 300)")
            time.sleep(0.3)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def scrape_search_results(self, search_query: str, max_items: int = 100) -> List[Dict[str, Any]]:
        products: List[Dict[str, Any]] = []

        # Clear state
        self._api_responses.clear()
        self._all_json_urls.clear()

        with sync_playwright() as playwright:
            from scrapers.browser import get_browser, create_context
            browser = get_browser(playwright, headless=self.headless)

            context = create_context(
                browser,
                user_agent=random.choice(self.USER_AGENTS),
                viewport={"width": 1920, "height": 1080},
                locale="en-GB",
                timezone_id="Europe/London",
                extra_http_headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-GB,en;q=0.9",
                    "DNT": "1",
                    "Cache-Control": "max-age=0",
                },
            )

            page = context.new_page()
            self._configure_stealth(page)

            # Wire up API interception BEFORE navigation
            page.on("response", self._on_response)

            try:
                print(f"🔄 Scraping Sainsbury's: {search_query}")

                # Visit homepage first
                print(f"🏠 First visiting homepage...")
                page.goto(self.base_url, wait_until="domcontentloaded", timeout=30000)
                self._random_delay(2, 4)

                # Dismiss cookies
                try:
                    for btn_sel in (
                        "#onetrust-accept-btn-handler",
                        'button:has-text("Accept All")',
                        'button:has-text("Accept")',
                    ):
                        btn = page.locator(btn_sel).first
                        if btn.count() > 0:
                            btn.click()
                            self._random_delay(1, 2)
                            break
                except Exception:
                    pass

                # Navigate to search
                search_url = f"{self.base_url}/gol-ui/SearchResults/{search_query}"
                print(f"🌐 Searching: {search_url}")

                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                self._random_delay(3, 5)

                if self.debug:
                    print(f"📄 Page title: {page.title()}")
                    print(f"🔗 Current URL: {page.url}")

                # Scroll to trigger lazy-loaded API calls
                self._human_like_scroll(page, steps=5)
                self._random_delay(2, 3)

                # Second scroll pass
                self._human_like_scroll(page, steps=3)
                self._random_delay(1, 2)

                # Log captured URLs
                if self.debug and self._all_json_urls:
                    print(f"\n  📋 All JSON URLs captured ({len(self._all_json_urls)}):")
                    for u in self._all_json_urls:
                        print(f"     {u[:120]}")

                # Strategy 1: Parse API responses
                products = self._parse_api_products(max_items)

                # Strategy 2: HTML fallback
                if not products:
                    if self.debug:
                        print("  ℹ️ No API data, trying HTML fallback...")
                    products = self._extract_products_html(page, max_items)

                # Strategy 3: If still nothing, dump page info for debugging
                if not products and self.debug:
                    print("  ⚠ No products found via API or HTML")
                    try:
                        page.screenshot(path="sainsburys_debug_screenshot.png")
                        print("  📸 Debug screenshot saved")
                    except Exception:
                        pass

                    # Dump any captured JSON for analysis
                    if self._api_responses:
                        try:
                            with open("sainsburys_api_debug.json", "w") as f:
                                json.dump(self._api_responses, f, indent=2)
                            print("  📝 API responses dumped to sainsburys_api_debug.json")
                        except Exception:
                            pass

                print(f"✓ Scraped {len(products)} products from Sainsbury's")

            except Exception as e:
                print(f"✗ Error scraping Sainsbury's: {e}")

            finally:
                browser.close()

        return products


def main():
    scraper = SainsburysPlaywrightScraper(headless=False)
    products = scraper.scrape_search_results("milk", max_items=20)
    print(f"\nFound {len(products)} products:")
    for p in products[:5]:
        print(f"  - {p.get('name')}: {p.get('price')}")


if __name__ == "__main__":
    main()
