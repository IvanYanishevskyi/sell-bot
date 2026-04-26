from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from order_bot.bot.formatters import (
    format_client_list,
    format_confirmed_invoice,
    format_order_approval,
    format_orders_list,
    format_parse_errors,
    format_price_preview,
    format_price_upload_success,
    format_warehouse_list,
    format_warehouse_upload_success,
)
from order_bot.bot.keyboards import (
    cancel_edit_keyboard,
    client_list_management_keyboard,
    clients_keyboard,
    order_actions_keyboard,
    order_actions_keyboard_view_only,
    order_list_keyboard,
    order_items_keyboard,
    warehouse_list_management_keyboard,
    warehouses_keyboard,
)
from order_bot.bot.review_state import PendingAddItem, PendingEdit, ReviewStateStore
from order_bot.bootstrap import ServiceContainer
from order_bot.import_from_files import import_clients, import_warehouses


router = Router(name="main")


def _sanitize_filename(name: str) -> str:
    cleaned = "".join(ch for ch in name if ch.isalnum() or ch in "._-")
    return cleaned or "upload.bin"


def _detect_document_type(caption: str | None) -> str | None:
    if not caption:
        return None
    text = caption.lower()
    if "price" in text or "прайс" in text:
        return "price"
    if "warehouse" in text or "склади" in text or "локац" in text:
        return "warehouse"
    return None


def _detect_document_type_by_name(filename: str | None) -> str | None:
    if not filename:
        return None
    text = filename.lower()
    if any(token in text for token in ["price", "pricelist", "прайс"]):
        return "price"
    if any(token in text for token in ["warehouse", "warehouses", "локац", "branch", "склад"]):
        return "warehouse"
    return None


def _extract_parsed_payload(order_payload: dict[str, Any]) -> dict[str, Any] | None:
    raw_log = order_payload.get("raw_log") or {}
    llm_payload = raw_log.get("llm_payload")
    if not llm_payload:
        return None
    if isinstance(llm_payload, dict):
        return llm_payload
    if isinstance(llm_payload, str):
        try:
            parsed = json.loads(llm_payload)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
    return None


def _parse_callback(data: str | None) -> list[str]:
    if not data:
        return []
    return data.split("|")


async def _edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    if callback.message is None:
        return
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        await callback.message.answer(text, reply_markup=reply_markup)


# ───────────────────────── /start ─────────────────────────

@router.message(Command("start"))
async def start_handler(message: Message) -> None:
    await message.answer(
        "👋 Вітаю!\n\n"
        "Я бот для обробки замовлень та управління прайсами.\n\n"
        "📦 Прайс та склади:\n"
        "  • /upload_price — завантажити прайс (Excel)\n"
        "  • /upload_warehouses — завантажити довідник складів\n"
        "  • /price — переглянути активний прайс\n\n"
        "👥 Клієнти:\n"
        "  • /client_add — додати клієнта\n"
        "  • /clients — список клієнтів\n"
        "  • /sync_clients — синхронізувати з файлом\n\n"
        "🏭 Склади:\n"
        "  • /warehouse_add — додати склад\n"
        "  • /warehouses — список складів\n"
        "  • /sync_warehouses — синхронізувати з файлом\n\n"
        "📝 Замовлення:\n"
        "  • /orders — список замовлень\n"
        "  • /order &lt;id&gt; — деталі замовлення\n"
        "  • /delete_order &lt;id&gt; — видалити\n"
        "  • Просто надішліть текст — створити нове\n\n"
        "<i>Приклад:</i> <code>Виставте рахунок на 280л ГЕФ ЕСТ ПРО</code>",
        parse_mode="HTML",
    )


@router.message(Command("myid"))
async def myid_handler(message: Message) -> None:
    await message.answer(f"🆔 Ваш chat_id: <code>{message.chat.id}</code>")


# ───────────────────────── Upload modes ─────────────────────────

@router.message(Command("upload_price"))
async def upload_price_mode_handler(message: Message, review_state: ReviewStateStore) -> None:
    review_state.set_upload_mode(message.chat.id, "price")
    await message.answer(
        "📥 Режим завантаження прайсу\n\n"
        "Надішліть файл Excel (.xlsx, .xls) або CSV.\n"
        "Бот очікує колонки: Назва препарату, Базова ціна, Ціна 200к, Знижка 200к%, Ціна 150к, Знижка 150к%, Ціна 100к, Знижка 100к%\n\n"
        "<i>Щоб скасувати:</i> /cancel_upload"
    )


