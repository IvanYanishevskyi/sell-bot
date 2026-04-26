from __future__ import annotations

import pytest

from order_bot.parsers.direct_parsers import parse_clients_from_1c_report, parse_warehouses_from_1c_stock


def test_parse_clients_from_real_file() -> None:
    with open("ЯН контракти Дистрибютори 2026.xls", "rb") as f:
        clients = parse_clients_from_1c_report(f.read())

    assert len(clients) >= 20
    names = {c["name"] for c in clients}
    assert "АГРІКОЛА-К_м" in names
    assert "АГРОІМПУЛЬС" in names
    assert "АГРОТОК" in names

    # Check price levels mapping
    agrikola = next(c for c in clients if "АГРІКОЛА" in c["name"])
    assert agrikola["price_level"] == "base"

    agrar = next(c for c in clients if "АГРАРІУФ" in c["name"])
    assert agrar["price_level"] == "200k"

    hektar = next(c for c in clients if "ГЕКТАР" in c["name"])
    assert hektar["price_level"] == "100k"

    # Check phone normalization
    assert agrikola["phone"] is not None
    assert agrikola["phone"].startswith("+")
    assert "380" in agrikola["phone"]


def test_parse_warehouses_from_stock_file() -> None:
    with open("КомерцСклад 17-04-26.xls", "rb") as f:
        warehouses = parse_warehouses_from_1c_stock(f.read())

    names = {w["name"] for w in warehouses}
    print("Found warehouses:", names)

    assert "БОЯРКА" in names
    assert any("Кропивницький" in n for n in names)
    assert "Луцьк" in names
    assert any("Полтава" in n for n in names)
    # Make sure products are NOT included
    assert "КлетАКТИВ" not in names
    assert "Підсумок" not in names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
