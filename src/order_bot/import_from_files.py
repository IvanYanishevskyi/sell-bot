#!/usr/bin/env python3
"""Import clients from 'ЯН контракти Дистрибютори 2026.xls' and warehouses from 'КомерцСклад 17-04-26.xls'."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import xlrd

from order_bot.db import Database, init_db
from order_bot.services import MatchingService, OrderService

_PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = _PROJECT_ROOT / "data" / "app.db"
CLIENTS_FILE = _PROJECT_ROOT / "ЯН контракти Дистрибютори 2026.xls"
WAREHOUSES_FILE = _PROJECT_ROOT / "КомерцСклад 17-04-26.xls"


def _clean_phone(val) -> str | None:
    if val is None or val == "":
        return None
    s = str(val).strip().replace(".0", "")
    # keep only digits and leading +
    cleaned = "".join(ch for ch in s if ch.isdigit() or ch == "+")
    return cleaned or None


def _contract_to_price_level(contract: str) -> str:
    c = contract.strip().lower()
    if "200" in c:
        return "200k"
    if "150" in c:
        return "150k"
    if "100" in c:
        return "100k"
    return "base"


def import_clients() -> int:
    if not CLIENTS_FILE.exists():
        print(f"❌ Файл не знайдено: {CLIENTS_FILE}")
        return 0

    wb = xlrd.open_workbook(str(CLIENTS_FILE))
    sh = wb.sheet_by_index(0)

    db = Database(DB_PATH)
    order_service = OrderService(db, MatchingService())

    created = 0
    seen = set()

    for r in range(11, sh.nrows):
        name = str(sh.cell(r, 1).value).strip()
        contract = str(sh.cell(r, 2).value).strip()
        phone_raw = sh.cell(r, 5).value
        if not name or name in ("Сергій Янішевський", "Підсумок") or "Підсумок" in name:
            continue
        # normalize for deduplication
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        phone = _clean_phone(phone_raw)
        price_level = _contract_to_price_level(contract)

        try:
            order_service.create_client(
                name=name,
                discount_percent=0,
                discount_fixed=0,
                price_level=price_level,
                phone=phone,
                address=None,
                notes=None,
            )
            created += 1
            print(f"  + {name} ({price_level}) {phone or ''}")
        except Exception as exc:
            print(f"  ✗ {name}: {exc}")

    print(f"\n✅ Імпортовано клієнтів: {created}")
    return created


def import_warehouses() -> int:
    if not WAREHOUSES_FILE.exists():
        print(f"❌ Файл не знайдено: {WAREHOUSES_FILE}")
        return 0

    wb = xlrd.open_workbook(str(WAREHOUSES_FILE))
    sh = wb.sheet_by_index(0)

    db = Database(DB_PATH)
    order_service = OrderService(db, MatchingService())

    created = 0
    seen = set()

    for r in range(8, sh.nrows):
        val = str(sh.cell(r, 1).value).strip()
        if not val or val == "Номенклатура" or "Аналіз" in val or "Період" in val:
            continue
        # Heuristic: warehouse rows contain underscores, ALL CAPS, or specific keywords
        is_wh = (
            "_" in val
            or val.isupper()
            or "№" in val
            or "БАЗА" in val
            or "ВЗ" in val
            or "склад" in val.lower()
        )
        if not is_wh:
            continue
        # clean underscores
        clean = val.replace("_", " ").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)

        try:
            order_service.create_warehouse(clean)
            created += 1
            print(f"  + {clean}")
        except Exception as exc:
            print(f"  ✗ {clean}: {exc}")

    print(f"\n✅ Імпортовано складів: {created}")
    return created


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    init_db(DB_PATH)

    print("📦 Імпорт клієнтів...")
    import_clients()

    print("\n🏭 Імпорт складів...")
    import_warehouses()

    print("\n🎉 Готово!")


if __name__ == "__main__":
    main()