@router.message(Command("upload_warehouses"))
async def upload_warehouse_mode_handler(message: Message, review_state: ReviewStateStore) -> None:
    review_state.set_upload_mode(message.chat.id, "warehouse")
    await message.answer(
        "📥 Режим завантаження довідника складів\n\n"
        "Надішліть файл Excel (.xlsx, .xls) або CSV з колонкою «Назва складу».\n\n"
        "<i>Щоб скасувати:</i> /cancel_upload"
    )


@router.message(Command("cancel_upload"))
async def cancel_upload_mode_handler(message: Message, review_state: ReviewStateStore) -> None:
    review_state.clear_upload_mode(message.chat.id)
    await message.answer("✅ Режим завантаження скинуто.")


# ───────────────────────── Clients ─────────────────────────

@router.message(Command("client_add"))
async def client_add_handler(message: Message, command: CommandObject, services: ServiceContainer) -> None:
    if not command.args:
        await message.answer(
            "❌ Вкажіть дані клієнта.\n\n"
            "Формат:\n"
            "  <code>/client_add Назва | знижка_% | знижка_фікс | рівень_цін</code>\n\n"
            "Приклади:\n"
            "  <code>/client_add ТОВ Агро | 5 | 100</code>\n"
            "  <code>/client_add ТОВ Агро | 5 | 100 | 200k</code>\n\n"
            "<i>Рівні цін:</i> base, 200k, 150k, 100k\n"
            "<i>Якщо рівень не вказано — використовується base.</i>"
        )
        return

    parts = [p.strip() for p in command.args.split("|")]
    name = parts[0] if parts else ""
    if not name:
        await message.answer("❌ Вкажіть назву клієнта.")
        return

    try:
        discount_percent = float(parts[1]) if len(parts) > 1 and parts[1] else 0.0
        discount_fixed = float(parts[2]) if len(parts) > 2 and parts[2] else 0.0
    except ValueError:
        await message.answer(
            "❌ Знижка має бути числом.\n"
            "<i>Приклад: /client_add АгроЛайн | 5 | 100</i>"
        )
        return

    price_level = (parts[3] if len(parts) > 3 and parts[3] else "base").strip().lower()
    if price_level not in {"base", "200k", "150k", "100k"}:
        await message.answer(
            "❌ Невірний рівень цін. Доступні: base, 200k, 150k, 100k."
        )
        return

    try:
        created = services.order_service.create_client(
            name=name,
            discount_percent=discount_percent,
            discount_fixed=discount_fixed,
            price_level=price_level,
        )
    except ValueError as exc:
        await message.answer(f"❌ {exc}")
        return

    level_str = f" [{price_level}]" if price_level != "base" else ""
    await message.answer(
        f"✅ Клієнта створено\n\n"
        f"🆔 #{created['id']}\n"
        f"👤 {created['name']}{level_str}\n"
        f"🏷 Знижка: {float(created['discount_percent']):g}% + {float(created['discount_fixed']):g} USD"
    )


@router.message(Command("delete_client"))
async def delete_client_handler(message: Message, command: CommandObject, services: ServiceContainer) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer(
            "❌ Вкажіть ID клієнта.\n\n"
            "<i>Приклад: /delete_client 5</i>"
        )
        return
    client_id = int(command.args.strip())
    ok = services.order_service.delete_client(client_id)
    if ok:
        await message.answer(f"🗑 Клієнта #{client_id} видалено.")
    else:
        await message.answer(f"❌ Клієнта #{client_id} не знайдено.")


@router.message(Command("clients"))
async def clients_handler(message: Message, command: CommandObject, services: ServiceContainer) -> None:
    query = (command.args or "").strip()
    if query:
        clients = services.order_service.search_clients(query, limit=20)
    else:
        clients = services.order_service.list_clients(limit=20)

    if not clients:
        await message.answer("📭 Клієнтів не знайдено.")
        return

    text = format_client_list(clients)
    await message.answer(text, reply_markup=client_list_management_keyboard(clients))


# ───────────────────────── Warehouses ─────────────────────────

