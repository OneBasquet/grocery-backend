"""
Client + parser for the Pepesto grocery catalog API (pepesto.com).

The REST contract below is confirmed, not guessed — read directly out of the
`@pepesto/pepesto-mcp` npm package's compiled source (dist/client.js,
dist/tools/catalog.js, dist/tools/credits.js), since Pepesto's own public
docs never state it:

    Base URL : https://s.pepesto.com/api   (NOT www.pepesto.com)
    Catalog  : POST /catalog   {"supermarket_domain": "tesco.com", "webhook_url"?: "..."}
    Credits  : POST /credits   {}                (free balance check)
    Auth     : Authorization: Bearer <PEPESTO_API_KEY>
    Headers  : Content-Type: application/json, Accept: application/json

Confirmed real catalog response shape (from live calls against tesco.com and
groceries.morrisons.com):

    {
      "parsed_products": {
        "<retailer product/category URL>": {
          "entity_name": str,      # Pepesto's internal ingredient-taxonomy
                                    # label — UNRELIABLE, sometimes mismatched
                                    # to the actual product (e.g. entity_name
                                    # "Sunflower oil" paired with
                                    # names.en "Organic Jumbo Oats"). Never
                                    # used by normalize_pepesto_product().
          "names": {"en": str},     # actual retail product name — use this
          "price": int,             # pence
          "quantity_str": str,      # e.g. "680g", "250ml", "1kg"
          "quantity": {"Unit": {<UnitName>: int}, "accurate_grams": int?},
          "tags": [str, ...],       # optional
          "self_hosted_image": str, "remote_image": str,
        },
        ...
      }
    }

The URL key is either a specific product page or a category browse page
when Pepesto's matcher couldn't pin down a specific SKU for that entry —
only the former are real products. The URL *shape* is retailer-specific:
    tesco.com     .../products/250164181                      (id is the last segment)
    morrisons     .../products/ainsley-harriott.../113962863   (id is the last segment, after a slug)
    browse pages  .../browse/food-cupboard/.../all             (last segment is not numeric)
So rather than match one retailer's specific pattern, a URL is treated as a
real product page if its last path segment is purely numeric — that holds
across every retailer shape seen so far.

Confirmed supported UK supermarkets (from the package README's coverage
table — Ocado and Iceland are NOT on it, so they stay scraper-only):
    tesco.com, sainsburys.co.uk, asda.com, groceries.morrisons.com, waitrose.com
"""
import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

BASE_URL = "https://s.pepesto.com/api"
_TIMEOUT_SECONDS = 120  # pepesto_catalog is documented as "the heaviest call"


class PepestoApiError(RuntimeError):
    """Raised when a Pepesto API call fails."""


class PepestoClient:
    """Thin wrapper around Pepesto's REST API (confirmed contract, see module docstring)."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Pepesto API key is required (set PEPESTO_API_KEY)")
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _post(self, endpoint: str, body: Optional[Dict[str, Any]] = None) -> Any:
        resp = self._session.post(f"{BASE_URL}{endpoint}", json=body or {}, timeout=_TIMEOUT_SECONDS)
        if not resp.ok:
            raise PepestoApiError(f"Pepesto API {resp.status_code} on {endpoint}: {resp.text[:500]}")
        if not resp.text:
            return {}
        try:
            return resp.json()
        except ValueError:
            return resp.text

    def get_credits(self) -> Dict[str, Any]:
        """Free balance check — good for a connectivity/auth smoke test."""
        return self._post("/credits")

    def get_catalog(self, supermarket_domain: str) -> List[Dict[str, Any]]:
        """Fetch and filter the full SKU dump for one supermarket, e.g. 'tesco.com'.

        Returns only real per-SKU rows (see parse_catalog_response()), each
        with its source URL merged in under '_pepesto_url', ready for
        ProductNormalizer.normalize_pepesto_product().
        """
        data = self._post("/catalog", {"supermarket_domain": supermarket_domain})
        return parse_catalog_response(data)


def _is_product_page(url: str) -> bool:
    path = urlparse(url).path.rstrip("/")
    last_segment = path.rsplit("/", 1)[-1]
    return last_segment.isdigit()


def parse_catalog_response(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Filter a raw pepesto_catalog response down to real per-SKU rows.

    Category-page-keyed entries (Pepesto couldn't match a specific product)
    are dropped. Shared by both the live client and load_catalog() below.
    """
    parsed = data.get("parsed_products", data)  # tolerate a bare parsed_products dump too
    rows = []
    for url, raw in parsed.items():
        if not _is_product_page(url):
            continue
        rows.append({**raw, "_pepesto_url": url})
    return rows


def load_catalog(path: str) -> List[Dict[str, Any]]:
    """Load a saved pepesto_catalog response (e.g. for replay/testing) and
    return only real per-SKU rows. See parse_catalog_response()."""
    with open(path) as f:
        data = json.load(f)
    return parse_catalog_response(data)
