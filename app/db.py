from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import DB_PATH, DEFAULT_LOW_STOCK_THRESHOLD, DEFAULT_TAX_PERCENT

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'cashier')) DEFAULT 'cashier',
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS app_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT UNIQUE,
    email TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    phone TEXT,
    email TEXT,
    address TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE COLLATE NOCASE,
    barcode TEXT,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'General',
    brand TEXT,
    unit TEXT NOT NULL DEFAULT 'pcs',
    price REAL NOT NULL CHECK(price >= 0),
    cost_price REAL NOT NULL DEFAULT 0 CHECK(cost_price >= 0),
    discount_percent REAL NOT NULL DEFAULT 0 CHECK(discount_percent BETWEEN 0 AND 100),
    tax_percent REAL NOT NULL DEFAULT 0 CHECK(tax_percent BETWEEN 0 AND 100),
    stock_qty REAL NOT NULL DEFAULT 0,
    reorder_level REAL NOT NULL DEFAULT 5,
    expiry_date TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_no TEXT NOT NULL UNIQUE,
    customer_id INTEGER REFERENCES customers(id),
    cashier_id INTEGER NOT NULL REFERENCES users(id),
    sold_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    subtotal REAL NOT NULL,
    discount_total REAL NOT NULL DEFAULT 0,
    tax_total REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL,
    payment_method TEXT NOT NULL CHECK(payment_method IN ('Cash', 'UPI')),
    amount_tendered REAL NOT NULL DEFAULT 0,
    change_due REAL NOT NULL DEFAULT 0,
    payment_reference TEXT,
    refunded_total REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'COMPLETED' CHECK(status IN ('COMPLETED', 'PARTIALLY_REFUNDED', 'REFUNDED')),
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_sales_sold_at ON sales(sold_at);
CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE RESTRICT,
    product_id INTEGER REFERENCES products(id),
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    quantity REAL NOT NULL CHECK(quantity > 0),
    unit_price REAL NOT NULL,
    unit_cost REAL NOT NULL DEFAULT 0,
    discount_percent REAL NOT NULL DEFAULT 0,
    tax_percent REAL NOT NULL DEFAULT 0,
    gross_amount REAL NOT NULL,
    discount_amount REAL NOT NULL DEFAULT 0,
    tax_amount REAL NOT NULL DEFAULT 0,
    line_total REAL NOT NULL,
    refunded_qty REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL REFERENCES sales(id),
    method TEXT NOT NULL,
    amount REAL NOT NULL,
    reference TEXT,
    status TEXT NOT NULL DEFAULT 'RECORDED',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS refunds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    refund_no TEXT NOT NULL UNIQUE,
    sale_id INTEGER NOT NULL REFERENCES sales(id),
    amount REAL NOT NULL,
    tax_amount REAL NOT NULL DEFAULT 0,
    payment_method TEXT NOT NULL,
    reason TEXT,
    restocked INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS refund_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    refund_id INTEGER NOT NULL REFERENCES refunds(id),
    sale_item_id INTEGER NOT NULL REFERENCES sale_items(id),
    product_id INTEGER REFERENCES products(id),
    quantity REAL NOT NULL,
    amount REAL NOT NULL,
    tax_amount REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_no TEXT NOT NULL UNIQUE,
    supplier_id INTEGER REFERENCES suppliers(id),
    purchased_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    subtotal REAL NOT NULL,
    tax_total REAL NOT NULL DEFAULT 0,
    total REAL NOT NULL,
    notes TEXT,
    created_by INTEGER NOT NULL REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS purchase_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL REFERENCES purchases(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity REAL NOT NULL CHECK(quantity > 0),
    unit_cost REAL NOT NULL,
    tax_percent REAL NOT NULL DEFAULT 0,
    line_total REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL CHECK(amount > 0),
    expense_date TEXT NOT NULL DEFAULT CURRENT_DATE,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    movement_type TEXT NOT NULL CHECK(movement_type IN ('OPENING', 'PURCHASE', 'SALE', 'RETURN', 'ADJUSTMENT')),
    quantity REAL NOT NULL,
    reference_type TEXT,
    reference_id INTEGER,
    note TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_stock_movements_product ON stock_movements(product_id, created_at);
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id INTEGER,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 20000")
    return conn


@contextmanager
def transaction(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str | Path | None = None) -> None:
    conn = connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        defaults = {
            "store_name": "Retail Wizard Store",
            "store_address": "",
            "store_phone": "",
            "store_email": "",
            "currency": "INR",
            "low_stock_threshold": str(DEFAULT_LOW_STOCK_THRESHOLD),
            "default_tax_percent": str(DEFAULT_TAX_PERCENT),
            "upi_vpa": "",
        }
        conn.executemany(
            "INSERT OR IGNORE INTO app_settings(setting_key, setting_value) VALUES (?, ?)",
            defaults.items(),
        )
        conn.commit()
    finally:
        conn.close()


def backup_database(destination: str | Path, db_path: str | Path | None = None) -> Path:
    """Create a consistent SQLite backup using the online backup API."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    source = connect(db_path)
    backup = sqlite3.connect(str(target))
    try:
        source.backup(backup)
        backup.commit()
    finally:
        backup.close()
        source.close()
    return target