@router.message(Command("warehouse_add"))
async def warehouse_add_handler(message: Message, command: CommandObject, services: ServiceContainer) -> None:
    name = (command.args or "").strip()
    if not name:
        await message.answer(
            "❌ Вкажіть назву складу.\n\n"
            "<i>Приклад: /warehouse_add ВЗ Кропивницький</i>"
        )
        return
    try:
        created = services.order_service.create_warehouse(name=name)
    except ValueError as exc:
        await message.answer(f"❌ {exc}")
        return
    await message.answer(
        f"✅ Склад створено\n\n"
        f"🆔 #{created['id']}\n"
        f"🏭 {created['name']}"
    )


@router.message(Command("delete_warehouse"))
async def delete_warehouse_handler(message: Message, command: CommandObject, services: ServiceContainer) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer(
            "❌ Вкажіть ID складу.\n\n"
            "<i>Приклад: /delete_warehouse 3</i>"
        )
        return
    warehouse_id = int(command.args.strip())
    ok = services.order_service.delete_warehouse(warehouse_id)
    if ok:
        await message.answer(f"🗑 Склад #{warehouse_id} видалено.")
    else:
        await message.answer(f"❌ Склад #{warehouse_id} не знайдено.")


@router.message(Command("warehouses"))
async def warehouses_handler(message: Message, command: CommandObject, services: ServiceContainer) -> None:
    query = (command.args or "").strip()
    if query:
        warehouses = services.order_service.search_warehouses(query, limit=20)
    else:
        warehouses = services.order_service.list_warehouses(limit=20)

    if not warehouses:
        await message.answer("📭 Складів не знайдено.")
        return

    text = format_warehouse_list(warehouses)
    await message.answer(text, reply_markup=warehouse_list_management_keyboard(warehouses))


@router.message(Command("sync_clients"))
async def sync_clients_handler(message: Message, services: ServiceContainer) -> None:
    try:
        count = import_clients()
        await message.answer(f"🔄 Синхронізація клієнтів завершена. Імпортовано: {count}")
    except Exception as exc:
        await message.answer(f"❌ Помилка синхронізації клієнтів: {exc}")


@router.message(Command("sync_warehouses"))
async def sync_warehouses_handler(message: Message, services: ServiceContainer) -> None:
    try:
        count = import_warehouses()
        await message.answer(f"🔄 Синхронізація складів завершена. Імпортовано: {count}")
    except Exception as exc:
        await message.answer(f"❌ Помилка синхронізації складів: {exc}")


@router.message(Command("price"))
async def price_handler(message: Message, services: ServiceContainer) -> None:
    items = services.price_service.list_active_items(limit=30)
    await message.answer(format_price_preview(items))


@router.message(Command("orders"))
async def orders_handler(message: Message, services: ServiceContainer) -> None:
    orders = services.order_service.list_orders(limit=20)
    if not orders:
        await message.answer("📭 Список замовлень порожній.")
        return
    text = format_orders_list(orders)
    await message.answer(text, reply_markup=order_list_keyboard(orders))


@router.message(Command("order"))
async def order_detail_handler(message: Message, command: CommandObject, services: ServiceContainer) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer(
            "❌ Вкажіть номер замовлення.\n\n"
            "<i>Приклад: /order 42</i>"
        )
        return

    order_id = int(command.args.strip())
    order = services.order_service.get_order(order_id)
    if order is None:
        await message.answer(f"❌ Замовлення #{order_id} не знайдено.")
        return

    parsed = _extract_parsed_payload(order)
    status = order.get("status", "draft")
    kb = order_actions_keyboard(order_id) if status == "draft" else order_actions_keyboard_view_only(order_id)
    await message.answer(
        format_order_approval(order, parsed=parsed),
        reply_markup=kb,
    )


@router.message(Command("delete_order"))
async def delete_order_handler(message: Message, command: CommandObject, services: ServiceContainer) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer(
            "❌ Вкажіть номер замовлення.\n\n"
            "<i>Приклад: /delete_order 42</i>"
        )
        return
    order_id = int(command.args.strip())
    ok = services.order_service.delete_order(order_id)
    if ok:
        await message.answer(f"🗑 Замовлення #{order_id} видалено.")
    else:
        await message.answer(f"❌ Замовлення #{order_id} не знайдено.")


