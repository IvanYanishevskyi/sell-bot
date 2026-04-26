from __future__ import annotations

import pytest

from order_bot.llm.order_parser import OrderParser


@pytest.mark.skip(reason="OrderParser fallback heuristic removed; requires LLM")
def test_non_order_message_is_skipped() -> None:
    parser = OrderParser(api_key=None)
    result = parser.parse("Привет, как дела? Сегодня встреча в 17:00")

    assert result.status == "not_order"
    assert result.data is not None
    assert result.data["intent"]["is_order"] is False


def test_order_intent_without_items_is_detected() -> None:
    parser = OrderParser(api_key=None)
    raw = "Заказ МЕ202600685. Склад Кропивницький. Забере завтра."
    result = parser.parse(raw)

    # Intent is order-like, but parser cannot build items -> parse_error.
    assert result.status == "parse_error"
    assert result.error_message is not None
