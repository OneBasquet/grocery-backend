"""
Unit tests for the normalizer module.
"""
import unittest
import tempfile
import os
from pathlib import Path
import sys

# Add parent directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database import Database
from app.normalizer import ProductNormalizer


class TestProductNormalizer(unittest.TestCase):
    """Test cases for ProductNormalizer class."""
    
    def setUp(self):
        """Set up test database and normalizer."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db = Database(self.temp_db.name)
        self.normalizer = ProductNormalizer(self.db, fuzzy_threshold=85)
    
    def tearDown(self):
        """Clean up test database."""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
    
    def test_normalize_product(self):
        """Test product normalization."""
        raw_data = {
            'name': '  Test Product  ',
            'price': '£2.50',
            'unit_price': '£1.25/kg',
            'gtin': '1234567890123'
        }
        
        normalized = self.normalizer.normalize_product(raw_data, 'tesco')
        
        self.assertEqual(normalized['name'], 'Test Product')
        self.assertEqual(normalized['price'], 2.50)
        self.assertEqual(normalized['unit_price'], '£1.25/kg')
        self.assertEqual(normalized['gtin'], '1234567890123')
        self.assertEqual(normalized['retailer'], 'tesco')
    
    def test_parse_price_formats(self):
        """Test parsing different price formats."""
        test_cases = [
            ('£2.50', 2.50),
            ('2.50', 2.50),
            (2.50, 2.50),
            ('$3.99', 3.99),
            ('1,234.56', 1234.56),
        ]
        
        for raw_price, expected in test_cases:
            result = self.normalizer._parse_price(raw_price)
            self.assertAlmostEqual(result, expected, places=2)
    
    def test_extract_gtin(self):
        """Test GTIN extraction from various formats."""
        # Valid GTIN
        data1 = {'gtin': '1234567890123'}
        self.assertEqual(self.normalizer._extract_gtin(data1), '1234567890123')
        
        # GTIN in different field
        data2 = {'ean': '9876543210987'}
        self.assertEqual(self.normalizer._extract_gtin(data2), '9876543210987')
        
        # No valid GTIN
        data3 = {'name': 'Product'}
        self.assertIsNone(self.normalizer._extract_gtin(data3))
        
        # Invalid GTIN (too short)
        data4 = {'gtin': '123'}
        self.assertIsNone(self.normalizer._extract_gtin(data4))
    
    def test_insert_or_update_with_gtin(self):
        """Test insert or update with GTIN matching."""
        product_data = {
            'gtin': '1234567890123',
            'name': 'Test Product',
            'price': 2.50,
            'retailer': 'tesco'
        }
        
        # First insert
        action1, id1 = self.normalizer.insert_or_update_product(product_data)
        self.assertEqual(action1, 'inserted')
        
        # Update with same GTIN
        product_data['price'] = 2.75
        action2, id2 = self.normalizer.insert_or_update_product(product_data)
        self.assertEqual(action2, 'updated')
        self.assertEqual(id1, id2)
        
        # Verify price was updated
        found = self.db.find_product_by_gtin('1234567890123', 'tesco')
        self.assertEqual(found['price'], 2.75)
    
    def test_fuzzy_matching(self):
        """Test fuzzy matching for products without GTIN."""
        # Insert a product without GTIN
        product1 = {
            'name': 'Tesco Whole Milk 2L',
            'price': 2.50,
            'retailer': 'tesco'
        }
        
        self.normalizer.insert_or_update_product(product1)
        
        # Try to insert very similar product (should match)
        product2 = {
            'name': 'Tesco Whole Milk 2 Litre',
            'price': 2.60,
            'retailer': 'tesco'
        }
        
        action, _ = self.normalizer.insert_or_update_product(product2)
        # Should match due to high similarity
        self.assertIn(action, ['matched', 'inserted'])
    
    def test_batch_insert_products(self):
        """Test batch insertion of products."""
        raw_products = [
            {'name': 'Product 1', 'price': '1.50'},
            {'name': 'Product 2', 'price': '2.50'},
            {'name': 'Product 3', 'price': '3.50'},
        ]
        
        stats = self.normalizer.batch_insert_products(raw_products, 'tesco')
        
        self.assertEqual(stats['inserted'], 3)
        self.assertEqual(stats['errors'], 0)
        
        count = self.db.get_product_count()
        self.assertEqual(count, 3)


if __name__ == '__main__':
    unittest.main()