# ───────────────────────── Confirm via command ─────────────────────────

@router.message(Command("confirm"))
async def confirm_order_handler(message: Message, command: CommandObject, services: ServiceContainer) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer(
            "❌ Вкажіть номер замовлення.\n\n"
            "<i>Приклад: /confirm 42</i>"
        )
        return

    order_id = int(command.args.strip())
    ok = services.order_service.confirm_order(order_id)
    if not ok:
        await message.answer(f"❌ Замовлення #{order_id} не знайдено або вже не в чернетці.")
        return

    refreshed = services.order_service.get_order(order_id)
    if refreshed is None:
        await message.answer(f"✅ Замовлення #{order_id} підтверджено.")
        return

    parsed = _extract_parsed_payload(refreshed)
    await message.answer(format_confirmed_invoice(refreshed, parsed=parsed))


# ───────────────────────── Document upload ─────────────────────────

@router.message(F.document)
async def document_handler(
    message: Message,
    bot: Bot,
    services: ServiceContainer,
    review_state: ReviewStateStore,
) -> None:
    if message.document is None:
        await message.answer("❌ Файл не знайдено.")
        return

    file_info = await bot.get_file(message.document.file_id)
    buffer = BytesIO()
    await bot.download_file(file_info.file_path, destination=buffer)
    file_bytes = buffer.getvalue()

    original_name = message.document.file_name or "upload.xlsx"
    if original_name.startswith("~$"):
        await message.answer(
            "⚠️ Це тимчасовий службовий файл Office.\n"
            "Надішліть основний файл без префікса <code>~$</code>.",
            parse_mode="HTML",
        )
        return

    safe_name = _sanitize_filename(original_name)
    saved_path = Path(services.upload_dir) / f"{message.document.file_unique_id}_{safe_name}"
    saved_path.write_bytes(file_bytes)

    mode_type = review_state.get_upload_mode(message.chat.id)
    doc_type = mode_type or _detect_document_type(message.caption) or _detect_document_type_by_name(original_name)

    parse_result = None
    if doc_type in {"price", "warehouse"}:
        try:
            parse_result = services.file_parser.parse(
                file_bytes=file_bytes,
                filename=original_name,
                forced_type=doc_type,
            )
            print(f"Parsed {doc_type} document: {len(parse_result.rows)} rows, {len(parse_result.errors)} errors")
        except Exception as exc:
            await message.answer(f"❌ Не вдалося прочитати файл: {exc}")
            return
    else:
        # Auto-detect: try price first, then warehouse
        try:
            parsed_price = services.file_parser.parse(
                file_bytes=file_bytes,
                filename=original_name,
                forced_type="price",
            )
            parsed_warehouse = services.file_parser.parse(
                file_bytes=file_bytes,
                filename=original_name,
                forced_type="warehouse",
            )
        except Exception as exc:
            await message.answer(f"❌ Не вдалося прочитати файл: {exc}")
            return

        price_ok = len(parsed_price.errors) == 0 and len(parsed_price.rows) > 0
        warehouse_ok = len(parsed_warehouse.errors) == 0 and len(parsed_warehouse.rows) > 0

        if price_ok and not warehouse_ok:
            doc_type = "price"
            parse_result = parsed_price
        elif warehouse_ok and not price_ok:
            doc_type = "warehouse"
            parse_result = parsed_warehouse
        elif price_ok and warehouse_ok:
            await message.answer(
                "⚠️ Не вдалося однозначно визначити тип файлу.\n\n"
                "Використайте команду перед відправкою файлу:\n"
                "  • /upload_price — для прайсу\n"
                "  • /upload_warehouses — для довідника складів"
            )
            return
        else:
            candidates = [parsed_price, parsed_warehouse]
            parse_result = min(candidates, key=lambda candidate: len(candidate.errors))
            await message.answer(format_parse_errors(parse_result.errors))
            return

    if parse_result is None:
        await message.answer("❌ Не вдалося обробити файл.")
        return

    if parse_result.errors:
        await message.answer(format_parse_errors(parse_result.errors))
        return

    username = message.from_user.username if message.from_user else None

    if doc_type == "price":
        version_id = services.price_service.upload_new_price(
            rows=parse_result.rows,
            source_filename=str(saved_path),
            created_by=username,
        )
        await message.answer(format_price_upload_success(version_id, len(parse_result.rows)))
        return

    if doc_type == "warehouse":
        try:
            result = services.warehouse_service.upload_warehouses(
                rows=parse_result.rows,
                source_filename=str(saved_path),
                uploaded_by=username,
            )
        except ValueError as exc:
            await message.answer(f"❌ {exc}")
            return
        await message.answer(format_warehouse_upload_success(
            result["rows_total"], result["created"], result["updated"]
        ))
        return

    await message.answer(
        "⚠️ Тип файлу не визначено.\n\n"
        "Використайте команду перед відправкою:\n"
        "  • /upload_price — для прайсу\n"
        "  • /upload_warehouses — для довідника складів"
    )


