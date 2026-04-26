from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from .query_builder import QueryBuilder 

class Database:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def initialize_schema(self, schema_path: str | Path) -> None:
        schema_sql = Path(schema_path).read_text(encoding="utf-8")
        with self.connect() as conn:
            conn.executescript(schema_sql)
            conn.commit()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
                # ====================== PRICE SERVICE ======================
    def insert_price(
        self,
        rows: list[dict],
        source_filename: str,
        created_by: str | None = None,
    ) -> int:
        """Завантажує новий прайс"""
        if not rows:
            raise ValueError("Прайс порожній")
        with self.transaction() as conn:
            qb = QueryBuilder(conn)
            
            # Деактивуємо старі версії
            conn.execute("UPDATE price_versions SET is_active = 0")
            
            # Створюємо нову версію
            version_id = qb.insert("price_versions", {
                "version_label": source_filename,
                "source_filename": source_filename,
                "is_active": 1,
                "created_by": created_by,
                "items_count": 0,
            })
            
            # Будуємо items з підтримкою багатьох рівнів цін
            price_items = []
            for row in rows:
                # Підтримка нового формату з багатьма рівнями цін
                if "base_price" in row:
                    item = {
                        "price_version_id": version_id,
                        "sku": str(row.get("sku") or row.get("name") or "").strip(),
                        "name": str(row.get("name") or "").strip(),
                        "base_price": float(row.get("base_price") or 0),
                        "price_200k": float(row.get("price_200k") or row.get("base_price") or 0),
                        "discount_200k_percent": float(row.get("discount_200k_percent") or 0),
                        "price_150k": float(row.get("price_150k") or row.get("base_price") or 0),
                        "discount_150k_percent": float(row.get("discount_150k_percent") or 0),
                        "price_100k": float(row.get("price_100k") or row.get("base_price") or 0),
                        "discount_100k_percent": float(row.get("discount_100k_percent") or 0),
                    }
                else:
                    # Старий формат
                    price_val = float(row.get("price") or row.get("price_at_order") or 0)
                    item = {
                        "price_version_id": version_id,
                        "sku": str(row.get("sku") or row.get("name") or "").strip(),
                        "name": str(row.get("name") or "").strip(),
                        "base_price": price_val,
                        "price_200k": price_val,
                        "discount_200k_percent": 0,
                        "price_150k": price_val,
                        "discount_150k_percent": 0,
                        "price_100k": price_val,
                        "discount_100k_percent": 0,
                    }
                
                if item["name"] and item["base_price"] > 0:
                    price_items.append(item)
            
            if price_items:
                qb.bulk_insert("price_items", price_items)
                qb.update("price_versions", {"items_count": len(price_items)}, "id = ?", (version_id,))
            
            print(f"✅ Прайс завантажено: {len(price_items)} рядків")
            return version_id