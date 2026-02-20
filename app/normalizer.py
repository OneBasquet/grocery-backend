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
            'timestamp': datetime.now().isoformat()
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
        Clean unit price string and extract numeric value.
        
        Extracts only the numeric value from strings like:
        - '£1.74 / kg' -> '1.74'
        - '£1.35 / ltr' -> '1.35'
        - '1.06' -> '1.06'
        
        Args:
            unit_price: Raw unit price data
            
        Returns:
            Numeric unit price string or None
        """
        if not unit_price:
            return None
        
        # Convert to string
        unit_price_str = str(unit_price).strip()
        
        # Use regex to extract the first decimal number
        # Pattern matches: optional £/$, digits, optional decimal point and more digits
        match = re.search(r'[£$]?\s*(\d+\.?\d*)', unit_price_str)
        
        if match:
            numeric_value = match.group(1)
            # Return only if it's a valid number
            try:
                float(numeric_value)
                return numeric_value
            except ValueError:
                pass
        
        return None
    
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
                # For products without GTIN, we still return the matched ID
                # but we might want to insert as new entry to track price history
                pass
            
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