# ───────────────────────── Order review callbacks ─────────────────────────

@router.callback_query(F.data.startswith("ord|"))
async def order_review_callback(
    callback: CallbackQuery,
    services: ServiceContainer,
    review_state: ReviewStateStore,
) -> None:
    parts = _parse_callback(callback.data)
    if len(parts) < 3:
        await callback.answer("❌ Некоректна команда", show_alert=True)
        return

    _, action, order_id_raw, *rest = parts
    if not order_id_raw.isdigit():
        await callback.answer("❌ Некоректний номер замовлення", show_alert=True)
        return

    order_id = int(order_id_raw)
    chat_id = callback.message.chat.id if callback.message else None

    if action == "rf" or action == "view":
        order_payload = services.order_service.get_order(order_id)
        if order_payload is None:
            await callback.answer("❌ Замовлення не знайдено", show_alert=True)
            return
        parsed = _extract_parsed_payload(order_payload)
        text = format_order_approval(order_payload, parsed=parsed)
        status = order_payload.get("status", "draft")
        kb = order_actions_keyboard(order_id) if status == "draft" else order_actions_keyboard_view_only(order_id)
        await _edit_or_send(callback, text, reply_markup=kb)
        if chat_id is not None:
            review_state.clear_pending(chat_id)
        await callback.answer("🔄 Оновлено")
        return

    if action == "cfm":
        ok = services.order_service.confirm_order(order_id)
        if not ok:
            await callback.answer("❌ Неможливо підтвердити: замовлення не в чернетці", show_alert=True)
            return
        order_payload = services.order_service.get_order(order_id)
        if order_payload is None:
            await callback.answer("✅ Підтверджено")
            return
        parsed = _extract_parsed_payload(order_payload)
        text = format_confirmed_invoice(order_payload, parsed=parsed)
        await _edit_or_send(callback, text, reply_markup=order_actions_keyboard_view_only(order_id))
        if chat_id is not None:
            review_state.clear_pending(chat_id)
        await callback.answer("✅ Замовлення підтверджено")
        return

    if action == "cnl":
        ok = services.order_service.cancel_order(order_id)
        if not ok:
            await callback.answer("❌ Неможливо скасувати: замовлення не в чернетці", show_alert=True)
            return
        order_payload = services.order_service.get_order(order_id)
        if order_payload is None:
            await callback.answer("❌ Скасовано")
            return
        parsed = _extract_parsed_payload(order_payload)
        text = format_order_approval(order_payload, parsed=parsed) + "\n\n❌ Статус: скасовано"
        await _edit_or_send(callback, text, reply_markup=order_actions_keyboard_view_only(order_id))
        if chat_id is not None:
            review_state.clear_pending(chat_id)
        await callback.answer("❌ Замовлення скасовано")
        return

    if action == "del":
        ok = services.order_service.delete_order(order_id)
        if not ok:
            await callback.answer("❌ Неможливо видалити замовлення", show_alert=True)
            return
        await _edit_or_send(callback, f"🗑 Замовлення #{order_id} видалено.")
        if chat_id is not None:
            review_state.clear_pending(chat_id)
        await callback.answer("🗑 Видалено")
        return

    if action == "bc":
        clients = services.order_service.list_clients(limit=20)
        if not clients:
            await callback.answer(
                "📭 Список клієнтів порожній. Додайте через /client_add",
                show_alert=True,
            )
            return
        await _edit_or_send(
            callback,
            "👤 Оберіть клієнта для прив'язки",
            reply_markup=clients_keyboard(order_id, clients),
        )
        await callback.answer()
        return

    if action == "bcn":
        try:
            order_payload = services.order_service.bind_client(order_id=order_id, client_id=None)
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        parsed = _extract_parsed_payload(order_payload)
        await _edit_or_send(
            callback,
            format_order_approval(order_payload, parsed=parsed),
            order_actions_keyboard(order_id),
        )
        await callback.answer("👤 Клієнта відв'язано, ціни повернено на base")
        return

    if action == "bci":
        if len(rest) != 1 or not rest[0].isdigit():
            await callback.answer("❌ Некоректний ID клієнта", show_alert=True)
            return
        client_id = int(rest[0])
        try:
            order_payload = services.order_service.bind_client(order_id=order_id, client_id=client_id)
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        parsed = _extract_parsed_payload(order_payload)
        await _edit_or_send(
            callback,
            format_order_approval(order_payload, parsed=parsed),
            order_actions_keyboard(order_id),
        )
        await callback.answer("✅ Клієнта прив'язано, знижку та ціни перераховано")
        return

    if action == "bw":
        warehouses = services.order_service.list_warehouses(limit=20)
        if not warehouses:
            await callback.answer(
                "📭 Список складів порожній. Додайте через /warehouse_add",
                show_alert=True,
            )
            return
        await _edit_or_send(
            callback,
            "🏭 Оберіть склад для прив'язки",
            reply_markup=warehouses_keyboard(order_id, warehouses),
        )
        await callback.answer()
        return

    if action == "bwn":
        try:
            order_payload = services.order_service.bind_warehouse(order_id=order_id, warehouse_id=None)
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        parsed = _extract_parsed_payload(order_payload)
        await _edit_or_send(
            callback,
            format_order_approval(order_payload, parsed=parsed),
            order_actions_keyboard(order_id),
        )
        await callback.answer("🏭 Склад відв'язано")
        return

    if action == "bwi":
        if len(rest) != 1 or not rest[0].isdigit():
            await callback.answer("❌ Некоректний ID складу", show_alert=True)
            return
        warehouse_id = int(rest[0])
        try:
            order_payload = services.order_service.bind_warehouse(order_id=order_id, warehouse_id=warehouse_id)
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        parsed = _extract_parsed_payload(order_payload)
        await _edit_or_send(
            callback,
            format_order_approval(order_payload, parsed=parsed),
            order_actions_keyboard(order_id),
        )
        await callback.answer("✅ Склад прив'язано")
        return

    if action == "add":
        if chat_id is None:
            await callback.answer("❌ Неможливо додати позицію", show_alert=True)
            return
        review_state.set_pending(chat_id, PendingAddItem(order_id=order_id))
        await _edit_or_send(
            callback,
            "➕ Додавання позиції\n\n"
            "Введіть товар і кількість:\n"
            "<code>Назва товару — кількість</code>\n\n"
            "<i>Приклад: ГЕФ ЕСТ ПРО 50</i>\n"
            "Або <code>/cancel</code> для скасування.",
            reply_markup=cancel_edit_keyboard(order_id),
        )
        await callback.answer("✏️ Очікуємо позицію")
        return

    if action in {"eq", "ep", "rm"}:
        order_payload = services.order_service.get_order(order_id)
        if order_payload is None:
            await callback.answer("❌ Замовлення не знайдено", show_alert=True)
            return
        items = order_payload.get("items", [])
        if not items:
            await callback.answer("📭 У замовленні немає активних позицій", show_alert=True)
            return

        if action == "eq":
            text = "🔢 Оберіть позицію для зміни кількості"
            kb_action = "iq"
        elif action == "ep":
            text = "💰 Оберіть позицію для зміни ціни"
            kb_action = "ip"
        else:
            text = "🗑 Оберіть позицію для видалення"
            kb_action = "ir"

        await _edit_or_send(callback, text, reply_markup=order_items_keyboard(order_id, items, kb_action))
        await callback.answer()
        return

    if action in {"iq", "ip"}:
        if len(rest) != 1 or not rest[0].isdigit():
            await callback.answer("❌ Некоректний ID позиції", show_alert=True)
            return
        if chat_id is None:
            await callback.answer("❌ Неможливо почати редагування", show_alert=True)
            return

        item_id = int(rest[0])
        pending_action = "qty" if action == "iq" else "price"
        review_state.set_pending(chat_id, PendingEdit(action=pending_action, order_id=order_id, item_id=item_id))

        prompt = (
            f"🔢 Введіть нову кількість для позиції #{item_id}\n\n"
            f"<i>Або /cancel для скасування</i>"
            if pending_action == "qty"
            else f"💰 Введіть нову цену для позиції #{item_id}\n\n"
                 f"<i>Або /cancel для скасування</i>"
        )
        await _edit_or_send(callback, prompt, reply_markup=cancel_edit_keyboard(order_id))
        await callback.answer("✏️ Очікуємо значення")
        return

    if action == "ir":
        if len(rest) != 1 or not rest[0].isdigit():
            await callback.answer("❌ Некоректний ID позиції", show_alert=True)
            return
        item_id = int(rest[0])
        try:
            order_payload = services.order_service.remove_item(order_id=order_id, item_id=item_id)
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return

        parsed = _extract_parsed_payload(order_payload)
        text = format_order_approval(order_payload, parsed=parsed)
        await _edit_or_send(callback, text, reply_markup=order_actions_keyboard(order_id))
        await callback.answer("🗑 Позицію видалено")
        return

    await callback.answer("❌ Невідома дія", show_alert=True)


