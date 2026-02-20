"""
Sainsbury's scraper using Apify client.
Uses a dedicated Sainsbury's Apify actor for faster, more reliable scraping with GTINs.
"""
from apify_client import ApifyClient
from typing import List, Dict, Any, Optional
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config.settings import APIFY_API_TOKEN


class SainsburysApifyScraper:
    """Scraper for Sainsbury's using Apify platform."""
    
    def __init__(self, api_token: Optional[str] = None):
        """
        Initialize the Sainsbury's Apify scraper.
        
        Args:
            api_token: Apify API token (optional, defaults to env variable)
        """
        self.api_token = api_token or APIFY_API_TOKEN
        
        if not self.api_token:
            raise ValueError("APIFY_API_TOKEN not found. Please set it in your .env file")
        
        self.client = ApifyClient(self.api_token)
        self.retailer = "sainsburys"
        
        # Sainsbury's Groceries scraper actor
        # Source: https://console.apify.com/actors/zGhd4ucc2ffvbsw2k
        self.actor_id = "zGhd4ucc2ffvbsw2k"
    
    def scrape_search_results(self, search_query: str, max_items: int = 100) -> List[Dict[str, Any]]:
        """
        Scrape Sainsbury's search results for a given query.
        
        Args:
            search_query: Search term (e.g., "milk", "bread")
            max_items: Maximum number of products to scrape
            
        Returns:
            List of product dictionaries with keys: name, gtin, price, unit_price, retailer
        """
        # Build search URL for Sainsbury's
        search_url = f"https://www.sainsburys.co.uk/gol-ui/SearchResults/{search_query}"
        
        # Input configuration for the Sainsbury's actor
        run_input = {
            "startUrls": [search_url],
            "maxItems": max_items,
            "scrapeAdditionalData": True  # Get nutrition, description, etc. (includes GTIN)
        }
        
        try:
            print(f"🔄 Starting Sainsbury's scrape for: '{search_query}'")
            run = self.client.actor(self.actor_id).call(run_input=run_input)
            
            # Fetch results from the dataset
            products = []
            for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
                # Normalize the data structure
                # Apify actors may use different field names, so we handle variations
                normalized = {
                    "name": item.get("title") or item.get("name") or item.get("productName", ""),
                    "gtin": (
                        item.get("gtin") or 
                        item.get("ean") or 
                        item.get("barcode") or 
                        item.get("productCode")
                    ),
                    "price": self._extract_price(item),
                    "unit_price": item.get("unitPrice") or item.get("pricePerUnit"),
                    "url": item.get("url") or item.get("productUrl"),
                    "retailer": "sainsburys"
                }
                
                # Only add if we have at least a name and price
                if normalized["name"] and normalized["price"] is not None:
                    products.append(normalized)
            
            print(f"✓ Scraped {len(products)} products from Sainsbury's")
            return products
            
        except Exception as e:
            print(f"✗ Error scraping Sainsbury's via Apify: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _extract_price(self, item: Dict[str, Any]) -> Optional[float]:
        """
        Extract price from various possible fields.
        
        Args:
            item: Raw product data from Apify
            
        Returns:
            Price as float or None
        """
        # Try different price field names
        price_fields = ['price', 'currentPrice', 'salePrice', 'retailPrice']
        
        for field in price_fields:
            if field in item:
                price_value = item[field]
                
                # Handle different price formats
                if isinstance(price_value, (int, float)):
                    return float(price_value)
                elif isinstance(price_value, str):
                    # Remove currency symbols and parse
                    try:
                        clean_price = price_value.replace('£', '').replace('$', '').replace(',', '').strip()
                        return float(clean_price)
                    except (ValueError, AttributeError):
                        continue
        
        return None


def main():
    """Example usage of the Sainsbury's Apify scraper."""
    scraper = SainsburysApifyScraper()
    
    # Example: Search for milk
    products = scraper.scrape_search_results("milk", max_items=10)
    
    print(f"\nFound {len(products)} products:")
    for product in products[:5]:  # Show first 5
        gtin = product.get('gtin', 'No GTIN')
        print(f"  - {product.get('name')}: £{product.get('price')} (GTIN: {gtin})")


if __name__ == "__main__":
    main()
