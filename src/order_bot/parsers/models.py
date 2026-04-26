from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParseError:
    row: int
    field: str
    message: str


@dataclass
class ParseResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    errors: list[ParseError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0
