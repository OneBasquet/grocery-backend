"""
Warm-cache worker: pre-populates the database by scraping the most common
grocery items so that users get instant results instead of cold-start delays.

Usage:
    python -m app.worker                          # scrape all seed terms, all retailers
    python -m app.worker --limit 10               # scrape first 10 only
    python -m app.worker --term "eggs"            # scrape a single term
    python -m app.worker --skip tesco             # skip Tesco
    python -m app.worker --only sainsburys asda   # only these retailers
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


def run(terms: list[str], max_items: int = 20, skip_retailers: list[str] = None):
    orchestrator = GroceryPriceOrchestrator()
    total = len(terms)

    print(f"\n{'='*60}")
    print(f"  WARM-CACHE WORKER — {total} terms to scrape")
    if skip_retailers:
        print(f"  Skipping: {', '.join(skip_retailers)}")
    print(f"{'='*60}\n")

    for i, term in enumerate(terms, 1):
        print(f"[{i}/{total}] Scraping '{term}'...")
        try:
            stats = orchestrator.scrape_all_retailers(
                term, max_items=max_items, skip_retailers=skip_retailers
            )
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
    all_retailers = ["tesco", "sainsburys", "asda"]

    parser = argparse.ArgumentParser(description="Warm-cache worker for grocery DB")
    parser.add_argument("--limit", type=int, default=0, help="Only scrape the first N terms")
    parser.add_argument("--term", type=str, help="Scrape a single term instead of the seed list")
    parser.add_argument("--max-items", type=int, default=20, help="Max products per retailer per term")
    parser.add_argument("--skip", nargs="+", default=[], help="Retailers to skip (e.g. --skip tesco)")
    parser.add_argument("--only", nargs="+", default=[], help="Only scrape these retailers (e.g. --only sainsburys asda)")
    args = parser.parse_args()

    if args.term:
        terms = [args.term]
    else:
        terms = load_seed_terms()
        if args.limit > 0:
            terms = terms[:args.limit]

    # Build skip list from --skip or --only
    skip = [r.lower() for r in args.skip]
    if args.only:
        only = [r.lower() for r in args.only]
        skip = [r for r in all_retailers if r not in only]

    run(terms, max_items=args.max_items, skip_retailers=skip or None)
