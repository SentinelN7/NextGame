from aiogram import Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from services.database import update_user_state, update_last_activity
import logging

router = Router()

menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔍 Поиск игры")],
        [KeyboardButton(text="🎮 Личный кабинет")],
        [KeyboardButton(text="⭐ Рекомендации")]
    ],
    resize_keyboard=True
)

@router.message(Command("menu"))
async def show_menu(message: Message, bot: Bot | None = None):
    """ Отображает главное меню """
    user_id = message.from_user.id
    logging.info(f"Пользователь {user_id} перешел в главное меню")

    update_last_activity(user_id)
    update_user_state(user_id, "Main Menu")
    text = (
        "📌 *Главное меню*\n\n"
        "🔍 *Поиск игры* — Огромное хранилище игр. Ищешь что-то конкретное во вселенной видеоигр? Тебе сюда.\n\n"
        "🎮 *Личный кабинет* — Твоё досье. Любимые, нелюбимые и оцененные тобой игры лежат здесь.\n\n"
        "⭐ *Рекомендации* — Твой советник. Получи список игр, которые могут тебе понравиться, или настрой бота так, чтобы периодически получать их\n\n"
        "⚠️ *Обрати внимание:* Бот - твой молчаливый союзник, потому что даст тебе то, что ты ищешь, но не поддержит беседу. Пока что..."
    )

    if bot:
        await bot.send_message(message.chat.id, text, reply_markup=menu_keyboard, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=menu_keyboard, parse_mode="Markdown")


@router.message()
async def delete_unwanted_messages(message: Message):
    """ Удаляет все сообщения, не соответствующие командам """
    await message.delete()

def register_handlers(dp):
    dp.include_router(router)
