from __future__ import annotations

import sqlite3
from typing import Any

from order_bot.repositories.base import BaseRepository


class WarehouseRepository(BaseRepository):
    @staticmethod
    def _normalize(name: str) -> str:
        return " ".join(name.strip().lower().split())

    def get_by_id(self, warehouse_id: int) -> sqlite3.Row | None:
        return self.qb.fetch_one("SELECT * FROM warehouses WHERE id = ?", (warehouse_id,))

    def get_by_normalized_name(self, name_normalized: str) -> sqlite3.Row | None:
        return self.qb.fetch_one("SELECT * FROM warehouses WHERE name_normalized = ?", (name_normalized,))

    def deactivate_all_active(self) -> None:
        self.qb.execute("UPDATE warehouses SET is_active = 0 WHERE is_active = 1")

    def list_active(self, limit: int = 20) -> list[sqlite3.Row]:
        lim = max(1, min(limit, 100))
        return self.qb.fetch_all(
            "SELECT * FROM warehouses WHERE is_active = 1 ORDER BY updated_at DESC, id DESC LIMIT ?",
            (lim,),
        )

    def search_active_by_name(self, query: str, limit: int = 20) -> list[sqlite3.Row]:
        lim = max(1, min(limit, 100))
        q = f"%{self._normalize(query)}%"
        return self.qb.fetch_all(
            "SELECT * FROM warehouses WHERE is_active = 1 AND name_normalized LIKE ? ORDER BY updated_at DESC LIMIT ?",
            (q, lim),
        )

    def create_warehouse(self, name: str) -> int:
        return self.qb.insert(
            "warehouses",
            {
                "name": name.strip(),
                "name_normalized": self._normalize(name),
                "is_active": 1,
            },
        )

    def deactivate(self, warehouse_id: int) -> int:
        return self.qb.update("warehouses", {"is_active": 0}, "id = ?", (warehouse_id,))

    def update_warehouse(self, warehouse_id: int, name: str | None = None) -> int:
        fields: dict[str, Any] = {}
        if name is not None:
            fields["name"] = name.strip()
            fields["name_normalized"] = self._normalize(name)
        if not fields:
            return 0
        return self.qb.update("warehouses", fields, "id = ?", (warehouse_id,))

    def upsert_warehouse(self, name: str) -> sqlite3.Row:
        clean_name = name.strip()
        normalized = self._normalize(clean_name)
        self.qb.upsert(
            table="warehouses",
            data={
                "name": clean_name,
                "name_normalized": normalized,
                "is_active": 1,
            },
            conflict_columns=["name_normalized"],
            update_columns=["name", "is_active", "updated_at"],
        )
        row = self.get_by_normalized_name(normalized)
        if row is None:
            raise RuntimeError("warehouse upsert failed")
        return row
