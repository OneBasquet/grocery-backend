"""
Tesco scraper using Playwright with stealth mode.
Scrapes product data from Tesco search results locally.
"""
from playwright.sync_api import sync_playwright, Page, Browser
from typing import List, Dict, Any, Optional
import time
import random


class TescoPlaywrightScraper:
    """Stealth scraper for Tesco using Playwright."""
    
    # Stealth configuration
    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    ]
    
    def __init__(self, headless: bool = True):
        """
        Initialize the Tesco Playwright scraper.
        
        Args:
            headless: Whether to run browser in headless mode
        """
        self.headless = headless
        self.retailer = "tesco"
        self.base_url = "https://www.tesco.com"
        self.debug = True
    
    def _configure_stealth(self, page: Page):
        """Configure page for stealth mode to avoid detection."""
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
                get: () => ['en-GB', 'en-US', 'en']
            });
        """)
    
    def _random_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0):
        """Add random delay to mimic human behavior."""
        time.sleep(random.uniform(min_seconds, max_seconds))
    
    def scrape_search_results(self, search_query: str, max_items: int = 100) -> List[Dict[str, Any]]:
        """
        Scrape Tesco search results for a given query.
        
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
                # Visit homepage first
                print(f"🔄 Scraping Tesco: {search_query}")
                if self.debug:
                    print(f"🏠 First visiting homepage...")
                
                page.goto(self.base_url, wait_until='domcontentloaded', timeout=30000)
                self._random_delay(2, 3)
                
                # Handle cookie consent
                try:
                    cookie_button = page.locator('button:has-text("Accept"), button:has-text("Accept All"), #accept-cookies')
                    if cookie_button.count() > 0:
                        cookie_button.first.click()
                        if self.debug:
                            print(f"  ✓ Accepted cookies")
                        self._random_delay(1, 2)
                except:
                    pass
                
                # Now navigate to search
                search_url = f"{self.base_url}/groceries/en-GB/search?query={search_query}"
                if self.debug:
                    print(f"🌐 Now searching: {search_url}")
                
                page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
                
                if self.debug:
                    print(f"📄 Page title: {page.title()}")
                    print(f"🔗 Current URL: {page.url}")
                
                # Wait for products to load (they're loaded dynamically)
                if self.debug:
                    print(f"⏳ Waiting for products to load...")
                
                self._random_delay(5, 7)  # Longer wait for JS to execute
                
                # Try to wait for product elements
                try:
                    page.wait_for_selector('a[data-auto*="product"], [class*="product"], img[alt*="product"]', timeout=10000)
                except:
                    if self.debug:
                        print(f"  ⚠ Timeout waiting for products")
                
                # Scroll to trigger lazy loading
                if self.debug:
                    print(f"📜 Scrolling to load more products...")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                self._random_delay(2, 3)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                self._random_delay(2, 3)
                
                # Take a screenshot for debugging
                if self.debug:
                    try:
                        page.screenshot(path='tesco_debug_screenshot.png')
                        print(f"📸 Screenshot saved: tesco_debug_screenshot.png")
                    except:
                        pass
                
                # Tesco product selectors - look for links/cards with product data
                product_selectors = [
                    'a[data-auto*="product-tile"]',
                    '[data-auto-id*="productTile"]',
                    'a[href*="/product/"]',
                    'div[class*="product-tile"]',
                    'ul[class*="product"] > li',
                    '[class*="product-list"] > li',
                    'main ul > li',
                    '[data-auto-id*="product"]'
                ]
                
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
                        print("\n🔍 DEBUG: Checking page content...")
                        
                        # Try to find common patterns
                        debug_selectors = [
                            '[class*="product"]',
                            '[class*="item"]',
                            '[class*="tile"]',
                            'article',
                            'li',
                            '[data-auto*="product"]',
                            'ul > li',
                            '[class*="grid"] > div'
                        ]
                        
                        print("\n  Common patterns found:")
                        for sel in debug_selectors:
                            try:
                                count = page.locator(sel).count()
                                if count > 0 and count < 200:
                                    print(f"    '{sel}': {count} elements")
                                    # Show first element text for promising selectors
                                    if count > 5 and sel in ['[class*="product"]', 'li', 'article']:
                                        try:
                                            first_text = page.locator(sel).first.inner_text()[:100]
                                            print(f"      First element: {first_text}...")
                                        except:
                                            pass
                            except:
                                pass
                    
                    return products
                
                print(f"✓ Using selector: '{found_selector}' ({product_elements.count()} elements)")
                
                # Debug: Show first few elements to find products
                if self.debug and product_elements.count() > 0:
                    print(f"\n🔍 Inspecting first 10 elements to find products:")
                    for idx in range(min(10, product_elements.count())):
                        try:
                            elem = product_elements.nth(idx)
                            text = elem.inner_text()[:80].replace('\n', ' ')
                            has_price = '£' in text
                            
                            # Show HTML structure for first element
                            if idx == 0:
                                html = elem.inner_html()[:300]
                                print(f"  First element HTML: {html}...\n")
                            
                            print(f"  [{idx}] {'💰' if has_price else '  '} {text}...")
                        except Exception as e:
                            print(f"  [{idx}] Error: {e}")
                
                count = min(product_elements.count(), max_items)
                
                for i in range(count):
                    try:
                        element = product_elements.nth(i)
                        
                        # Skip navigation/UI elements
                        try:
                            elem_text = element.inner_text().lower()
                            skip_keywords = ['skip to', 'navigation', 'menu', 'filter', 'sort', 'basket']
                            if any(keyword in elem_text[:50] for keyword in skip_keywords):
                                continue
                        except:
                            pass
                        
                        # Extract product name
                        name = None
                        name_selectors = [
                            'h3',
                            '[data-auto="product-tile-title"]',
                            '.product-tile--title',
                            'a[data-auto*="title"]'
                        ]
                        
                        for sel in name_selectors:
                            try:
                                name_elem = element.locator(sel).first
                                if name_elem.count() > 0:
                                    name = name_elem.inner_text().strip()
                                    if name and len(name) > 3:
                                        break
                            except:
                                continue
                        
                        # Extract price
                        price = None
                        price_selectors = [
                            '.price-per-quantity-weight',
                            '[data-auto="price-value"]',
                            '.product-tile--price',
                            'span[class*="value"]'
                        ]
                        
                        for sel in price_selectors:
                            try:
                                price_elem = element.locator(sel).first
                                if price_elem.count() > 0:
                                    price_text = price_elem.inner_text().strip()
                                    if '£' in price_text:
                                        price = price_text
                                        break
                            except:
                                continue
                        
                        # Extract unit price
                        unit_price = None
                        try:
                            unit_elem = element.locator('[class*="unit-price"], .price-per-quantity-weight').first
                            if unit_elem.count() > 0:
                                unit_price = unit_elem.inner_text().strip()
                        except:
                            pass
                        
                        # Try to extract GTIN
                        gtin = None
                        try:
                            for attr in ['data-gtin', 'data-product-id', 'data-ean']:
                                gtin_val = element.get_attribute(attr)
                                if gtin_val:
                                    gtin = gtin_val
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
                    
                    except Exception as e:
                        if self.debug:
                            print(f"  ⚠ Error extracting product {i}: {e}")
                        continue
            
            finally:
                browser.close()
        
        return products


def main():
    """Example usage of the Tesco Playwright scraper."""
    scraper = TescoPlaywrightScraper(headless=False)
    
    # Example: Search for bread
    products = scraper.scrape_search_results("bread", max_items=5)
    
    print(f"\nFound {len(products)} products:")
    for product in products:
        print(f"  - {product.get('name')}: {product.get('price')}")


if __name__ == "__main__":
    main()