# ───────────────────────── Client / Warehouse management callbacks ─────────────────────────

@router.callback_query(F.data.startswith("cli|"))
async def client_management_callback(callback: CallbackQuery, services: ServiceContainer) -> None:
    parts = callback.data.split("|")
    if len(parts) < 3:
        await callback.answer("❌ Некоректна команда", show_alert=True)
        return
    _, action, client_id_raw = parts
    if not client_id_raw.isdigit():
        await callback.answer("❌ Некоректний ID", show_alert=True)
        return
    client_id = int(client_id_raw)

    if action == "del":
        ok = services.order_service.delete_client(client_id)
        if ok:
            await _edit_or_send(callback, f"🗑 Клієнта #{client_id} видалено.")
            await callback.answer("Видалено")
        else:
            await callback.answer("❌ Клієнта не знайдено", show_alert=True)
        return

    if action == "view":
        client = services.order_service.get_client_by_id(client_id)
        if client is None:
            await callback.answer("❌ Клієнта не знайдено", show_alert=True)
            return
        level = client.get("price_level", "base")
        lines = [
            f"👤 {client['name']}",
            f"🆔 #{client_id}",
            f"🏷 Рівень цін: {level}",
            f"💰 Знижка: {float(client.get('discount_percent', 0)):g}% + {float(client.get('discount_fixed', 0)):g}",
        ]
        if client.get("phone"):
            lines.append(f"📞 {client['phone']}")
        await _edit_or_send(callback, "\n".join(lines))
        await callback.answer()
        return

    await callback.answer("❌ Невідома дія", show_alert=True)


