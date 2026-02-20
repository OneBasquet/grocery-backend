"""
Unit tests for the database module.
"""
import unittest
import tempfile
import os
from pathlib import Path
import sys

# Add parent directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database import Database


class TestDatabase(unittest.TestCase):
    """Test cases for Database class."""
    
    def setUp(self):
        """Set up test database."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db = Database(self.temp_db.name)
    
    def tearDown(self):
        """Clean up test database."""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
    
    def test_database_initialization(self):
        """Test that database is initialized correctly."""
        count = self.db.get_product_count()
        self.assertEqual(count, 0)
    
    def test_insert_product(self):
        """Test inserting a product."""
        product_data = {
            'gtin': '1234567890123',
            'name': 'Test Milk',
            'price': 2.50,
            'unit_price': '£2.50/L',
            'retailer': 'tesco'
        }
        
        product_id = self.db.insert_product(product_data)
        self.assertIsNotNone(product_id)
        self.assertGreater(product_id, 0)
        
        count = self.db.get_product_count()
        self.assertEqual(count, 1)
    
    def test_find_product_by_gtin(self):
        """Test finding a product by GTIN."""
        product_data = {
            'gtin': '9876543210987',
            'name': 'Test Bread',
            'price': 1.50,
            'retailer': 'sainsburys'
        }
        
        self.db.insert_product(product_data)
        
        found = self.db.find_product_by_gtin('9876543210987', 'sainsburys')
        self.assertIsNotNone(found)
        self.assertEqual(found['name'], 'Test Bread')
        self.assertEqual(found['price'], 1.50)
    
    def test_update_product_by_gtin(self):
        """Test updating a product by GTIN."""
        # Insert initial product
        product_data = {
            'gtin': '1111111111111',
            'name': 'Test Eggs',
            'price': 2.00,
            'retailer': 'asda'
        }
        
        self.db.insert_product(product_data)
        
        # Update the product
        updated_data = {
            'gtin': '1111111111111',
            'name': 'Test Eggs Updated',
            'price': 2.25,
            'retailer': 'asda'
        }
        
        result = self.db.update_product_by_gtin('1111111111111', updated_data)
        self.assertTrue(result)
        
        # Verify update
        found = self.db.find_product_by_gtin('1111111111111', 'asda')
        self.assertEqual(found['price'], 2.25)
        self.assertEqual(found['name'], 'Test Eggs Updated')
    
    def test_get_all_products_by_retailer(self):
        """Test getting all products filtered by retailer."""
        # Insert products from different retailers
        products = [
            {'name': 'Tesco Product', 'price': 1.0, 'retailer': 'tesco'},
            {'name': 'Asda Product', 'price': 2.0, 'retailer': 'asda'},
            {'name': 'Tesco Product 2', 'price': 3.0, 'retailer': 'tesco'},
        ]
        
        for product in products:
            self.db.insert_product(product)
        
        tesco_products = self.db.get_all_products('tesco')
        self.assertEqual(len(tesco_products), 2)
        
        asda_products = self.db.get_all_products('asda')
        self.assertEqual(len(asda_products), 1)
    
    def test_find_similar_products(self):
        """Test finding similar products."""
        # Insert products with similar names
        products = [
            {'name': 'Whole Milk 2L', 'price': 2.50, 'retailer': 'tesco'},
            {'name': 'Whole Milk 1L', 'price': 1.50, 'retailer': 'tesco'},
            {'name': 'Skimmed Milk 2L', 'price': 2.30, 'retailer': 'tesco'},
        ]
        
        for product in products:
            self.db.insert_product(product)
        
        similar = self.db.find_similar_products('Whole Milk', 'tesco', limit=10)
        self.assertGreaterEqual(len(similar), 2)


if __name__ == '__main__':
    unittest.main()
