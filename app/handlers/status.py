from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.keyboards.common import connection_keyboard, main_menu, renew_keyboard
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.subscription import SubscriptionService

router = Router()


@router.message(F.text == "📊 Статус")
async def show_status(
    message: Message,
    subscription_service: SubscriptionService,
    user_repo: UserRepository,
    bot_username: str,
) -> None:
    user, marzban_user = await subscription_service.get_status_details(message.from_user.id)
    trial_used, _, _ = await user_repo.get_user_meta(message.from_user.id)
    if not user or not user.subscription_expires_at:
        text = "Подписка не активна. Оформи доступ за пару минут."
        if not trial_used:
            text = f"{text}\n\nМожно активировать пробный период."
        if bot_username:
            ref_link = f"https://t.me/{bot_username}?start={message.from_user.id}"
            text = f"{text}\n\nПригласи друга: {ref_link}"
        await message.answer(text, reply_markup=renew_keyboard())
        return
    text = _format_status_text(user, marzban_user)
    keyboard = connection_keyboard(user.subscription_link or "")
    if not keyboard:
        await message.answer("ℹ️ Access link is not ready yet.")
        await message.answer(text, reply_markup=renew_keyboard())
        return
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "nav:back")
async def nav_back(callback: CallbackQuery) -> None:
    await callback.message.answer("Выбери действие.", reply_markup=main_menu())
    await callback.answer()


def _format_status_text(user: User, marzban_user: dict[str, object] | None) -> str:
    expires_at = user.subscription_expires_at
    traffic_limit_gb = user.traffic_limit_gb
    is_stale = user.is_stale
    status_value = marzban_user.get("status") if marzban_user else None
    if not isinstance(status_value, str) or not status_value:
        status_value = "active" if not is_stale else "unknown"
    status_label = "активна" if status_value == "active" else status_value

    expires_text = "—"
    if expires_at:
        expires_text = expires_at.strftime("%d.%m.%Y")

    traffic_limit_gb = traffic_limit_gb or 0
    traffic_used_bytes = 0
    if marzban_user:
        used_value = marzban_user.get("used_traffic") or marzban_user.get("used")
        if isinstance(used_value, (int, float)):
            traffic_used_bytes = int(used_value)

    traffic_used_gb = traffic_used_bytes / (1024**3) if traffic_used_bytes else 0
    traffic_left_gb = max(traffic_limit_gb - traffic_used_gb, 0)

    traffic_line = f"{traffic_used_gb:.2f} / {traffic_limit_gb:.0f} GB"
    if traffic_limit_gb <= 0:
        traffic_line = f"{traffic_used_gb:.2f} GB"
        traffic_left_gb = 0

    extras: list[str] = []
    if traffic_limit_gb > 0:
        extras.append(f"Остаток: {traffic_left_gb:.2f} GB")
    if is_stale:
        extras.append("Данные обновятся при следующей синхронизации.")

    extras_text = ""
    if extras:
        extras_text = "\n" + "\n".join(extras)

    return (
        "🛡 Статус доступа\n"
        "━━━━━━━━━━━━\n"
        f"Статус: {status_label}\n"
        f"Трафик: {traffic_line}\n"
        f"Действует до: {expires_text}{extras_text}"
    )
