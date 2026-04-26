from __future__ import annotations
from typing import Any


def _status_ua(status: str) -> str:
    mapping = {
        "draft": "📝 Чернетка",
        "confirmed": "✅ Підтверджено",
        "cancelled": "❌ Скасовано",
        "parse_error": "⚠️ Помилка розбору",
    }
    return mapping.get(status, status)


def format_parse_errors(errors: list[Any], max_count: int = 10) -> str:
    """Форматування помилок парсингу файлу."""
    if not errors:
        return "✅ У файлі не знайдено помилок."

    lines = ["❌ Помилки у файлі:"]

    for err in errors[:max_count]:
        if isinstance(err, str):
            lines.append(f"  • {err}")
        elif hasattr(err, "row") and hasattr(err, "field") and hasattr(err, "message"):
            row = err.row if err.row is not None else "?"
            lines.append(f"  • рядок {row}, поле <code>{err.field}</code>: {err.message}")
        else:
            lines.append(f"  • {str(err)}")

    if len(errors) > max_count:
        lines.append(f"... і ще {len(errors) - max_count} помилок")

    return "\n".join(lines)


def format_order_draft(order_payload: dict[str, Any]) -> str:
    order = order_payload["order"]
    items = order_payload["items"]
    lines = [
        f"📝 Чернетка замовлення #{order['id']}",
        f"Статус: {_status_ua(str(order['status']))}",
        f"💰 Сума: {order['total_amount']} {order['currency']}",
        f"🔍 Потребує перевірки: {'так ⚠️' if order['needs_review'] else 'ні ✅'}",
        "",
        "📦 Позиції:",
    ]
    for item in items:
        review_flag = " ⚠️ ПЕРЕВІРИТИ" if item["needs_review"] else ""
        lines.append(
            f"  • {item['name']} — {item['qty']} шт × {item['price_at_order']} = "
            f"{item['line_total']} {order['currency']}{review_flag}"
        )
    lines.append("")
    lines.append(f"Підтвердити: <code>/confirm {order['id']}</code>")
    return "\n".join(lines)


def format_order_approval(
    order_payload: dict[str, Any],
    parsed: dict[str, Any] | None = None,
    source_subject: str | None = None,
    source_from: str | None = None,
) -> str:
    order = order_payload["order"]
    items = order_payload["items"]
    parsed = parsed or {}

    lines: list[str] = []
    lines.append("🛒 Нове замовлення на погодження")

    if source_from:
        lines.append(f"👤 Джерело: {source_from}")
    if source_subject:
        lines.append(f"📧 Тема: {source_subject}")

    if parsed.get("order_no"):
        lines.append(f"📋 Номер: {parsed['order_no']}")

    client_name = order.get("client_name")
    if client_name:
        lines.append(f"👤 Клієнт: {client_name}")
        discount_pct = float(order.get("client_discount_percent") or 0)
        discount_fix = float(order.get("client_discount_fixed") or 0)
        if discount_pct or discount_fix:
            lines.append(
                f"🏷 Знижка клієнта: {discount_pct:g}% + {discount_fix:g} {order['currency']}"
            )
    else:
        lines.append("👤 Клієнт: не прив'язаний")

    warehouse = order.get("warehouse_name") or parsed.get("warehouse_hint")
    if warehouse:
        lines.append(f"🏭 Склад: {warehouse}")

    if parsed.get("contact_hint"):
        lines.append(f"📇 Контакт: {parsed['contact_hint']}")
    if parsed.get("phone_hint"):
        lines.append(f"📞 Телефон: {parsed['phone_hint']}")
    if parsed.get("vehicle_hint"):
        lines.append(f"🚚 Транспорт: {parsed['vehicle_hint']}")

    lines.append("")
    lines.append(f"📦 Замовлення #{order['id']}")
    lines.append(f"Статус: {_status_ua(str(order['status']))}")

    subtotal = float(order.get("subtotal_amount", order["total_amount"]))
    discount = float(order.get("discount_amount", 0))
    total = float(order["total_amount"])

    lines.append(f"💵 Проміжний підсумок: {subtotal:.2f} {order['currency']}")
    if discount:
        lines.append(f"🏷 Знижка: –{discount:.2f} {order['currency']}")
    lines.append(f"💰 Разом: {total:.2f} {order['currency']}")

    if order.get("needs_review"):
        lines.append("⚠️ Потребує перевірки!")

    lines.append("")
    lines.append("📦 Позиції:")
    for item in items:
        review_flag = " ⚠️ ПЕРЕВІРИТИ" if item["needs_review"] else ""
        conf = item.get("match_confidence")
        conf_str = f" ({conf:.0%})" if conf is not None else ""
        lines.append(
            f"  • {item['name']} — {item['qty']} шт × {item['price_at_order']} = "
            f"{item['line_total']} {order['currency']}{conf_str}{review_flag}"
        )

    return "\n".join(lines)


