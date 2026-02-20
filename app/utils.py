"""
Utility functions for the grocery price comparison engine.
"""
from typing import Any, Dict, List
import re


def parse_price(price_str: str) -> float:
    """
    Parse price string to float.
    
    Args:
        price_str: Price string (e.g., "£2.50", "$3.99")
        
    Returns:
        Price as float
    """
    if isinstance(price_str, (int, float)):
        return float(price_str)
    
    # Remove currency symbols and extract numbers
    price_clean = re.sub(r'[£$€,\s]', '', str(price_str))
    
    try:
        return float(price_clean)
    except ValueError:
        return 0.0


def format_price(price: float, currency: str = '£') -> str:
    """
    Format price for display.
    
    Args:
        price: Price as float
        currency: Currency symbol
        
    Returns:
        Formatted price string
    """
    return f"{currency}{price:.2f}"


def clean_product_name(name: str) -> str:
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
    
    # Remove leading/trailing punctuation
    name = name.strip('.,;:-')
    
    return name


def extract_gtin_variants(text: str) -> List[str]:
    """
    Extract potential GTIN/EAN/UPC codes from text.
    
    Args:
        text: Text to search
        
    Returns:
        List of potential GTIN codes
    """
    # Match 8, 12, 13, or 14 digit codes
    pattern = r'\b\d{8,14}\b'
    matches = re.findall(pattern, text)
    
    # Filter to valid GTIN lengths
    valid_lengths = {8, 12, 13, 14}
    return [m for m in matches if len(m) in valid_lengths]


def calculate_unit_price(price: float, quantity: float, unit: str = 'kg') -> str:
    """
    Calculate unit price.
    
    Args:
        price: Total price
        quantity: Quantity
        unit: Unit of measurement
        
    Returns:
        Formatted unit price string
    """
    if quantity <= 0:
        return "N/A"
    
    unit_price = price / quantity
    return f"£{unit_price:.2f}/{unit}"


def compare_products(product1: Dict[str, Any], product2: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare two products and return comparison results.
    
    Args:
        product1: First product dictionary
        product2: Second product dictionary
        
    Returns:
        Comparison results
    """
    price1 = product1.get('price', 0)
    price2 = product2.get('price', 0)
    
    if isinstance(price1, str):
        price1 = parse_price(price1)
    if isinstance(price2, str):
        price2 = parse_price(price2)
    
    difference = abs(price1 - price2)
    cheaper = product1['retailer'] if price1 < price2 else product2['retailer']
    percentage_diff = (difference / min(price1, price2) * 100) if min(price1, price2) > 0 else 0
    
    return {
        'product1': product1,
        'product2': product2,
        'price_difference': difference,
        'cheaper_retailer': cheaper,
        'percentage_difference': percentage_diff
    }


def validate_product_data(product: Dict[str, Any]) -> bool:
    """
    Validate that product data has required fields.
    
    Args:
        product: Product dictionary
        
    Returns:
        True if valid, False otherwise
    """
    required_fields = ['name', 'price', 'retailer']
    
    for field in required_fields:
        if field not in product or not product[field]:
            return False
    
    return True


def get_best_deal(products: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Find the best deal from a list of products.
    
    Args:
        products: List of product dictionaries
        
    Returns:
        Product with the lowest price
    """
    if not products:
        return {}
    
    valid_products = [p for p in products if validate_product_data(p)]
    
    if not valid_products:
        return {}
    
    # Convert prices to float for comparison
    for product in valid_products:
        if isinstance(product['price'], str):
            product['price'] = parse_price(product['price'])
    
    return min(valid_products, key=lambda x: x['price'])
