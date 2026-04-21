"""
Database module for the grocery price comparison engine.
Supports PostgreSQL (Supabase) via SQLAlchemy, with SQLite fallback for local dev.
"""
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any, Union

from sqlalchemy import (
    create_engine, Column, Integer, Float, String, Text, DateTime, Boolean,
    Index, text, inspect,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.sql import func


# ── Helpers ──────────────────────────────────────────────────────────────────

def format_time_ago(ts: Union[str, datetime, None]) -> Optional[str]:
    """Turn a timestamp into a human-readable 'Updated X ago' string."""
    if not ts:
        return None
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None
    elif isinstance(ts, datetime):
        dt = ts
    else:
        return None

    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "Updated just now"
    if seconds < 60:
        return "Updated just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"Updated {minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"Updated {hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days < 30:
        return f"Updated {days} day{'s' if days != 1 else ''} ago"
    months = days // 30
    if months < 12:
        return f"Updated {months} month{'s' if months != 1 else ''} ago"
    years = days // 365
    return f"Updated {years} year{'s' if years != 1 else ''} ago"


# ── Connection helpers (must be defined before models) ───────────────────────

def _get_database_url() -> str:
    """Resolve the database URL from environment, falling back to local SQLite."""
    url = os.environ.get("DATABASE_URL", "")
    if url:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url
    return "sqlite:///products.db"


def _is_postgres(url: str = "") -> bool:
    return (url or _get_database_url()).startswith("postgresql")


# ── SQLAlchemy models ────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class ProductModel(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gtin = Column(String, nullable=True, index=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    unit_price = Column(String, nullable=True)
    retailer = Column(String, nullable=False)
    timestamp = Column(DateTime, default=func.now())
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    is_clubcard_price = Column(Integer, default=0)
    normal_price = Column(Float, nullable=True)
    member_price = Column(Float, nullable=True)

    __table_args__ = (
        Index("idx_retailer_name", "retailer", "name"),
    )


def _items_column():
    """Use JSONB on PostgreSQL, TEXT on SQLite."""
    if _is_postgres(_get_database_url()):
        return Column(JSONB, nullable=False)
    return Column(Text, nullable=False)


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    items = _items_column()
    total_price = Column(Float, nullable=False)
    retailer = Column(String, nullable=False)
    address = Column(String, nullable=False)
    delivery_time = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, default=func.now())


# ── Database class (same public API as the old SQLite version) ───────────────

class Database:
    """Database manager for grocery products. Works with PostgreSQL and SQLite."""

    def __init__(self, db_path: str = "products.db"):
        db_url = _get_database_url()

        if _is_postgres(db_url):
            self.engine = create_engine(db_url, pool_pre_ping=True, pool_size=5)
            self._dialect = "postgresql"
        else:
            self.engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
            self._dialect = "sqlite"

        self.Session = sessionmaker(bind=self.engine)
        self._initialize_database()
        self.db_path = db_path  # kept for compat with code that reads this attribute

    @property
    def is_postgres(self) -> bool:
        return self._dialect == "postgresql"

    def _initialize_database(self):
        """Create tables if they don't exist."""
        Base.metadata.create_all(self.engine)
        print(f"✓ Database initialized ({self._dialect})")

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert an ORM model instance to a plain dict."""
        d = {c.key: getattr(row, c.key) for c in row.__table__.columns}
        # Ensure datetime fields are ISO strings for JSON serialisation
        for k in ("timestamp", "created_at", "updated_at"):
            if k in d and isinstance(d[k], datetime):
                d[k] = d[k].isoformat()
        return d

    # ── Products ─────────────────────────────────────────────────────────

    def insert_product(self, product_data: Dict[str, Any]) -> int:
        with self.Session() as s:
            p = ProductModel(
                gtin=product_data.get("gtin"),
                name=product_data["name"],
                price=product_data["price"],
                unit_price=product_data.get("unit_price"),
                retailer=product_data["retailer"],
                timestamp=product_data.get("timestamp", datetime.now()),
                is_clubcard_price=product_data.get("is_clubcard_price", 0),
                normal_price=product_data.get("normal_price"),
                member_price=product_data.get("member_price"),
            )
            s.add(p)
            s.commit()
            s.refresh(p)
            return p.id

    def update_product_by_gtin(self, gtin: str, product_data: Dict[str, Any]) -> bool:
        if not gtin:
            return False
        with self.Session() as s:
            row = s.query(ProductModel).filter_by(gtin=gtin, retailer=product_data["retailer"]).first()
            if not row:
                return False
            row.price = product_data["price"]
            row.unit_price = product_data.get("unit_price")
            row.name = product_data["name"]
            row.timestamp = product_data.get("timestamp", datetime.now())
            row.updated_at = datetime.now()
            row.is_clubcard_price = product_data.get("is_clubcard_price", 0)
            row.normal_price = product_data.get("normal_price")
            row.member_price = product_data.get("member_price")
            s.commit()
            return True

    def update_product_by_id(self, product_id: int, product_data: Dict[str, Any]) -> bool:
        with self.Session() as s:
            row = s.query(ProductModel).get(product_id)
            if not row:
                return False
            row.price = product_data["price"]
            row.unit_price = product_data.get("unit_price")
            row.name = product_data["name"]
            row.timestamp = product_data.get("timestamp", datetime.now())
            row.updated_at = datetime.now()
            row.is_clubcard_price = product_data.get("is_clubcard_price", 0)
            row.normal_price = product_data.get("normal_price")
            row.member_price = product_data.get("member_price")
            s.commit()
            return True

    def find_product_by_gtin(self, gtin: str, retailer: str) -> Optional[Dict[str, Any]]:
        if not gtin:
            return None
        with self.Session() as s:
            row = (
                s.query(ProductModel)
                .filter_by(gtin=gtin, retailer=retailer)
                .order_by(ProductModel.timestamp.desc())
                .first()
            )
            return self._row_to_dict(row) if row else None

    def find_similar_products(self, name: str, retailer: str, limit: int = 10) -> List[Dict[str, Any]]:
        with self.Session() as s:
            rows = (
                s.query(ProductModel)
                .filter(ProductModel.retailer == retailer, ProductModel.name.ilike(f"%{name[:20]}%"))
                .order_by(ProductModel.timestamp.desc())
                .limit(limit)
                .all()
            )
            return [self._row_to_dict(r) for r in rows]

    def get_all_products(self, retailer: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.Session() as s:
            q = s.query(ProductModel)
            if retailer:
                q = q.filter_by(retailer=retailer)
            rows = q.order_by(ProductModel.timestamp.desc()).all()
            return [self._row_to_dict(r) for r in rows]

    def get_product_count(self) -> int:
        with self.Session() as s:
            return s.query(ProductModel).count()

    def get_latest_products(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self.Session() as s:
            rows = (
                s.query(ProductModel)
                .order_by(ProductModel.timestamp.desc())
                .limit(limit)
                .all()
            )
            return [self._row_to_dict(r) for r in rows]

    # ── Orders ───────────────────────────────────────────────────────────

    def create_order(self, order_data: Dict[str, Any]) -> int:
        items = order_data.get("items", [])
        with self.Session() as s:
            o = OrderModel(
                items=items if self.is_postgres else json.dumps(items),
                total_price=order_data["total_price"],
                retailer=order_data["retailer"],
                address=order_data["address"],
                delivery_time=order_data["delivery_time"],
                phone=order_data.get("phone"),
                status=order_data.get("status", "pending"),
            )
            s.add(o)
            s.commit()
            s.refresh(o)
            return o.id

    def get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        with self.Session() as s:
            row = s.query(OrderModel).get(order_id)
            if not row:
                return None
            order = self._row_to_dict(row)
            if isinstance(order["items"], str):
                order["items"] = json.loads(order["items"])
            return order