@router.callback_query(F.data.startswith("wh|"))
async def warehouse_management_callback(callback: CallbackQuery, services: ServiceContainer) -> None:
    parts = callback.data.split("|")
    if len(parts) < 3:
        await callback.answer("❌ Некоректна команда", show_alert=True)
        return
    _, action, wh_id_raw = parts
    if not wh_id_raw.isdigit():
        await callback.answer("❌ Некоректний ID", show_alert=True)
        return
    wh_id = int(wh_id_raw)

    if action == "del":
        ok = services.order_service.delete_warehouse(wh_id)
        if ok:
            await _edit_or_send(callback, f"🗑 Склад #{wh_id} видалено.")
            await callback.answer("Видалено")
        else:
            await callback.answer("❌ Склад не знайдено", show_alert=True)
        return

    if action == "view":
        wh = services.order_service.get_warehouse_by_id(wh_id)
        if wh is None:
            await callback.answer("❌ Склад не знайдено", show_alert=True)
            return
        await _edit_or_send(callback, f"🏭 {wh['name']}\n🆔 #{wh_id}")
        await callback.answer()
        return

    await callback.answer("❌ Невідома дія", show_alert=True)


# ───────────────────────── Text messages (orders + edits) ─────────────────────────

@router.message(F.text)
async def message_handler(
    message: Message,
    services: ServiceContainer,
    review_state: ReviewStateStore,
) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    if text.startswith("/"):
        return

    pending = review_state.get_pending(message.chat.id)
    if pending is not None:
        if text.lower() in {"/cancel", "cancel", "отмена", "скасувати"}:
            review_state.clear_pending(message.chat.id)
            await message.answer("✅ Редагування скасовано.")
            return

        # ── PendingAddItem ──
        if isinstance(pending, PendingAddItem):
            # Parse "Name Qty" or "Name - Qty"
            import re as _re
            match_qty = _re.search(r'(\d+(?:[.,]\d+)?)\s*$', text)
            if match_qty:
                name_hint = text[:match_qty.start()].strip()
                qty_str = match_qty.group(1).replace(",", ".")
                try:
                    qty = int(float(qty_str))
                except ValueError:
                    await message.answer(
                        "❌ Не вдалося розібрати кількість.\n\n"
                        "<i>Формат: Назва товару — кількість</i>\n"
                        "<i>Приклад: ГЕФ ЕСТ ПРО 50</i>\n\n"
                        "Або <code>/cancel</code>"
                    )
                    return
            else:
                # Try to find any number in the text
                numbers = _re.findall(r'\d+', text)
                if not numbers:
                    await message.answer(
                        "❌ Вкажіть кількість.\n\n"
                        "<i>Формат: Назва товару — кількість</i>\n"
                        "<i>Приклад: ГЕФ ЕСТ ПРО 50</i>\n\n"
                        "Або <code>/cancel</code>"
                    )
                    return
                qty = int(numbers[-1])
                name_hint = text[:text.rfind(numbers[-1])].strip()

            if not name_hint or qty <= 0:
                await message.answer(
                    "❌ Невірні дані. Назва товару і кількість повинні бути > 0.\n\n"
                    "Або <code>/cancel</code>"
                )
                return

            try:
                updated = services.order_service.add_item_to_order(
                    order_id=pending.order_id,
                    name_hint=name_hint,
                    qty=qty,
                )
            except ValueError as exc:
                await message.answer(f"❌ {exc}\n\nАбо <code>/cancel</code>")
                return

            review_state.clear_pending(message.chat.id)
            parsed = _extract_parsed_payload(updated)
            await message.answer(
                format_order_approval(updated, parsed=parsed),
                reply_markup=order_actions_keyboard(pending.order_id),
            )
            await message.answer("✅ Позицію додано.")
            return

        # ── PendingEdit (qty/price) ──
        try:
            if pending.action == "qty":
                qty = int(float(text.replace(",", ".")))
                updated = services.order_service.edit_item_qty(
                    order_id=pending.order_id,
                    item_id=pending.item_id,
                    qty=qty,
                )
            else:
                price = float(text.replace(" ", "").replace(",", "."))
                updated = services.order_service.edit_item_price(
                    order_id=pending.order_id,
                    item_id=pending.item_id,
                    price_at_order=price,
                )
        except ValueError as exc:
            await message.answer(
                f"❌ Помилка: {exc}\n\n"
                f"Введіть коректне число або <code>/cancel</code>",
                parse_mode="HTML",
            )
            return

        review_state.clear_pending(message.chat.id)
        parsed = _extract_parsed_payload(updated)
        await message.answer(
            format_order_approval(updated, parsed=parsed),
            reply_markup=order_actions_keyboard(pending.order_id),
        )
        return

    parse = services.order_parser.parse(text)
    if parse.status == "not_order":
        await message.answer(
            "🤔 Схоже, це не замовлення.\n\n"
            "Надішліть позиції у форматі:\n"
            "<code>Товар - кількість</code>\n\n"
            "<i>Приклад: Виставте рахунок на 280л ГЕФ ЕСТ ПРО</i>"
        )
        return

    if parse.status != "ok" or parse.data is None:
        services.order_service.save_parse_error(raw_text=text, error_message=parse.error_message or "parse error")
        await message.answer(
            f"❌ Не вдалося розібрати замовлення.\n\n"
            f"<i>Помилка:</i> {parse.error_message}\n\n"
            f"Спробуйте інший формат."
        )
        return

    created = services.order_service.create_draft_from_parsed(parsed=parse.data, raw_text=text)
    await message.answer(
        format_order_approval(created, parsed=parse.data),
        reply_markup=order_actions_keyboard(int(created["order"]["id"])),
    )
