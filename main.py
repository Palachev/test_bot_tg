from __future__ import annotations

from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

import logging
import asyncio
from contextlib import suppress

from aiogram import Bot, Dispatcher

from app.config import Settings
from app.db import Database
from app.handlers import admin, help, install, purchase, renew, start, status, trial
from app.repositories.payment_repository import PaymentRepository
from app.repositories.referral_repository import ReferralRepository
from app.repositories.user_repository import UserRepository
from app.services.context import DependencyMiddleware
from app.services.marzban import MarzbanService
from app.services.payments import PaymentService
from app.services.payment_retry import payment_retry_loop
from app.services.referral import ReferralService
from app.services.reminders import reminder_loop
from app.services.subscription import SubscriptionService

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    settings = Settings()
    db = Database(settings.database_path)
    await db.connect()

    user_repo = UserRepository(db)
    payment_repo = PaymentRepository(db)
    referral_repo = ReferralRepository(db)

    bot = Bot(
        token=settings.telegram_token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )

    async def notify_admins(message: str) -> None:
        for admin_id in settings.telegram_admin_ids:
            await bot.send_message(admin_id, message)

    marzban = MarzbanService(
        settings.marzban_base_url,
        settings.marzban_api_key,
        notify_admin=notify_admins,
    )
    payment_service = PaymentService(settings, payment_repo)
    referral_service = ReferralService(settings, referral_repo, user_repo)
    subscription_service = SubscriptionService(settings, user_repo, payment_repo, marzban)
    dp = Dispatcher(storage=MemoryStorage())

    bot_info = await bot.get_me()
    dp.message.middleware(DependencyMiddleware(
        payment_service=payment_service,
        subscription_service=subscription_service,
        referral_service=referral_service,
        user_repo=user_repo,
        payment_repo=payment_repo,
        settings=settings,
        bot_username=bot_info.username,
    ))
    dp.callback_query.middleware(DependencyMiddleware(
        payment_service=payment_service,
        subscription_service=subscription_service,
        referral_service=referral_service,
        user_repo=user_repo,
        payment_repo=payment_repo,
        settings=settings,
        bot_username=bot_info.username,
    ))

    dp.include_router(start.router)
    dp.include_router(purchase.router)
    dp.include_router(install.router)
    dp.include_router(status.router)
    dp.include_router(renew.router)
    dp.include_router(trial.router)
    dp.include_router(help.router)
    dp.include_router(admin.router)

    reminder_task = asyncio.create_task(reminder_loop(bot, user_repo))
    retry_task = asyncio.create_task(
        payment_retry_loop(bot, settings, payment_repo, subscription_service)
    )
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        reminder_task.cancel()
        retry_task.cancel()
        with suppress(asyncio.CancelledError):
            await reminder_task
        with suppress(asyncio.CancelledError):
            await retry_task
        await marzban.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
