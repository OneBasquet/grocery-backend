"""
Database module for the grocery price comparison engine.
Handles SQLite operations for product storage and retrieval.
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager


class Database:
    """SQLite database manager for grocery products."""
    
    def __init__(self, db_path: str = "products.db"):
        """
        Initialize the database connection.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = Path(db_path)
        self.connection = None
        self._initialize_database()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _initialize_database(self):
        """Create the products table if it doesn't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    gtin TEXT,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    unit_price TEXT,
                    retailer TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_clubcard_price INTEGER DEFAULT 0,
                    normal_price REAL
                )
            """)
            
            # Migration: Add is_clubcard_price and normal_price columns if they don't exist
            cursor.execute("PRAGMA table_info(products)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'is_clubcard_price' not in columns:
                cursor.execute("""
                    ALTER TABLE products ADD COLUMN is_clubcard_price INTEGER DEFAULT 0
                """)
                print("✓ Added 'is_clubcard_price' column to database")
            
            if 'normal_price' not in columns:
                cursor.execute("""
                    ALTER TABLE products ADD COLUMN normal_price REAL
                """)
                print("✓ Added 'normal_price' column to database")

            if 'member_price' not in columns:
                cursor.execute("""
                    ALTER TABLE products ADD COLUMN member_price REAL
                """)
                print("✓ Added 'member_price' column to database")
            
            # Create index on GTIN for faster lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_gtin 
                ON products(gtin) 
                WHERE gtin IS NOT NULL
            """)
            
            # Create index on retailer and name for fuzzy matching
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_retailer_name 
                ON products(retailer, name)
            """)
            
            print(f"✓ Database initialized at {self.db_path}")
    
    def insert_product(self, product_data: Dict[str, Any]) -> int:
        """
        Insert a new product into the database.
        
        Args:
            product_data: Dictionary containing product information
            
        Returns:
            int: The ID of the inserted product
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO products (gtin, name, price, unit_price, retailer, timestamp,
                                      is_clubcard_price, normal_price, member_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                product_data.get('gtin'),
                product_data['name'],
                product_data['price'],
                product_data.get('unit_price'),
                product_data['retailer'],
                product_data.get('timestamp', datetime.now().isoformat()),
                product_data.get('is_clubcard_price', 0),
                product_data.get('normal_price'),
                product_data.get('member_price'),
            ))
            return cursor.lastrowid
    
    def update_product_by_gtin(self, gtin: str, product_data: Dict[str, Any]) -> bool:
        """
        Update an existing product by GTIN.
        
        Args:
            gtin: The GTIN to search for
            product_data: Dictionary containing updated product information
            
        Returns:
            bool: True if product was updated, False if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE products
                SET price = ?,
                    unit_price = ?,
                    name = ?,
                    timestamp = ?,
                    updated_at = CURRENT_TIMESTAMP,
                    is_clubcard_price = ?,
                    normal_price = ?,
                    member_price = ?
                WHERE gtin = ? AND retailer = ?
            """, (
                product_data['price'],
                product_data.get('unit_price'),
                product_data['name'],
                product_data.get('timestamp', datetime.now().isoformat()),
                product_data.get('is_clubcard_price', 0),
                product_data.get('normal_price'),
                product_data.get('member_price'),
                gtin,
                product_data['retailer']
            ))
            return cursor.rowcount > 0
    
    def update_product_by_id(self, product_id: int, product_data: Dict[str, Any]) -> bool:
        """
        Update an existing product by its primary key.
        Used for fuzzy-matched products that have no GTIN.

        Args:
            product_id: The row id to update
            product_data: Dictionary containing updated product information

        Returns:
            bool: True if a row was updated, False otherwise
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE products
                SET price = ?,
                    unit_price = ?,
                    name = ?,
                    timestamp = ?,
                    updated_at = CURRENT_TIMESTAMP,
                    is_clubcard_price = ?,
                    normal_price = ?,
                    member_price = ?
                WHERE id = ?
            """, (
                product_data['price'],
                product_data.get('unit_price'),
                product_data['name'],
                product_data.get('timestamp', datetime.now().isoformat()),
                product_data.get('is_clubcard_price', 0),
                product_data.get('normal_price'),
                product_data.get('member_price'),
                product_id,
            ))
            return cursor.rowcount > 0

    def find_product_by_gtin(self, gtin: str, retailer: str) -> Optional[Dict[str, Any]]:
        """
        Find a product by GTIN and retailer.
        
        Args:
            gtin: The GTIN to search for
            retailer: The retailer name
            
        Returns:
            Dict containing product data or None if not found
        """
        if not gtin:
            return None
            
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM products 
                WHERE gtin = ? AND retailer = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (gtin, retailer))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def find_similar_products(self, name: str, retailer: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Find products with similar names from the same retailer.
        Used for fuzzy matching.
        
        Args:
            name: Product name to search for
            retailer: The retailer name
            limit: Maximum number of results
            
        Returns:
            List of dictionaries containing product data
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM products 
                WHERE retailer = ? AND name LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (retailer, f"%{name[:20]}%", limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_products(self, retailer: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all products, optionally filtered by retailer.
        
        Args:
            retailer: Optional retailer name to filter by
            
        Returns:
            List of dictionaries containing product data
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if retailer:
                cursor.execute("""
                    SELECT * FROM products 
                    WHERE retailer = ?
                    ORDER BY timestamp DESC
                """, (retailer,))
            else:
                cursor.execute("""
                    SELECT * FROM products 
                    ORDER BY timestamp DESC
                """)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_product_count(self) -> int:
        """Get the total number of products in the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM products")
            return cursor.fetchone()[0]
    
    def get_latest_products(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most recently added/updated products.
        
        Args:
            limit: Maximum number of products to return
            
        Returns:
            List of dictionaries containing product data
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM products 
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
