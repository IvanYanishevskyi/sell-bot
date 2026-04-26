from __future__ import annotations

import sqlite3
from typing import Any

from order_bot.repositories.base import BaseRepository


class ClientRepository(BaseRepository):
    @staticmethod
    def _normalize(name: str) -> str:
        return " ".join(name.strip().lower().split())

    def get_or_create(self, name: str, telegram_user_id: int | None = None, phone: str | None = None) -> sqlite3.Row:
        normalized = self._normalize(name)
        row = self.qb.fetch_one("SELECT * FROM clients WHERE name_normalized = ?", (normalized,))
        if row:
            return row

        client_id = self.qb.insert(
            "clients",
            {
                "name": name.strip(),
                "name_normalized": normalized,
                "telegram_user_id": telegram_user_id,
                "phone": phone,
            },
        )
        created = self.qb.fetch_one("SELECT * FROM clients WHERE id = ?", (client_id,))
        if created is None:
            raise RuntimeError("Failed to create client")
        return created

    def get_by_id(self, client_id: int) -> sqlite3.Row | None:
        return self.qb.fetch_one("SELECT * FROM clients WHERE id = ?", (client_id,))

    def list_active(self, limit: int = 20) -> list[sqlite3.Row]:
        lim = max(1, min(limit, 100))
        return self.qb.fetch_all(
            "SELECT * FROM clients WHERE is_active = 1 ORDER BY updated_at DESC, id DESC LIMIT ?",
            (lim,),
        )

    def search_active_by_name(self, query: str, limit: int = 20) -> list[sqlite3.Row]:
        lim = max(1, min(limit, 100))
        q = f"%{self._normalize(query)}%"
        return self.qb.fetch_all(
            "SELECT * FROM clients WHERE is_active = 1 AND name_normalized LIKE ? ORDER BY updated_at DESC LIMIT ?",
            (q, lim),
        )

    def create_client(
        self,
        name: str,
        discount_percent: float = 0,
        discount_fixed: float = 0,
        price_level: str = "base",
        telegram_user_id: int | None = None,
        phone: str | None = None,
    ) -> int:
        normalized = self._normalize(name)
        return self.qb.insert(
            "clients",
            {
                "name": name.strip(),
                "name_normalized": normalized,
                "telegram_user_id": telegram_user_id,
                "phone": phone,
                "discount_percent": float(discount_percent),
                "discount_fixed": float(discount_fixed),
                "price_level": price_level,
                "is_active": 1,
            },
        )

    def deactivate(self, client_id: int) -> int:
        return self.qb.update("clients", {"is_active": 0}, "id = ?", (client_id,))

    def update_client(
        self,
        client_id: int,
        name: str | None = None,
        discount_percent: float | None = None,
        discount_fixed: float | None = None,
        price_level: str | None = None,
        phone: str | None = None,
    ) -> int:
        fields: dict[str, Any] = {}
        if name is not None:
            fields["name"] = name.strip()
            fields["name_normalized"] = self._normalize(name)
        if discount_percent is not None:
            fields["discount_percent"] = float(discount_percent)
        if discount_fixed is not None:
            fields["discount_fixed"] = float(discount_fixed)
        if price_level is not None:
            fields["price_level"] = price_level
        if phone is not None:
            fields["phone"] = phone
        if not fields:
            return 0
        return self.qb.update("clients", fields, "id = ?", (client_id,))
