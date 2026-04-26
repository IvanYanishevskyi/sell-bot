from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UserActivity:
    timestamps: list[float] = field(default_factory=list)
    warned: bool = False
    blocked_until: float = 0.0


class AntiSpam:
    """Simple sliding-window rate limiter per user."""

    def __init__(
        self,
        window_sec: float = 60.0,
        max_messages: int = 15,
        block_duration_sec: float = 120.0,
        warn_threshold: int = 10,
    ) -> None:
        self.window_sec = window_sec
        self.max_messages = max_messages
        self.block_duration_sec = block_duration_sec
        self.warn_threshold = warn_threshold
        self._users: dict[int, UserActivity] = {}

    def _cleanup(self, now: float) -> None:
        cutoff = now - self.window_sec
        for act in self._users.values():
            act.timestamps = [t for t in act.timestamps if t > cutoff]

    def check(self, user_id: int) -> tuple[bool, str | None]:
        """Returns (allowed, warning_or_block_message)."""
        now = time.time()
        self._cleanup(now)

        act = self._users.setdefault(user_id, UserActivity())

        # Check block
        if now < act.blocked_until:
            remaining = int(act.blocked_until - now)
            return False, (
                f"Ви тимчасово заблоковані через надмірну активність. "
                f"Спробуйте ще раз через {remaining} сек."
            )

        act.timestamps.append(now)

        if len(act.timestamps) > self.max_messages:
            act.blocked_until = now + self.block_duration_sec
            return False, (
                f"Забагато повідомлень. Ви заблоковані на {int(self.block_duration_sec)} сек. "
                f"Будь ласка, не спамте."
            )

        if len(act.timestamps) >= self.warn_threshold and not act.warned:
            act.warned = True
            return True, (
                f"Повільніше — ви надто активні. "
                f"Ще {self.max_messages - self.warn_threshold + 1} повідомлень і ви отримаєте тимчасовий бан."
            )

        # Reset warned if they slow down
        if len(act.timestamps) < self.warn_threshold:
            act.warned = False

        return True, None

    def is_admin(self, user_id: int, admin_ids: set[int] | None = None) -> bool:
        if admin_ids is None:
            return False
        return user_id in admin_ids


# Global instance (attached to dispatcher context in main.py)
_default_anti_spam: AntiSpam | None = None


def get_anti_spam(config: Any | None = None) -> AntiSpam:
    global _default_anti_spam
    if _default_anti_spam is None:
        _default_anti_spam = AntiSpam()
    return _default_anti_spam
