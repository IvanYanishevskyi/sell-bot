from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher

from order_bot.bootstrap import build_services, build_viber_ingest
from order_bot.bot.handlers import router
from order_bot.bot.review_state import ReviewStateStore
from order_bot.config import load_config


async def run_bot() -> None:
    config = load_config()
    services = build_services(config)
    viber_ingest = build_viber_ingest(config, services)
    review_state = ReviewStateStore()

    bot = Bot(token=config.telegram_bot_token)
    dp = Dispatcher()
    dp.include_router(router)
    dp["services"] = services
    dp["review_state"] = review_state

    if viber_ingest is not None:
        await viber_ingest.start(bot)

    try:
        await dp.start_polling(bot)
    finally:
        if viber_ingest is not None:
            await viber_ingest.stop()


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
