"""
Waitrose scraper using Playwright with API response interception.
Captures GraphQL and REST JSON responses from Waitrose's React frontend.
"""
from playwright.sync_api import sync_playwright, Page, Response as PWResponse
from typing import List, Dict, Any, Optional
import json
import time
import random
import re


class WaitrosePlaywrightScraper:
    """Scraper for Waitrose using Playwright + API interception."""

    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    ]

    PRODUCT_API_PATTERNS = (
        "graphql",
        "/api/content-orchestrator/",
        "/api/custsearch/",
        "/ecom/shop/search",
        "searchProduct",
        "productsInResultset",
    )

    SKIP_URL_FRAGMENTS = (
        "analytics", "tracking", "consent", "onetrust", "geolocation",
        "trolley", "basket", "slot", "delivery",
        ".css", ".js", "fonts", "favicon", "images", "svg",
        "contentsquare", "citrusad",
    )

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.retailer = "waitrose"
        self.base_url = "https://www.waitrose.com"
        self.debug = True
        self._api_responses: List[Dict] = []
        self._all_json_urls: List[str] = []

    # ------------------------------------------------------------------
    # Response interception
    # ------------------------------------------------------------------

    def _on_response(self, response: PWResponse) -> None:
        url = response.url
        try:
            ct = response.headers.get("content-type", "")
            if "json" not in ct or response.status != 200:
                return
            if any(skip in url.lower() for skip in self.SKIP_URL_FRAGMENTS):
                return

            body = response.json()
            self._all_json_urls.append(url)

            url_match = any(p in url for p in self.PRODUCT_API_PATTERNS)
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
                        "name", "title", "displayName", "searchProduct",
                        "price", "currentSaleUnitPrice", "typicalWeight",
                        "lineNumber", "productId", "gtin", "ean",
                        "productImageUrl", "thumbnail", "brandName",
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
        results: List[List] = []
        if depth > 10:
            return results

        if isinstance(obj, dict):
            for key in ("products", "items", "results", "searchResults",
                        "componentsAndProducts", "productsInResultset",
                        "hits", "data", "fops", "entries", "searchProduct"):
                if key in obj and isinstance(obj[key], list) and obj[key]:
                    first = obj[key][0]
                    if isinstance(first, dict) and self._looks_like_product(first):
                        results.append(obj[key])
                    # Waitrose sometimes nests: { searchProduct: [{searchProduct: {...}}] }
                    elif isinstance(first, dict) and "searchProduct" in first:
                        unwrapped = [i["searchProduct"] for i in obj[key] if "searchProduct" in i]
                        if unwrapped:
                            results.append(unwrapped)
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
        keys = set(item.keys())
        indicators = {
            "name", "title", "displayName", "lineNumber",
            "price", "currentSaleUnitPrice", "typicalWeight",
            "gtin", "ean", "productImageUrl", "thumbnail",
        }
        return len(keys & indicators) >= 2

    def _api_item_to_product(self, item: dict) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict):
            return None

        # Unwrap nested searchProduct
        if "searchProduct" in item and isinstance(item["searchProduct"], dict):
            item = item["searchProduct"]

        name = (
            item.get("name") or item.get("title") or
            item.get("displayName") or ""
        ).strip()
        if not name:
            return None

        price = self._extract_price(item)
        if not price or price <= 0:
            return None

        unit_price = (
            item.get("unitPrice") or item.get("unit_price") or
            item.get("pricePerUnit") or None
        )
        if isinstance(unit_price, dict):
            unit_price = unit_price.get("label") or unit_price.get("value")

        gtin = item.get("gtin") or item.get("ean") or item.get("lineNumber") or None
        if gtin:
            gtin = str(gtin).strip()
            if not gtin.isdigit() or len(gtin) < 8:
                gtin = None

        member_price = self._extract_member_price(item)

        return {
            "name": name,
            "price": str(price),
            "unit_price": str(unit_price) if unit_price else None,
            "gtin": gtin,
            "member_price": member_price,
            "is_clubcard_price": bool(member_price),
        }

    @staticmethod
    def _extract_price(item: dict) -> Optional[float]:
        for key in ("currentSaleUnitPrice", "price", "retail_price", "displayPrice"):
            val = item.get(key)
            if isinstance(val, (int, float)) and val > 0:
                return float(val)
            if isinstance(val, str):
                m = re.search(r'[\d.]+', val.replace("£", ""))
                if m:
                    return float(m.group())

        price_info = item.get("priceInfo") or item.get("prices") or {}
        if isinstance(price_info, dict):
            for key in ("price", "now", "selling_price"):
                val = price_info.get(key)
                if isinstance(val, (int, float)) and val > 0:
                    return float(val)
        return None

    @staticmethod
    def _extract_member_price(item: dict) -> Optional[str]:
        for key in ("myWaitrosePrice", "memberPrice", "member_price", "loyaltyPrice"):
            val = item.get(key)
            if isinstance(val, (int, float)) and val > 0:
                return str(val)
            if isinstance(val, str):
                m = re.search(r'[\d.]+', val.replace("£", ""))
                if m:
                    return m.group()

        promos = item.get("promotions") or item.get("offers") or []
        if isinstance(promos, list):
            for p in promos:
                if isinstance(p, dict):
                    desc = str(p.get("description", "") or p.get("text", "")).lower()
                    if "mywaitrose" in desc or "my waitrose" in desc:
                        m = re.search(r'£\s*([\d.]+)', desc)
                        if m:
                            return m.group(1)
        return None

    # ------------------------------------------------------------------
    # HTML fallback
    # ------------------------------------------------------------------

    def _parse_html_fallback(self, page: Page, max_items: int) -> List[Dict[str, Any]]:
        products = []
        selectors = [
            '[class*="product-pod"]',
            '[data-testid="product-pod"]',
            '[class*="productName"]',
            '[class*="product-tile"]',
            'article[class*="product"]',
            'li[class*="product"]',
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
                for line in lines:
                    if len(line) > 10 and "£" not in line and not line.isdigit():
                        name = line
                        break
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
                extra_http_headers={"Accept-Language": "en-GB,en;q=0.9"},
            )

            page = context.new_page()
            page.on("response", self._on_response)

            try:
                print(f"🔄 Scraping Waitrose: {search_query}")
                print(f"  🏠 Visiting homepage first...")
                page.goto(self.base_url, wait_until="domcontentloaded", timeout=60000)
                self._random_delay(2, 4)

                # Dismiss cookies
                for btn_sel in (
                    "#onetrust-accept-btn-handler",
                    'button:has-text("Accept All")',
                    'button:has-text("Accept all cookies")',
                    'button:has-text("Accept")',
                ):
                    try:
                        btn = page.locator(btn_sel).first
                        if btn.count() > 0:
                            btn.click()
                            self._random_delay(0.5, 1)
                            break
                    except Exception:
                        continue

                # Use search bar — more reliable than direct URL
                print(f"  🔍 Using search bar for: {search_query}")
                search_submitted = False
                for input_sel in (
                    'input[name="search"]',
                    'input[type="search"]',
                    'input[placeholder*="Search"]',
                    'input[placeholder*="search"]',
                    'input[id*="search"]',
                    'input[aria-label*="Search"]',
                ):
                    try:
                        search_input = page.locator(input_sel).first
                        if search_input.count() > 0:
                            search_input.click()
                            self._random_delay(0.5, 1)
                            search_input.fill(search_query)
                            self._random_delay(0.5, 1)
                            search_input.press("Enter")
                            search_submitted = True
                            if self.debug:
                                print(f"  ✓ Search submitted via '{input_sel}'")
                            break
                    except Exception:
                        continue

                if not search_submitted:
                    # Fallback: direct URL
                    print("  ⚠ Search bar not found, trying direct URL...")
                    page.goto(
                        f"{self.base_url}/ecom/shop/search?searchTerm={search_query}",
                        wait_until="domcontentloaded", timeout=30000,
                    )

                self._random_delay(3, 5)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass

                if self.debug:
                    print(f"  📄 Page title: {page.title()}")
                    print(f"  🔗 URL: {page.url}")

                self._human_like_scroll(page, steps=5)
                self._random_delay(2, 3)
                self._human_like_scroll(page, steps=3)
                self._random_delay(1, 2)

                if self.debug and self._all_json_urls:
                    print(f"\n  📋 All JSON URLs captured ({len(self._all_json_urls)}):")
                    for u in self._all_json_urls:
                        print(f"     {u[:120]}")

                products = self._parse_api_products(max_items)

                if not products:
                    if self.debug:
                        print("  ℹ️ No API data, trying HTML fallback...")
                    products = self._parse_html_fallback(page, max_items)

                if not products and self.debug:
                    print("  ⚠ No products found via API or HTML")
                    try:
                        page.screenshot(path="waitrose_debug_screenshot.png")
                        print("  📸 Debug screenshot saved")
                    except Exception:
                        pass

                print(f"✓ Scraped {len(products)} products from Waitrose")

            except Exception as e:
                print(f"✗ Error scraping Waitrose: {e}")

            finally:
                browser.close()

        return products


def main():
    scraper = WaitrosePlaywrightScraper(headless=False)
    products = scraper.scrape_search_results("milk", max_items=20)
    print(f"\nFound {len(products)} products:")
    for p in products[:5]:
        print(f"  - {p.get('name')}: {p.get('price')}")


if __name__ == "__main__":
    main()
