"""
Tesco scraper using Apify client.
Integrates with Apify's actors to scrape Tesco grocery data.
"""
from apify_client import ApifyClient
from typing import List, Dict, Any, Optional
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config.settings import APIFY_API_TOKEN


class TescoApifyScraper:
    """Scraper for Tesco using Apify platform."""
    
    def __init__(self, api_token: Optional[str] = None):
        """
        Initialize the Tesco Apify scraper.
        
        Args:
            api_token: Apify API token (optional, defaults to env variable)
        """
        self.api_token = api_token or APIFY_API_TOKEN
        
        if not self.api_token:
            raise ValueError("APIFY_API_TOKEN not found. Please set it in your .env file")
        
        self.client = ApifyClient(self.api_token)
        self.retailer = "tesco"
    
    def scrape_search_results(self, search_query: str, max_items: int = 100) -> List[Dict[str, Any]]:
        """
        Scrape Tesco search results for a given query.
        
        Args:
            search_query: Search term (e.g., "milk", "bread")
            max_items: Maximum number of products to scrape
            
        Returns:
            List of product dictionaries with keys: name, gtin, price, retailer
        """
        # Use specialized Tesco scraper actor
        actor_id = "radeance/tesco-scraper"
        
        # Simple input format for the Tesco actor
        run_input = {
            "keyword": search_query,
            "max_items": max_items
        }
        
        try:
            print(f"🔄 Starting Tesco scrape for: '{search_query}'")
            run = self.client.actor(actor_id).call(run_input=run_input)
            
            # Fetch results from the dataset
            products = []
            for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
                # Normalize the data structure
                normalized = {
                    "name": item.get("name", ""),
                    "gtin": item.get("gtin"),
                    "price": item.get("price"),
                    "unit_price": item.get("unit_price"),
                    "url": item.get("url"),
                    "retailer": "tesco"
                }
                products.append(normalized)
            
            print(f"✓ Scraped {len(products)} products from Tesco")
            return products
            
        except Exception as e:
            print(f"✗ Error scraping Tesco: {e}")
            import traceback
            traceback.print_exc()
            return []
    


def main():
    """Example usage of the Tesco Apify scraper."""
    scraper = TescoApifyScraper()
    
    # Example: Search for milk
    products = scraper.scrape_search_results("milk", max_items=20)
    
    print(f"\nFound {len(products)} products:")
    for product in products[:5]:  # Show first 5
        print(f"  - {product.get('name')}: {product.get('price')}")


if __name__ == "__main__":
    main()
