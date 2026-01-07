from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.keyboards.common import install_connection_keyboard, platform_keyboard
from app.services.subscription import SubscriptionService

router = Router()

PLATFORM_GUIDES = {
    "android": {
        "app": "HApp Proxy",
        "url": "https://happ.pro",
        "steps": [
            "Установи HApp Proxy",
            "Открой приложение и нажми +",
            "Вставь ссылку-подписку из бота",
            "Нажми «Подключиться»",
        ],
    },
    "ios": {
        "app": "HApp Proxy",
        "url": "https://happ.pro",
        "steps": [
            "Установи HApp Proxy",
            "Открой приложение и нажми +",
            "Вставь ссылку-подписку из бота",
            "Нажми «Подключиться»",
        ],
    },
    "windows": {
        "app": "HApp Proxy",
        "url": "https://happ.pro",
        "steps": [
            "Установи HApp Proxy",
            "Открой приложение и нажми +",
            "Вставь ссылку-подписку из бота",
            "Нажми «Подключиться»",
        ],
    },
    "macos": {
        "app": "HApp Proxy",
        "url": "https://happ.pro",
        "steps": [
            "Установи HApp Proxy",
            "Открой приложение и нажми +",
            "Вставь ссылку-подписку из бота",
            "Нажми «Подключиться»",
        ],
    },
}


@router.message(F.text == "🔑 Установить VPN")
async def pick_platform(message: Message) -> None:
    await message.answer("Выбери платформу, пошаговые инструкции ниже:", reply_markup=platform_keyboard())


@router.callback_query(F.data.startswith("install:"))
async def send_guide(callback: CallbackQuery, subscription_service: SubscriptionService) -> None:
    platform = callback.data.split(":", maxsplit=1)[1]
    if platform == "connect_missing":
        await callback.message.answer("Подключение появится после оплаты или активации пробного периода.")
        await callback.answer()
        return
    guide = PLATFORM_GUIDES[platform]
    steps = "\n".join([f"{idx+1}. {step}" for idx, step in enumerate(guide["steps"])])
    user = await subscription_service.get_status(callback.from_user.id)
    text = (
        f"{guide['app']}\n{guide['url']}\n\n"
        "Как подключить:\n"
        f"{steps}\n\n"
        "После оплаты бот пришлёт твою персональную ссылку подписки."
    )
    await callback.message.answer(text, reply_markup=install_connection_keyboard(user.subscription_link if user else None))
    await callback.answer()
