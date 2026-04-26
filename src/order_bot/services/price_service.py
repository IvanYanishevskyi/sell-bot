from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from order_bot.db.connection import Database
from order_bot.repositories.price import PriceRepository


class PriceService:
    def __init__(self, db: Database) -> None:
        self.db = db
    def upload_new_price(
        self,
        rows: list,
        source_filename: str,
        created_by: str | None = None,
    ) -> int:
        """Завантажує новий прайс"""
        if not rows:
            raise ValueError("Прайс порожній")

        price_rows = []

        for row in rows:
            if hasattr(row, 'model_dump'):
                row_dict = row.model_dump()
            elif hasattr(row, 'dict'):
                row_dict = row.dict()
            else:
                row_dict = dict(row) if isinstance(row, (dict, tuple)) else vars(row)

            # Новий формат з багатьма рівнями цін
            sku = str(row_dict.get("sku") or row_dict.get("name") or "").strip()
            name = str(row_dict.get("name") or "").strip()
            base_price = float(row_dict.get("base_price") or 0)

            if not sku or not name or base_price <= 0:
                continue

            # Збираємо всі рівні цін
            price_rows.append({
                "sku": sku,
                "name": name,
                "base_price": base_price,
                "price_200k": float(row_dict.get("price_200k") or base_price),
                "discount_200k_percent": float(row_dict.get("discount_200k_percent") or 0),
                "price_150k": float(row_dict.get("price_150k") or base_price),
                "discount_150k_percent": float(row_dict.get("discount_150k_percent") or 0),
                "price_100k": float(row_dict.get("price_100k") or base_price),
                "discount_100k_percent": float(row_dict.get("discount_100k_percent") or 0),
            })

        if not price_rows:
            raise ValueError("Не знайдено жодного валідного рядка в прайсі")

        version_id = self.db.insert_price(
            rows=price_rows,
            source_filename=source_filename,
            created_by=created_by,
        )

        return version_id

    def get_active(self) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            repo = PriceRepository(conn)
            return repo.get_active()

    def list_active_items(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            repo = PriceRepository(conn)
            return [dict(row) for row in repo.list_active_items(limit=limit, offset=offset)]
