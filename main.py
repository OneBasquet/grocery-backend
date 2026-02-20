#!/usr/bin/env python3
"""
Main entry point for the Grocery Price Comparison Engine.
"""
import argparse
from app.orchestrator import GroceryPriceOrchestrator


def main():
    """Main CLI interface for the grocery price comparison engine."""
    parser = argparse.ArgumentParser(
        description='Grocery Price Comparison Engine - Compare prices across Tesco, Sainsbury\'s, and Asda'
    )
    
    parser.add_argument(
        'command',
        choices=['scrape', 'compare', 'stats', 'savings'],
        help='Command to execute'
    )
    
    parser.add_argument(
        '--query',
        '-q',
        type=str,
        help='Search query (e.g., "milk", "bread")',
        required=False
    )
    
    parser.add_argument(
        '--retailer',
        '-r',
        choices=['all', 'tesco', 'sainsburys', 'asda'],
        default='all',
        help='Retailer to scrape (default: all)'
    )
    
    parser.add_argument(
        '--max-items',
        '-m',
        type=int,
        default=50,
        help='Maximum number of items to scrape per retailer (default: 50)'
    )
    
    parser.add_argument(
        '--limit',
        '-l',
        type=int,
        default=10,
        help='Maximum number of results to show for compare command (default: 10)'
    )
    
    parser.add_argument(
        '--db',
        type=str,
        default='products.db',
        help='Path to SQLite database (default: products.db)'
    )
    
    parser.add_argument(
        '--fuzzy-threshold',
        type=int,
        default=85,
        help='Fuzzy matching threshold 0-100 (default: 85)'
    )
    
    parser.add_argument(
        '--fetch-gtin',
        action='store_true',
        help='Fetch GTINs from product detail pages (slower but more accurate for Sainsbury\'s)'
    )
    
    args = parser.parse_args()
    
    # Initialize orchestrator
    orchestrator = GroceryPriceOrchestrator(
        db_path=args.db,
        fuzzy_threshold=args.fuzzy_threshold,
        fetch_gtin=args.fetch_gtin
    )
    
    # Execute command
    if args.command == 'scrape':
        if not args.query:
            print("❌ Error: --query is required for scrape command")
            return 1
        
        if args.retailer == 'all':
            orchestrator.scrape_all_retailers(args.query, args.max_items)
        else:
            orchestrator.scrape_retailer(args.retailer, args.query, args.max_items)
    
    elif args.command == 'compare':
        # Allow comparing all products if no query provided
        if args.query:
            results = orchestrator.compare_prices(args.query, args.limit)
            query_display = f"'{args.query}'"
        else:
            results = orchestrator.compare_prices("", args.limit)
            query_display = "All Products"
        
        if not results:
            if args.query:
                print(f"No products found matching '{args.query}'")
            else:
                print(f"No products found in database")
            return 0
        
        print(f"\n{'='*80}")
        print(f"💰 PRICE COMPARISON: {query_display}")
        print(f"{'='*80}\n")
        
        print(f"{'Retailer':<15} {'Price':<10} {'Unit Price':<20} {'Product Name'}")
        print(f"{'-'*80}")
        
        for product in results:
            retailer = product['retailer'].upper()
            price = f"£{product['price']:.2f}" if isinstance(product['price'], (int, float)) else product['price']
            
            # Clean up unit price (remove duplicate prices)
            unit_price = product.get('unit_price', 'N/A') or 'N/A'
            if unit_price != 'N/A' and '£' in unit_price:
                # Extract just the unit price part (after /)
                import re
                unit_match = re.search(r'£[\d.]+\s*/\s*\w+', unit_price)
                if unit_match:
                    unit_price = unit_match.group()
            
            name = product['name'][:40] + '...' if len(product['name']) > 40 else product['name']
            
            print(f"{retailer:<15} {price:<10} {unit_price:<20} {name}")
        
        print(f"\n{'='*80}\n")
    
    elif args.command == 'stats':
        stats = orchestrator.get_database_stats()
        
        print(f"\n{'='*60}")
        print("📊 DATABASE STATISTICS")
        print(f"{'='*60}\n")
        print(f"Total Products: {stats['total_products']}")
        print(f"  ├─ Tesco: {stats['tesco']}")
        print(f"  ├─ Sainsbury's: {stats['sainsburys']}")
        print(f"  └─ Asda: {stats['asda']}")
        print(f"{'='*60}\n")
        
        # Show latest products
        latest = orchestrator.db.get_latest_products(5)
        if latest:
            print("🕐 Latest Products:")
            for product in latest:
                print(f"  • [{product['retailer'].upper()}] {product['name']} - £{product['price']}")
            print()
    
    elif args.command == 'savings':
        savings = orchestrator.find_savings_opportunities(min_percentage=10.0, limit=args.limit)
        
        if not savings:
            print("\n💡 No significant savings opportunities found (>10% difference)")
            print("   Try scraping more products from different retailers!\n")
            return 0
        
        print(f"\n{'='*110}")
        print(f"💰 SAVINGS OPPORTUNITIES (>{10}% price difference)")
        print(f"{'='*110}\n")
        print(f"Found {len(savings)} products where you can save money by shopping at different retailers!\n")
        
        print(f"{'Product':<40} {'Cheapest':<12} {'Most Exp.':<12} {'You Save':<15} {'Save %':<10} {'Match'}")
        print(f"{'-'*110}")
        
        for item in savings:
            product_name = item['product_name'][:37] + '...' if len(item['product_name']) > 37 else item['product_name']
            cheapest = f"{item['cheapest_retailer'].upper()[:4]} £{item['cheapest_price']:.2f}"
            expensive = f"{item['expensive_retailer'].upper()[:4]} £{item['expensive_price']:.2f}"
            savings_str = f"£{item['savings_amount']:.2f}"
            percentage = f"{item['savings_percentage']:.1f}%"
            match_type = item.get('match_type', 'GTIN')
            
            print(f"{product_name:<40} {cheapest:<12} {expensive:<12} {savings_str:<15} {percentage:<10} {match_type}")
        
        total_savings = sum(item['savings_amount'] for item in savings)
        print(f"\n{'-'*110}")
        print(f"💵 TOTAL POTENTIAL SAVINGS: £{total_savings:.2f}")
        print(f"{'='*110}\n")
    
    return 0


if __name__ == "__main__":
    exit(main())
