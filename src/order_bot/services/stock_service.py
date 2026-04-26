from __future__ import annotations

from typing import Any

from order_bot.db.connection import Database
from order_bot.repositories.stock import StockRepository


class StockService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def upload_stock(
        self,
        rows: list[dict[str, Any]],
        source_filename: str,
        uploaded_by: str | None = None,
    ) -> int:
        if not rows:
            raise ValueError("Stock rows are empty")

        normalized_rows = [
            {
                "sku": str(row["sku"]).strip(),
                "quantity": int(row["quantity"]),
            }
            for row in rows
        ]

        with self.db.transaction() as conn:
            repo = StockRepository(conn)
            upload_id = repo.create_upload(
                source_filename=source_filename,
                rows_count=len(normalized_rows),
                uploaded_by=uploaded_by,
            )
            repo.add_items(upload_id, normalized_rows)
            # Every stock file is treated as a full fresh snapshot.
            repo.deactivate_current()
            repo.upsert_current(upload_id, normalized_rows)
            return upload_id
