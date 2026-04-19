"""FastAPI gateway for the grocery price comparison engine."""
import sys
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
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
    """Search matched products across all retailers."""
    try:
        if live:
            orchestrator.scrape_all_retailers(query, max_items=limit)
        results = orchestrator.compare_prices(query, limit=limit)
        return {"query": query, "count": len(results), "results": [_decorate(p) for p in results]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/basket/optimize")
def basket_optimize(
    ids: List[int] = Query(..., description="Product IDs to include in basket"),
):
    """Return total basket cost per retailer using effective (member) prices."""
    if not ids:
        raise HTTPException(status_code=400, detail="At least one product id is required")

    products = {p["id"]: p for p in orchestrator.db.get_all_products() if p.get("id") in set(ids)}
    missing = [pid for pid in ids if pid not in products]
    if missing:
        raise HTTPException(status_code=404, detail=f"Products not found: {missing}")

    totals = {r: {"retailer": r, "total": 0.0, "items": [], "member_savings": 0.0}
              for r in ("tesco", "sainsburys", "asda")}

    for pid in ids:
        p = products[pid]
        retailer = (p.get("retailer") or "").lower()
        if retailer not in totals:
            continue
        item = _decorate(p)
        shelf = float(p.get("price") or 0)
        effective = item["effective_price"]
        totals[retailer]["items"].append(item)
        totals[retailer]["total"] += effective
        if item["has_member_price"]:
            totals[retailer]["member_savings"] += (shelf - effective)

    breakdown = []
    for r, data in totals.items():
        data["total"] = round(data["total"], 2)
        data["member_savings"] = round(data["member_savings"], 2)
        data["item_count"] = len(data["items"])
        breakdown.append(data)

    available = [b for b in breakdown if b["item_count"] > 0]
    cheapest = min(available, key=lambda b: b["total"]) if available else None

    return {
        "requested_ids": ids,
        "cheapest_retailer": cheapest["retailer"] if cheapest else None,
        "cheapest_total": cheapest["total"] if cheapest else None,
        "breakdown": breakdown,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
