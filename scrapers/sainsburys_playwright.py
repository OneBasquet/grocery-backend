"""
Sainsbury's scraper using Playwright with stealth mode.
Scrapes product data from Sainsbury's search results locally.
Includes Nectar Price extraction (member_price) via two strategies:
  1. Parent-search: pre-scan all nectar elements on the page and walk up
     the DOM to their product-tile ancestor, building a tile-index map.
  2. Within-tile fallback: search each tile directly for nectar selectors
     and text-line patterns.
"""
from playwright.sync_api import sync_playwright, Page, Browser
from typing import List, Dict, Any, Optional
import time
import random
import re


class SainsburysPlaywrightScraper:
    """Stealth scraper for Sainsbury's using Playwright."""
    
    # Stealth configuration
    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    ]
    
    def __init__(self, headless: bool = True, fetch_gtin: bool = False):
        """
        Initialize the Sainsbury's Playwright scraper.
        
        Args:
            headless: Whether to run browser in headless mode
            fetch_gtin: Whether to visit product detail pages to fetch GTINs (slower but more accurate)
        """
        self.headless = headless
        self.fetch_gtin = fetch_gtin
        self.retailer = "sainsburys"
        self.base_url = "https://www.sainsburys.co.uk"
        
        # Debug flag - set to True to see detailed output
        self.debug = True  # Enable debug to see GTIN extraction
    
    def _configure_stealth(self, page: Page):
        """
        Configure page for stealth mode to avoid detection.
        
        Args:
            page: Playwright page object
        """
        # Add stealth scripts to avoid detection
        page.add_init_script("""
            // Override navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false
            });
            
            // Override chrome property
            window.chrome = {
                runtime: {}
            };
            
            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // Override plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en', 'en-GB']
            });
        """)
    
    def _random_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0):
        """Add random delay to mimic human behavior."""
        time.sleep(random.uniform(min_seconds, max_seconds))
    
    def scrape_search_results(self, search_query: str, max_items: int = 100) -> List[Dict[str, Any]]:
        """
        Scrape Sainsbury's search results for a given query.
        
        Args:
            search_query: Search term (e.g., "milk", "bread")
            max_items: Maximum number of products to scrape
            
        Returns:
            List of product dictionaries
        """
        products = []
        
        with sync_playwright() as playwright:
            # Launch browser — cloud CDP or local
            from scrapers.browser import get_browser
            browser = get_browser(playwright, headless=self.headless)
            
            # Create context with custom user agent and extra headers
            context = browser.new_context(
                user_agent=random.choice(self.USER_AGENTS),
                viewport={'width': 1920, 'height': 1080},
                locale='en-GB',
                timezone_id='Europe/London',
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-GB,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Cache-Control': 'max-age=0'
                }
            )
            
            page = context.new_page()
            self._configure_stealth(page)
            
            try:
                print(f"🔄 Scraping Sainsbury's: {search_query}")
                print(f"🏠 First visiting homepage...")

                page.goto(self.base_url, wait_until='domcontentloaded', timeout=30000)
                self._random_delay(2, 4)

                # Handle cookie consent early
                try:
                    for btn_sel in (
                        '#onetrust-accept-btn-handler',
                        'button:has-text("Accept All")',
                        'button:has-text("Accept all")',
                        'button:has-text("Accept")',
                    ):
                        btn = page.locator(btn_sel).first
                        if btn.count() > 0:
                            btn.click()
                            self._random_delay(1, 2)
                            break
                except:
                    pass

                # Try multiple search URL patterns — Sainsbury's changes these
                search_urls = [
                    f"{self.base_url}/gol-ui/SearchResults/{search_query}",
                    f"{self.base_url}/gol-ui/search/{search_query}",
                    f"{self.base_url}/gol-ui/SearchDisplayView?searchTerm={search_query}",
                ]

                search_success = False
                for search_url in search_urls:
                    print(f"🌐 Trying: {search_url}")
                    try:
                        resp = page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
                        status = resp.status if resp else 0
                        if status == 404 or status >= 500:
                            print(f"  ⚠ HTTP {status}, trying next URL...")
                            continue

                        self._random_delay(3, 5)

                        if self.debug:
                            print(f"📄 Page title: {page.title()}")
                            print(f"🔗 Current URL: {page.url}")

                        # Wait for product content to render (JS-heavy site)
                        try:
                            page.wait_for_selector(
                                '[data-testid="product-tile"], [class*="product"], [class*="pt-grid"]',
                                timeout=10000,
                            )
                        except:
                            pass

                        search_success = True
                        break
                    except Exception as e:
                        print(f"  ⚠ Failed: {e}")
                        continue

                if not search_success:
                    # Last resort: use the search bar on the homepage
                    print("🔍 Trying search bar fallback...")
                    try:
                        search_input = page.locator(
                            'input[name="search-bar-input"], input[name="search"], '
                            'input[type="search"], input[placeholder*="Search"]'
                        ).first
                        if search_input.count() > 0:
                            search_input.click()
                            self._random_delay(0.5, 1)
                            search_input.fill(search_query)
                            self._random_delay(0.5, 1)
                            search_input.press("Enter")
                            self._random_delay(3, 5)
                            try:
                                page.wait_for_selector(
                                    '[data-testid="product-tile"], [class*="product"]',
                                    timeout=10000,
                                )
                            except:
                                pass
                            search_success = True
                            if self.debug:
                                print(f"📄 Page title: {page.title()}")
                                print(f"🔗 Current URL: {page.url}")
                    except Exception as e:
                        print(f"  ⚠ Search bar fallback failed: {e}")

                # Scroll to load more products (lazy loading)
                self._scroll_page(page, scrolls=5)
                self._random_delay(1, 2)

                # Take a debug screenshot
                try:
                    page.screenshot(path="sainsburys_debug_screenshot.png")
                    if self.debug:
                        print("📸 Screenshot saved: sainsburys_debug_screenshot.png")
                except:
                    pass

                # Extract product data
                products = self._extract_products(page, max_items)
                
                print(f"✓ Scraped {len(products)} products from Sainsbury's")
                
            except Exception as e:
                print(f"✗ Error scraping Sainsbury's: {e}")
            
            finally:
                browser.close()
        
        return products
    
    def _scroll_page(self, page: Page, scrolls: int = 3):
        """
        Scroll the page to trigger lazy loading.
        
        Args:
            page: Playwright page object
            scrolls: Number of scroll iterations
        """
        for i in range(scrolls):
            page.evaluate("window.scrollBy(0, window.innerHeight)")
            self._random_delay(0.5, 1.5)
    
    def _extract_products(self, page: Page, max_items: int) -> List[Dict[str, Any]]:
        """
        Extract product data from the page.
        
        Args:
            page: Playwright page object
            max_items: Maximum number of products to extract
            
        Returns:
            List of product dictionaries
        """
        products = []
        
        # Sainsbury's product selectors — ordered most-specific to broadest.
        # The site changes DOM structure periodically; keep multiple patterns.
        product_selectors = [
            '[data-testid="product-tile"]',
            'li[data-testid="product-tile"]',
            '[data-testid="search-product-tile"]',
            'article[data-testid*="product"]:not([data-testid*="filter"]):not([data-testid*="toolbar"])',
            'li[data-testid*="product"]',
            '[class*="pt-grid__item"]',
            '[class*="productTile"]',
            '[class*="product-tile"]',
            '[class*="ProductCard"]',
            '[class*="product_card"]',
            'article[class*="product"]',
            '[data-testid*="product-"]',
            # Broader fallbacks
            'ul[data-testid*="product"] > li',
            'div[class*="search"] li[class]',
        ]
        
        # Try different selectors
        product_elements = None
        found_selector = None
        
        if self.debug:
            print(f"\n🔍 Trying {len(product_selectors)} different selectors...")
        
        for selector in product_selectors:
            product_elements = page.locator(selector)
            count = product_elements.count()
            if self.debug:
                print(f"  Selector '{selector}': found {count} elements")
            if count > 0:
                found_selector = selector
                break
        
        if not product_elements or product_elements.count() == 0:
            print("⚠ No products found with known selectors")
            
            if self.debug:
                # Try to help debug by looking at page content
                print("\n🔍 DEBUG: Checking page content...")
                
                # Check if there's any content
                body_text = page.locator('body').inner_text()
                if 'no results' in body_text.lower() or 'no products' in body_text.lower():
                    print("  → Page says 'no results found'")
                
                # Look for common product-related classes
                debug_selectors = [
                    '[class*="product"]',
                    '[class*="item"]',
                    '[data-testid*="product"]',
                    'article',
                    '[class*="grid"] > div',
                    'li[class*="product"]'
                ]
                
                print("\n  Common patterns found:")
                for sel in debug_selectors:
                    try:
                        count = page.locator(sel).count()
                        if count > 0:
                            print(f"    '{sel}': {count} elements")
                    except:
                        pass
            
            return products
        
        print(f"✓ Using selector: '{found_selector}' ({product_elements.count()} elements, filtering non-products...)")

        # Build the Nectar price map via parent-search before iterating tiles.
        # This pre-scans the whole page once so the per-tile loop stays fast.
        nectar_map = self._prebuild_nectar_map(page, found_selector)

        count = min(product_elements.count(), max_items)
        
        for i in range(count):
            try:
                element = product_elements.nth(i)
                
                # Skip if this looks like a UI element, not a product
                try:
                    elem_text = element.inner_text().lower()
                    # Filter out known UI elements
                    skip_keywords = ['filters', 'sort by', 'toolbar', 'relevance', 'price - low to high']
                    if any(keyword in elem_text[:50] for keyword in skip_keywords):
                        continue
                except:
                    pass
                
                # Debug: Show element structure for first product
                if self.debug and i == 0:
                    print(f"\n🔍 Inspecting first product element...")
                    try:
                        # Get all text content
                        all_text = element.inner_text()
                        print(f"  All text: {all_text[:200]}...")
                        
                        # Try to find data-testid attributes
                        html = element.inner_html()[:500]
                        import re
                        testids = re.findall(r'data-testid="([^"]+)"', html)
                        if testids:
                            print(f"  data-testid values found: {testids[:5]}")
                    except:
                        pass
                
                # Try to get all text first, then parse
                try:
                    full_text = element.inner_text()
                    lines = [line.strip() for line in full_text.split('\n') if line.strip()]
                except Exception:
                    lines = []

                # Resolve the nectar price for this tile early so price
                # extraction can exclude it when scanning lines.
                tile_nectar_price = nectar_map.get(i)

                # Extract product name - try multiple approaches
                name = None
                
                # Approach 1: Specific selectors
                name_selectors = [
                    '[data-testid*="title"]',
                    '[data-testid*="name"]',
                    'a[href*="/product/"]',  # Product links
                    'h2',
                    'h3',
                    'a',
                    'span[class*="name"]',
                    '[class*="title"]'
                ]
                name = self._find_text(element, name_selectors)
                
                # Approach 2: If no name found, try first meaningful line
                if not name and lines:
                    # Skip common non-product words
                    skip_words = ['sponsored', 'filters', 'sort by', 'offers', 'nectar', 'nectar price', 'add', 'chilled', 'frozen']
                    for line in lines:
                        line_lower = line.lower()
                        # Product name is usually longer than 10 chars and not a price or label
                        if (len(line) > 10 and  # Names are longer
                            '£' not in line and 
                            not line.replace('.', '').replace('(', '').replace(')', '').isdigit() and  # Skip ratings like (315)
                            not any(skip in line_lower for skip in skip_words) and
                            not line.isupper()):  # Skip labels like "CHILLED"
                            name = line
                            break
                
                # Extract price - try multiple approaches
                price = None

                # Approach 1: Specific selectors — explicitly exclude Nectar
                # elements (data-testid="nectar-price-label" contains "price"
                # and would otherwise be matched).
                price_selectors = [
                    '[data-testid*="price"]:not([data-testid*="unit"]):not([data-testid*="nectar"])',
                    '[class*="price"]:not([class*="unit"]):not([class*="nectar"])',
                    'span:has-text("£")',
                    'p:has-text("£")',
                    '[class*="cost"]'
                ]
                price = self._find_text(element, price_selectors)

                # Validate: reject if the value is a Nectar label, missing £,
                # or numerically equal to the already-known Nectar price.
                if price:
                    if 'nectar' in price.lower() or '£' not in price:
                        price = None
                    elif tile_nectar_price:
                        try:
                            if abs(float(price.replace('£', '')) - float(tile_nectar_price)) < 0.001:
                                price = None  # Selector matched the Nectar element
                        except ValueError:
                            pass

                # Approach 2: line scan — skip the nectar price value so we
                # land on the shelf price (e.g. skip £2.00 and take £2.65).
                if not price:
                    for line in lines:
                        if '£' not in line:
                            continue
                        if 'nectar' in line.lower() and 'price' in line.lower():
                            continue
                        price_match = re.search(r'£(\d+\.?\d*)', line)
                        if not price_match:
                            continue
                        candidate = price_match.group(0)
                        # Skip if this value is the known Nectar price.
                        if tile_nectar_price:
                            try:
                                if abs(float(price_match.group(1)) - float(tile_nectar_price)) < 0.001:
                                    continue
                            except ValueError:
                                pass
                        price = candidate
                        break
                
                # Extract unit price — must contain '/' or 'per' to be valid
                unit_price_selectors = [
                    '[data-testid*="unit-price"]',
                    '[data-testid*="price-per"]',
                    '[data-testid*="unit_price"]',
                    '[data-testid*="unit"]',
                    '[class*="unit-price"]',
                    '[class*="unitPrice"]',
                    'span:has-text("/kg")',
                    'span:has-text("/litre")',
                    'span:has-text("/l")',
                    'span:has-text("/100")',
                    'p:has-text("/kg")',
                    'p:has-text("/litre")',
                    'p:has-text("/l")',
                ]
                unit_price = None
                for sel in unit_price_selectors:
                    try:
                        loc = element.locator(sel).first
                        if loc.count() > 0:
                            text = loc.inner_text().strip()
                            # Only accept if it actually contains the unit separator
                            if text and ('/' in text or 'per' in text.lower()):
                                unit_price = text
                                break
                    except Exception:
                        continue

                # Fallback: scan all lines for a unit price pattern
                if not unit_price and lines:
                    import re as _re
                    for line in lines:
                        line = line.strip()
                        if _re.search(r'(£[\d.]+|[\d.]+p)\s*/\s*\w+', line, _re.I):
                            unit_price = line
                            break
                        if '/' in line and ('£' in line or line.endswith('g') or line.endswith('l')):
                            unit_price = line
                            break
                
                # Try to find GTIN (may be in data attributes, URLs, or script tags)
                gtin = None
                product_url = None
                try:
                    # First, always try to extract product URL (needed for fetch_gtin)
                    try:
                        link = element.locator('a[href]').first
                        if link.count() > 0:
                            href = link.get_attribute('href')
                            if href:
                                product_url = href if href.startswith('http') else f"https://www.sainsburys.co.uk{href}"
                                if self.debug and i == 0:
                                    print(f"  ✓ Product URL: {product_url[:60]}...")
                    except Exception as e:
                        if self.debug and i == 0:
                            print(f"  ⚠ Failed to extract URL: {e}")
                    
                    # Try multiple data attribute names for GTIN
                    for attr in ['data-gtin', 'data-ean', 'data-product-id', 'data-item-id', 'data-sku']:
                        gtin_attr = element.get_attribute(attr)
                        if gtin_attr and gtin_attr.strip():
                            gtin = gtin_attr.strip()
                            if self.debug and i == 0:
                                print(f"  ✓ Found GTIN in {attr}: {gtin}")
                            break
                    
                    # Try to extract GTIN from product URL pattern
                    if not gtin and product_url:
                        try:
                            import re
                            match = re.search(r'/(\d{7,13})', product_url)
                            if match:
                                gtin = match.group(1)
                                if self.debug and i == 0:
                                    print(f"  ✓ Extracted GTIN from URL: {gtin}")
                        except:
                            pass
                except:
                    pass
                
                # ---- Nectar (member) price --------------------------------
                # tile_nectar_price was resolved from the parent-search map at
                # the start of this iteration; fall back to within-tile search.
                nectar_price = tile_nectar_price or self._extract_nectar_price(
                    element, lines
                )
                # ----------------------------------------------------------

                if name and price:
                    # If fetch_gtin is enabled and we have a product URL but no GTIN, visit detail page
                    if self.fetch_gtin and not gtin and product_url:
                        if self.debug and len(products) < 3:
                            print(f"  🔍 Fetching GTIN from detail page...")
                        gtin = self._extract_gtin_from_detail_page(page, product_url)
                        if gtin and self.debug and len(products) < 3:
                            print(f"  ✓ Found GTIN: {gtin}")

                    products.append({
                        'name': name.strip(),
                        'price': price.strip(),
                        'unit_price': unit_price.strip() if unit_price else None,
                        'gtin': gtin,
                        'url': product_url,
                        'member_price': nectar_price,
                        'is_clubcard_price': bool(nectar_price),
                    })
                    if self.debug and len(products) <= 3:
                        gtin_status = f"(GTIN: {gtin})" if gtin else "(No GTIN)"
                        nectar_status = f" | Nectar £{nectar_price}" if nectar_price else ""
                        print(f"  ✓ Product #{len(products)}: '{name[:40]}' - {price}{nectar_status} {gtin_status}")
                elif self.debug and i < 10 and (name or price):
                    print(f"  ⚠ Element {i} (partial): name='{name[:30] if name else 'None'}', price='{price or 'None'}'")
                    if i < 2 and lines:
                        print(f"    Available lines: {lines[:5]}")
                
            except Exception as e:
                print(f"⚠ Error extracting product {i}: {e}")
                continue
        
        return products
    
    def _extract_gtin_from_detail_page(self, page: Page, product_url: str) -> Optional[str]:
        """
        Visit a product detail page and extract GTIN.
        
        Args:
            page: Playwright page object
            product_url: URL of the product detail page
            
        Returns:
            GTIN string or None
        """
        if not product_url:
            if self.debug:
                print(f"    ⚠ No product URL provided")
            return None
            
        try:
            if self.debug:
                print(f"    → Visiting: {product_url[:70]}...")
            
            # Visit the product page
            page.goto(product_url, wait_until='domcontentloaded', timeout=15000)
            self._random_delay(0.5, 1)  # Short delay
            
            if self.debug:
                print(f"    → Page loaded: {page.title()[:50]}")
            
            # Strategy 1: Look for JSON-LD structured data
            try:
                scripts = page.locator('script[type="application/ld+json"]').all()
                if self.debug:
                    print(f"    → Strategy 1: Found {len(scripts)} JSON-LD scripts")
                
                for script in scripts:
                    content = script.inner_text()
                    import json
                    data = json.loads(content)
                    
                    # Check for GTIN in various formats
                    for gtin_key in ['gtin', 'gtin13', 'gtin12', 'gtin14', 'gtin8', 'ean']:
                        if gtin_key in data:
                            gtin = str(data[gtin_key]).strip()
                            if gtin and gtin.isdigit() and len(gtin) >= 8:
                                if self.debug:
                                    print(f"    ✓ Found GTIN in JSON-LD ({gtin_key}): {gtin}")
                                return gtin
            except Exception as e:
                if self.debug:
                    print(f"    ⚠ Strategy 1 error: {e}")
            
            # Strategy 2: Look for meta tags
            try:
                meta_selectors = [
                    'meta[property="product:ean"]',
                    'meta[property="og:upc"]',
                    'meta[name="gtin"]',
                    'meta[itemprop="gtin"]',
                    'meta[itemprop="gtin13"]'
                ]
                for selector in meta_selectors:
                    meta = page.locator(selector).first
                    if meta.count() > 0:
                        content = meta.get_attribute('content')
                        if content and content.strip().isdigit():
                            return content.strip()
            except:
                pass
            
            # Strategy 3: Look for data attributes in product containers
            try:
                product_containers = [
                    '[data-gtin]',
                    '[data-ean]',
                    '[itemtype*="Product"]',
                    '.product-details'
                ]
                for selector in product_containers:
                    elements = page.locator(selector).all()
                    for elem in elements:
                        for attr in ['data-gtin', 'data-ean', 'data-product-code']:
                            gtin = elem.get_attribute(attr)
                            if gtin and gtin.strip().isdigit() and len(gtin.strip()) >= 8:
                                return gtin.strip()
            except:
                pass
            
            # Strategy 4: Look in page text for "GTIN:" or "EAN:" patterns
            try:
                page_text = page.content()
                import re
                patterns = [
                    r'gtin["\s:]+(\d{8,14})',
                    r'ean["\s:]+(\d{8,14})',
                    r'"gtin13":\s*"(\d{13})"',
                    r'"ean":\s*"(\d{13})"'
                ]
                for pattern in patterns:
                    match = re.search(pattern, page_text, re.IGNORECASE)
                    if match:
                        gtin = match.group(1)
                        if self.debug:
                            print(f"    ✓ Found GTIN in page text: {gtin}")
                        return gtin
            except Exception as e:
                if self.debug:
                    print(f"    ⚠ Strategy 4 error: {e}")
            
            if self.debug:
                print(f"    ❌ No GTIN found after all strategies")
            return None
            
        except Exception as e:
            if self.debug:
                print(f"  ⚠ Error fetching GTIN from {product_url}: {e}")
            return None
    
    # ------------------------------------------------------------------
    # Nectar price extraction
    # ------------------------------------------------------------------

    # Selectors that Sainsbury's uses to mark Nectar price elements.
    # Ordered from most specific to most general.
    _NECTAR_SELECTORS = (
        '[data-testid="nectar-price"]',
        '[data-testid*="nectar"]',
        '[class*="nectar-price"]',
        '[class*="NectarPrice"]',
        '[class*="nectar"]',
        'span:has-text("with Nectar")',
        'p:has-text("with Nectar")',
        '*:has-text("Nectar Price")',
    )

    def _prebuild_nectar_map(self, page: Page, tile_selector: str) -> Dict[int, str]:
        """
        Parent-search approach: scan the entire page for every Nectar price
        element, then walk each element up the DOM tree until an ancestor that
        matches the product-tile selector is found.  Returns a dict of
        tile_index (0-based, matching the order of tile_selector on the page)
        → nectar_price_string.

        This is more robust than a simple within-tile search because Nectar
        elements can be nested at arbitrary depth, or even placed as siblings
        of the tile rather than inside it (depending on the page version).
        """
        nectar_map: Dict[int, str] = {}
        # Escape single quotes in the selector for safe JS interpolation.
        safe_sel = tile_selector.replace("'", "\\'")

        for nectar_sel in self._NECTAR_SELECTORS:
            try:
                nectar_els = page.locator(nectar_sel).all()
                for nectar_el in nectar_els:
                    try:
                        text = nectar_el.inner_text().strip()
                    except Exception:
                        continue
                    m = re.search(r'£\s*(\d+\.?\d*)', text)
                    if not m:
                        continue
                    price_val = m.group(1)

                    # Walk up the DOM tree in JS to find which tile index this
                    # element belongs to.
                    try:
                        tile_idx = nectar_el.evaluate(f"""
                            (el) => {{
                                const tiles = Array.from(
                                    document.querySelectorAll('{safe_sel}')
                                );
                                let node = el;
                                while (node) {{
                                    const idx = tiles.indexOf(node);
                                    if (idx !== -1) return idx;
                                    node = node.parentElement;
                                }}
                                return -1;
                            }}
                        """)
                    except Exception:
                        tile_idx = -1

                    if isinstance(tile_idx, int) and tile_idx >= 0:
                        nectar_map.setdefault(tile_idx, price_val)

            except Exception:
                continue

        if self.debug and nectar_map:
            print(f"  🟣 Nectar map (parent-search): {len(nectar_map)} tiles "
                  f"have a Nectar price")
        return nectar_map

    def _extract_nectar_price(self, element, lines: List[str]) -> Optional[str]:
        """
        Within-tile fallback: search a product tile directly for a Nectar price.

        Strategy 1 — selector scan: try known data-testid / class selectors.
        Strategy 2 — line scan: look for lines containing 'nectar' and '£'.

        Returns the numeric price string (e.g. '1.25') or None.
        """
        # Strategy 1: known selectors inside the tile
        for sel in self._NECTAR_SELECTORS:
            try:
                loc = element.locator(sel).first
                if loc.count() > 0:
                    text = loc.inner_text().strip()
                    m = re.search(r'£\s*(\d+\.?\d*)', text)
                    if m:
                        return m.group(1)
            except Exception:
                continue

        # Strategy 2: text-line scan
        for line in lines:
            if 'nectar' in line.lower() and '£' in line:
                m = re.search(r'£\s*(\d+\.?\d*)', line)
                if m:
                    return m.group(1)

        return None

    # ------------------------------------------------------------------
    # Generic text helper
    # ------------------------------------------------------------------

    def _find_text(self, element, selectors: List[str]) -> str:
        """
        Try multiple selectors to find text content.

        Args:
            element: Playwright locator
            selectors: List of CSS selectors to try

        Returns:
            Text content or empty string
        """
        for selector in selectors:
            try:
                locator = element.locator(selector).first
                if locator.count() > 0:
                    return locator.inner_text()
            except Exception:
                continue
        return ""


def main():
    """Example usage of the Sainsbury's Playwright scraper."""
    scraper = SainsburysPlaywrightScraper(headless=False)
    
    # Example: Search for milk
    products = scraper.scrape_search_results("milk", max_items=20)
    
    print(f"\nFound {len(products)} products:")
    for product in products[:5]:  # Show first 5
        print(f"  - {product.get('name')}: {product.get('price')}")


if __name__ == "__main__":
    main()
