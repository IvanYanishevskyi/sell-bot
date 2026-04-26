from __future__ import annotations

from pathlib import Path

from order_bot.db.connection import Database


def _table_exists(db: Database, table: str) -> bool:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table,),
        ).fetchone()
        return row is not None


def _ensure_column(db: Database, table: str, column: str, definition_sql: str) -> None:
    with db.connect() as conn:
        cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {str(col["name"]) for col in cols}
        if column in existing:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition_sql}")
        conn.commit()


def _ensure_column_if_table_exists(db: Database, table: str, column: str, definition_sql: str) -> None:
    if not _table_exists(db, table):
        return
    _ensure_column(db, table, column, definition_sql)


def _migrate_price_items_if_needed(db: Database) -> None:
    """Migrate old price_items (with 'price' column) to new multi-level schema."""
    if not _table_exists(db, "price_items"):
        return

    with db.connect() as conn:
        cols = conn.execute("PRAGMA table_info(price_items)").fetchall()
        existing = {str(col["name"]) for col in cols}
        if "base_price" in existing:
            return  # already migrated

        conn.execute("""
            CREATE TABLE price_items_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                price_version_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                name TEXT NOT NULL,
                base_price NUMERIC NOT NULL,
                price_200k NUMERIC NOT NULL,
                discount_200k_percent NUMERIC DEFAULT 0,
                price_150k NUMERIC NOT NULL,
                discount_150k_percent NUMERIC DEFAULT 0,
                price_100k NUMERIC NOT NULL,
                discount_100k_percent NUMERIC DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'UAH',
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (price_version_id) REFERENCES price_versions(id) ON DELETE CASCADE,
                UNIQUE(price_version_id, sku)
            )
        """)

        conn.execute("""
            INSERT INTO price_items_new (
                id, price_version_id, sku, name, base_price,
                price_200k, discount_200k_percent,
                price_150k, discount_150k_percent,
                price_100k, discount_100k_percent,
                currency, is_active, created_at, updated_at
            )
            SELECT
                id, price_version_id, sku, name, price as base_price,
                price as price_200k, 0 as discount_200k_percent,
                price as price_150k, 0 as discount_150k_percent,
                price as price_100k, 0 as discount_100k_percent,
                currency, is_active, created_at, updated_at
            FROM price_items
        """)

        conn.execute("DROP TABLE price_items")
        conn.execute("ALTER TABLE price_items_new RENAME TO price_items")
        conn.execute("CREATE INDEX idx_price_items_sku ON price_items(sku)")
        conn.execute("CREATE INDEX idx_price_items_is_active ON price_items(is_active)")
        conn.execute("CREATE INDEX idx_price_items_updated_at ON price_items(updated_at)")
        conn.execute("CREATE INDEX idx_price_items_version_id ON price_items(price_version_id)")
        conn.commit()


def init_db(db_path: str | Path, schema_path: str | Path | None = None) -> None:
    schema_file = Path(schema_path) if schema_path else Path(__file__).with_name("schema.sql")
    db = Database(db_path)

    # Pre-migration for old DBs: schema now creates index on orders.warehouse_id.
    _ensure_column_if_table_exists(db, "orders", "warehouse_id", "warehouse_id INTEGER")

    db.initialize_schema(schema_file)

    # Forward-safe additive migrations for existing SQLite files.
    _ensure_column(db, "clients", "discount_percent", "discount_percent NUMERIC NOT NULL DEFAULT 0")
    _ensure_column(db, "clients", "discount_fixed", "discount_fixed NUMERIC NOT NULL DEFAULT 0")
    _ensure_column(db, "clients", "price_level", "price_level TEXT DEFAULT 'base' CHECK (price_level IN ('base', '200k', '150k', '100k'))")
    _ensure_column(db, "orders", "subtotal_amount", "subtotal_amount NUMERIC NOT NULL DEFAULT 0")
    _ensure_column(db, "orders", "discount_amount", "discount_amount NUMERIC NOT NULL DEFAULT 0")
    _ensure_column(db, "orders", "warehouse_id", "warehouse_id INTEGER")

    _migrate_price_items_if_needed(db)
