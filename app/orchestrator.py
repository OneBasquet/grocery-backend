"""
Main orchestrator for the grocery price comparison engine.
Coordinates scraping, normalization, and database operations.
"""
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add parent directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database import Database
from app.normalizer import ProductNormalizer
from scrapers.tesco_playwright import TescoPlaywrightScraper  # Using Playwright instead of Apify
from scrapers.sainsburys_playwright import SainsburysPlaywrightScraper
from scrapers.asda_playwright import AsdaPlaywrightScraper


class GroceryPriceOrchestrator:
    """Main orchestrator for the grocery price comparison system."""
    
    def __init__(self, db_path: str = "products.db", fuzzy_threshold: int = 85, fetch_gtin: bool = False):
        """
        Initialize the orchestrator.
        
        Args:
            db_path: Path to SQLite database
            fuzzy_threshold: Threshold for fuzzy matching (0-100)
            fetch_gtin: Whether to fetch GTINs from product detail pages (slower)
        """
        self.db = Database(db_path)
        self.normalizer = ProductNormalizer(self.db, fuzzy_threshold)
        self.fetch_gtin = fetch_gtin
        
        # Initialize scrapers (will be created on-demand)
        self._tesco_scraper = None
        self._sainsburys_scraper = None
        self._asda_scraper = None
    
    @property
    def tesco_scraper(self) -> TescoPlaywrightScraper:
        """Lazy load Tesco scraper (now using Playwright instead of Apify)."""
        if self._tesco_scraper is None:
            # Use headless=False to avoid bot detection
            self._tesco_scraper = TescoPlaywrightScraper(headless=False)
        return self._tesco_scraper
    
    @property
    def sainsburys_scraper(self) -> SainsburysPlaywrightScraper:
        """Lazy load Sainsbury's scraper."""
        if self._sainsburys_scraper is None:
            # Use headless=False to avoid bot detection
            # Pass fetch_gtin flag to enable/disable GTIN fetching from detail pages
            self._sainsburys_scraper = SainsburysPlaywrightScraper(
                headless=False, 
                fetch_gtin=self.fetch_gtin
            )
        return self._sainsburys_scraper
    
    @property
    def asda_scraper(self) -> AsdaPlaywrightScraper:
        """Lazy load Asda scraper."""
        if self._asda_scraper is None:
            # Use headless=False to avoid bot detection
            self._asda_scraper = AsdaPlaywrightScraper(headless=False)
        return self._asda_scraper
    
    def scrape_all_retailers(self, search_query: str, max_items: int = 50,
                             skip_retailers: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Scrape all retailers for a given search query.

        Args:
            search_query: Search term (e.g., "milk", "bread")
            max_items: Maximum items per retailer
            skip_retailers: List of retailer names to skip (e.g. ["tesco"])

        Returns:
            Dictionary with scraping statistics
        """
        skip = set(r.lower() for r in (skip_retailers or []))

        print(f"\n{'='*60}")
        print(f"🛒 SCRAPING ALL RETAILERS: '{search_query}'")
        if skip:
            print(f"   Skipping: {', '.join(skip)}")
        print(f"{'='*60}\n")

        total_stats = {
            'tesco': {'scraped': 0, 'inserted': 0, 'updated': 0, 'matched': 0, 'errors': 0},
            'sainsburys': {'scraped': 0, 'inserted': 0, 'updated': 0, 'matched': 0, 'errors': 0},
            'asda': {'scraped': 0, 'inserted': 0, 'updated': 0, 'matched': 0, 'errors': 0}
        }

        # Scrape Tesco
        if 'tesco' not in skip:
            try:
                tesco_products = self.tesco_scraper.scrape_search_results(search_query, max_items)
                total_stats['tesco']['scraped'] = len(tesco_products)

                if tesco_products:
                    stats = self.normalizer.batch_insert_products(tesco_products, 'tesco')
                    total_stats['tesco'].update(stats)
            except Exception as e:
                print(f"✗ Tesco scraping failed: {e}")
                total_stats['tesco']['errors'] = 1

        # Scrape Sainsbury's
        if 'sainsburys' not in skip:
            try:
                sainsburys_products = self.sainsburys_scraper.scrape_search_results(search_query, max_items)
                total_stats['sainsburys']['scraped'] = len(sainsburys_products)

                if sainsburys_products:
                    stats = self.normalizer.batch_insert_products(sainsburys_products, 'sainsburys')
                    total_stats['sainsburys'].update(stats)
            except Exception as e:
                print(f"✗ Sainsbury's scraping failed: {e}")
                total_stats['sainsburys']['errors'] = 1

        # Scrape Asda
        if 'asda' not in skip:
            try:
                asda_products = self.asda_scraper.scrape_search_results(search_query, max_items)
                total_stats['asda']['scraped'] = len(asda_products)

                if asda_products:
                    stats = self.normalizer.batch_insert_products(asda_products, 'asda')
                    total_stats['asda'].update(stats)
            except Exception as e:
                print(f"✗ Asda scraping failed: {e}")
                total_stats['asda']['errors'] = 1

        # Print summary
        self._print_summary(total_stats)

        return total_stats
    
    def scrape_retailer(self, retailer: str, search_query: str, max_items: int = 50) -> Dict[str, Any]:
        """
        Scrape a specific retailer.
        
        Args:
            retailer: Retailer name ('tesco', 'sainsburys', 'asda')
            search_query: Search term
            max_items: Maximum items to scrape
            
        Returns:
            Dictionary with scraping statistics
        """
        retailer = retailer.lower()
        
        print(f"\n{'='*60}")
        print(f"🛒 SCRAPING {retailer.upper()}: '{search_query}'")
        print(f"{'='*60}\n")
        
        products = []
        
        if retailer == 'tesco':
            products = self.tesco_scraper.scrape_search_results(search_query, max_items)
        elif retailer == 'sainsburys':
            products = self.sainsburys_scraper.scrape_search_results(search_query, max_items)
        elif retailer == 'asda':
            products = self.asda_scraper.scrape_search_results(search_query, max_items)
        else:
            raise ValueError(f"Unknown retailer: {retailer}")
        
        # Normalize and insert products
        stats = self.normalizer.batch_insert_products(products, retailer)
        stats['scraped'] = len(products)
        
        print(f"\n✓ {retailer.upper()} Summary:")
        print(f"  Scraped: {stats['scraped']}")
        print(f"  Inserted: {stats['inserted']}")
        print(f"  Updated: {stats['updated']}")
        print(f"  Matched: {stats['matched']}")
        print(f"  Errors: {stats['errors']}")
        
        return stats
    
    def compare_prices(self, search_query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Compare prices across all retailers for similar products.
        
        Args:
            search_query: Product search term (empty string returns all products)
            limit: Maximum results per retailer (ignored if search_query is empty)
            
        Returns:
            List of product comparisons sorted by price
        """
        results = []
        
        for retailer in ['tesco', 'sainsburys', 'asda']:
            products = self.db.get_all_products(retailer)
            
            # Filter products matching search query and with valid prices
            if search_query:
                # Try GTIN exact match first, then fall back to name substring
                gtin_matches = [
                    p for p in products
                    if p.get('gtin') and p['gtin'] == search_query and p['price'] > 0
                ]
                if gtin_matches:
                    matching = gtin_matches[:limit]
                else:
                    from thefuzz import fuzz

                    query_lower = search_query.lower()
                    words = query_lower.split()
                    scored = []

                    for p in products:
                        if p['price'] <= 0:
                            continue
                        name_lower = p['name'].lower()
                        text = name_lower + ' ' + (p.get('retailer') or '').lower()

                        # Tier 1: all words present (any order) — best
                        if all(w in text for w in words):
                            scored.append((p, 200))
                            continue

                        # Tier 2: fuzzy match on full query vs name
                        ratio = fuzz.token_set_ratio(query_lower, name_lower)
                        if ratio >= 60:
                            scored.append((p, ratio))

                    scored.sort(key=lambda x: x[1], reverse=True)
                    matching = [p for p, _ in scored][:limit]
            else:
                # Return all products with valid prices (no limit)
                matching = [p for p in products if p['price'] > 0]

            results.extend(matching)

        # Sort by relevance first (exact word matches), then price
        # Re-score all results so sorting is consistent across retailers
        from thefuzz import fuzz as _fuzz
        query_lower = search_query.lower() if search_query else ""

        def _sort_key(p):
            if not query_lower:
                return (0, p['price'])
            text = p['name'].lower() + ' ' + (p.get('retailer') or '').lower()
            words = query_lower.split()
            has_all = all(w in text for w in words)
            ratio = _fuzz.token_set_ratio(query_lower, p['name'].lower())
            # Sort: exact word matches first, then by fuzzy score desc, then price asc
            return (0 if has_all else 1, -ratio, p['price'])

        results.sort(key=_sort_key)
        
        return results
    
    def find_savings_opportunities(self, min_percentage: float = 10.0, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Find products with significant price differences between retailers.
        Uses GTIN matching first, then fuzzy name matching as fallback.
        
        Args:
            min_percentage: Minimum price difference percentage (default: 10%)
            limit: Maximum number of results to return
            
        Returns:
            List of dictionaries containing savings opportunities with:
            - product_name: Product name
            - cheapest_retailer: Retailer with lowest price
            - cheapest_price: Lowest price
            - expensive_retailer: Retailer with highest price
            - expensive_price: Highest price
            - savings_amount: Absolute savings (£)
            - savings_percentage: Percentage savings
        """
        from thefuzz import fuzz
        
        savings = []
        processed = set()  # Track processed product pairs to avoid duplicates
        
        # Get all products from all retailers.
        # Use ProductNormalizer.effective_price() so that any member/loyalty price
        # (e.g. Tesco Clubcard) is used when it is lower than the shelf price.
        retailers_data = {}
        for retailer in ['tesco', 'sainsburys', 'asda']:
            products = []
            for p in self.db.get_all_products(retailer):
                if (p.get('price') or 0) <= 0:
                    continue
                effective_p = self.normalizer.effective_price(p)
                effective = dict(p)
                effective['price'] = effective_p
                if effective_p != float(p['price']):
                    effective['_price_note'] = f"Member price £{effective_p:.2f}"
                products.append(effective)
            retailers_data[retailer] = products
        
        # Strategy 1: Match by GTIN (exact match)
        gtin_groups = {}
        for retailer, products in retailers_data.items():
            for product in products:
                gtin = product.get('gtin')
                if gtin:
                    if gtin not in gtin_groups:
                        gtin_groups[gtin] = []
                    gtin_groups[gtin].append({
                        'retailer': retailer,
                        'name': product['name'],
                        'price': product['price'],
                        'gtin': gtin
                    })
        
        # Process GTIN matches
        for gtin, product_list in gtin_groups.items():
            if len(product_list) < 2:  # Need at least 2 retailers
                continue
            
            product_list.sort(key=lambda x: x['price'])
            cheapest = product_list[0]
            most_expensive = product_list[-1]
            
            # Skip if same retailer
            if cheapest['retailer'] == most_expensive['retailer']:
                continue
            
            price_diff = most_expensive['price'] - cheapest['price']
            percentage_diff = (price_diff / most_expensive['price']) * 100
            
            if percentage_diff >= min_percentage:
                pair_key = f"{gtin}_{cheapest['retailer']}_{most_expensive['retailer']}"
                processed.add(pair_key)
                
                savings.append({
                    'product_name': cheapest['name'],
                    'cheapest_retailer': cheapest['retailer'],
                    'cheapest_price': cheapest['price'],
                    'cheapest_is_member': bool(cheapest.get('_price_note')),
                    'expensive_retailer': most_expensive['retailer'],
                    'expensive_price': most_expensive['price'],
                    'savings_amount': price_diff,
                    'savings_percentage': percentage_diff,
                    'gtin': gtin,
                    'match_type': 'GTIN'
                })
        
        # Strategy 2: Fuzzy name matching for products without GTIN or cross-retailer
        fuzzy_threshold = 80  # 80% similarity
        
        # Compare products across retailers
        for retailer1, products1 in retailers_data.items():
            for retailer2, products2 in retailers_data.items():
                if retailer1 >= retailer2:  # Avoid duplicate comparisons
                    continue
                
                for p1 in products1:
                    for p2 in products2:
                        # Skip if both have same GTIN (already processed)
                        if p1.get('gtin') and p2.get('gtin') and p1['gtin'] == p2['gtin']:
                            continue
                        
                        # Calculate name similarity
                        similarity = fuzz.token_sort_ratio(
                            p1['name'].lower(),
                            p2['name'].lower()
                        )
                        
                        if similarity >= fuzzy_threshold:
                            # Found a match!
                            if p1['price'] < p2['price']:
                                cheapest, expensive = p1, p2
                                cheap_retailer, exp_retailer = retailer1, retailer2
                            else:
                                cheapest, expensive = p2, p1
                                cheap_retailer, exp_retailer = retailer2, retailer1
                            
                            price_diff = expensive['price'] - cheapest['price']
                            percentage_diff = (price_diff / expensive['price']) * 100
                            
                            if percentage_diff >= min_percentage:
                                # Create unique key to avoid duplicates
                                name_key = cheapest['name'].lower()[:30]
                                pair_key = f"{name_key}_{cheap_retailer}_{exp_retailer}"
                                
                                if pair_key not in processed:
                                    processed.add(pair_key)
                                    
                                    savings.append({
                                        'product_name': cheapest['name'],
                                        'cheapest_retailer': cheap_retailer,
                                        'cheapest_price': cheapest['price'],
                                        'cheapest_is_member': bool(cheapest.get('_price_note')),
                                        'expensive_retailer': exp_retailer,
                                        'expensive_price': expensive['price'],
                                        'savings_amount': price_diff,
                                        'savings_percentage': percentage_diff,
                                        'gtin': cheapest.get('gtin'),
                                        'match_type': f'Fuzzy ({similarity}%)'
                                    })
        
        # Sort by savings percentage (highest first)
        savings.sort(key=lambda x: x['savings_percentage'], reverse=True)
        
        return savings[:limit]
    
    def get_database_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the database.
        
        Returns:
            Dictionary with database statistics
        """
        total = self.db.get_product_count()
        tesco_count = len(self.db.get_all_products('tesco'))
        sainsburys_count = len(self.db.get_all_products('sainsburys'))
        asda_count = len(self.db.get_all_products('asda'))
        
        return {
            'total_products': total,
            'tesco': tesco_count,
            'sainsburys': sainsburys_count,
            'asda': asda_count
        }
    
    def _print_summary(self, stats: Dict[str, Dict[str, int]]):
        """Print a summary of scraping results."""
        print(f"\n{'='*60}")
        print("📊 SCRAPING SUMMARY")
        print(f"{'='*60}\n")
        
        for retailer, retailer_stats in stats.items():
            print(f"{retailer.upper()}:")
            print(f"  Scraped: {retailer_stats['scraped']}")
            print(f"  Inserted: {retailer_stats['inserted']}")
            print(f"  Updated: {retailer_stats['updated']}")
            print(f"  Matched: {retailer_stats['matched']}")
            print(f"  Errors: {retailer_stats['errors']}")
            print()
        
        # Database stats
        db_stats = self.get_database_stats()
        print(f"DATABASE TOTALS:")
        print(f"  Total Products: {db_stats['total_products']}")
        print(f"  Tesco: {db_stats['tesco']}")
        print(f"  Sainsbury's: {db_stats['sainsburys']}")
        print(f"  Asda: {db_stats['asda']}")
        print(f"{'='*60}\n")


def main():
    """Example usage of the orchestrator."""
    orchestrator = GroceryPriceOrchestrator()
    
    # Example 1: Scrape all retailers
    # orchestrator.scrape_all_retailers("milk", max_items=20)
    
    # Example 2: Scrape single retailer
    orchestrator.scrape_retailer("sainsburys", "bread", max_items=10)
    
    # Example 3: Compare prices
    # comparisons = orchestrator.compare_prices("milk", limit=5)
    # for product in comparisons:
    #     print(f"{product['retailer']}: {product['name']} - £{product['price']}")


if __name__ == "__main__":
    main()
