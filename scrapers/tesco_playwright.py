"""
Tesco scraper using Playwright with API interception technique.
Uses the advanced method from the Tesco Bakery Scraper:
- API interception from xapi.tesco.com for structured JSON data
- Real Chrome browser (channel="chrome") for genuine fingerprint
- Headed mode as default for better anti-bot bypass
- Retry with exponential backoff
- Clubcard price and normal price extraction
"""
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, Response as PWResponse
try:
    from playwright_stealth import Stealth
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False
from typing import List, Dict, Any, Optional
import time
import random
import re
from datetime import datetime, timezone


class TescoPlaywrightScraper:
    """Advanced Tesco scraper using API interception."""
    
    # Realistic Chrome user agents matching the Chrome version Playwright uses
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
    
    def __init__(self, headless: bool = True):  # Headless by default for speed
        """
        Initialize the Tesco Playwright scraper with API interception.
        
        Args:
            headless: Whether to run browser in headless mode (True = faster, False = better bypass)
        """
        self.headless = headless
        self.retailer = "tesco"
        self.base_url = "https://www.tesco.com"
        self.debug = True
        
        # Buffer for intercepted API responses
        self._api_responses: List[Dict] = []
    
    def _on_response(self, response: PWResponse) -> None:
        """
        Callback for every network response. Captures JSON payloads from
        Tesco's internal APIs (xapi.tesco.com, etc.) for structured data.
        """
        url = response.url
        # Tesco's React app fetches data from xapi.tesco.com and other endpoints
        api_patterns = (
            "xapi.tesco.com",
            "/api/",
            "/resources",
            "productsByCategory",
            "product-list",
            "/search/",
            "graphql",
        )
        
        if any(p in url for p in api_patterns):
            try:
                ct = response.headers.get("content-type", "")
                if "json" in ct and response.status == 200:
                    body = response.json()
                    self._api_responses.append(body)
                    if self.debug:
                        print(f"  📡 Intercepted API response from {url[:80]}...")
                        # Debug: Save API responses to file for analysis
                        if "xapi.tesco.com" in url or "product" in url.lower():
                            try:
                                import json
                                with open('tesco_api_debug.json', 'a', encoding='utf-8') as f:
                                    f.write(f"\n\n=== URL: {url} ===\n")
                                    json.dump(body, f, indent=2)
                            except Exception:
                                pass
            except Exception:
                pass  # Not every matching URL is valid JSON
    
    def _random_delay(self, min_seconds: Optional[float] = None, max_seconds: Optional[float] = None):
        """Add random delay to mimic human behavior."""
        min_s = min_seconds if min_seconds is not None else self.MIN_DELAY
        max_s = max_seconds if max_seconds is not None else self.MAX_DELAY
        time.sleep(random.uniform(min_s, max_s))
    
    def _human_like_scroll(self, page: Page):
        """Simulate human-like scrolling behavior."""
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)
        except Exception:
            pass
    
    def _parse_api_products(self) -> List[Dict[str, Any]]:
        """
        Extract products from intercepted API JSON responses.
        Tesco's internal API nests product lists in various shapes.
        """
        products: List[Dict[str, Any]] = []
        
        for payload in self._api_responses:
            # Walk into nested structures looking for product arrays
            candidates = self._find_product_arrays(payload)
            for arr in candidates:
                for item in arr:
                    product = self._api_item_to_product(item)
                    if product and (product.get('name') or product.get('gtin')):
                        products.append(product)
        
        if products and self.debug:
            print(f"  📦 Extracted {len(products)} products from API responses")
        
        return products
    
    @staticmethod
    def _find_product_arrays(obj, depth: int = 0) -> List[List]:
        """Recursively search a JSON object for arrays that look like product lists."""
        results: List[List] = []
        if depth > 8:
            return results
        
        if isinstance(obj, dict):
            # Check common keys Tesco uses
            for key in ("products", "productItems", "results", "items", "data"):
                if key in obj and isinstance(obj[key], list) and obj[key]:
                    first = obj[key][0]
                    if isinstance(first, dict) and (
                        "id" in first or "productId" in first or 
                        "title" in first or "name" in first
                    ):
                        results.append(obj[key])
            # Recurse into all dict values
            for v in obj.values():
                results.extend(TescoPlaywrightScraper._find_product_arrays(v, depth + 1))
        
        elif isinstance(obj, list):
            for item in obj:
                results.extend(TescoPlaywrightScraper._find_product_arrays(item, depth + 1))
        
        return results
    
    @staticmethod
    def _api_item_to_product(item: dict) -> Optional[Dict[str, Any]]:
        """Convert one API product dict into our product format."""
        if not isinstance(item, dict):
            return None
        
        product = {}
        
        # Product ID / GTIN
        product['gtin'] = str(
            item.get("gtin", "") or
            item.get("id", "") or 
            item.get("productId", "") or 
            item.get("tpnb", "") or 
            item.get("tpnc", "")
        ) or None
        
        # Name
        product['name'] = (
            item.get("title", "") or 
            item.get("name", "") or 
            item.get("description", "")
        )
        
        # Price extraction - handle nested sellers.results structure
        price_obj = None
        
        # Try sellers.results[0].price first (common in xapi responses)
        sellers = item.get("sellers", {})
        if isinstance(sellers, dict) and "results" in sellers:
            results = sellers.get("results", [])
            if results and isinstance(results, list) and len(results) > 0:
                price_obj = results[0].get("price", {})
        
        # Fallback to direct price field
        if not price_obj:
            price_obj = item.get("price", item.get("retailPrice", {}))
        
        # Extract price, unitPrice, and unitOfMeasure
        if isinstance(price_obj, dict):
            # Regular price
            product['price'] = str(price_obj.get("actual", price_obj.get("price", "")))
            
            # Unit price with unit of measure
            unit_price_val = price_obj.get("unitPrice")
            unit_of_measure = price_obj.get("unitOfMeasure", "")
            
            if unit_price_val and unit_of_measure:
                # Only store unit price when the unit label is also present;
                # a bare number without a unit is meaningless in comparisons.
                product['unit_price'] = f"{unit_price_val}/{unit_of_measure}"
        elif price_obj:
            product['price'] = str(price_obj)
        
        # Clubcard price — stored separately as member_price.
        # price stays as the regular shelf price so comparisons are fair.

        # Helper: try to parse a Clubcard numeric value from a promotions list.
        def _extract_clubcard_from_promotions(promos) -> Optional[str]:
            for promo in (promos or []):
                if not isinstance(promo, dict):
                    continue
                attrs = promo.get("attributes") or []
                promo_type = (promo.get("type") or promo.get("promotionType") or "").lower()
                is_clubcard = "CLUBCARD_PRICING" in attrs or "clubcard" in promo_type
                if not is_clubcard:
                    continue
                # The numeric Clubcard price is in the description, e.g. "£3.00 Clubcard Price".
                # price.afterDiscount mirrors the regular price in xapi responses — don't use it.
                desc = promo.get("description") or ""
                # Skip multi-buy bundles ("Any 2 for £3.50") — per-unit price is indeterminate.
                if re.search(r'\d+\s+for\b', desc, re.IGNORECASE):
                    continue
                m = re.search(r'£\s*(\d+\.?\d*)', desc)
                if m:
                    return m.group(1)
                # Fallback to explicit price fields (other API shapes)
                val = promo.get("offerPrice") or promo.get("price")
                if isinstance(val, dict):
                    val = val.get("afterDiscount") or val.get("price")
                if val is not None:
                    return str(val)
            return None

        # Priority 1: top-level clubcardPrice / promotionalPrice field
        clubcard_raw = item.get("clubcardPrice") or item.get("promotionalPrice") or ""

        # Priority 2: promotions nested inside sellers.results[0] (xapi.tesco.com GraphQL shape)
        if not clubcard_raw:
            for seller_result in (sellers.get("results", []) if isinstance(sellers, dict) else []):
                if not isinstance(seller_result, dict):
                    continue
                found = _extract_clubcard_from_promotions(seller_result.get("promotions"))
                if found:
                    clubcard_raw = found
                    break

        # Priority 3: promotions at item root (other endpoint shapes)
        if not clubcard_raw:
            clubcard_raw = _extract_clubcard_from_promotions(item.get("promotions")) or ""

        member_price_val = None
        if isinstance(clubcard_raw, dict):
            member_price_val = clubcard_raw.get("price", clubcard_raw.get("actual"))
        elif clubcard_raw:
            member_price_val = clubcard_raw

        if member_price_val:
            product['member_price'] = str(member_price_val)

        product['is_clubcard_price'] = bool(member_price_val)
        
        # No bare-number unit price fallback — without a unit label it's meaningless
        
        return product if product.get('name') or product.get('gtin') else None
    
    def _parse_html_fallback(self, page: Page) -> List[Dict[str, Any]]:
        """
        Fallback: Extract products from rendered HTML if API interception failed.
        Uses selectors similar to the Tesco Bakery Scraper.
        """
        import re
        products: List[Dict[str, Any]] = []
        
        try:
            # Find product tiles (Tesco uses verticalTile/horizontalTile classes)
            product_selectors = [
                '[class*="verticalTile"]',
                '[class*="horizontalTile"]',
                '[class*="product-tile"]',
                'a[href*="/products/"]'
            ]
            
            product_elements = None
            for selector in product_selectors:
                elements = page.locator(selector)
                if elements.count() > 0:
                    product_elements = elements
                    if self.debug:
                        print(f"  ✓ HTML fallback: Using selector '{selector}' ({elements.count()} elements)")
                    break
            
            if not product_elements or product_elements.count() == 0:
                return products
            
            for i in range(min(product_elements.count(), 50)):
                try:
                    tile = product_elements.nth(i)
                    
                    # Name & URL
                    name = None
                    gtin = None
                    link = tile.locator('a[class*="titleLink"], a[href*="/products/"]').first
                    if link.count() > 0:
                        name = link.inner_text().strip()
                        href = link.get_attribute('href') or ''
                        m = re.search(r'/products/(\d+)', href)
                        if m:
                            gtin = m.group(1)
                    
                    if not name:
                        continue
                    
                    # Regular price
                    price = None
                    price_elem = tile.locator('p[class*="priceText"], [class*="price"]').first
                    if price_elem.count() > 0:
                        price_text = price_elem.inner_text().strip()
                        price_match = re.search(r'£[\d.]+', price_text)
                        if price_match:
                            price = price_match.group(0)
                    
                    # Clubcard price
                    clubcard_price = None
                    is_clubcard = False
                    club_elem = tile.locator('p[class*="value-bar"], p[class*="contentText"]').first
                    if club_elem.count() > 0:
                        club_text = club_elem.inner_text().strip()
                        if "clubcard" in club_text.lower():
                            club_match = re.search(r'£[\d.]+', club_text)
                            if club_match:
                                clubcard_price = club_match.group(0)
                                is_clubcard = True
                    
                    # Unit price (often in parentheses like "(£0.73/litre)")
                    unit_price = None
                    
                    # First try specific selectors
                    unit_selectors = [
                        'p[class*="subText"]',
                        'p[class*="subtext"]',  
                        'span[class*="subText"]',
                        'p[class*="unit-price"]',
                        'p[class*="pricePerUnit"]',
                        '[class*="unitPrice"]',
                        '[class*="weight"]',
                        'span[class*="unit"]',
                        'p:has-text("/")',
                        'span:has-text("/")'
                    ]
                    
                    for sel in unit_selectors:
                        try:
                            unit_elem = tile.locator(sel).first
                            if unit_elem.count() > 0:
                                unit_text = unit_elem.inner_text().strip().strip('()')
                                # Check if it contains a price-like pattern
                                if ('£' in unit_text or '/' in unit_text or 'per' in unit_text.lower()) and len(unit_text) < 50:
                                    unit_price = unit_text
                                    break
                        except Exception:
                            continue
                    
                    # Fallback: Search all text in the tile for unit price pattern
                    if not unit_price:
                        try:
                            all_text = tile.inner_text()
                            # Pattern: (£X.XX/unit) or £X.XX/unit or X.XXp/unit
                            unit_match = re.search(r'\(?([£\d.]+\s*(?:p|£)?\s*/\s*\w+)\)?', all_text)
                            if unit_match:
                                unit_price = unit_match.group(1).strip('()')
                        except Exception:
                            pass
                    
                    if name and (price or clubcard_price):
                        product = {
                            'name': name,
                            'gtin': gtin,
                            'is_clubcard_price': is_clubcard,
                            # Regular shelf price always goes in 'price'.
                            # Clubcard price goes in 'member_price' so that
                            # effective_price() and savings logic work correctly.
                            'price': price.replace('£', '') if price else (
                                clubcard_price.replace('£', '') if clubcard_price else None
                            ),
                            'member_price': clubcard_price.replace('£', '') if is_clubcard and clubcard_price else None,
                            'normal_price': None,
                            'unit_price': unit_price,
                        }
                        products.append(product)
                
                except Exception as e:
                    if self.debug:
                        print(f"  ⚠ Error parsing tile {i}: {e}")
                    continue
        
        except Exception as e:
            if self.debug:
                print(f"  ⚠ HTML fallback error: {e}")
        
        return products
    
    def _navigate_with_retry(self, page: Page, url: str) -> bool:
        """
        Navigate to URL with retry + exponential backoff.
        Returns True on success, False on failure.
        """
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                if self.debug:
                    print(f"  🌐 Navigating to {url} (attempt {attempt}/{self.MAX_RETRIES})")
                
                # Clear API response buffer
                self._api_responses.clear()
                
                response = page.goto(url, wait_until='domcontentloaded', timeout=45000)
                status = response.status if response else 0
                
                if status in (403, 429):
                    wait = (2 ** attempt) + random.uniform(1, 3)
                    if self.debug:
                        print(f"  ⚠ HTTP {status} - backing off {wait:.1f}s")
                    time.sleep(wait)
                    continue
                
                # Give React app time to render
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                
                # Dismiss cookie banner
                for selector in (
                    "button:has-text('Accept all cookies')",
                    "button:has-text('Accept All Cookies')",
                    "button#onetrust-accept-btn-handler",
                ):
                    try:
                        page.click(selector, timeout=2000)
                        time.sleep(0.5)
                        break
                    except Exception:
                        continue
                
                # Scroll to trigger lazy-loaded content
                self._human_like_scroll(page)
                
                return True
            
            except Exception as exc:
                wait = (2 ** attempt) + random.uniform(1, 3)
                if self.debug:
                    print(f"  ⚠ Error: {exc} - retrying in {wait:.1f}s")
                time.sleep(wait)
        
        if self.debug:
            print(f"  ❌ All {self.MAX_RETRIES} attempts failed")
        return False
    
    def scrape_search_results(self, search_query: str, max_items: int = 100) -> List[Dict[str, Any]]:
        """
        Scrape Tesco search results using API interception technique.
        
        Args:
            search_query: Search term (e.g., "milk", "bread")
            max_items: Maximum number of products to scrape
            
        Returns:
            List of product dictionaries with Clubcard price support
        """
        products = []
        
        with sync_playwright() as playwright:
            try:
                # Launch browser — cloud CDP or local
                from scrapers.browser import get_browser, create_context
                browser = get_browser(playwright, headless=self.headless)

                # Create context with realistic settings + proxy
                context = create_context(browser,
                    user_agent=random.choice(self.USER_AGENTS),
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-GB',
                    timezone_id='Europe/London',
                    color_scheme='light',
                    extra_http_headers={
                        'Accept-Language': 'en-GB,en;q=0.9',
                    },
                )
                
                page = context.new_page()
                
                # Apply playwright-stealth patches
                if STEALTH_AVAILABLE:
                    stealth = Stealth(
                        navigator_platform_override="MacIntel",
                        navigator_languages_override=("en-GB", "en"),
                    )
                    stealth.apply_stealth_sync(page)
                
                # Set up API response interception
                page.on("response", self._on_response)
                
                print(f"🔄 Scraping Tesco: {search_query}")
                
                # Navigate to search page with retry
                search_url = f"{self.base_url}/groceries/en-GB/search?query={search_query}"
                success = self._navigate_with_retry(page, search_url)
                
                if not success:
                    if self.debug:
                        print("  ❌ Failed to load search page")
                    return products
                
                if self.debug:
                    print(f"  📄 Page title: {page.title()}")
                
                # Wait for the main xapi product response to arrive.
                # Scroll triggers additional lazy-load API calls.
                self._random_delay(2, 3)
                self._human_like_scroll(page)
                self._random_delay(1, 2)

                # Strategy 1: Parse intercepted API responses
                products = self._parse_api_products()

                # The xapi GraphQL endpoint sometimes returns trending/recommended
                # products instead of (or alongside) actual search results.
                # Filter to items whose name contains at least one query word.
                # If NONE match, the API payload is off-topic — discard it and
                # let the HTML fallback read the correct search result DOM.
                if products and search_query:
                    query_words = [w for w in search_query.lower().split() if len(w) > 2]
                    if query_words:
                        relevant = [
                            p for p in products
                            if any(w in (p.get('name') or '').lower() for w in query_words)
                        ]
                        if relevant:
                            if self.debug and len(relevant) < len(products):
                                print(f"  🔎 Query filter: kept {len(relevant)}/{len(products)} "
                                      f"products matching '{search_query}'")
                            products = relevant
                        else:
                            # Zero matches — API returned off-topic content entirely.
                            if self.debug:
                                print(f"  ⚠️ API results don't match '{search_query}' "
                                      f"({len(products)} products, none relevant) — "
                                      f"discarding, will use HTML fallback")
                            products = []

                # Strategy 2: Fall back to HTML if API gave nothing.
                # The HTML fallback also captures Clubcard prices via DOM selectors
                # and correctly stores them as member_price.
                if not products:
                    if self.debug:
                        print("  ℹ️ No API data, falling back to HTML parsing...")
                    products = self._parse_html_fallback(page)
                
                # Take screenshot for debugging
                if self.debug:
                    try:
                        page.screenshot(path='tesco_debug_screenshot.png')
                        print(f"  📸 Screenshot saved: tesco_debug_screenshot.png")
                    except Exception:
                        pass
                
                # Limit results
                products = products[:max_items]
                
                print(f"✓ Scraped {len(products)} products from Tesco")
            
            except Exception as e:
                print(f"❌ Error scraping Tesco: {e}")
            
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
        
        return products


def main():
    """Example usage of the advanced Tesco Playwright scraper."""
    scraper = TescoPlaywrightScraper(headless=False)  # Headed mode for best results
    
    # Example: Search for milk with Clubcard prices
    products = scraper.scrape_search_results("milk", max_items=10)
    
    print(f"\nFound {len(products)} products:")
    for product in products:
        clubcard_indicator = " 🎫" if product.get('is_clubcard_price') else ""
        normal_price = f" (was £{product.get('normal_price')})" if product.get('normal_price') else ""
        print(f"  - {product.get('name')}: £{product.get('price')}{clubcard_indicator}{normal_price}")


if __name__ == "__main__":
    main()
