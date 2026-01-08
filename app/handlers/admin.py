from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.types.input_file import FSInputFile
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.config import Settings
from app.keyboards.admin import admin_broadcast_keyboard, admin_panel_keyboard
from app.repositories.payment_repository import PaymentRepository
from app.repositories.user_repository import UserRepository
from app.services.subscription import SubscriptionService

router = Router()


class BroadcastState(StatesGroup):
    waiting_message = State()


def _is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.telegram_admin_ids


async def _render_stats(user_repo: UserRepository, payment_repo: PaymentRepository) -> str:
    total_users = await user_repo.count_users()
    active_users = await user_repo.count_active_subscriptions(datetime.utcnow().isoformat())
    paid_count = await payment_repo.count_paid_invoices()
    paid_total = await payment_repo.sum_paid_amount()
    return (
        "Админ-панель\n\n"
        f"Пользователей всего: {total_users}\n"
        f"Активных подписок: {active_users}\n"
        f"Оплат успешно: {paid_count}\n"
        f"Выручка (в валюте): {paid_total:.2f}"
    )


def _build_export_text(title: str, rows: list[tuple[int, str]]) -> str:
    lines = [title, ""]
    if not rows:
        return f"{title}\n\nНет данных."
    for idx, (telegram_id, created_at) in enumerate(rows, start=1):
        lines.append(f"{idx}. {telegram_id} ({created_at})")
    return "\n".join(lines)


async def _send_export_file(message: Message, title: str, rows: list[tuple[int, str]]) -> None:
    text = _build_export_text(title, rows)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".txt") as tmp_file:
        tmp_file.write(text)
        tmp_path = Path(tmp_file.name)
    try:
        await message.answer_document(FSInputFile(tmp_path), caption=title)
    finally:
        tmp_path.unlink(missing_ok=True)


@router.message(Command("admin"))
async def admin_panel(
    message: Message,
    settings: Settings,
    user_repo: UserRepository,
    payment_repo: PaymentRepository,
) -> None:
    if not _is_admin(message.from_user.id, settings):
        await message.answer("Доступ запрещён.")
        return
    text = await _render_stats(user_repo, payment_repo)
    await message.answer(text, reply_markup=admin_panel_keyboard())


@router.message(Command("retry_pending"))
async def retry_pending(
    message: Message,
    settings: Settings,
    payment_repo: PaymentRepository,
    subscription_service: SubscriptionService,
) -> None:
    if not _is_admin(message.from_user.id, settings):
        await message.answer("Доступ запрещён.")
        return
    if hasattr(payment_repo, "list_recoverable"):
        pending = await payment_repo.list_recoverable()
    else:
        pending = []
        for invoice_id in await payment_repo.list_pending_invoices():
            invoice = await payment_repo.get_invoice(invoice_id)
            if invoice:
                pending.append(invoice)
    if not pending:
        await message.answer("Нет платежей для повторной выдачи.")
        return
    success = 0
    failed = 0
    for invoice in pending:
        try:
            user = await subscription_service.process_payment_success(invoice.invoice_id)
            if user:
                success += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    await message.answer(
        "Повторная выдача завершена.\n"
        f"Успешно: {success}\n"
        f"Ошибок: {failed}"
    )


@router.callback_query(F.data.in_(["admin:stats", "admin:refresh"]))
async def admin_refresh(
    callback: CallbackQuery,
    settings: Settings,
    user_repo: UserRepository,
    payment_repo: PaymentRepository,
) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    text = await _render_stats(user_repo, payment_repo)
    try:
        await callback.message.edit_text(text, reply_markup=admin_panel_keyboard())
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
    await callback.answer()


@router.callback_query(F.data.startswith("admin:broadcast:"))
async def admin_broadcast_start(
    callback: CallbackQuery,
    settings: Settings,
    state: FSMContext,
) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    target = callback.data.split(":", maxsplit=2)[2]
    await state.update_data(broadcast_target=target)
    await state.set_state(BroadcastState.waiting_message)
    target_label = {
        "all": "всем пользователям",
        "active": "пользователям с активной подпиской",
        "inactive": "пользователям без активной подписки",
    }.get(target, "всем пользователям")
    await callback.message.edit_text(
        f"Отправьте сообщение для рассылки {target_label}. Можно отправить текст, фото или файл.",
        reply_markup=admin_broadcast_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:cancel_broadcast")
async def admin_broadcast_cancel(
    callback: CallbackQuery,
    settings: Settings,
    user_repo: UserRepository,
    payment_repo: PaymentRepository,
    state: FSMContext,
) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    text = await _render_stats(user_repo, payment_repo)
    await callback.message.edit_text(f"Рассылка отменена.\n\n{text}", reply_markup=admin_panel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin:back")
async def admin_back_to_panel(
    callback: CallbackQuery,
    settings: Settings,
    user_repo: UserRepository,
    payment_repo: PaymentRepository,
    state: FSMContext,
) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await state.clear()
    text = await _render_stats(user_repo, payment_repo)
    await callback.message.edit_text(text, reply_markup=admin_panel_keyboard())
    await callback.answer()


@router.message(BroadcastState.waiting_message)
async def admin_broadcast_send(
    message: Message,
    settings: Settings,
    state: FSMContext,
    user_repo: UserRepository,
) -> None:
    if not _is_admin(message.from_user.id, settings):
        await message.answer("Доступ запрещён.")
        return
    data = await state.get_data()
    target = data.get("broadcast_target", "all")
    now_iso = datetime.utcnow().isoformat()
    if target == "active":
        user_ids = await user_repo.list_active_subscription_ids(now_iso)
    elif target == "inactive":
        user_ids = await user_repo.list_inactive_subscription_ids(now_iso)
    else:
        user_ids = await user_repo.list_telegram_ids()
    success = 0
    failed = 0
    for user_id in user_ids:
        try:
            await message.copy_to(user_id)
            success += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            failed += 1
    await state.clear()
    await message.answer(
        "Рассылка завершена.\n"
        f"Получателей: {len(user_ids)}\n"
        f"Доставлено: {success}\n"
        f"Ошибок: {failed}",
        reply_markup=admin_panel_keyboard(),
    )


@router.callback_query(F.data == "admin:export:paid")
async def admin_export_paid(
    callback: CallbackQuery,
    settings: Settings,
    user_repo: UserRepository,
) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    rows = await user_repo.list_paid_users()
    await _send_export_file(callback.message, "Купили VPN", rows)
    await callback.answer()


@router.callback_query(F.data == "admin:export:trial")
async def admin_export_trial(
    callback: CallbackQuery,
    settings: Settings,
    user_repo: UserRepository,
) -> None:
    if not _is_admin(callback.from_user.id, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    rows = await user_repo.list_trial_only_users()
    await _send_export_file(callback.message, "Пробный период", rows)
    await callback.answer()
