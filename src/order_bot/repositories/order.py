from __future__ import annotations

import json
import sqlite3
from typing import Any

from order_bot.repositories.base import BaseRepository


class OrderRepository(BaseRepository):
    def create_draft(
        self,
        client_id: int | None,
        warehouse_id: int | None,
        subtotal_amount: float,
        discount_amount: float,
        total_amount: float,
        currency: str = "UAH",
        needs_review: bool = False,
    ) -> int:
        return self.qb.insert(
            "orders",
            {
                "client_id": client_id,
                "warehouse_id": warehouse_id,
                "status": "draft",
                "subtotal_amount": float(subtotal_amount),
                "discount_amount": float(discount_amount),
                "total_amount": total_amount,
                "currency": currency,
                "needs_review": 1 if needs_review else 0,
                "is_active": 1,
            },
        )

    def add_items(self, order_id: int, items: list[dict[str, Any]]) -> None:
        payload = [
            {
                "order_id": order_id,
                "sku": item["sku"],
                "name": item["name"],
                "qty": int(item["qty"]),
                "price_at_order": item["price_at_order"],
                "line_total": item["line_total"],
                "match_confidence": item.get("match_confidence"),
                "needs_review": 1 if item.get("needs_review") else 0,
                "available_qty": item.get("available_qty"),
                "is_active": 1,
            }
            for item in items
        ]
        self.qb.bulk_insert("order_items", payload)

    def update_status(self, order_id: int, status: str) -> int:
        return self.qb.update("orders", {"status": status}, "id = ?", (order_id,))

    def get_order_status(self, order_id: int) -> str | None:
        row = self.qb.fetch_one("SELECT status FROM orders WHERE id = ?", (order_id,))
        return str(row["status"]) if row else None

    def get_active_items(self, order_id: int) -> list[sqlite3.Row]:
        return self.qb.fetch_all(
            "SELECT * FROM order_items WHERE order_id = ? AND is_active = 1 ORDER BY id ASC",
            (order_id,),
        )

    def get_by_id(self, order_id: int) -> dict[str, Any] | None:
        order = self.qb.fetch_one(
            """
            SELECT
                o.*,
                c.name AS client_name,
                c.discount_percent AS client_discount_percent,
                c.discount_fixed AS client_discount_fixed,
                c.price_level AS client_price_level,
                w.name AS warehouse_name
            FROM orders o
            LEFT JOIN clients c ON c.id = o.client_id
            LEFT JOIN warehouses w ON w.id = o.warehouse_id
            WHERE o.id = ? AND o.is_active = 1
            """,
            (order_id,),
        )
        if order is None:
            return None

        items = self.qb.fetch_all(
            "SELECT * FROM order_items WHERE order_id = ? AND is_active = 1 ORDER BY id ASC",
            (order_id,),
        )
        raw_log = self.qb.fetch_one(
            "SELECT * FROM order_raw_log WHERE order_id = ? ORDER BY id DESC LIMIT 1",
            (order_id,),
        )
        return {
            "order": dict(order),
            "items": [dict(i) for i in items],
            "raw_log": dict(raw_log) if raw_log else None,
        }

    def add_raw_log(
        self,
        source_text: str,
        llm_payload: dict[str, Any] | None,
        parse_status: str,
        error_message: str | None = None,
        order_id: int | None = None,
    ) -> int:
        return self.qb.insert(
            "order_raw_log",
            {
                "order_id": order_id,
                "source_text": source_text,
                "llm_payload": json.dumps(llm_payload, ensure_ascii=False) if llm_payload is not None else None,
                "parse_status": parse_status,
                "error_message": error_message,
                "is_active": 1,
            },
        )

    def get_item(self, order_id: int, item_id: int) -> sqlite3.Row | None:
        return self.qb.fetch_one(
            "SELECT * FROM order_items WHERE id = ? AND order_id = ? AND is_active = 1",
            (item_id, order_id),
        )

    def update_item_qty(self, order_id: int, item_id: int, qty: int) -> int:
        row = self.get_item(order_id, item_id)
        if row is None:
            return 0
        price = float(row["price_at_order"])
        line_total = float(qty) * price
        return self.qb.update(
            "order_items",
            {"qty": int(qty), "line_total": line_total},
            "id = ? AND order_id = ? AND is_active = 1",
            (item_id, order_id),
        )

    def update_item_price(self, order_id: int, item_id: int, price_at_order: float) -> int:
        row = self.get_item(order_id, item_id)
        if row is None:
            return 0
        qty = int(row["qty"])
        line_total = float(price_at_order) * qty
        return self.qb.update(
            "order_items",
            {"price_at_order": float(price_at_order), "line_total": line_total},
            "id = ? AND order_id = ? AND is_active = 1",
            (item_id, order_id),
        )

    def add_item(self, order_id: int, item: dict[str, Any]) -> int:
        return self.qb.insert(
            "order_items",
            {
                "order_id": order_id,
                "sku": item["sku"],
                "name": item["name"],
                "qty": int(item["qty"]),
                "price_at_order": float(item["price_at_order"]),
                "line_total": float(item["line_total"]),
                "match_confidence": item.get("match_confidence"),
                "needs_review": 1 if item.get("needs_review") else 0,
                "available_qty": item.get("available_qty"),
                "is_active": 1,
            },
        )

    def deactivate_item(self, order_id: int, item_id: int) -> int:
        return self.qb.update(
            "order_items",
            {"is_active": 0},
            "id = ? AND order_id = ? AND is_active = 1",
            (item_id, order_id),
        )

    def count_active_items(self, order_id: int) -> int:
        row = self.qb.fetch_one(
            "SELECT COUNT(1) AS cnt FROM order_items WHERE order_id = ? AND is_active = 1",
            (order_id,),
        )
        return int(row["cnt"]) if row is not None else 0

    def set_client(self, order_id: int, client_id: int | None) -> int:
        return self.qb.update("orders", {"client_id": client_id}, "id = ?", (order_id,))

    def set_warehouse(self, order_id: int, warehouse_id: int | None) -> int:
        return self.qb.update("orders", {"warehouse_id": warehouse_id}, "id = ?", (order_id,))

    def list_orders(
        self,
        limit: int = 20,
        offset: int = 0,
        status_filter: str | None = None,
    ) -> list[sqlite3.Row]:
        params: list[Any] = [limit, offset]
        status_clause = ""
        if status_filter:
            status_clause = "AND o.status = ?"
            params.insert(0, status_filter)

        return self.qb.fetch_all(
            f"""
            SELECT o.id, o.status, o.total_amount, o.currency,
                   c.name AS client_name, w.name AS warehouse_name,
                   COUNT(oi.id) AS item_count
            FROM orders o
            LEFT JOIN clients c ON c.id = o.client_id
            LEFT JOIN warehouses w ON w.id = o.warehouse_id
            LEFT JOIN order_items oi ON oi.order_id = o.id AND oi.is_active = 1
            WHERE o.is_active = 1 {status_clause}
            GROUP BY o.id
            ORDER BY o.id DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params),
        )

    def deactivate_order(self, order_id: int) -> int:
        return self.qb.update(
            "orders",
            {"is_active": 0},
            "id = ? AND is_active = 1",
            (order_id,),
        )

    def deactivate_all_items(self, order_id: int) -> int:
        return self.qb.update(
            "order_items",
            {"is_active": 0},
            "order_id = ?",
            (order_id,),
        )

    def recalc_order_totals(self, order_id: int) -> None:
        row = self.qb.fetch_one(
            """
            SELECT
                COALESCE(SUM(oi.line_total), 0) AS subtotal_amount,
                COALESCE(MAX(oi.needs_review), 0) AS needs_review,
                COALESCE(MAX(c.discount_percent), 0) AS discount_percent,
                COALESCE(MAX(c.discount_fixed), 0) AS discount_fixed
            FROM orders o
            LEFT JOIN clients c ON c.id = o.client_id
            LEFT JOIN order_items oi ON oi.order_id = o.id AND oi.is_active = 1
            WHERE o.id = ?
            """,
            (order_id,),
        )
        subtotal_amount = float(row["subtotal_amount"]) if row else 0.0
        needs_review = int(row["needs_review"]) if row else 0
        discount_percent = float(row["discount_percent"]) if row else 0.0
        discount_fixed = float(row["discount_fixed"]) if row else 0.0

        raw_discount = (subtotal_amount * discount_percent / 100.0) + discount_fixed
        discount_amount = min(subtotal_amount, max(0.0, raw_discount))
        total_amount = subtotal_amount - discount_amount

        self.qb.update(
            "orders",
            {
                "subtotal_amount": subtotal_amount,
                "discount_amount": discount_amount,
                "total_amount": total_amount,
                "needs_review": needs_review,
            },
            "id = ?",
            (order_id,),
        )
