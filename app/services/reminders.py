from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.keyboards.common import renew_keyboard
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


async def reminder_loop(
    bot: Bot,
    user_repo: UserRepository,
    interval_seconds: int = 3600,
) -> None:
    while True:
        try:
            await send_expiry_reminders(bot, user_repo)
        except Exception:
            logger.exception("Failed to send expiry reminders")
        await asyncio.sleep(interval_seconds)


async def send_expiry_reminders(bot: Bot, user_repo: UserRepository) -> None:
    now = datetime.utcnow()
    until = now + timedelta(days=3)
    rows = await user_repo.list_expiring_users(now.isoformat(), until.isoformat())
    for telegram_id, expires_at_raw, reminder_3d_sent, reminder_1d_sent in rows:
        try:
            expires_at = datetime.fromisoformat(expires_at_raw)
        except (TypeError, ValueError):
            continue
        days_left = (expires_at.date() - now.date()).days
        if days_left == 3 and not reminder_3d_sent:
            await _send_reminder(bot, telegram_id, 3)
            await user_repo.mark_reminder_sent(telegram_id, 3)
        elif days_left == 1 and not reminder_1d_sent:
            await _send_reminder(bot, telegram_id, 1)
            await user_repo.mark_reminder_sent(telegram_id, 1)


async def _send_reminder(bot: Bot, telegram_id: int, days_left: int) -> None:
    if days_left == 1:
        text = "⏳ До конца подписки остался 1 день.\nПродлить сейчас?"
    else:
        text = f"⏳ До конца подписки осталось {days_left} дня.\nПродлить сейчас?"
    try:
        await bot.send_message(telegram_id, text, reply_markup=renew_keyboard())
    except (TelegramForbiddenError, TelegramBadRequest):
        logger.info("Reminder skipped: telegram_id=%s", telegram_id)
