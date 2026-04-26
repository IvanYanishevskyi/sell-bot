from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher

from order_bot.repositories.price import PriceRepository

try:
    from rapidfuzz import fuzz, process
except ImportError:  # pragma: no cover
    fuzz = None
    process = None


SKU_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{3,}")
NON_ALNUM_RE = re.compile(r"[^a-zA-Zа-яА-ЯіІїЇєЄґҐ0-9]+")


@dataclass
class MatchResult:
    sku: str
    name: str
    price: float
    base_price: float
    price_200k: float
    price_150k: float
    price_100k: float
    currency: str
    confidence: float
    needs_review: bool


class MatchingService:
    def __init__(self, confidence_threshold: float = 0.82, min_accept_confidence: float = 0.55) -> None:
        self.confidence_threshold = confidence_threshold
        self.min_accept_confidence = min_accept_confidence

    @staticmethod
    def _build_result(row: dict, confidence: float, needs_review: bool) -> MatchResult:
        base = float(row.get("base_price") or row.get("price") or 0)
        return MatchResult(
            sku=str(row["sku"]),
            name=str(row["name"]),
            price=base,
            base_price=base,
            price_200k=float(row.get("price_200k", base)),
            price_150k=float(row.get("price_150k", base)),
            price_100k=float(row.get("price_100k", base)),
            currency=str(row.get("currency", "USD")),
            confidence=confidence,
            needs_review=needs_review,
        )

    def match(self, conn: sqlite3.Connection, name_hint: str) -> MatchResult | None:
        price_repo = PriceRepository(conn)

        sku_hint = self._extract_possible_sku(name_hint)
        if sku_hint:
            exact = price_repo.get_active_item_by_sku(sku_hint)
            if exact is not None:
                return self._build_result(exact, confidence=1.0, needs_review=False)

        active_price = price_repo.get_active()
        if active_price is None:
            return None

        items = active_price["items"]
        if not items:
            return None

        contains_item, contains_conf = self._substring_match(name_hint, items)
        if contains_item is not None:
            needs_review = contains_conf < self.confidence_threshold
            return self._build_result(contains_item, confidence=contains_conf, needs_review=needs_review)

        best_item, confidence = self._fuzzy_match(name_hint, items)
        if best_item is None:
            return None
        if confidence < self.min_accept_confidence:
            return None

        needs_review = confidence < self.confidence_threshold
        return self._build_result(best_item, confidence=confidence, needs_review=needs_review)

    @staticmethod
    def _extract_possible_sku(text: str) -> str | None:
        matches = SKU_TOKEN_RE.findall(text.upper())
        if not matches:
            return None
        return matches[0]

    def _fuzzy_match(self, name_hint: str, items: list[dict]) -> tuple[dict | None, float]:
        names = [str(item["name"]) for item in items]
        if process is not None and fuzz is not None:
            best = process.extractOne(name_hint, names, scorer=fuzz.WRatio)
            if best is None:
                return None, 0.0
            matched_name, score, index = best
            _ = matched_name
            return items[int(index)], float(score) / 100.0

        best_index = -1
        best_score = 0.0
        for idx, candidate in enumerate(names):
            score = SequenceMatcher(None, name_hint.lower(), candidate.lower()).ratio()
            if score > best_score:
                best_score = score
                best_index = idx

        if best_index < 0:
            return None, 0.0
        return items[best_index], best_score

    def _substring_match(self, name_hint: str, items: list[dict]) -> tuple[dict | None, float]:
        hint = self._norm(name_hint)
        if not hint:
            return None, 0.0
        hint_tokens = set(hint.split())

        best_item: dict | None = None
        best_score = 0.0
        for item in items:
            candidate = self._norm(str(item["name"]))
            if not candidate:
                continue
            score = 0.0
            if hint in candidate:
                score = max(score, 0.9)
            if candidate in hint:
                score = max(score, 0.78)

            cand_tokens = set(candidate.split())
            if hint_tokens and hint_tokens.issubset(cand_tokens):
                score = max(score, 0.88)
            elif hint_tokens:
                overlap = len(hint_tokens & cand_tokens) / max(1, len(hint_tokens))
                if overlap >= 0.7:
                    score = max(score, 0.72)

            if score > best_score:
                best_item = item
                best_score = score

        if best_item is None or best_score < self.min_accept_confidence:
            return None, 0.0
        return best_item, best_score

    @staticmethod
    def _norm(value: str) -> str:
        compact = NON_ALNUM_RE.sub(" ", value.lower()).strip()
        return " ".join(compact.split())
