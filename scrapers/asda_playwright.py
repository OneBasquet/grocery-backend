"""
Asda scraper using Playwright with stealth mode.
Scrapes product data from Asda search results locally.
"""
from playwright.sync_api import sync_playwright, Page, Browser
from typing import List, Dict, Any
import time
import random


class AsdaPlaywrightScraper:
    """Stealth scraper for Asda using Playwright."""
    
    # Stealth configuration
    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    ]
    
    def __init__(self, headless: bool = True):
        """
        Initialize the Asda Playwright scraper.
        
        Args:
            headless: Whether to run browser in headless mode
        """
        self.headless = headless
        self.retailer = "asda"
        self.base_url = "https://groceries.asda.com"
        self.debug = True
    
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
        Scrape Asda search results for a given query.
        
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
                    '--disable-dev-shm-usage'
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
                # Visit homepage first (more human-like)
                print(f"🔄 Scraping Asda: {search_query}")
                print(f"🏠 First visiting homepage...")
                
                page.goto(self.base_url, wait_until='networkidle', timeout=60000)
                self._random_delay(3, 4)
                
                if self.debug:
                    print(f"  Homepage title: {page.title()}")
                    # Check for any blocking messages
                    page_text = page.content()
                    if "cannot show" in page_text.lower() or "try again" in page_text.lower():
                        print(f"  ⚠ Homepage shows blocking message")
                    else:
                        print(f"  ✓ Homepage loaded successfully")
                
                # Handle cookie consent FIRST
                print(f"🍪 Handling cookie consent...")
                try:
                    cookie_selectors = [
                        'button:has-text("Accept All")',
                        'button:has-text("Accept all")',
                        'button:has-text("Accept")',
                        '[data-testid*="accept"]',
                        'button[id*="accept"]',
                        'button[class*="accept"]'
                    ]
                    for selector in cookie_selectors:
                        try:
                            button = page.locator(selector).first
                            if button.is_visible(timeout=3000):
                                button.click()
                                print(f"  ✓ Clicked cookie button")
                                self._random_delay(2, 3)
                                break
                        except:
                            continue
                except Exception as e:
                    if self.debug:
                        print(f"  ⚠ Cookie handling: {e}")
                
                # Try to set postcode/location (Asda might require this)
                print(f"📍 Checking for location/postcode requirement...")
                try:
                    # Look for postcode input or location button
                    location_selectors = [
                        'input[placeholder*="postcode"]',
                        'input[placeholder*="Postcode"]',
                        'input[name*="postcode"]',
                        'button:has-text("Set location")',
                        'button:has-text("Choose location")'
                    ]
                    for selector in location_selectors:
                        try:
                            element = page.locator(selector).first
                            if element.is_visible(timeout=2000):
                                if 'input' in selector:
                                    element.fill('SW1A 1AA')  # Westminster postcode
                                    print(f"  ✓ Entered postcode")
                                    self._random_delay(1, 2)
                                    # Try to submit
                                    page.keyboard.press('Enter')
                                    self._random_delay(3, 4)
                                else:
                                    element.click()
                                    print(f"  ✓ Clicked location button")
                                    self._random_delay(2, 3)
                                break
                        except:
                            continue
                except Exception as e:
                    if self.debug:
                        print(f"  ⚠ Location handling: {e}")
                
                # Browse categories to establish proper session
                print(f"📂 Browsing categories to establish session...")
                try:
                    # Visit milk category directly
                    page.goto('https://groceries.asda.com/aisle/fresh-food/fresh-milk-butter-eggs/fresh-milk/1215683611804-1215683611833-1215683611847', 
                             wait_until='networkidle', timeout=60000)
                    self._random_delay(3, 4)
                    
                    # Check if products loaded successfully
                    page_text = page.content()
                    if "Sorry, we cannot show you" in page_text:
                        print(f"  ⚠ Still blocked on category page")
                    else:
                        print(f"  ✓ Category page loaded successfully")
                except Exception as e:
                    if self.debug:
                        print(f"  ⚠ Category browse: {e}")
                
                # Now navigate to search
                search_url = f"{self.base_url}/search/{search_query}"
                print(f"🌐 Now searching: {search_url}")
                
                page.goto(search_url, wait_until='networkidle', timeout=60000)
                
                if self.debug:
                    print(f"📄 Page title: {page.title()}")
                    print(f"🔗 Current URL: {page.url}")
                
                # Wait longer for products to load (they might be lazy-loaded)
                self._random_delay(3, 5)
                
                # Try to wait for products to appear
                try:
                    page.wait_for_selector('[class*="product"], article, li[class*="item"]', timeout=5000)
                except:
                    pass
                
                # Scroll down to trigger lazy loading
                if self.debug:
                    print("📜 Scrolling to trigger lazy-loaded content...")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                self._random_delay(2, 3)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                self._random_delay(2, 3)
                
                # Take screenshot for debugging
                if self.debug:
                    try:
                        screenshot_path = 'asda_debug_screenshot.png'
                        page.screenshot(path=screenshot_path, full_page=False)
                        print(f"📸 Screenshot saved: {screenshot_path}")
                    except:
                        pass
                
                # Scroll to load more products (lazy loading)
                self._scroll_page(page)
                
                # Extract product data
                products = self._extract_products(page, max_items)
                
                print(f"✓ Scraped {len(products)} products from Asda")
                
            except Exception as e:
                print(f"✗ Error scraping Asda: {e}")
            
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
        
        # Asda product selectors (may need adjustment based on site changes)
        product_selectors = [
            '[data-auto-id="productTile"]',
            '[data-auto-id*="product"]',
            'article[class*="product"]',
            'li[class*="product"]',
            '[class*="productTile"]',
            '[class*="product-tile"]',
            '[class*="product"][class*="card"]',
            '[class*="product"][class*="item"]',
            '.co-product',
            'article[class*="card"]',
            'li[class*="item"]',
            'article',
            '[data-testid*="product"]:not([data-testid*="recall"])',
            '[class*="product"]'
        ]
        
        if self.debug:
            print(f"\n🔍 Trying {len(product_selectors)} different selectors...")
        
        # Try different selectors
        product_elements = None
        found_selector = None
        
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
                print("\n🔍 DEBUG: Checking page content...")
                
                # Check page content
                body_text = page.locator('body').inner_text()
                if 'access denied' in body_text.lower():
                    print("  → Access Denied detected!")
                if 'no results' in body_text.lower():
                    print("  → No results found for query")
                
                # Try common patterns
                debug_selectors = [
                    '[class*="product"]',
                    '[class*="item"]',
                    '[class*="card"]',
                    '[class*="tile"]',
                    '[data-auto-id*="product"]',
                    'article',
                    'li',
                    'div[class*="grid"] > div',
                    'ul > li'
                ]
                
                print("\n  Common patterns found:")
                for sel in debug_selectors:
                    try:
                        count = page.locator(sel).count()
                        if count > 0:
                            print(f"    '{sel}': {count} elements")
                            # Show first element text for most promising selectors
                            if count > 5 and count < 100 and sel in ['[class*="product"]', '[class*="item"]', 'article', 'li']:
                                try:
                                    first_text = page.locator(sel).first.inner_text()[:100]
                                    print(f"      First element text: {first_text}...")
                                except:
                                    pass
                    except:
                        pass
                
                # Show actual HTML structure hints
                print("\n  🔬 Analyzing page structure...")
                try:
                    # Look for divs that might contain products
                    main_content = page.locator('main, [role="main"], #main, .main-content').first
                    if main_content.count() > 0:
                        # Get all direct children
                        html_snippet = main_content.evaluate('el => el.outerHTML')[:2000]
                        print(f"  Main content HTML (first 2000 chars):\n{html_snippet}\n")
                except:
                    pass
            
            return products
        
        print(f"✓ Using selector: '{found_selector}' ({product_elements.count()} products)")
        
        count = min(product_elements.count(), max_items)
        
        for i in range(count):
            try:
                element = product_elements.nth(i)
                
                # Skip if this looks like a UI element, not a product
                try:
                    elem_text = element.inner_text().lower()
                    # Filter out known UI elements
                    skip_keywords = ['filters', 'sort by', 'toolbar', 'showing results']
                    if any(keyword in elem_text[:50] for keyword in skip_keywords):
                        continue
                except:
                    pass
                
                # Debug: Show element structure for first product
                if self.debug and i == 0:
                    print(f"\n🔍 Inspecting first product element...")
                    try:
                        all_text = element.inner_text()
                        print(f"  All text: {all_text[:200]}...")
                        
                        # Try to find data-auto-id attributes
                        html = element.inner_html()[:500]
                        import re
                        auto_ids = re.findall(r'data-auto-id="([^"]+)"', html)
                        if auto_ids:
                            print(f"  data-auto-id values found: {auto_ids[:5]}")
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
                    '[data-auto-id="linkProductTitle"]',
                    '[data-auto-id*="product"]',
                    '.co-product__title',
                    'a[href*="/product/"]',
                    'h2',
                    'h3',
                    'a',
                    '[class*="title"]',
                    '.product-name'
                ]
                name = self._find_text(element, name_selectors)
                
                # Approach 2: If no name found, try first meaningful line
                if not name and lines:
                    skip_words = ['sponsored', 'filters', 'sort by', 'offers', 'add', 'frozen']
                    for line in lines:
                        line_lower = line.lower()
                        # Product name is usually longer than 10 chars
                        if (len(line) > 10 and 
                            '£' not in line and 
                            not line.replace('.', '').replace('(', '').replace(')', '').isdigit() and
                            not any(skip in line_lower for skip in skip_words) and
                            not line.isupper()):
                            name = line
                            break
                
                # Extract price - try multiple approaches
                price = None
                
                # Approach 1: Specific selectors
                price_selectors = [
                    '[data-auto-id="productPrice"]',
                    '[data-auto-id*="price"]',
                    '.co-product__price',
                    '[class*="price"]:not([class*="unit"])',
                    'span:has-text("£")',
                    'p:has-text("£")',
                    '.price'
                ]
                price = self._find_text(element, price_selectors)
                
                # Validate: If price doesn't contain £ or digits, it's not a real price
                if price and '£' not in price:
                    price = None
                
                # Approach 2: Find any text with £ symbol
                if not price:
                    import re
                    for line in lines:
                        if '£' in line:
                            # Extract price using regex
                            price_match = re.search(r'£\d+\.?\d*', line)
                            if price_match:
                                price = price_match.group()
                                break
                
                # Extract unit price
                unit_price_selectors = [
                    '[data-auto-id="productUnitPrice"]',
                    '[data-auto-id*="unit"]',
                    '.co-product__price-per-uom',
                    '[class*="unit"]',
                    '.unit-price'
                ]
                unit_price = self._find_text(element, unit_price_selectors)
                
                # Alternative: Look for pattern in lines
                if not unit_price and lines:
                    for line in lines:
                        if '/' in line and '£' in line:
                            unit_price = line
                            break
                
                # Try to find GTIN (may be in data attributes)
                gtin = None
                try:
                    gtin_attrs = ['data-gtin', 'data-product-id', 'data-sku']
                    for attr in gtin_attrs:
                        gtin = element.get_attribute(attr)
                        if gtin:
                            break
                except:
                    pass
                
                if name and price:
                    products.append({
                        'name': name.strip(),
                        'price': price.strip(),
                        'unit_price': unit_price.strip() if unit_price else None,
                        'gtin': gtin
                    })
                    if self.debug and len(products) <= 3:
                        print(f"  ✓ Product #{len(products)}: '{name[:40]}' - {price}")
                elif self.debug and i < 10 and (name or price):
                    print(f"  ⚠ Element {i} (partial): name='{name[:30] if name else 'None'}', price='{price or 'None'}'")
                    if i < 2 and lines:
                        print(f"    Available lines: {lines[:5]}")
                
            except Exception as e:
                if self.debug and i < 3:
                    print(f"⚠ Error extracting product {i}: {e}")
                continue
        
        return products
    
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
    """Example usage of the Asda Playwright scraper."""
    scraper = AsdaPlaywrightScraper(headless=False)
    
    # Example: Search for milk
    products = scraper.scrape_search_results("milk", max_items=20)
    
    print(f"\nFound {len(products)} products:")
    for product in products[:5]:  # Show first 5
        print(f"  - {product.get('name')}: {product.get('price')}")


if __name__ == "__main__":
    main()
