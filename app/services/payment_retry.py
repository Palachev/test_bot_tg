from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging

from aiogram import Bot

from app.config import Settings
from app.repositories.payment_repository import PaymentRepository
from app.services.subscription import SubscriptionService

logger = logging.getLogger(__name__)


def _backoff_delay_seconds(attempts: int, base_delay: int, max_delay: int) -> int:
    delay = base_delay * (2**max(attempts - 1, 0))
    return min(delay, max_delay)


async def payment_retry_loop(
    bot: Bot,
    settings: Settings,
    payment_repo: PaymentRepository,
    subscription_service: SubscriptionService,
    interval_seconds: int = 45,
    max_attempts: int = 5,
    base_delay: int = 30,
    max_delay: int = 900,
) -> None:
    while True:
        try:
            await _retry_pending(
                bot=bot,
                settings=settings,
                payment_repo=payment_repo,
                subscription_service=subscription_service,
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
            )
        except Exception:
            logger.exception("Payment retry loop failed")
        await asyncio.sleep(interval_seconds)


async def _retry_pending(
    bot: Bot,
    settings: Settings,
    payment_repo: PaymentRepository,
    subscription_service: SubscriptionService,
    max_attempts: int,
    base_delay: int,
    max_delay: int,
) -> None:
    now = datetime.utcnow()
    invoices = await payment_repo.list_paid_pending()
    for invoice in invoices:
        if invoice.attempts >= max_attempts:
            await payment_repo.mark_failed(
                invoice.invoice_id,
                invoice.last_error or "Max retry attempts exceeded",
            )
            for admin_id in settings.telegram_admin_ids:
                await bot.send_message(
                    admin_id,
                    "❗️Платеж помечен как failed после максимума попыток.\n"
                    f"Invoice: {invoice.invoice_id}",
                )
            continue
        if invoice.updated_at:
            delay = _backoff_delay_seconds(invoice.attempts + 1, base_delay, max_delay)
            if now - invoice.updated_at < timedelta(seconds=delay):
                continue
        try:
            user = await subscription_service.process_payment_success(invoice.invoice_id)
            if user:
                continue
            await payment_repo.mark_failed(
                invoice.invoice_id,
                "Invoice not found during retry",
            )
            for admin_id in settings.telegram_admin_ids:
                await bot.send_message(
                    admin_id,
                    "⚠️ Retry failed: invoice not found.\n"
                    f"Invoice: {invoice.invoice_id}",
                )
        except Exception as exc:
            logger.exception("Retry provisioning failed: invoice_id=%s", invoice.invoice_id)
            await payment_repo.mark_paid_pending(invoice.invoice_id, str(exc))
