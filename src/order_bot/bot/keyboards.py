from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def order_actions_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"ord|cfm|{order_id}"),
                InlineKeyboardButton(text="❌ Скасувати", callback_data=f"ord|cnl|{order_id}"),
            ],
            [
                InlineKeyboardButton(text="➕ Додати позицію", callback_data=f"ord|add|{order_id}"),
                InlineKeyboardButton(text="🗑 Видалити позицію", callback_data=f"ord|rm|{order_id}"),
            ],
            [
                InlineKeyboardButton(text="👤 Прив'язати клієнта", callback_data=f"ord|bc|{order_id}"),
                InlineKeyboardButton(text="👤 Відв'язати", callback_data=f"ord|bcn|{order_id}"),
            ],
            [
                InlineKeyboardButton(text="🏭 Прив'язати склад", callback_data=f"ord|bw|{order_id}"),
                InlineKeyboardButton(text="🏭 Відв'язати", callback_data=f"ord|bwn|{order_id}"),
            ],
            [
                InlineKeyboardButton(text="🔢 Змінити к-сть", callback_data=f"ord|eq|{order_id}"),
                InlineKeyboardButton(text="💰 Змінити ціну", callback_data=f"ord|ep|{order_id}"),
            ],
            [
                InlineKeyboardButton(text="🔄 Оновити", callback_data=f"ord|rf|{order_id}"),
            ],
        ]
    )


def order_actions_keyboard_view_only(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Видалити замовлення", callback_data=f"ord|del|{order_id}"),
            ],
            [
                InlineKeyboardButton(text="🔄 Оновити", callback_data=f"ord|rf|{order_id}"),
            ],
        ]
    )


def order_list_keyboard(orders: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for order in orders:
        order_id = int(order["id"])
        status = order.get("status", "draft")
        icon = {"draft": "📋", "confirmed": "✅", "cancelled": "❌"}.get(status, "📋")
        total = float(order.get("total", 0))
        rows.append([InlineKeyboardButton(text=f"{icon} #{order_id} {total:.2f} {order.get('currency', 'USD')}", callback_data=f"ord|view|{order_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_items_keyboard(order_id: int, items: list[dict], action: str) -> InlineKeyboardMarkup:
    rows = []
    for item in items:
        item_id = int(item["id"])
        label = f"#{item_id} {item['name']} ({item['qty']} шт)"
        rows.append([InlineKeyboardButton(text=label[:64], callback_data=f"ord|{action}|{order_id}|{item_id}")])

    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"ord|rf|{order_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_edit_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Скасувати редагування", callback_data=f"ord|rf|{order_id}")],
        ]
    )


def clients_keyboard(order_id: int, clients: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for client in clients:
        client_id = int(client["id"])
        percent = float(client.get("discount_percent") or 0)
        fixed = float(client.get("discount_fixed") or 0)
        price_level = client.get("price_level", "base")
        level_str = f"[{price_level}]" if price_level != "base" else ""
        label = f"#{client_id} {client['name']} {level_str} ({percent:g}%+{fixed:g})"
        rows.append([InlineKeyboardButton(text=label[:64], callback_data=f"ord|bci|{order_id}|{client_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"ord|rf|{order_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def warehouses_keyboard(order_id: int, warehouses: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for wh in warehouses:
        warehouse_id = int(wh["id"])
        label = f"#{warehouse_id} {wh['name']}"
        rows.append([InlineKeyboardButton(text=label[:64], callback_data=f"ord|bwi|{order_id}|{warehouse_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"ord|rf|{order_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def client_list_management_keyboard(clients: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for client in clients:
        client_id = int(client["id"])
        name = str(client.get("name", ""))[:30]
        level = client.get("price_level", "base")
        label = f"👤 {name} [{level}]"
        rows.append([
            InlineKeyboardButton(text=label[:64], callback_data=f"cli|view|{client_id}"),
            InlineKeyboardButton(text="🗑", callback_data=f"cli|del|{client_id}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def warehouse_list_management_keyboard(warehouses: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for wh in warehouses:
        wh_id = int(wh["id"])
        name = str(wh.get("name", ""))[:40]
        rows.append([
            InlineKeyboardButton(text=f"🏭 {name}"[:64], callback_data=f"wh|view|{wh_id}"),
            InlineKeyboardButton(text="🗑", callback_data=f"wh|del|{wh_id}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)
