from __future__ import annotations

import re
from typing import Any

try:
    import xlrd
except ImportError:
    xlrd = None


def _normalize_phone(val: Any) -> str | None:
    if val is None or val == "":
        return None
    s = str(val).replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    # Remove trailing .0 from float representation BEFORE stripping all dots
    if s.endswith(".0"):
        s = s[:-2]
    s = s.replace(".", "")
    # Keep only digits
    digits = re.sub(r"\D", "", s)
    if not digits:
        return None
    # Ukrainian mobile: 9 digits (e.g. 664032390) or 12 (380664032390)
    if len(digits) == 9:
        digits = "380" + digits
    if len(digits) == 12 and digits.startswith("380"):
        return f"+{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"+38{digits[1:]}"
    if len(digits) == 10 and not digits.startswith("0"):
        return f"+38{digits}"
    return digits if len(digits) >= 7 else None


def _contract_to_price_level(contract: str) -> str:
    c = str(contract).strip().lower().replace(" ", "")
    if "200" in c:
        return "200k"
    if "100" in c:
        return "100k"
    if "150" in c:
        return "150k"
    return "base"


def _clean_warehouse_name(name: str) -> str:
    # Remove underscores and extra whitespace
    cleaned = re.sub(r"[_]+", " ", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _is_likely_product(name: str) -> bool:
    # Product names contain volume/weight units
    return bool(re.search(r"\d+\s*(л|кг|мл|гр|грам|г)\b", name.lower()))


def parse_clients_from_1c_report(file_bytes: bytes) -> list[dict[str, Any]]:
    """Parse client list from 1C 'Контракти Дистрибютори' .xls report."""
    if xlrd is None:
        raise RuntimeError("xlrd is not installed")

    book = xlrd.open_workbook(file_contents=file_bytes)
    sheet = book.sheet_by_index(0)

    clients: list[dict[str, Any]] = []

    for r in range(sheet.nrows):
        row = sheet.row_values(r)
        if len(row) < 6:
            continue

        name = str(row[1]).strip() if row[1] else ""
        contract = str(row[2]).strip() if row[2] else ""
        manager = str(row[4]).strip() if row[4] else ""
        phone_raw = row[5] if len(row) > 5 else ""
        location = str(row[6]).strip() if len(row) > 6 and row[6] else ""
        plan_2026 = str(row[7]).strip() if len(row) > 7 and row[7] else ""

        # Skip empty, summary, or group-header rows
        if not name or name.lower() in ("підсумок", "итого", "разом", "всього"):
            continue
        if not contract and not manager and not phone_raw:
            continue
        # Group headers typically have no contract type and no phone
        if not contract and not _normalize_phone(phone_raw):
            continue
        # Exclude obvious product or warehouse names
        if _is_likely_product(name):
            continue

        phone = _normalize_phone(phone_raw)
        price_level = _contract_to_price_level(contract)

        notes_parts = []
        if manager:
            notes_parts.append(f"Менеджер: {manager}")
        if plan_2026:
            notes_parts.append(f"План 2026: {plan_2026}")

        client = {
            "name": name,
            "price_level": price_level,
            "phone": phone,
            "address": location or None,
            "notes": "; ".join(notes_parts) if notes_parts else None,
        }
        clients.append(client)

    return clients


def parse_warehouses_from_1c_stock(file_bytes: bytes) -> list[dict[str, Any]]:
    """Extract warehouse names from 1C stock report .xls file.

    In 1C stock reports, warehouse names appear as group-header rows
    followed by product detail rows.
    """
    if xlrd is None:
        raise RuntimeError("xlrd is not installed")

    book = xlrd.open_workbook(file_contents=file_bytes)
    sheet = book.sheet_by_index(0)

    warehouses: list[dict[str, Any]] = []

    for r in range(sheet.nrows):
        row = sheet.row_values(r)
        if len(row) < 2:
            continue

        col1 = str(row[1]).strip() if row[1] else ""
        col2 = row[2] if len(row) > 2 else None

        if not col1:
            continue

        # Skip obvious products (volume/weight units)
        if _is_likely_product(col1):
            continue

        # Skip summary / header rows
        first_word = (col1.split()[0] if col1 else "").lower().strip(".,;:!?")
        if first_word in ("підсумок", "итого", "разом", "всього", "відбори", "групування", "показники"):
            continue

        # Strong warehouse signals in 1C reports
        has_underscores = "_" in col1
        # Use strict threshold: product names like "КлетАКТИВ" should not pass
        is_mostly_upper = sum(1 for c in col1 if c.isupper()) / max(len(col1), 1) > 0.75
        has_number_sign = "№" in col1

        if not (has_underscores or is_mostly_upper or has_number_sign):
            continue

        # Weak signal — require col2 to be a large numeric total, except zero-stock warehouses
        col2_is_large_number = isinstance(col2, (int, float)) and float(col2) >= 500
        if not col2_is_large_number and not (has_underscores and len(col1) > 10):
            continue

        name = _clean_warehouse_name(col1)
        if not name or len(name) < 3:
            continue

        warehouses.append({"name": name})

    # Deduplicate by normalized name
    seen: set[str] = set()
    unique_warehouses: list[dict[str, Any]] = []
    for w in warehouses:
        norm = w["name"].lower()
        if norm not in seen:
            seen.add(norm)
            unique_warehouses.append(w)

    return unique_warehouses
