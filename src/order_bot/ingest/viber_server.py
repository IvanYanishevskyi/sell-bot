from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from aiohttp import web
from aiogram import Bot

from order_bot.bot.formatters import format_order_approval
from order_bot.bot.keyboards import order_actions_keyboard

if TYPE_CHECKING:
    from order_bot.bootstrap import ServiceContainer


@dataclass
class ViberConfig:
    enabled: bool
    host: str
    port: int
    path: str
    auth_token: str | None
    manager_chat_id: int | None


class ViberIngestServer:
    def __init__(self, config: ViberConfig, services: "ServiceContainer") -> None:
        self.config = config
        self.services = services
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    async def start(self, bot: Bot) -> None:
        if not self.config.enabled:
            return

        app = web.Application()
        app["bot"] = bot
        app.router.add_post(self.config.path, self._handle_webhook)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host=self.config.host, port=self.config.port)
        await self._site.start()
        print(f"[viber] webhook listening on {self.config.host}:{self.config.port}{self.config.path}")

    async def stop(self) -> None:
        if self._site is not None:
            with suppress(Exception):
                await self._site.stop()
            self._site = None
        if self._runner is not None:
            with suppress(Exception):
                await self._runner.cleanup()
            self._runner = None

    async def _handle_webhook(self, request: web.Request) -> web.Response:
        if self.config.auth_token:
            header_token = request.headers.get("X-Viber-Auth-Token", "")
            if header_token != self.config.auth_token:
                return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

        event = str(payload.get("event") or "").lower()
        if event != "message":
            return web.json_response({"ok": True, "skipped": "non_message_event"})

        message = payload.get("message") or {}
        text = str(message.get("text") or "").strip()
        if not text:
            return web.json_response({"ok": True, "skipped": "empty_text"})

        sender = payload.get("sender") or {}
        sender_name = str(sender.get("name") or "")
        sender_id = str(sender.get("id") or "")

        raw_text = self._compose_raw_text(sender_name=sender_name, sender_id=sender_id, text=text)
        parse = self.services.order_parser.parse(raw_text)
        if parse.status == "not_order":
            return web.json_response({"ok": True, "skipped": "not_order"})
        if parse.status != "ok" or parse.data is None:
            self.services.order_service.save_parse_error(raw_text=raw_text, error_message=parse.error_message or "parse error")
            return web.json_response({"ok": True, "skipped": "parse_error"})

        created = self.services.order_service.create_draft_from_parsed(parsed=parse.data, raw_text=raw_text)

        manager_chat_id = self.config.manager_chat_id
        if manager_chat_id is None:
            return web.json_response({"ok": True, "skipped": "manager_chat_not_set"})

        bot: Bot = request.app["bot"]
        await bot.send_message(
            chat_id=manager_chat_id,
            text=format_order_approval(
                order_payload=created,
                parsed=parse.data,
                source_subject="Viber incoming message",
                source_from=sender_name or sender_id or "Viber",
            ),
            reply_markup=order_actions_keyboard(int(created["order"]["id"])),
        )
        return web.json_response({"ok": True, "status": "draft_sent"})

    @staticmethod
    def _compose_raw_text(sender_name: str, sender_id: str, text: str) -> str:
        header = [f"Viber sender: {sender_name or '-'}"]
        if sender_id:
            header.append(f"Viber sender_id: {sender_id}")
        return "\n".join(header) + "\n\n" + text
