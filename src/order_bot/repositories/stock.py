from __future__ import annotations

import sqlite3
from typing import Any

from order_bot.repositories.base import BaseRepository


class StockRepository(BaseRepository):
    def create_upload(self, source_filename: str, rows_count: int, uploaded_by: str | None = None) -> int:
        return self.qb.insert(
            "stock_uploads",
            {
                "source_filename": source_filename,
                "rows_count": rows_count,
                "uploaded_by": uploaded_by,
                "is_active": 1,
            },
        )

    def add_items(self, upload_id: int, items: list[dict[str, Any]]) -> None:
        payload = [
            {
                "stock_upload_id": upload_id,
                "sku": item["sku"],
                "quantity": int(item["quantity"]),
                "is_active": 1,
            }
            for item in items
        ]
        self.qb.bulk_insert("stock_items", payload)

    def deactivate_current(self) -> None:
        self.qb.execute("UPDATE stock_current SET is_active = 0 WHERE is_active = 1")

    def upsert_current(self, upload_id: int, items: list[dict[str, Any]]) -> None:
        for item in items:
            self.qb.upsert(
                table="stock_current",
                data={
                    "sku": item["sku"],
                    "stock_upload_id": upload_id,
                    "quantity": int(item["quantity"]),
                    "is_active": 1,
                },
                conflict_columns=["sku"],
                update_columns=["stock_upload_id", "quantity", "is_active", "updated_at"],
            )

    def get_by_sku(self, sku: str) -> sqlite3.Row | None:
        return self.qb.fetch_one(
            "SELECT sku, quantity, stock_upload_id FROM stock_current WHERE sku = ? AND is_active = 1",
            (sku,),
        )
