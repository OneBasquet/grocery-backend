#!/usr/bin/env python3
"""
Example usage script for the Grocery Price Comparison Engine.
This demonstrates common use cases and patterns.
"""

from app.orchestrator import GroceryPriceOrchestrator
from app.utils import format_price, get_best_deal
import pandas as pd


def example_1_scrape_single_retailer():
    """Example 1: Scrape a single retailer."""
    print("\n" + "="*60)
    print("EXAMPLE 1: Scraping Sainsbury's for 'milk'")
    print("="*60 + "\n")
    
    orchestrator = GroceryPriceOrchestrator()
    stats = orchestrator.scrape_retailer("sainsburys", "milk", max_items=10)
    
    print(f"\n✓ Successfully scraped {stats['scraped']} products")
    print(f"  - New products: {stats['inserted']}")
    print(f"  - Updated products: {stats['updated']}")


def example_2_scrape_all_retailers():
    """Example 2: Scrape all retailers."""
    print("\n" + "="*60)
    print("EXAMPLE 2: Scraping all retailers for 'bread'")
    print("="*60 + "\n")
    
    orchestrator = GroceryPriceOrchestrator()
    stats = orchestrator.scrape_all_retailers("bread", max_items=15)
    
    total_scraped = sum(s['scraped'] for s in stats.values())
    print(f"\n✓ Total products scraped: {total_scraped}")


def example_3_compare_prices():
    """Example 3: Compare prices across retailers."""
    print("\n" + "="*60)
    print("EXAMPLE 3: Comparing prices for 'milk'")
    print("="*60 + "\n")
    
    orchestrator = GroceryPriceOrchestrator()
    results = orchestrator.compare_prices("milk", limit=10)
    
    if not results:
        print("No products found. Try scraping first!")
        return
    
    print(f"Found {len(results)} products:\n")
    for i, product in enumerate(results[:5], 1):
        price = format_price(product['price'])
        print(f"{i}. [{product['retailer'].upper()}] {product['name']}")
        print(f"   Price: {price}")
        if product.get('unit_price'):
            print(f"   Unit Price: {product['unit_price']}")
        print()
    
    # Find best deal
    best = get_best_deal(results)
    if best:
        print(f"🏆 Best Deal: {best['name']} at {best['retailer'].upper()}")
        print(f"   Price: {format_price(best['price'])}")


def example_4_export_to_csv():
    """Example 4: Export products to CSV."""
    print("\n" + "="*60)
    print("EXAMPLE 4: Exporting products to CSV")
    print("="*60 + "\n")
    
    orchestrator = GroceryPriceOrchestrator()
    products = orchestrator.db.get_all_products()
    
    if not products:
        print("No products in database. Try scraping first!")
        return
    
    # Convert to DataFrame
    df = pd.DataFrame(products)
    
    # Export to CSV
    filename = "grocery_products.csv"
    df.to_csv(filename, index=False)
    
    print(f"✓ Exported {len(products)} products to {filename}")
    
    # Show summary statistics
    print("\nProduct counts by retailer:")
    print(df['retailer'].value_counts())
    
    print("\nAverage prices by retailer:")
    print(df.groupby('retailer')['price'].mean())


def example_5_find_cheapest_products():
    """Example 5: Find cheapest products by category."""
    print("\n" + "="*60)
    print("EXAMPLE 5: Finding cheapest products")
    print("="*60 + "\n")
    
    orchestrator = GroceryPriceOrchestrator()
    
    categories = ["milk", "bread", "eggs"]
    
    for category in categories:
        results = orchestrator.compare_prices(category, limit=1)
        if results:
            product = results[0]
            print(f"Cheapest {category}:")
            print(f"  {product['name']}")
            print(f"  {product['retailer'].upper()} - {format_price(product['price'])}")
            print()


def example_6_database_operations():
    """Example 6: Direct database operations."""
    print("\n" + "="*60)
    print("EXAMPLE 6: Database operations")
    print("="*60 + "\n")
    
    orchestrator = GroceryPriceOrchestrator()
    
    # Get statistics
    stats = orchestrator.get_database_stats()
    print(f"Total products: {stats['total_products']}")
    print(f"  - Tesco: {stats['tesco']}")
    print(f"  - Sainsbury's: {stats['sainsburys']}")
    print(f"  - Asda: {stats['asda']}")
    
    # Get latest products
    print("\nLatest 5 products:")
    latest = orchestrator.db.get_latest_products(5)
    for product in latest:
        print(f"  - [{product['retailer'].upper()}] {product['name']} - £{product['price']}")


def example_7_custom_scraping():
    """Example 7: Custom scraping with individual scrapers."""
    print("\n" + "="*60)
    print("EXAMPLE 7: Using individual scrapers")
    print("="*60 + "\n")
    
    # Import individual scrapers
    from scrapers.sainsburys_playwright import SainsburysPlaywrightScraper
    from scrapers.asda_playwright import AsdaPlaywrightScraper
    from app.normalizer import ProductNormalizer
    from app.database import Database
    
    # Initialize components
    db = Database()
    normalizer = ProductNormalizer(db)
    
    # Scrape Sainsbury's
    print("Scraping Sainsbury's...")
    sainsburys_scraper = SainsburysPlaywrightScraper(headless=True)
    products = sainsburys_scraper.scrape_search_results("coffee", max_items=5)
    
    # Normalize and insert
    stats = normalizer.batch_insert_products(products, "sainsburys")
    print(f"✓ Scraped {len(products)} coffee products from Sainsbury's")
    print(f"  - Inserted: {stats['inserted']}, Updated: {stats['updated']}")


def main():
    """Run examples."""
    print("\n" + "="*70)
    print("  GROCERY PRICE COMPARISON ENGINE - EXAMPLE USAGE")
    print("="*70)
    
    # Uncomment the examples you want to run:
    
    # example_1_scrape_single_retailer()
    # example_2_scrape_all_retailers()
    # example_3_compare_prices()
    # example_4_export_to_csv()
    # example_5_find_cheapest_products()
    example_6_database_operations()
    # example_7_custom_scraping()
    
    print("\n" + "="*70)
    print("  All examples completed!")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
