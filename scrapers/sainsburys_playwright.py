"""
Sainsbury's scraper using Playwright with stealth mode.
Scrapes product data from Sainsbury's search results locally.
"""
from playwright.sync_api import sync_playwright, Page, Browser
from typing import List, Dict, Any, Optional
import time
import random


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
            # Launch browser with stealth settings
            browser = playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-crash-reporter',  # Disable Crashpad
                    '--disable-breakpad',         # Disable crash reporting  
                    '--disable-extensions'        # Disable extensions
                ]
            )
            
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
                # Try going to homepage first (more human-like)
                print(f"🔄 Scraping Sainsbury's: {search_query}")
                print(f"🏠 First visiting homepage...")
                
                page.goto(self.base_url, wait_until='domcontentloaded', timeout=30000)
                self._random_delay(2, 3)
                
                # Now navigate to search
                search_url = f"{self.base_url}/gol-ui/SearchResults/{search_query}"
                print(f"🌐 Now searching: {search_url}")
                
                page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
                
                if self.debug:
                    print(f"📄 Page title: {page.title()}")
                    print(f"🔗 Current URL: {page.url}")
                
                self._random_delay(2, 4)
                
                # Handle cookie consent if present
                try:
                    cookie_button = page.locator('button:has-text("Accept"), button:has-text("Accept all")')
                    if cookie_button.count() > 0:
                        cookie_button.first.click()
                        self._random_delay(1, 2)
                except:
                    pass
                
                # Scroll to load more products (lazy loading)
                self._scroll_page(page)
                
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
        
        # Sainsbury's product selectors - be more specific to avoid UI elements
        product_selectors = [
            '[data-testid="product-tile"]',  # Most specific - actual product tiles
            'article[data-testid*="product"]:not([data-testid*="filter"]):not([data-testid*="toolbar"])',  # Articles only
            'li[data-testid*="product"]',  # List items
            '[class*="productTile"]',  # Class with productTile
            '[class*="product-tile"]',  # Kebab case
            'article[class*="product"]',
            '[data-testid*="product-"]'  # Hyphenated patterns like product-XXX
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
                except:
                    lines = []
                
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
                
                # Approach 1: Specific selectors
                price_selectors = [
                    '[data-testid*="price"]:not([data-testid*="unit"])',
                    '[class*="price"]:not([class*="unit"])',
                    'span:has-text("£")',
                    'p:has-text("£")',
                    '[class*="cost"]'
                ]
                price = self._find_text(element, price_selectors)
                
                # Validate: If price doesn't contain £ or digits, it's not a real price
                if price and ('nectar' in price.lower() or '£' not in price):
                    price = None  # Reset and try fallback
                
                # Approach 2: Find any text with £ symbol
                if not price:
                    import re
                    # Look through ALL lines for actual price patterns
                    for line in lines:
                        if '£' in line:
                            # Skip lines that are clearly labels, not prices
                            if 'nectar' in line.lower() and 'price' in line.lower():
                                continue
                            
                            # Extract price using regex (e.g., "£2.65" from "£2.65£1.33 / ltr")
                            price_match = re.search(r'£\d+\.?\d*', line)
                            if price_match:
                                price = price_match.group()
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
                        'url': product_url
                    })
                    if self.debug and len(products) <= 3:  # Show first 3 actual products
                        gtin_status = f"(GTIN: {gtin})" if gtin else "(No GTIN)"
                        print(f"  ✓ Product #{len(products)}: '{name[:40]}' - {price} {gtin_status}")
                elif self.debug and i < 10 and (name or price):  # Show partial matches
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
            except:
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
