from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PendingEdit:
    action: str  # qty | price
    order_id: int
    item_id: int


@dataclass
class PendingAddItem:
    order_id: int


class ReviewStateStore:
    def __init__(self) -> None:
        self._pending_by_chat: dict[int, PendingEdit | PendingAddItem] = {}
        self._upload_mode_by_chat: dict[int, str] = {}

    def set_pending(self, chat_id: int, pending: PendingEdit | PendingAddItem) -> None:
        self._pending_by_chat[chat_id] = pending

    def get_pending(self, chat_id: int) -> PendingEdit | PendingAddItem | None:
        return self._pending_by_chat.get(chat_id)

    def clear_pending(self, chat_id: int) -> None:
        self._pending_by_chat.pop(chat_id, None)

    def set_upload_mode(self, chat_id: int, mode: str) -> None:
        if mode not in {"price", "warehouse"}:
            raise ValueError("mode must be 'price' or 'warehouse'")
        self._upload_mode_by_chat[chat_id] = mode

    def get_upload_mode(self, chat_id: int) -> str | None:
        return self._upload_mode_by_chat.get(chat_id)

    def clear_upload_mode(self, chat_id: int) -> None:
        self._upload_mode_by_chat.pop(chat_id, None)
