# Grocery Price Comparison Engine

A Python-based price comparison system that scrapes grocery products from Tesco, Sainsbury's, and Asda — including **loyalty scheme prices** (Tesco Clubcard & Sainsbury's Nectar) — and finds genuine savings opportunities using intelligent fuzzy matching.

## Quick Start

```bash
# Setup
conda activate grocery-backend

# Scrape a category across all three retailers
python main.py scrape --query "milk" --retailer all --max-items 20

# Compare prices (loyalty prices shown in Member Price column)
python main.py compare --query "milk"

# Find savings opportunities (>10% difference, loyalty prices factored in)
python main.py savings

# Database stats
python main.py stats
```

## Features

- **Three working scrapers** — Playwright-based scrapers for Tesco, Sainsbury's, and Asda; no paid APIs required
- **Loyalty price capture** — Tesco Clubcard prices extracted from `xapi.tesco.com` promotion descriptions; Sainsbury's Nectar prices extracted via DOM parent-search
- **Effective price logic** — `ProductNormalizer.effective_price()` uses the loyalty price in savings calculations when it is lower than the shelf price
- **Query-scoped scraping** — Tesco's API returns trending/recommended products alongside search results; an automatic filter discards off-topic products and falls back to HTML parsing
- **Fuzzy matching** — Matches products across retailers with 80–100% accuracy using `thefuzz.token_sort_ratio()`
- **GTIN + fuzzy deduplication** — GTIN exact match first, fuzzy name match as fallback; both paths now write updated prices and member prices back to the DB on every scrape
- **SQLite storage** — Normalized schema with `member_price` column, automatic upserts, and timestamps
- **CLI interface** — `scrape`, `compare`, `savings`, `stats`, `report` commands

## Project Structure

```
grocery-backend/
├── main.py                          # CLI entry point
├── app/
│   ├── database.py                  # SQLite operations (inc. update_product_by_id)
│   ├── normalizer.py                # Data cleaning, fuzzy matching, effective_price()
│   └── orchestrator.py             # Scrape → normalise → store coordination
├── scrapers/
│   ├── tesco_playwright.py          # Tesco: API interception + HTML fallback
│   ├── sainsburys_playwright.py     # Sainsbury's: DOM scraping + Nectar parent-search
│   └── asda_playwright.py          # Asda: Algolia API interception + HTML fallback
├── tests/
│   ├── test_database.py
│   └── test_normalizer.py
├── products.db                      # SQLite database
├── requirements.txt
└── environment.yml
```

## Loyalty Scheme Prices

### Tesco Clubcard (`🎫 CC`)

Tesco's internal GraphQL API (`xapi.tesco.com`) returns a `promotions` array inside each seller result. Clubcard promotions are identified by `"CLUBCARD_PRICING"` in the `attributes` field. The numeric price is parsed from the `description` string (e.g. `"£3.00 Clubcard Price"`) using a regex, since `price.afterDiscount` in the API response echoes the regular shelf price.

Multi-buy promotions (e.g. `"Any 2 for £3.50 Clubcard Price"`) are skipped as the per-unit price cannot be determined.

### Sainsbury's Nectar (`🌟 Nectar`)

Sainsbury's search results pages render Nectar price elements with `data-testid="nectar-price-label"`. Two extraction strategies run per scrape:

1. **Parent-search** (pre-loop): all Nectar elements on the page are located, then a JavaScript ancestor-walk finds which product tile each belongs to, building a `tile_index → price` map before the iteration starts.
2. **Within-tile fallback**: if a tile has no entry in the map, known selectors and a text-line scan are tried directly on that tile.

The shelf price selector explicitly excludes `[data-testid*="nectar"]` elements, and the line-scan skips any value numerically equal to the known Nectar price, so shelf price and loyalty price are always stored separately.

### Effective Price in Savings

`ProductNormalizer.effective_price(product)` returns `member_price` when it is both present and strictly lower than the shelf price; otherwise it returns the shelf price. This is used in `find_savings_opportunities()` for all retailers, so a Clubcard or Nectar price automatically makes a product appear cheaper in the savings ranking.

