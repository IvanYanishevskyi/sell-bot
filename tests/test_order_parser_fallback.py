from __future__ import annotations

import pytest

from order_bot.llm.order_parser import OrderParser


@pytest.mark.skip(reason="OrderParser fallback heuristic removed; requires LLM")
def test_fallback_parser_handles_multiline_mail_order() -> None:
    raw = """
订单📝 МЕ202600685
ТОВ «Аграріуф» контракт 200 тис
1. Міланіт 5 л - 185 л
2. Склад  Вінницькі хутори
Забере
АВ 3817 МВ
Citroen Jumper
068 622 86 98
Савицький Костянтин
""".strip()

    parser = OrderParser(api_key=None)
    result = parser.parse(raw)

    assert result.status == "ok"
    assert result.data is not None
    assert result.data["parse_source"] == "heuristic"
    assert result.data["order_no"] == "МЕ202600685"
    assert result.data["client_hint"] is None
    assert result.data["warehouse_hint"] == "Вінницькі хутори"
    assert result.data["phone_hint"] == "068 622 86 98"
    assert result.data["vehicle_hint"] == "АВ 3817 МВ"
    assert result.data["items"][0]["name_hint"].startswith("Міланіт")
    assert result.data["items"][0]["qty"] == 185


@pytest.mark.skip(reason="OrderParser fallback heuristic removed; requires LLM")
def test_fallback_parser_generic_dash_line() -> None:
    raw = """
АГРОСІТІ-КРОП
Сатіс - 0,5л -2,5-3,5
""".strip()

    parser = OrderParser(api_key=None)
    result = parser.parse(raw)

    assert result.status == "ok"
    assert result.data is not None
    assert result.data["client_hint"] is None
    assert len(result.data["items"]) == 1
    assert result.data["items"][0]["name_hint"] == "Сатіс"
    assert result.data["items"][0]["qty"] == 4


@pytest.mark.skip(reason="OrderParser fallback heuristic removed; requires LLM")
def test_fallback_parser_invoice_phrase_with_qty_before_name() -> None:
    raw = """
Виставте рахунок на 280л гефест про
Дякую
""".strip()

    parser = OrderParser(api_key=None)
    result = parser.parse(raw)

    assert result.status == "ok"
    assert result.data is not None
    assert len(result.data["items"]) == 1
    assert result.data["items"][0]["name_hint"].lower() == "гефест про"
    assert result.data["items"][0]["qty"] == 280


def test_sanitize_order_no_rejects_quantity_like_value() -> None:
    parser = OrderParser(api_key=None)
    assert parser._sanitize_order_no("280л") is None
    assert parser._sanitize_order_no("ME202600685") == "ME202600685"


class _BadLLM:
    @property
    def enabled(self) -> bool:  # pragma: no cover - trivial
        return True

    def parse_json(self, system_prompt: str, raw_text: str) -> dict:
        if "Classify whether user text" in system_prompt:
            return {"is_order": True, "reason": "llm"}
        return {
            "items": [{"name_hint": "гефест", "qty": 1}],
            "order_no": "280л",
            "warehouse_hint": None,
            "contact_hint": None,
            "phone_hint": None,
            "vehicle_hint": None,
        }


@pytest.mark.skip(reason="OrderParser fallback heuristic removed; requires LLM")
def test_heuristic_override_when_llm_qty_is_wrong() -> None:
    parser = OrderParser(api_key=None)
    parser.llm = _BadLLM()
    result = parser.parse("Виставте рахунок на 280л гефест про")

    assert result.status == "ok"
    assert result.data is not None
    assert result.data["parse_source"] == "heuristic_override"
    assert result.data["order_no"] is None
    assert result.data["items"][0]["name_hint"].lower() == "гефест про"
    assert result.data["items"][0]["qty"] == 280
