from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📈 Статистика", callback_data="admin:stats")],
            [InlineKeyboardButton(text="📣 Рассылка всем", callback_data="admin:broadcast:all")],
            [InlineKeyboardButton(text="✅ Рассылка активным", callback_data="admin:broadcast:active")],
            [InlineKeyboardButton(text="🚫 Рассылка без подписки", callback_data="admin:broadcast:inactive")],
            [InlineKeyboardButton(text="📄 Купившие VPN (txt)", callback_data="admin:export:paid")],
            [InlineKeyboardButton(text="🧪 Пробный период (txt)", callback_data="admin:export:trial")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin:refresh")],
        ]
    )


def admin_broadcast_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В админ-панель", callback_data="admin:back")],
            [InlineKeyboardButton(text="✖️ Отмена рассылки", callback_data="admin:cancel_broadcast")],
        ]
    )