## Database Schema

```sql
CREATE TABLE products (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    gtin             TEXT,           -- Barcode (when available)
    name             TEXT NOT NULL,  -- Product name
    price            REAL NOT NULL,  -- Regular shelf price
    unit_price       TEXT,           -- Normalised unit price (e.g. "1.74/kg")
    retailer         TEXT NOT NULL,  -- "tesco" | "sainsburys" | "asda"
    timestamp        DATETIME,       -- Last scrape time
    created_at       DATETIME,       -- First insertion
    updated_at       DATETIME,       -- Last update
    is_clubcard_price INTEGER DEFAULT 0,  -- 1 if any member price exists
    normal_price     REAL,           -- Pre-offer price (when known)
    member_price     REAL            -- Clubcard / Nectar price
);
```

## Commands

### Scrape
```bash
# Single retailer
python main.py scrape --query "cheese" --retailer tesco --max-items 20

# All retailers at once
python main.py scrape --query "bread" --retailer all --max-items 20
```

### Compare
```bash
# Compare by product category
python main.py compare --query "milk"

# Show all products in the DB
python main.py compare
```

Example output:
```
Retailer        Price      Member Price      Unit Price    Product Name
------------------------------------------------------------------------
TESCO           £1.75      🎫 CC £1.25       21.88/kg      Cheestrings Original 4 Pack
TESCO           £2.95      🎫 CC £2.00       14.75/kg      Président French Brie 200g
SAINSBURYS      £2.65      🌟 Nectar £2.00   1.33/litre    Cravendale Whole Milk 2L
ASDA            £1.64                        1.64/litre    Cravendale Semi Skimmed 2L
```

### Savings
```bash
python main.py savings --limit 20
```

Example output:
```
Product                       Cheapest              Most Exp.     You Save   Save %
------------------------------------------------------------------------------------
Warburtons Tiger Bloomer 600g 🎫 CC TESC £1.45      ASDA £2.85    £1.40      49.1%
Président French Brie 200g    🎫 CC TESC £2.00      SAIN £3.10    £1.10      35.5%
```

The `🎫 CC` and `🌟 Nectar` prefixes on the Cheapest column indicate the effective price is a loyalty scheme price, not the standard shelf price.

### Stats & Report
```bash
python main.py stats           # Product counts per retailer
python main.py report          # Full summary: stats + cheapest items + savings
```

## How Fuzzy Matching Works

Products are matched across retailers even when names differ slightly:

```
Tesco:       "Warburtons Wholemeal Medium Sliced Bread 800g"
Sainsbury's: "Warburtons Wholemeal Medium Sliced Bread 800g"
Similarity:  100% → exact fuzzy match ✅

Tesco:       "Tesco British Semi Skimmed Milk 2.272L"
Sainsbury's: "Sainsbury's British Semi Skimmed Milk 2.27L"
Similarity:  81% → good match ✅
```

`thefuzz.token_sort_ratio()` is used with an 85% threshold (configurable via `--fuzzy-threshold`). When a fuzzy match is found, the existing DB row is updated via `update_product_by_id()` so prices and member prices stay current on every scrape.

## Dependencies

- `playwright` — browser automation for all three scrapers
- `playwright-stealth` — anti-bot fingerprint patches
- `thefuzz` — fuzzy string matching
- `python-dotenv` — environment variables

## Current Status

✅ **All three scrapers working:**
- **Tesco** — API interception (`xapi.tesco.com` GraphQL) with HTML fallback; Clubcard prices from promotion descriptions; query-relevance filter prevents off-topic API results being stored
- **Sainsbury's** — DOM scraping with dual Nectar price extraction (parent-search + within-tile fallback); shelf price correctly separated from Nectar price
- **Asda** — Algolia API interception (`algolia.net`); no loyalty scheme

✅ **Loyalty prices captured and used in savings ranking**

✅ **177 products across milk, cheese, bread, eggs categories**

---

**Built with Python 3.9+ | SQLite | Playwright**
