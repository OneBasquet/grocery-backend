"""FastAPI gateway for the grocery price comparison engine."""
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

from fastapi import BackgroundTasks, FastAPI, Header as FastAPIHeader, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.orchestrator import GroceryPriceOrchestrator
from app.normalizer import ProductNormalizer
from app.database import format_time_ago

MEMBER_SCHEME_LABELS = {
    "tesco": "Clubcard Price",
    "sainsburys": "Nectar Price",
    "asda": "Asda Rewards",
}

app = FastAPI(title="Grocery Price API", version="1.0.0")

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://grocery-frontend-omega.vercel.app",
]


def _allow_origin(origin: str) -> bool:
    if origin in ALLOWED_ORIGINS:
        return True
    # Allow all Vercel preview/deployment URLs for this project
    if origin.endswith(".vercel.app") and "grocery-frontend" in origin:
        return True
    return False


from starlette.middleware.cors import CORSMiddleware as _CORSMiddleware


class DynamicCORSMiddleware(_CORSMiddleware):
    def is_allowed_origin(self, origin: str) -> bool:
        return _allow_origin(origin)


app.add_middleware(
    DynamicCORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = GroceryPriceOrchestrator()


def _decorate(product: dict) -> dict:
    """Attach effective price and a member-scheme label for the frontend."""
    out = dict(product)
    shelf = float(product.get("price") or 0)
    member = product.get("member_price")
    effective = ProductNormalizer.effective_price(product)
    out["effective_price"] = effective
    out["has_member_price"] = bool(member and float(member) > 0 and float(member) < shelf)
    out["_member_scheme_label"] = (
        MEMBER_SCHEME_LABELS.get((product.get("retailer") or "").lower())
        if out["has_member_price"]
        else None
    )
    # Prefer updated_at (bumped on every refresh) and fall back to timestamp.
    ts = product.get("updated_at") or product.get("timestamp")
    out["timestamp"] = ts
    out["updated_ago"] = format_time_ago(ts)
    return out


@app.get("/health")
def health():
    return {"status": "ok", **orchestrator.get_database_stats()}


@app.get("/search")
def search(
    query: str = Query(..., min_length=1, description="Product search term"),
    limit: int = Query(20, ge=1, le=200),
    live: bool = Query(False, description="If true, run live scrapers before searching"),
):
    """Search matched products across all retailers.

    If `live` is false and the DB returns 0 results, the response includes a
    `hint` field suggesting the frontend can retry with `live=true`.
    """
    try:
        if live:
            orchestrator.scrape_all_retailers(query, max_items=limit)
        results = orchestrator.compare_prices(query, limit=limit)

        hint = None
        if not results and not live:
            hint = "no_cache"

        return {
            "query": query,
            "count": len(results),
            "results": [_decorate(p) for p in results],
            **({"hint": hint} if hint else {}),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/search/grouped")
def search_grouped(
    query: str = Query(..., min_length=1, description="Product search term"),
    limit: int = Query(20, ge=1, le=200),
    threshold: int = Query(75, ge=50, le=100, description="Fuzzy match threshold for grouping"),
):
    """Search and group similar products across retailers for side-by-side comparison."""
    from thefuzz import fuzz
    import re

    # ── Conflict words: products with DIFFERENT values must never group ──
    CONFLICT_SETS: list[set[str]] = [
        # Milk type
        {"whole", "semi", "semi-skimmed", "skimmed", "1%"},
        # Organic vs conventional
        {"organic"},
        # Dietary / variant
        {"unsweetened", "sweetened", "unsalted", "salted", "light", "diet", "zero",
         "free range", "free-range", "oat", "almond", "soy", "soya", "coconut",
         "lactose free", "lactose-free"},
        # Fat content for yoghurt, etc.
        {"fat free", "fat-free", "low fat", "low-fat", "full fat", "full-fat"},
        # Bread type
        {"white", "wholemeal", "wholegrain", "seeded", "sourdough", "brown", "multigrain"},
    ]

    # ── Unit/size patterns: extracted and compared as hard blockers ──
    _SIZE_RE = re.compile(
        r'(\d+(?:\.\d+)?)\s*'
        r'(l|lt|ltr|litre|litres|liter|liters|ml|'
        r'kg|kgs|kilogram|kilograms|g|gm|gms|gram|grams|'
        r'pint|pints|pt|pts|'
        r'pk|pack|packs|rolls|sheets|'
        r'cl)\b',
        re.IGNORECASE,
    )

    def _extract_sizes(text: str) -> set[str]:
        """Return normalised size tokens, e.g. {'4pint', '2.272l'}."""
        sizes: set[str] = set()
        for m in _SIZE_RE.finditer(text):
            qty = m.group(1)
            unit = m.group(2).lower().rstrip("s")
            # Normalise common aliases
            if unit in ("lt", "ltr", "litre", "liter"):
                unit = "l"
            elif unit in ("gm", "gms", "gram"):
                unit = "g"
            elif unit in ("pt", "pint"):
                unit = "pint"
            elif unit in ("pk", "pack"):
                unit = "pack"
            elif unit in ("kg", "kilogram"):
                unit = "kg"
            sizes.add(f"{qty}{unit}")
        return sizes

    def _extract_conflict_tags(text: str) -> set[str]:
        """Return the set of conflict words found in the text."""
        lower = text.lower()
        tags: set[str] = set()
        for group in CONFLICT_SETS:
            for word in group:
                if word in lower:
                    tags.add(word)
                    break  # one match per conflict set is enough
        return tags

    def _can_group(name_a: str, name_b: str) -> bool:
        """Return False if conflict words or sizes disagree."""
        # Size check: if both have sizes, they must overlap
        sizes_a = _extract_sizes(name_a)
        sizes_b = _extract_sizes(name_b)
        if sizes_a and sizes_b and sizes_a.isdisjoint(sizes_b):
            return False
        # Conflict-word check: tags must be identical
        tags_a = _extract_conflict_tags(name_a)
        tags_b = _extract_conflict_tags(name_b)
        if tags_a != tags_b:
            return False
        return True

    try:
        results = orchestrator.compare_prices(query, limit=limit)
        decorated = [_decorate(p) for p in results]

        # Normalise name for grouping: lowercase, strip retailer-specific prefixes,
        # collapse whitespace, keep size/quantity info.
        RETAILER_PREFIXES = (
            "tesco", "asda", "sainsbury's", "sainsburys", "by sainsbury's",
            "waitrose", "morrisons", "ocado", "iceland",
            "m&s", "marks & spencer",
        )
        BRAND_TAGS = (
            "finest", "own brand", "essentials", "everyday", "chosen by you",
            "extra special", "just essentials", "taste the difference",
            "so organic", "aldi", "lidl", "by sainsbury's",
        )

        def _normalise_for_group(name: str) -> str:
            n = name.lower()
            for prefix in RETAILER_PREFIXES:
                if n.startswith(prefix):
                    n = n[len(prefix):].lstrip()
            for tag in BRAND_TAGS:
                n = n.replace(tag, "")
            n = re.sub(r"\s+", " ", n).strip()
            return n

        def _clean_display_name(name: str) -> str:
            """Strip retailer branding for a neutral group display name."""
            n = name
            for prefix in RETAILER_PREFIXES:
                if n.lower().startswith(prefix):
                    n = n[len(prefix):].lstrip()
                    break
            for tag in BRAND_TAGS:
                n = re.sub(re.escape(tag), "", n, flags=re.IGNORECASE)
            n = re.sub(r"\s+", " ", n).strip()
            # Capitalise first letter
            return n[0].upper() + n[1:] if n else n

        # Build groups greedily with conflict/size guards
        groups: list[dict] = []
        group_keys: list[str] = []
        group_raw_names: list[str] = []  # un-normalised anchor name for conflict checks

        for product in decorated:
            norm = _normalise_for_group(product["name"])
            raw_name = product["name"]
            retailer = product.get("retailer", "").lower()

            best_group_idx = -1
            best_score = 0

            for idx, key in enumerate(group_keys):
                if retailer in groups[idx]["options"]:
                    continue
                # Hard blocker: conflict words or sizes mismatch
                if not _can_group(raw_name, group_raw_names[idx]):
                    continue
                score = fuzz.token_sort_ratio(norm, key)
                if score >= threshold and score > best_score:
                    best_score = score
                    best_group_idx = idx

            if best_group_idx >= 0:
                groups[best_group_idx]["options"][retailer] = product
            else:
                groups.append({
                    "display_name": _clean_display_name(product["name"]),
                    "_norm": norm,
                    "options": {retailer: product},
                })
                group_keys.append(norm)
                group_raw_names.append(raw_name)

        # Compute cheapest per group and clean up
        output = []
        for g in groups:
            options = g["options"]
            cheapest = min(options.items(), key=lambda kv: kv[1]["effective_price"])
            output.append({
                "display_name": g["display_name"],
                "options": options,
                "cheapest_retailer": cheapest[0],
                "cheapest_price": cheapest[1]["effective_price"],
                "retailer_count": len(options),
            })

        # Sort: groups with more retailers first, then by cheapest price
        output.sort(key=lambda g: (-g["retailer_count"], g["cheapest_price"]))

        return {
            "query": query,
            "group_count": len(output),
            "groups": output,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Free-delivery minimum spend thresholds (£)
FREE_DELIVERY_THRESHOLDS = {
    "tesco": 40.0,
    "sainsburys": 40.0,
    "asda": 40.0,
}


@app.post("/basket/optimize")
def basket_optimize_post(payload: dict):
    """Accept basket items with quantities and return optimised totals.

    Body: { "items": [ { "id": 1, "quantity": 2 }, ... ] }
    """
    raw_items = payload.get("items", [])
    if not raw_items:
        raise HTTPException(status_code=400, detail="At least one item is required")

    # Normalise input — accept both {id, quantity} dicts and plain ints
    item_qty: dict[int, int] = {}
    for entry in raw_items:
        if isinstance(entry, dict):
            pid = int(entry["id"])
            qty = int(entry.get("quantity", 1))
        else:
            pid = int(entry)
            qty = 1
        item_qty[pid] = item_qty.get(pid, 0) + qty

    all_products = {p["id"]: p for p in orchestrator.db.get_all_products() if p.get("id") in set(item_qty)}
    missing = [pid for pid in item_qty if pid not in all_products]
    if missing:
        raise HTTPException(status_code=404, detail=f"Products not found: {missing}")

    totals = {r: {"retailer": r, "total": 0.0, "items": [], "member_savings": 0.0, "total_quantity": 0}
              for r in ("tesco", "sainsburys", "asda")}

    for pid, qty in item_qty.items():
        p = all_products[pid]
        retailer = (p.get("retailer") or "").lower()
        if retailer not in totals:
            continue
        item = _decorate(p)
        item["quantity"] = qty
        shelf = float(p.get("price") or 0)
        effective = item["effective_price"]
        line_total = effective * qty
        totals[retailer]["items"].append(item)
        totals[retailer]["total"] += line_total
        totals[retailer]["total_quantity"] += qty
        if item["has_member_price"]:
            totals[retailer]["member_savings"] += (shelf - effective) * qty

    breakdown = []
    for r, data in totals.items():
        data["total"] = round(data["total"], 2)
        data["member_savings"] = round(data["member_savings"], 2)
        data["item_count"] = len(data["items"])

        # Delivery threshold
        threshold = FREE_DELIVERY_THRESHOLDS.get(r, 40.0)
        data["free_delivery_threshold"] = threshold
        data["meets_free_delivery"] = data["total"] >= threshold
        data["amount_to_free_delivery"] = round(max(0, threshold - data["total"]), 2)

        breakdown.append(data)

    available = [b for b in breakdown if b["item_count"] > 0]
    cheapest = min(available, key=lambda b: b["total"]) if available else None

    return {
        "requested_ids": list(item_qty.keys()),
        "cheapest_retailer": cheapest["retailer"] if cheapest else None,
        "cheapest_total": cheapest["total"] if cheapest else None,
        "breakdown": breakdown,
    }


# Keep GET for backwards compatibility (frontend sends repeated ids)
@app.get("/basket/optimize")
def basket_optimize_get(
    ids: List[int] = Query(..., description="Product IDs to include in basket"),
):
    """GET wrapper — converts repeated IDs into {id, quantity} and delegates to POST."""
    from collections import Counter
    counts = Counter(ids)
    return basket_optimize_post({"items": [{"id": pid, "quantity": qty} for pid, qty in counts.items()]})


@app.post("/order")
def create_order(payload: dict):
    """Accept a checkout order, persist to DB, and return the order ID."""
    required = ("items", "retailer", "total", "address", "delivery_time")
    missing = [f for f in required if not payload.get(f)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing fields: {missing}")

    order_id = orchestrator.db.create_order({
        "items": payload["items"],
        "total_price": payload["total"],
        "retailer": payload["retailer"],
        "address": payload["address"],
        "delivery_time": payload["delivery_time"],
        "phone": payload.get("phone", ""),
    })

    retailer_upper = payload["retailer"].upper()
    print(f"\n{'='*60}")
    print(f"🚀 NEW ORDER RECEIVED FOR {retailer_upper}!")
    print(f"   Order #{order_id} — £{payload['total']:.2f} — {len(payload['items'])} items")
    print(f"   Address: {payload['address'][:60]}")
    print(f"   Slot: {payload['delivery_time']} | Phone: {payload.get('phone', 'N/A')}")
    print(f"{'='*60}\n")

    return {"order_id": order_id, "status": "confirmed"}


@app.post("/seed")
def seed(products: List[dict]):
    """Bulk-insert products into the database. Accepts a JSON array of product dicts."""
    inserted = 0
    for p in products:
        if not p.get("name") or not p.get("retailer"):
            continue
        try:
            orchestrator.db.insert_product(p)
            inserted += 1
        except Exception:
            continue
    return {"inserted": inserted, "total": orchestrator.db.get_product_count()}


ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "onebasqet-warm-2026")
SEED_ITEMS_PATH = Path(__file__).resolve().parent.parent / "config" / "seed_items.json"

_warm_cache_running = False


def _run_warm_cache(max_items: int = 20, delay: int = 10,
                    skip_retailers: Optional[list] = None):
    """Background task: iterate seed items and scrape all retailers."""
    global _warm_cache_running
    _warm_cache_running = True

    with open(SEED_ITEMS_PATH) as f:
        terms: list[str] = json.load(f)

    total = len(terms)
    print(f"\n{'='*60}")
    print(f"  🔥 WARM-CACHE STARTED — {total} items")
    if skip_retailers:
        print(f"  Skipping: {', '.join(skip_retailers)}")
    print(f"{'='*60}\n")

    for i, term in enumerate(terms, 1):
        print(f"[warm-cache {i}/{total}] Scraping '{term}'...")
        try:
            stats = orchestrator.scrape_all_retailers(
                term, max_items=max_items, skip_retailers=skip_retailers
            )
            scraped = sum(s.get("scraped", 0) for s in stats.values())
            print(f"  -> {scraped} products scraped")
        except Exception as e:
            print(f"  -> FAILED: {e}")

        if i < total:
            time.sleep(delay)

    db_stats = orchestrator.get_database_stats()
    print(f"\n{'='*60}")
    print(f"  🔥 WARM-CACHE COMPLETE — {db_stats['total_products']} total products")
    print(f"{'='*60}\n")
    _warm_cache_running = False


@app.post("/admin/warm-cache")
def warm_cache(
    background_tasks: BackgroundTasks,
    x_api_key: Optional[str] = FastAPIHeader(None),
    max_items: int = Query(20, ge=1, le=50),
    delay: int = Query(10, ge=5, le=30),
    skip: List[str] = Query(default=[], description="Retailers to skip, e.g. skip=tesco"),
):
    """Trigger a background warm-cache job. Requires X-API-Key header."""
    if x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if _warm_cache_running:
        return {"status": "already_running", "message": "A warm-cache job is already in progress."}

    skip_list = [s.lower() for s in skip] if skip else None
    background_tasks.add_task(_run_warm_cache, max_items=max_items, delay=delay,
                              skip_retailers=skip_list)
    terms_count = len(json.loads(open(SEED_ITEMS_PATH).read()))
    msg = f"Warm-cache started for {terms_count} items with {delay}s delay."
    if skip_list:
        msg += f" Skipping: {', '.join(skip_list)}."
    return {"status": "started", "message": msg}


@app.get("/admin/warm-cache/status")
def warm_cache_status(x_api_key: Optional[str] = FastAPIHeader(None)):
    """Check whether a warm-cache job is currently running."""
    if x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return {
        "running": _warm_cache_running,
        **orchestrator.get_database_stats(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
