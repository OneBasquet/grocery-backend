"""
Warm-cache worker: pre-populates the database by scraping the most common
grocery items so that users get instant results instead of cold-start delays.

Usage:
    python -m app.worker                  # scrape all 100 seed terms
    python -m app.worker --limit 10       # scrape first 10 only
    python -m app.worker --term "eggs"    # scrape a single term
"""
import argparse
import json
import random
import time
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.orchestrator import GroceryPriceOrchestrator

SEED_FILE = Path(__file__).resolve().parent.parent / "config" / "seed_terms.json"


def load_seed_terms() -> list[str]:
    with open(SEED_FILE) as f:
        return json.load(f)


def run(terms: list[str], max_items: int = 20):
    orchestrator = GroceryPriceOrchestrator()
    total = len(terms)

    print(f"\n{'='*60}")
    print(f"  WARM-CACHE WORKER — {total} terms to scrape")
    print(f"{'='*60}\n")

    for i, term in enumerate(terms, 1):
        print(f"[{i}/{total}] Scraping '{term}'...")
        try:
            stats = orchestrator.scrape_all_retailers(term, max_items=max_items)
            scraped = sum(s["scraped"] for s in stats.values())
            errors = sum(s["errors"] for s in stats.values())
            print(f"  -> {scraped} products scraped, {errors} errors\n")
        except Exception as e:
            print(f"  -> FAILED: {e}\n")

        if i < total:
            delay = random.uniform(5, 10)
            print(f"  Waiting {delay:.1f}s before next term...")
            time.sleep(delay)

    db_stats = orchestrator.get_database_stats()
    print(f"\n{'='*60}")
    print(f"  WARM-CACHE COMPLETE")
    print(f"  Total products in DB: {db_stats['total_products']}")
    print(f"  Tesco: {db_stats['tesco']} | Sainsbury's: {db_stats['sainsburys']} | Asda: {db_stats['asda']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Warm-cache worker for grocery DB")
    parser.add_argument("--limit", type=int, default=0, help="Only scrape the first N terms")
    parser.add_argument("--term", type=str, help="Scrape a single term instead of the seed list")
    parser.add_argument("--max-items", type=int, default=20, help="Max products per retailer per term")
    args = parser.parse_args()

    if args.term:
        terms = [args.term]
    else:
        terms = load_seed_terms()
        if args.limit > 0:
            terms = terms[:args.limit]

    run(terms, max_items=args.max_items)
