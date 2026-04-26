from __future__ import annotations

import sqlite3
from typing import Any

from order_bot.db.connection import Database
from order_bot.repositories.client import ClientRepository
from order_bot.repositories.order import OrderRepository
from order_bot.repositories.price import PriceRepository
from order_bot.repositories.stock import StockRepository
from order_bot.repositories.warehouse import WarehouseRepository
from order_bot.services.matching_service import MatchingService


class OrderService:
    def __init__(self, db: Database, matching_service: MatchingService) -> None:
        self.db = db
        self.matching_service = matching_service

    def create_draft_from_parsed(self, parsed: dict[str, Any], raw_text: str) -> dict[str, Any]:
        items = parsed.get("items", [])

        if not items:
            raise ValueError("Замовлення не містить позицій")

        with self.db.transaction() as conn:
            order_repo = OrderRepository(conn)
            stock_repo = StockRepository(conn)

            order_items_payload: list[dict[str, Any]] = []
            subtotal_amount = 0.0
            order_needs_review = False

            for req_item in items:
                name_hint = str(req_item.get("name_hint", "")).strip()
                qty = int(req_item.get("qty", 0))
                if not name_hint or qty <= 0:
                    continue

                match = self.matching_service.match(conn, name_hint)
                if match is None:
                    order_items_payload.append(
                        {
                            "sku": "UNMATCHED",
                            "name": name_hint,
                            "qty": qty,
                            "price_at_order": 0,
                            "line_total": 0,
                            "match_confidence": 0.0,
                            "needs_review": True,
                            "available_qty": None,
                        }
                    )
                    order_needs_review = True
                    continue

                stock_row = stock_repo.get_by_sku(match.sku)
                available_qty = int(stock_row["quantity"]) if stock_row else None

                line_total = float(match.price) * qty
                subtotal_amount += line_total
                order_needs_review = order_needs_review or match.needs_review

                order_items_payload.append(
                    {
                        "sku": match.sku,
                        "name": match.name,
                        "qty": qty,
                        "price_at_order": match.price,
                        "line_total": line_total,
                        "match_confidence": match.confidence,
                        "needs_review": match.needs_review,
                        "available_qty": available_qty,
                    }
                )

            if not order_items_payload:
                raise ValueError("Немає валідних позицій після перевірки")

            order_id = order_repo.create_draft(
                client_id=None,
                warehouse_id=None,
                subtotal_amount=subtotal_amount,
                discount_amount=0.0,
                total_amount=subtotal_amount,
                currency="USD",
                needs_review=order_needs_review,
            )
            order_repo.add_items(order_id, order_items_payload)
            order_repo.recalc_order_totals(order_id)
            order_repo.add_raw_log(
                source_text=raw_text,
                llm_payload=parsed,
                parse_status="ok",
                error_message=None,
                order_id=order_id,
            )

            created = order_repo.get_by_id(order_id)
            if created is None:
                raise RuntimeError("Failed to load created order")
            return created

    def save_parse_error(self, raw_text: str, error_message: str, llm_payload: dict[str, Any] | None = None) -> int:
        with self.db.transaction() as conn:
            order_repo = OrderRepository(conn)
            return order_repo.add_raw_log(
                source_text=raw_text,
                llm_payload=llm_payload,
                parse_status="parse_error",
                error_message=error_message,
                order_id=None,
            )

    def update_status(self, order_id: int, status: str) -> bool:
        with self.db.transaction() as conn:
            order_repo = OrderRepository(conn)
            affected = order_repo.update_status(order_id, status)
            return affected > 0

    def get_order(self, order_id: int) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            order_repo = OrderRepository(conn)
            return order_repo.get_by_id(order_id)

    def confirm_order(self, order_id: int) -> bool:
        with self.db.transaction() as conn:
            order_repo = OrderRepository(conn)
            status = order_repo.get_order_status(order_id)
            if status != "draft":
                return False
            affected = order_repo.update_status(order_id, "confirmed")
            return affected > 0

    def cancel_order(self, order_id: int) -> bool:
        with self.db.transaction() as conn:
            order_repo = OrderRepository(conn)
            status = order_repo.get_order_status(order_id)
            if status != "draft":
                return False
            affected = order_repo.update_status(order_id, "cancelled")
            return affected > 0

    def edit_item_qty(self, order_id: int, item_id: int, qty: int) -> dict[str, Any]:
        if qty <= 0:
            raise ValueError("Кількість має бути > 0")
        with self.db.transaction() as conn:
            order_repo = OrderRepository(conn)
            status = order_repo.get_order_status(order_id)
            if status != "draft":
                raise ValueError("Редагувати можна лише чернетку")
            updated = order_repo.update_item_qty(order_id, item_id, qty)
            if updated == 0:
                raise ValueError("Позицію не знайдено")
            order_repo.recalc_order_totals(order_id)
            refreshed = order_repo.get_by_id(order_id)
            if refreshed is None:
                raise RuntimeError("order not found after update")
            return refreshed

    def edit_item_price(self, order_id: int, item_id: int, price_at_order: float) -> dict[str, Any]:
        if price_at_order < 0:
            raise ValueError("Ціна має бути >= 0")
        with self.db.transaction() as conn:
            order_repo = OrderRepository(conn)
            status = order_repo.get_order_status(order_id)
            if status != "draft":
                raise ValueError("Редагувати можна лише чернетку")
            updated = order_repo.update_item_price(order_id, item_id, price_at_order)
            if updated == 0:
                raise ValueError("Позицію не знайдено")
            order_repo.recalc_order_totals(order_id)
            refreshed = order_repo.get_by_id(order_id)
            if refreshed is None:
                raise RuntimeError("order not found after update")
            return refreshed

    def remove_item(self, order_id: int, item_id: int) -> dict[str, Any]:
        with self.db.transaction() as conn:
            order_repo = OrderRepository(conn)
            status = order_repo.get_order_status(order_id)
            if status != "draft":
                raise ValueError("Редагувати можна лише чернетку")
            active_items = order_repo.count_active_items(order_id)
            if active_items <= 1:
                raise ValueError("Не можна видалити останню позицію")
            affected = order_repo.deactivate_item(order_id, item_id)
            if affected == 0:
                raise ValueError("Позицію не знайдено")
            order_repo.recalc_order_totals(order_id)
            refreshed = order_repo.get_by_id(order_id)
            if refreshed is None:
                raise RuntimeError("order not found after update")
            return refreshed

    def bind_client(self, order_id: int, client_id: int | None) -> dict[str, Any]:
        with self.db.transaction() as conn:
            order_repo = OrderRepository(conn)
            client_repo = ClientRepository(conn)
            price_repo = PriceRepository(conn)

            status = order_repo.get_order_status(order_id)
            if status != "draft":
                raise ValueError("Редагувати можна лише чернетку")

            price_level = "base"
            if client_id is not None:
                client = client_repo.get_by_id(client_id)
                if client is None or int(client["is_active"]) != 1:
                    raise ValueError("Клієнта не знайдено")
                price_level = str(client["price_level"] or "base").strip().lower()

            affected = order_repo.set_client(order_id, client_id)
            if affected == 0:
                raise ValueError("Замовлення не знайдено")

            # Перерахунок цін позицій згідно прайсу та price_level клієнта
            if price_level != "base":
                active_price = price_repo.get_active()
                price_map = {}
                if active_price:
                    price_map = {item["sku"]: item for item in active_price["items"]}

                for item in order_repo.get_active_items(order_id):
                    sku = item["sku"]
                    qty = int(item["qty"])
                    price_item = price_map.get(sku)
                    if price_item is None:
                        continue

                    if price_level == "200k":
                        new_price = float(price_item.get("price_200k") or price_item.get("base_price") or price_item.get("price"))
                    elif price_level == "150k":
                        new_price = float(price_item.get("price_150k") or price_item.get("base_price") or price_item.get("price"))
                    elif price_level == "100k":
                        new_price = float(price_item.get("price_100k") or price_item.get("base_price") or price_item.get("price"))
                    else:
                        new_price = float(price_item.get("base_price") or price_item.get("price"))

                    order_repo.update_item_price(order_id, int(item["id"]), new_price)

            order_repo.recalc_order_totals(order_id)
            refreshed = order_repo.get_by_id(order_id)
            if refreshed is None:
                raise RuntimeError("order not found after client bind")
            return refreshed

    def get_client_by_id(self, client_id: int) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            repo = ClientRepository(conn)
            row = repo.get_by_id(client_id)
            return dict(row) if row else None

    def list_clients(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            repo = ClientRepository(conn)
            return [dict(row) for row in repo.list_active(limit=limit)]

    def search_clients(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            repo = ClientRepository(conn)
            return [dict(row) for row in repo.search_active_by_name(query=query, limit=limit)]

    def create_client(
        self,
        name: str,
        discount_percent: float = 0,
        discount_fixed: float = 0,
        price_level: str = "base",
        phone: str | None = None,
        address: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Потрібно вказати назву клієнта")
        if discount_percent < 0 or discount_fixed < 0:
            raise ValueError("Значення знижки мають бути невід'ємними")

        with self.db.transaction() as conn:
            repo = ClientRepository(conn)
            try:
                client_id = repo.create_client(
                    name=clean_name,
                    discount_percent=discount_percent,
                    discount_fixed=discount_fixed,
                    price_level=price_level,
                    phone=phone,
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("Клієнт з такою назвою вже існує") from exc
            created = repo.get_by_id(client_id)
            if created is None:
                raise RuntimeError("failed to create client")
            return dict(created)

    def delete_client(self, client_id: int) -> bool:
        with self.db.transaction() as conn:
            repo = ClientRepository(conn)
            client = repo.get_by_id(client_id)
            if client is None:
                return False
            affected = repo.deactivate(client_id)
            return affected > 0

    def update_client(
        self,
        client_id: int,
        name: str | None = None,
        discount_percent: float | None = None,
        discount_fixed: float | None = None,
        price_level: str | None = None,
        phone: str | None = None,
    ) -> dict[str, Any]:
        with self.db.transaction() as conn:
            repo = ClientRepository(conn)
            repo.update_client(
                client_id=client_id,
                name=name,
                discount_percent=discount_percent,
                discount_fixed=discount_fixed,
                price_level=price_level,
                phone=phone,
            )
            updated = repo.get_by_id(client_id)
            if updated is None:
                raise RuntimeError("client not found after update")
            return dict(updated)

    def upload_clients(
        self,
        rows: list[dict[str, Any]],
        source_filename: str,
        uploaded_by: str | None = None,
    ) -> dict[str, Any]:
        created = 0
        skipped = 0
        with self.db.transaction() as conn:
            repo = ClientRepository(conn)
            for row in rows:
                name = str(row.get("name") or "").strip()
                if not name:
                    skipped += 1
                    continue
                try:
                    repo.create_client(
                        name=name,
                        price_level=row.get("price_level", "base"),
                        phone=row.get("phone"),
                    )
                    created += 1
                except sqlite3.IntegrityError:
                    skipped += 1
        return {"created": created, "skipped": skipped, "total": len(rows)}

    def bind_warehouse(self, order_id: int, warehouse_id: int | None) -> dict[str, Any]:
        with self.db.transaction() as conn:
            order_repo = OrderRepository(conn)
            warehouse_repo = WarehouseRepository(conn)

            status = order_repo.get_order_status(order_id)
            if status != "draft":
                raise ValueError("Редагувати можна лише чернетку")

            if warehouse_id is not None:
                warehouse = warehouse_repo.get_by_id(warehouse_id)
                if warehouse is None or int(warehouse["is_active"]) != 1:
                    raise ValueError("Склад не знайдено")

            affected = order_repo.set_warehouse(order_id, warehouse_id)
            if affected == 0:
                raise ValueError("Замовлення не знайдено")

            refreshed = order_repo.get_by_id(order_id)
            if refreshed is None:
                raise RuntimeError("order not found after warehouse bind")
            return refreshed

    def add_item_to_order(self, order_id: int, name_hint: str, qty: int) -> dict[str, Any]:
        with self.db.transaction() as conn:
            order_repo = OrderRepository(conn)
            stock_repo = StockRepository(conn)

            status = order_repo.get_order_status(order_id)
            if status != "draft":
                raise ValueError("Редагувати можна лише чернетку")

            match = self.matching_service.match(conn, name_hint)
            if match is None:
                raise ValueError(f"Товар '{name_hint}' не знайдено в прайсі")

            stock_row = stock_repo.get_by_sku(match.sku)
            available_qty = int(stock_row["quantity"]) if stock_row else None

            line_total = float(match.price) * qty
            order_repo.add_item(
                order_id,
                {
                    "sku": match.sku,
                    "name": match.name,
                    "qty": qty,
                    "price_at_order": match.price,
                    "line_total": line_total,
                    "match_confidence": match.confidence,
                    "needs_review": match.needs_review,
                    "available_qty": available_qty,
                },
            )
            order_repo.recalc_order_totals(order_id)
            refreshed = order_repo.get_by_id(order_id)
            if refreshed is None:
                raise RuntimeError("order not found after add item")
            return refreshed

    def list_orders(self, limit: int = 20, status_filter: str | None = None) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            repo = OrderRepository(conn)
            return [dict(row) for row in repo.list_orders(limit=limit, status_filter=status_filter)]

    def delete_order(self, order_id: int) -> bool:
        with self.db.transaction() as conn:
            repo = OrderRepository(conn)
            order = repo.get_by_id(order_id)
            if order is None:
                return False
            # Soft delete: deactivate items and order
            repo.deactivate_all_items(order_id)
            affected = repo.deactivate_order(order_id)
            return affected > 0

    def get_warehouse_by_id(self, warehouse_id: int) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            repo = WarehouseRepository(conn)
            row = repo.get_by_id(warehouse_id)
            return dict(row) if row else None

    def list_warehouses(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            repo = WarehouseRepository(conn)
            return [dict(row) for row in repo.list_active(limit=limit)]

    def search_warehouses(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            repo = WarehouseRepository(conn)
            return [dict(row) for row in repo.search_active_by_name(query=query, limit=limit)]

    def delete_warehouse(self, warehouse_id: int) -> bool:
        with self.db.transaction() as conn:
            repo = WarehouseRepository(conn)
            wh = repo.get_by_id(warehouse_id)
            if wh is None:
                return False
            affected = repo.deactivate(warehouse_id)
            return affected > 0

    def update_warehouse(self, warehouse_id: int, name: str) -> dict[str, Any]:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Потрібно вказати назву складу")
        with self.db.transaction() as conn:
            repo = WarehouseRepository(conn)
            repo.update_warehouse(warehouse_id, name=clean_name)
            updated = repo.get_by_id(warehouse_id)
            if updated is None:
                raise RuntimeError("warehouse not found after update")
            return dict(updated)

    def create_warehouse(self, name: str) -> dict[str, Any]:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Потрібно вказати назву складу")
        with self.db.transaction() as conn:
            repo = WarehouseRepository(conn)
            try:
                warehouse_id = repo.create_warehouse(name=clean_name)
            except sqlite3.IntegrityError as exc:
                raise ValueError("Склад з такою назвою вже існує") from exc
            created = repo.get_by_id(warehouse_id)
            if created is None:
                raise RuntimeError("failed to create warehouse")
            return dict(created)
