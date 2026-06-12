import os
import sys
import sqlite3
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import src.utils.Constants as CONSTANT
from src.utils.LogSetup import get_logger

logger = get_logger()


def setup_database():
    """
    Purpose: Creates the complete SQLite database schema for AtlasCare, dropping existing tables first.
    Args: None
    Returns: None
    Raises: sqlite3.Error if database execution fails.
    """
    conn = None
    try:
        conn = sqlite3.connect("acme-retail.db")
        cursor = conn.cursor()

        # Enforce foreign key constraints
        cursor.execute("PRAGMA foreign_keys = ON;")

        logger.info("🧹 Dropping existing tables if they exist...")
        # 0. Drop existing tables (Child tables dropped before parent tables)
        cursor.execute("DROP TABLE IF EXISTS performance_logs")
        cursor.execute("DROP TABLE IF EXISTS cases")
        cursor.execute("DROP TABLE IF EXISTS orders")
        cursor.execute("DROP TABLE IF EXISTS customers")

        logger.info("🏗️ Creating fresh tables...")
        # 1. CRM Customers
        cursor.execute("""
            CREATE TABLE customers (
                customer_id TEXT PRIMARY KEY,
                name TEXT,
                email TEXT UNIQUE,
                phone TEXT,
                tier TEXT,
                preferred_refund_method TEXT,
                addresses TEXT 
            )
        """)

        # 2. Orders (The Source of Truth for order state)
        cursor.execute("""
            CREATE TABLE orders (
                order_id TEXT PRIMARY KEY,
                customer_id TEXT,
                status TEXT,
                created_at TEXT,
                estimated_delivery TEXT,
                tracking_number TEXT,
                shipping_address TEXT,
                items TEXT,
                total_amount REAL,
                payment_method TEXT,
                FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
            )
        """)

        # 3. CRM Cases (Escalation history)
        cursor.execute("""
            CREATE TABLE cases (
                case_id TEXT PRIMARY KEY,
                customer_id TEXT,
                order_id TEXT,
                status TEXT DEFAULT 'open', -- 'open', 'in_progress', 'resolved',
                priority TEXT,
                description TEXT,
                item TEXT,
                amount_inr REAL,
                created_at TEXT,
                resolved_at TEXT,
                FOREIGN KEY(customer_id) REFERENCES customers(customer_id),
                FOREIGN KEY(order_id) REFERENCES orders(order_id)
            )
        """)


        # 4. Performance Logs (Tier 1 & 2 Business Metrics)
        cursor.execute("""
            CREATE TABLE performance_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                user_email TEXT,
                tokens_used INTEGER,
                is_escalated BOOLEAN,
                value_automated REAL,
                journey TEXT DEFAULT 'General Inquiry',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        logger.info(f"✅ Full schema successfully created inside database folder.")
        conn.close()
    except sqlite3.Error as e:
        logger.error(f"Database setup failed: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    setup_database()