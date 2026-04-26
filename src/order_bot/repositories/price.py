from __future__ import annotations

import sqlite3
from typing import Any

from order_bot.repositories.base import BaseRepository


class PriceRepository(BaseRepository):
    def create_version(
        self,
        version_label: str,
        source_filename: str,
        items_count: int,
        created_by: str | None = None,
    ) -> int:
        return self.qb.insert(
            "price_versions",
            {
                "version_label": version_label,
                "source_filename": source_filename,
                "items_count": items_count,
                "created_by": created_by,
                "is_active": 0,
            },
        )

    def add_items(self, version_id: int, items: list[dict[str, Any]]) -> None:
        payload = []
        for item in items:
            price_val = float(item.get("base_price") or item.get("price") or 0)
            payload.append({
                "price_version_id": version_id,
                "sku": item["sku"],
                "name": item["name"],
                "base_price": price_val,
                "price_200k": float(item.get("price_200k") or price_val),
                "discount_200k_percent": float(item.get("discount_200k_percent") or 0),
                "price_150k": float(item.get("price_150k") or price_val),
                "discount_150k_percent": float(item.get("discount_150k_percent") or 0),
                "price_100k": float(item.get("price_100k") or price_val),
                "discount_100k_percent": float(item.get("discount_100k_percent") or 0),
                "currency": item.get("currency", "USD"),
                "is_active": 1,
            })
        self.qb.bulk_insert("price_items", payload)

    def set_active(self, version_id: int) -> None:
        self.qb.execute("UPDATE price_versions SET is_active = 0 WHERE is_active = 1")
        self.qb.execute("UPDATE price_items SET is_active = 0 WHERE is_active = 1")
        self.qb.execute("UPDATE price_versions SET is_active = 1 WHERE id = ?", (version_id,))
        self.qb.execute("UPDATE price_items SET is_active = 1 WHERE price_version_id = ?", (version_id,))

    def get_active(self) -> dict[str, Any] | None:
        version = self.qb.fetch_one(
            "SELECT * FROM price_versions WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
        )
        if version is None:
            return None

        items = self.qb.fetch_all(
            """SELECT sku, name, base_price, base_price as price,
                price_200k, price_150k, price_100k, currency
            FROM price_items WHERE price_version_id = ? AND is_active = 1""",
            (version["id"],),
        )
        return {
            "version": dict(version),
            "items": [dict(row) for row in items],
        }

    def get_active_item_by_sku(self, sku: str) -> sqlite3.Row | None:
        return self.qb.fetch_one(
            """
            SELECT pi.sku, pi.name, pi.base_price as price, pi.base_price,
                pi.price_200k, pi.price_150k, pi.price_100k, pi.currency
            FROM price_items pi
            JOIN price_versions pv ON pv.id = pi.price_version_id
            WHERE pv.is_active = 1 AND pi.is_active = 1 AND pi.sku = ?
            LIMIT 1
            """,
            (sku,),
        )

    def list_active_items(self, limit: int = 50, offset: int = 0) -> list[sqlite3.Row]:
        return self.qb.fetch_all(
            """
            SELECT pi.sku, pi.name, pi.base_price, pi.price_200k, pi.price_150k, pi.price_100k, pi.currency
            FROM price_items pi
            JOIN price_versions pv ON pv.id = pi.price_version_id
            WHERE pv.is_active = 1 AND pi.is_active = 1
            ORDER BY pi.name
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
