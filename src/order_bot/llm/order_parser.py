from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any
from pydantic import BaseModel, Field, ValidationError
from order_bot.llm.client import JSONLLMClient, LLMClientConfig

INTENT_PROMPT = """
Classify whether user text is a product order request for sales processing.
Return ONLY JSON: {"is_order": boolean, "reason": string}
is_order=true when text contains order intent, product lines, quantities, pickup/shipping details.
""".strip()

PARSE_PROMPT = """
Parse mixed RU/UA order text into strict JSON.
Return ONLY JSON with fields:
- order_no: string|null
- warehouse_hint: string|null
- contact_hint: string|null
- phone_hint: string|null
- vehicle_hint: string|null
- items: array of {name_hint: string, qty: positive integer}
Rules:
- qty — це КІЛЬКІСТЬ УПАКОВОК/ОДИНИЦЬ товару, НЕ об'єм і НЕ вага
- Якщо написано "280л БАЛОР" або "БАЛОР 280л" — qty=280, name_hint="БАЛОР"
- Якщо написано "5 каністр АВАТАР" — qty=5, name_hint="АВАТАР"
- Об'єм фасування (5л, 20л, 10кг) — це частина назви товару, не кількість
- If quantity is fractional — round to nearest integer, minimum 1
- Ignore greetings, signatures, unrelated text
- Extract ALL product lines, even if format is inconsistent
""".strip()

class ParsedOrderItem(BaseModel):
    name_hint: str = Field(min_length=1)
    qty: int = Field(gt=0)

class ParsedOrder(BaseModel):
    client_hint: str | None = None
    items: list[ParsedOrderItem] = Field(min_length=1)
    order_no: str | None = None
    warehouse_hint: str | None = None
    contact_hint: str | None = None
    phone_hint: str | None = None
    vehicle_hint: str | None = None

@dataclass
class OrderParseResult:
    status: str
    data: dict[str, Any] | None
    error_message: str | None

class OrderParser:
    def __init__(
        self,
        llm: JSONLLMClient | None = None,
        provider: str = "openai",
        api_key: str | None = None,
        model: str = "gpt-4.1-mini",
        base_url: str | None = None,
        openrouter_site_url: str | None = None,
        openrouter_app_name: str | None = None,
    ) -> None:
        if llm is not None:
            self.llm = llm
        else:
            self.llm = JSONLLMClient(
                LLMClientConfig(
                    provider=provider,
                    api_key=api_key,
                    model=model,
                    base_url=base_url,
                    openrouter_site_url=openrouter_site_url,
                    openrouter_app_name=openrouter_app_name,
                )
            )

    def parse(self, raw_text: str) -> OrderParseResult:
        text = raw_text.strip()
        if not text:
            return OrderParseResult(status="parse_error", data=None, error_message="Empty order text")
        if not self.llm.enabled:
            return OrderParseResult(status="parse_error", data=None, error_message="LLM not configured")

        # 1. класифікуємо намір
        try:
            intent = self.llm.parse_json(INTENT_PROMPT, text)
        except Exception as exc:
            return OrderParseResult(status="parse_error", data=None, error_message=f"Intent check failed: {exc}")

        if not intent.get("is_order", False):
            return OrderParseResult(
                status="not_order",
                data=None,
                error_message=intent.get("reason") or "Not an order",
            )

        # 2. парсимо замовлення
        try:
            payload = self.llm.parse_json(PARSE_PROMPT, text)
            payload.setdefault("parse_source", "llm")
            validated = ParsedOrder.model_validate(payload)
            data = validated.model_dump()
            data["order_no"] = self._sanitize_order_no(data.get("order_no"))
            data["parse_source"] = "llm"
            return OrderParseResult(status="ok", data=data, error_message=None)
        except (json.JSONDecodeError, ValidationError) as exc:
            return OrderParseResult(status="parse_error", data=None, error_message=f"Schema validation error: {exc}")
        except Exception as exc:
            return OrderParseResult(status="parse_error", data=None, error_message=f"LLM parse error: {exc}")

    @staticmethod
    def _sanitize_order_no(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip().replace(" ", "")
        if not text:
            return None
        digits = sum(1 for ch in text if ch.isdigit())
        if digits < 5:
            return None
        return text
