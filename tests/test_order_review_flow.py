from __future__ import annotations

from order_bot.bot.formatters import format_confirmed_invoice
from order_bot.db import Database, init_db
from order_bot.services import MatchingService, OrderService, PriceService, StockService


def test_order_review_edit_and_confirm_flow(tmp_path) -> None:
    db_path = tmp_path / "app.db"
    init_db(db_path)
    db = Database(db_path)

    price_service = PriceService(db)
    stock_service = StockService(db)
    order_service = OrderService(db, MatchingService())

    price_service.upload_new_price(
        [
            {"sku": "A-1", "name": "Apple", "base_price": 10, "currency": "USD"},
            {"sku": "B-2", "name": "Banana", "base_price": 5, "currency": "USD"},
        ],
        source_filename="price.csv",
        created_by="tester",
    )
    stock_service.upload_stock(
        [{"sku": "A-1", "quantity": 20}, {"sku": "B-2", "quantity": 10}],
        source_filename="stock.csv",
        uploaded_by="tester",
    )

    parsed = {
        "items": [
            {"name_hint": "Apple", "qty": 2},
            {"name_hint": "Banana", "qty": 3},
        ],
    }
    created = order_service.create_draft_from_parsed(parsed=parsed, raw_text="test")
    order_id = int(created["order"]["id"])

    assert float(created["order"]["total_amount"]) == 35.0
    item_by_name = {item["name"]: item for item in created["items"]}

    apple_id = int(item_by_name["Apple"]["id"])
    banana_id = int(item_by_name["Banana"]["id"])

    updated_qty = order_service.edit_item_qty(order_id=order_id, item_id=apple_id, qty=4)
    assert float(updated_qty["order"]["total_amount"]) == 55.0

    updated_price = order_service.edit_item_price(order_id=order_id, item_id=banana_id, price_at_order=7)
    assert float(updated_price["order"]["total_amount"]) == 61.0

    removed = order_service.remove_item(order_id=order_id, item_id=banana_id)
    assert len(removed["items"]) == 1
    assert float(removed["order"]["total_amount"]) == 40.0

    client = order_service.create_client("Manual Client", discount_percent=10, discount_fixed=3)
    rebound = order_service.bind_client(order_id=order_id, client_id=int(client["id"]))
    assert rebound["order"]["client_name"] == "Manual Client"
    assert float(rebound["order"]["subtotal_amount"]) == 40.0
    assert float(rebound["order"]["discount_amount"]) == 7.0
    assert float(rebound["order"]["total_amount"]) == 33.0

    warehouse = order_service.create_warehouse("ВЗ Кропивницький 6")
    rebound_wh = order_service.bind_warehouse(order_id=order_id, warehouse_id=int(warehouse["id"]))
    assert rebound_wh["order"]["warehouse_name"] == "ВЗ Кропивницький 6"

    assert order_service.confirm_order(order_id) is True
    confirmed = order_service.get_order(order_id)
    assert confirmed is not None
    invoice = format_confirmed_invoice(confirmed, parsed={})
    assert "РАХУНОК" in invoice or "Рахунок" in invoice
    assert "Manual Client" in invoice
    assert "ВЗ Кропивницький 6" in invoice

    # After confirmation, edits are blocked.
    try:
        order_service.edit_item_qty(order_id=order_id, item_id=apple_id, qty=5)
        assert False, "edit_item_qty should fail for confirmed order"
    except ValueError as exc:
        assert "Редагувати можна лише чернетку" in str(exc)


def test_add_item_to_order_flow(tmp_path) -> None:
    db_path = tmp_path / "app.db"
    init_db(db_path)
    db = Database(db_path)

    price_service = PriceService(db)
    stock_service = StockService(db)
    order_service = OrderService(db, MatchingService())

    price_service.upload_new_price(
        [
            {"sku": "A-1", "name": "Apple", "base_price": 10, "currency": "USD"},
            {"sku": "B-2", "name": "Banana", "base_price": 5, "currency": "USD"},
            {"sku": "C-3", "name": "Cherry", "base_price": 8, "currency": "USD"},
        ],
        source_filename="price.csv",
        created_by="tester",
    )
    stock_service.upload_stock(
        [{"sku": "A-1", "quantity": 20}, {"sku": "B-2", "quantity": 10}, {"sku": "C-3", "quantity": 5}],
        source_filename="stock.csv",
        uploaded_by="tester",
    )

    parsed = {"items": [{"name_hint": "Apple", "qty": 2}]}
    created = order_service.create_draft_from_parsed(parsed=parsed, raw_text="test")
    order_id = int(created["order"]["id"])
    assert len(created["items"]) == 1
    assert float(created["order"]["total_amount"]) == 20.0

    # Add item by name hint
    updated = order_service.add_item_to_order(order_id, name_hint="Banana", qty=3)
    assert len(updated["items"]) == 2
    assert float(updated["order"]["total_amount"]) == 35.0

    # Add one more
    updated2 = order_service.add_item_to_order(order_id, name_hint="Cherry", qty=1)
    assert len(updated2["items"]) == 3
    assert float(updated2["order"]["total_amount"]) == 43.0

    # list_orders
    orders = order_service.list_orders(limit=10)
    assert len(orders) == 1
    assert orders[0]["id"] == order_id
    assert orders[0]["item_count"] == 3

    # list_orders status filter
    all_orders = order_service.list_orders(limit=10)
    assert len(all_orders) == 1
    assert all_orders[0]["status"] == "draft"

    # Cannot add to confirmed order
    order_service.confirm_order(order_id)
    try:
        order_service.add_item_to_order(order_id, name_hint="Apple", qty=1)
        assert False, "add_item should fail for confirmed order"
    except ValueError as exc:
        assert "Редагувати можна лише чернетку" in str(exc)


def test_delete_order_flow(tmp_path) -> None:
    db_path = tmp_path / "app.db"
    init_db(db_path)
    db = Database(db_path)

    price_service = PriceService(db)
    order_service = OrderService(db, MatchingService())

    price_service.upload_new_price(
        [
            {"sku": "A-1", "name": "Apple", "base_price": 10, "currency": "USD"},
        ],
        source_filename="price.csv",
        created_by="tester",
    )

    parsed = {"items": [{"name_hint": "Apple", "qty": 2}]}
    created = order_service.create_draft_from_parsed(parsed=parsed, raw_text="test")
    order_id = int(created["order"]["id"])

    # Delete (soft)
    ok = order_service.delete_order(order_id)
    assert ok is True

    # Order should be gone from active list
    orders = order_service.list_orders(limit=10)
    assert not any(o["id"] == order_id for o in orders)

    # get_order should still return it but is_active likely 0? depends on get_by_id query.
    # Our get_by_id queries is_active=1, so it should be None.
    assert order_service.get_order(order_id) is None

    # Double delete returns False
    assert order_service.delete_order(order_id) is False
