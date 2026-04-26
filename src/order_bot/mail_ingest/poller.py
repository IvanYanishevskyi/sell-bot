from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from aiogram import Bot

from order_bot.bot.formatters import format_order_approval, format_order_parse_failure
from order_bot.bot.keyboards import order_actions_keyboard
from order_bot.mail_ingest.imap_reader import ImapOrderReader, InboxMessage

if TYPE_CHECKING:
    from order_bot.bootstrap import ServiceContainer


class EmailOrderPoller:
    def __init__(
        self,
        reader: ImapOrderReader,
        services: "ServiceContainer",
        poll_seconds: int = 30,
        target_chat_id: int | None = None,
        batch_limit: int = 10,
    ) -> None:
        self.reader = reader
        self.services = services
        self.poll_seconds = max(5, poll_seconds)
        self.target_chat_id = target_chat_id
        self.batch_limit = batch_limit

    async def run_forever(self, bot: Bot) -> None:
        while True:
            try:
                await self.poll_once(bot=bot)
            except Exception as exc:
                print(f"[mail] poll error: {exc}")
            await asyncio.sleep(self.poll_seconds)

    async def poll_once(self, bot: Bot, chat_id: int | None = None) -> int:
        target_chat = chat_id or self.target_chat_id
        if target_chat is None:
            return 0

        messages = await asyncio.to_thread(self.reader.fetch_unseen, self.batch_limit)
        processed = 0
        for msg in messages:
            try:
                await self._process_message(bot, target_chat, msg)
                processed += 1
            finally:
                # Do not reprocess the same mail forever.
                await asyncio.to_thread(self.reader.mark_seen, msg.uid)
        return processed

    async def _process_message(self, bot: Bot, chat_id: int, msg: InboxMessage) -> None:
        raw_text = self._compose_raw_text(msg)
        parse = self.services.order_parser.parse(raw_text)
        if parse.status == "not_order":
            print(f"[mail] skipped non-order message uid={msg.uid} subject={msg.subject!r}")
            return

        if parse.status != "ok" or parse.data is None:
            self.services.order_service.save_parse_error(
                raw_text=raw_text,
                error_message=parse.error_message or "parse error",
            )
            text = format_order_parse_failure(
                subject=msg.subject,
                from_email=msg.from_email,
                error_message=parse.error_message or "parse error",
                raw_text=msg.body_text,
            )
            await bot.send_message(chat_id=chat_id, text=text)
            return

        created = self.services.order_service.create_draft_from_parsed(parsed=parse.data, raw_text=raw_text)
        text = format_order_approval(
            order_payload=created,
            parsed=parse.data,
            source_subject=msg.subject,
            source_from=msg.from_email,
        )
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=order_actions_keyboard(int(created["order"]["id"])),
        )

    @staticmethod
    def _compose_raw_text(msg: InboxMessage) -> str:
        header = [
            f"From: {msg.from_email}",
            f"Subject: {msg.subject}",
        ]
        if msg.message_id:
            header.append(f"Message-ID: {msg.message_id}")
        return "\n".join(header) + "\n\n" + msg.body_text
