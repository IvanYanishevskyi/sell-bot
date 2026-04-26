from __future__ import annotations

import csv
import io
from typing import Any


class FakeLLMClient:
    """Fake LLM client that parses simple tabular text for tests."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def parse_json(self, system_prompt: str, raw_text: str) -> dict[str, Any]:
        if "прайс" in system_prompt or "price" in system_prompt.lower():
            return self._parse_price(raw_text)
        if "залишк" in system_prompt or "stock" in system_prompt.lower():
            return self._parse_stock(raw_text)
        if "склад" in system_prompt or "warehouse" in system_prompt.lower():
            return self._parse_warehouse(raw_text)
        return {"rows": [], "errors": ["Unknown type"]}

    @staticmethod
    def _parse_csv_like(text: str) -> list[list[str]]:
        lines = text.strip().splitlines()
        if not lines:
            return []
        first = lines[0]
        if "\t" in first:
            reader = csv.reader(io.StringIO("\n".join(lines)), delimiter="\t")
        else:
            reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=",")
        rows = list(reader)
        if not rows:
            return []
        # heuristic header skip
        header = rows[0]
        header_hints = {"sku", "name", "назва", "артикул", "склад", "quantity", "кол", "price", "ціна", "№", "базова"}
        if any(any(hint in h.lower() for hint in header_hints) for h in header if h):
            rows = rows[1:]
        return rows

    @staticmethod
    def _to_float(val: str) -> float:
        return float(val.replace(",", ".").replace(" ", "").replace("\xa0", ""))

    def _parse_price(self, text: str) -> dict[str, Any]:
        rows = self._parse_csv_like(text)
        result: list[dict[str, Any]] = []
        for r in rows:
            if len(r) >= 3:
                try:
                    result.append(
                        {
                            "sku": r[0].strip(),
                            "name": r[1].strip(),
                            "base_price": self._to_float(r[2]),
                        }
                    )
                except (ValueError, IndexError):
                    pass
        return {"rows": result, "errors": []}

    def _parse_stock(self, text: str) -> dict[str, Any]:
        rows = self._parse_csv_like(text)
        result: list[dict[str, Any]] = []
        for r in rows:
            if len(r) >= 2:
                try:
                    result.append(
                        {
                            "name": r[0].strip(),
                            "qty": int(self._to_float(r[1])),
                        }
                    )
                except (ValueError, IndexError):
                    pass
        return {"rows": result, "errors": []}

    def _parse_warehouse(self, text: str) -> dict[str, Any]:
        rows = self._parse_csv_like(text)
        result: list[dict[str, Any]] = []
        for r in rows:
            if len(r) >= 1:
                result.append(
                    {
                        "name": r[0].strip(),
                        "address": r[1].strip() if len(r) > 1 else "",
                    }
                )
        return {"rows": result, "errors": []}