def format_confirmed_invoice(order_payload: dict[str, Any], parsed: dict[str, Any] | None = None) -> str:
    order = order_payload["order"]
    items = order_payload["items"]
    parsed = parsed or {}

    lines: list[str] = []
    lines.append("📄 РАХУНОК")
    lines.append("━" * 24)

    # Client (only if bound)
    if order.get("client_name"):
        lines.append(f"👤 Клієнт: {order['client_name']}")

    # Warehouse (only if bound)
    warehouse = order.get("warehouse_name") or parsed.get("warehouse_hint")
    if warehouse:
        lines.append(f"🏭 Склад: {warehouse}")

    if order.get("client_name") or warehouse:
        lines.append("")

    lines.append("📦 Позиції:")

    for idx, item in enumerate(items, 1):
        lines.append(
            f"  {idx}. {item['name']}\n"
            f"     {item['qty']} шт × {item['price_at_order']} = {float(item['line_total']):.2f} {order['currency']}"
        )

    lines.append("")
    lines.append("━" * 24)

    subtotal = float(order.get("subtotal_amount", order["total_amount"]))
    discount = float(order.get("discount_amount", 0))
    total = float(order["total_amount"])

    lines.append(f"💵 Підсумок: {subtotal:.2f} {order['currency']}")
    if discount:
        lines.append(f"🏷 Знижка: –{discount:.2f} {order['currency']}")
    lines.append(f"💰 Всього: {total:.2f} {order['currency']}")
    lines.append("━" * 24)

    return "\n".join(lines)


def format_order_parse_failure(subject: str, from_email: str, error_message: str, raw_text: str) -> str:
    snippet = (raw_text or "").strip()
    if len(snippet) > 800:
        snippet = snippet[:800] + "\n..."
    lines = [
        "⚠️ Лист не розпізнано як замовлення",
        f"📧 Джерело: {from_email}",
        f"📋 Тема: {subject}",
        f"❌ Помилка: {error_message}",
        "",
        "📝 Текст:",
        f"{snippet or '(порожньо)'}",
    ]
    return "\n".join(lines)


def format_price_upload_success(version_id: int, row_count: int) -> str:
    return (
        f"✅ Прайс завантажено\n"
        f"Активовано версія #{version_id}\n"
        f"Рядків: {row_count}"
    )


def format_stock_upload_success(upload_id: int, row_count: int) -> str:
    return (
        f"✅ Залишки завантажено\n"
        f"Upload #{upload_id}\n"
        f"Рядків: {row_count}\n"
        f"Актуальний срез повністю перезаписано."
    )


def format_warehouse_upload_success(rows_total: int, created: int, updated: int) -> str:
    return (
        f"✅ Довідник складів оновлено\n"
        f"Унікальних назв: {rows_total}\n"
        f"Нових: {created} | Оновлених: {updated}\n"
        f"Попередній активний список складів замінено."
    )


def format_client_list(clients: list[dict[str, Any]]) -> str:
    if not clients:
        return "📭 Клієнтів не знайдено."
    lines = ["👥 Клієнти:"]
    for c in clients:
        price_level = c.get("price_level", "base")
        level_str = f" [{price_level}]" if price_level != "base" else ""
        lines.append(
            f"  #{c['id']} {c['name']}{level_str} — "
            f"знижка {float(c['discount_percent']):g}% + {float(c['discount_fixed']):g}"
        )
    return "\n".join(lines)


def format_warehouse_list(warehouses: list[dict[str, Any]]) -> str:
    if not warehouses:
        return "📭 Склади не знайдено."
    lines = ["🏭 Склади:"]
    for w in warehouses:
        lines.append(f"  #{w['id']} {w['name']}")
    return "\n".join(lines)


def format_price_preview(items: list[dict[str, Any]]) -> str:
    if not items:
        return "📭 Активний прайс порожній. Завантажте прайс через /upload_price"

    lines = ["📊 Активний прайс (перші позиції)", ""]
    lines.append("<code>Назва           | Базова | 200к  | 150к  | 100к</code>")
    lines.append("━" * 40)

    for item in items:
        name = str(item.get("name", ""))[:20]
        base = float(item.get("base_price") or 0)
        p200 = float(item.get("price_200k") or base)
        p150 = float(item.get("price_150k") or base)
        p100 = float(item.get("price_100k") or base)
        lines.append(
            f"<code>{name:20} | {base:5.2f} | {p200:5.2f} | {p150:5.2f} | {p100:5.2f}</code>"
        )

    lines.append("")
    lines.append(f"<i>Показано {len(items)} позицій. Всього більше — завантажте повний файл.</i>")
    return "\n".join(lines)


def format_orders_list(orders: list[dict[str, Any]]) -> str:
    if not orders:
        return "📭 Замовлень не знайдено."

    status_titles = {
        "draft": "📝 Чернетки",
        "confirmed": "✅ Підтверджені",
        "cancelled": "❌ Скасовані",
        "parse_error": "⚠️ Помилки",
    }

    grouped: dict[str, list[str]] = {}
    for o in orders:
        status = str(o.get("status", "draft"))
        icon = {"draft": "📝", "confirmed": "✅", "cancelled": "❌", "parse_error": "⚠️"}.get(status, "❓")

        client = o.get("client_name") or "—"
        wh = o.get("warehouse_name") or "—"
        total = float(o.get("total_amount") or 0)
        currency = o.get("currency", "USD")
        item_count = int(o.get("item_count") or 0)

        line = f"{icon} #{o['id']} {client} | {wh}\n   📦 {item_count} поз. | 💰 {total:.2f} {currency}"
        grouped.setdefault(status, []).append(line)

    lines: list[str] = ["📋 Замовлення", ""]
    for status in ["draft", "confirmed", "cancelled", "parse_error"]:
        if status not in grouped:
            continue
        lines.append(status_titles.get(status, status))
        lines.append("━" * 28)
        lines.extend(grouped[status])
        lines.append("")

    return "\n".join(lines)
