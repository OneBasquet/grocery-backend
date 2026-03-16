"""
Normalization layer for standardizing product data from different sources.
Handles data validation, cleaning, and matching logic.
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
import re
from thefuzz import fuzz
from app.database import Database


class ProductNormalizer:
    """Normalizes and stores product data from various sources."""
    
    def __init__(self, db: Database, fuzzy_threshold: int = 85):
        """
        Initialize the normalizer.
        
        Args:
            db: Database instance
            fuzzy_threshold: Minimum similarity score (0-100) for fuzzy matching
        """
        self.db = db
        self.fuzzy_threshold = fuzzy_threshold
    
    def normalize_product(self, raw_data: Dict[str, Any], source: str) -> Dict[str, Any]:
        """
        Normalize product data from any source.
        
        Args:
            raw_data: Raw product data from scraper
            source: Source identifier (e.g., 'tesco', 'sainsburys', 'asda')
            
        Returns:
            Normalized product dictionary
        """
        normalized = {
            'gtin': self._extract_gtin(raw_data),
            'name': self._clean_name(raw_data.get('name', '')),
            'price': self._parse_price(raw_data.get('price', 0)),
            'unit_price': self._clean_unit_price(raw_data.get('unit_price')),
            'retailer': source.lower(),
            'timestamp': datetime.now().isoformat(),
            'is_clubcard_price': int(raw_data.get('is_clubcard_price', 0)),
            'normal_price': self._parse_price(raw_data.get('normal_price', 0)) if raw_data.get('normal_price') else None,
            'member_price': self._parse_price(raw_data.get('member_price', 0)) if raw_data.get('member_price') else None,
        }
        
        return normalized
    
    def _extract_gtin(self, data: Dict[str, Any]) -> Optional[str]:
        """
        Extract GTIN from various possible fields.
        
        Args:
            data: Raw product data
            
        Returns:
            GTIN string or None
        """
        # Try different possible field names
        for field in ['gtin', 'ean', 'barcode', 'upc', 'id']:
            if field in data and data[field]:
                gtin = str(data[field]).strip()
                if gtin and gtin.isdigit() and len(gtin) >= 8:
                    return gtin
        return None
    
    def _clean_name(self, name: str) -> str:
        """
        Clean and standardize product name.
        
        Args:
            name: Raw product name
            
        Returns:
            Cleaned product name
        """
        if not name:
            return ""
        
        # Remove extra whitespace
        name = ' '.join(name.split())
        
        # Remove common suffixes that might differ between retailers
        # but keep the core product name intact
        return name.strip()
    
    def _parse_price(self, price: Any) -> float:
        """
        Parse price from various formats.
        
        Args:
            price: Price in various formats (string, float, etc.)
            
        Returns:
            Price as float
        """
        if isinstance(price, (int, float)):
            return float(price)
        
        if isinstance(price, str):
            # Remove currency symbols and whitespace
            price_str = price.replace('£', '').replace('$', '').replace(',', '').strip()
            try:
                return float(price_str)
            except ValueError:
                return 0.0
        
        return 0.0
    
    def _clean_unit_price(self, unit_price: Any) -> Optional[str]:
        """
        Clean unit price string and normalize to standard format.
        
        Handles various formats:
        - '£1.74 / kg' -> '1.74/kg'
        - '0.73/litre' -> '0.73/litre' (from Tesco API)
        - '9.2p per 100g' -> '0.092/100g' (convert pence to pounds)
        - '(£1.23/kg)' -> '1.23/kg' (remove parentheses)
        - '1.06' -> '1.06' (raw number)
        
        Args:
            unit_price: Raw unit price data
            
        Returns:
            Cleaned unit price string or None
        """
        if not unit_price:
            return None
        
        # Convert to string and clean parentheses
        unit_price_str = str(unit_price).strip().strip('()')
        
        # Handle pence format (e.g., "9.2p per 100g" -> "0.092/100g")
        pence_match = re.match(r'(\d+\.?\d*)p\s*(?:per|/)\s*(\w+)', unit_price_str, re.I)
        if pence_match:
            pence_value = float(pence_match.group(1)) / 100  # Convert pence to pounds
            unit = ProductNormalizer._normalise_unit(pence_match.group(2))
            return f"{pence_value:.3f}/{unit}"
        
        # Handle standard formats with £/$ and unit
        # Pattern: £1.74 / kg or £1.74/kg or 0.73/litre
        standard_match = re.search(r'[£$]?\s*(\d+\.?\d*)\s*[/]?\s*(?:per\s+)?(\w+)?', unit_price_str, re.I)
        
        if standard_match:
            numeric_value = standard_match.group(1)
            unit = standard_match.group(2)
            
            # Validate numeric value
            try:
                float(numeric_value)
                # If we have a unit, normalise and format as "value/unit"
                if unit and len(unit) > 1:  # Avoid single-letter artifacts
                    unit = ProductNormalizer._normalise_unit(unit)
                    return f"{numeric_value}/{unit}"
                else:
                    return numeric_value
            except ValueError:
                pass
        
        # Fallback: Just extract the first number
        fallback_match = re.search(r'(\d+\.?\d*)', unit_price_str)
        if fallback_match:
            try:
                float(fallback_match.group(1))
                return fallback_match.group(1)
            except ValueError:
                pass
        
        return None

    @staticmethod
    def effective_price(product: Dict[str, Any]) -> float:
        """
        Return the best available price for a product.

        When a member/loyalty price (e.g. Tesco Clubcard) is present and lower
        than the shelf price, return it so that savings comparisons reflect what
        a card-holding shopper actually pays.
        """
        shelf = float(product.get('price') or 0)
        member = product.get('member_price')
        if member:
            try:
                member_f = float(member)
                if member_f > 0 and member_f < shelf:
                    return member_f
            except (TypeError, ValueError):
                pass
        return shelf

    @staticmethod
    def _normalise_unit(unit: str) -> str:
        """Normalise unit abbreviations to a consistent lowercase form."""
        mapping = {
            'lt': 'litre', 'ltr': 'litre', 'l': 'litre',
            'liters': 'litre', 'liter': 'litre', 'litres': 'litre',
            'kg': 'kg', 'kgs': 'kg', 'kilogram': 'kg', 'kilograms': 'kg',
            'g': 'g', 'grams': 'g', 'gram': 'g',
            'ml': 'ml', 'millilitre': 'ml', 'millilitres': 'ml',
            '100g': '100g', '100ml': '100ml',
        }
        return mapping.get(unit.lower(), unit.lower())
    
    def insert_or_update_product(self, product_data: Dict[str, Any]) -> tuple[str, int]:
        """
        Insert a new product or update existing one.
        
        Args:
            product_data: Normalized product data
            
        Returns:
            Tuple of (action, product_id) where action is 'inserted', 'updated', or 'matched'
        """
        gtin = product_data.get('gtin')
        retailer = product_data['retailer']
        
        # Strategy 1: Try GTIN matching first
        if gtin:
            existing = self.db.find_product_by_gtin(gtin, retailer)
            if existing:
                self.db.update_product_by_gtin(gtin, product_data)
                return ('updated', existing['id'])
        
        # Strategy 2: Fuzzy matching for products without GTIN or no GTIN match
        matched_id = self._fuzzy_match_product(product_data)
        if matched_id:
            return ('matched', matched_id)
        
        # Strategy 3: Insert as new product
        product_id = self.db.insert_product(product_data)
        return ('inserted', product_id)
    
    def _fuzzy_match_product(self, product_data: Dict[str, Any]) -> Optional[int]:
        """
        Try to find matching product using fuzzy string matching.
        
        Args:
            product_data: Normalized product data
            
        Returns:
            Product ID if match found, None otherwise
        """
        name = product_data['name']
        retailer = product_data['retailer']
        
        # Get similar products from the same retailer
        similar_products = self.db.find_similar_products(name, retailer, limit=20)
        
        if not similar_products:
            return None
        
        # Find best match using fuzzy string matching
        best_match = None
        best_score = 0
        
        for product in similar_products:
            # Use token sort ratio for better matching with reordered words
            score = fuzz.token_sort_ratio(name.lower(), product['name'].lower())
            
            if score > best_score and score >= self.fuzzy_threshold:
                best_score = score
                best_match = product
        
        # If we found a good match, update it
        if best_match:
            # Update the existing product with new price
            update_data = {
                **product_data,
                'name': best_match['name']  # Keep original name for consistency
            }
            
            if best_match.get('gtin'):
                self.db.update_product_by_gtin(best_match['gtin'], update_data)
            else:
                # No GTIN — update by primary key so price and member_price
                # are refreshed on every scrape rather than staying stale.
                self.db.update_product_by_id(best_match['id'], update_data)
            
            return best_match['id']
        
        return None
    
    def batch_insert_products(self, products: List[Dict[str, Any]], source: str) -> Dict[str, int]:
        """
        Normalize and insert/update multiple products.
        
        Args:
            products: List of raw product data
            source: Source identifier
            
        Returns:
            Dictionary with counts of inserted, updated, and matched products
        """
        stats = {
            'inserted': 0,
            'updated': 0,
            'matched': 0,
            'errors': 0
        }
        
        for raw_product in products:
            try:
                normalized = self.normalize_product(raw_product, source)
                action, _ = self.insert_or_update_product(normalized)
                stats[action] += 1
            except Exception as e:
                print(f"Error processing product: {e}")
                stats['errors'] += 1
        
        return stats
