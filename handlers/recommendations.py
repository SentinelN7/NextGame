import asyncio
import logging
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from services.database import *
from handlers.menu import show_menu
from services.game_api import fetch_game_details
from services import game_card

router = Router()

class RecommendationState(StatesGroup):
    viewing = State()

def generate_recommendation_menu(user_settings):
    text = (
        "⭐ *Добро пожаловать в меню рекомендаций!* ⭐\n\n"
        "Не знаешь, во что поиграть? Мы подберем для тебя лучшие варианты!\n"
        "Настрой выдачу под свои предпочтения или просто нажми кнопку, чтобы получить свежие рекомендации.\n\n"
        "🔧 *Текущие настройки:*\n"
        f"🎛 *Количество игр в запросе:* {user_settings['rec_count']}\n"
        f"🔔 *Частота уведомлений:* {user_settings['notif_freq']}\n"
        f"📩 *Количество игр в уведомлениях:* {user_settings['notif_count']}\n\n"
        "📌 *Что дальше?*\n"
        "🔹 Нажми 🎲 *Получить рекомендации*, чтобы увидеть подборку игр.\n"
        "🔹 Хочешь изменить параметры выдачи? Жми ✏️ *Редактировать параметры рекомендаций*.\n"
        "🔹 Вернуться в главное меню можно с помощью кнопки 🔙 *Вернуться в главное меню*."
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать параметры рекомендаций", callback_data="recommendations_settings")],
        [InlineKeyboardButton(text="🎲 Получить рекомендации", callback_data="get_recommendations")],
        [InlineKeyboardButton(text="🔙 Вернуться в главное меню", callback_data="back_to_menu")],
    ])

    return text, keyboard

@router.message(lambda msg: msg.text == "⭐ Рекомендации")
async def recommendations_menu(message: Message, state: FSMContext):
    """ Открывает меню рекомендаций для пользователя """
    user_id = message.from_user.id
    logging.info(f"Пользователь {user_id} открыл меню рекомендаций")

    update_last_activity(user_id)
    update_user_state(user_id, "Recommendations")
    user_settings = get_user_profile(user_id)

    text, keyboard = generate_recommendation_menu(user_settings)

    temp1 = await message.answer("🔄 Подглядываем в твои рекомендации, секунду...",
                         reply_markup=ReplyKeyboardMarkup(keyboard=[[]], resize_keyboard=True))
    await asyncio.sleep(0.5)
    await temp1.delete()
    temp2 = await message.answer("✅ Готово", reply_markup=ReplyKeyboardRemove())
    await temp2.delete()

    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(lambda msg: msg.text == "🔙 Вернуться в главное меню")
@router.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(event: CallbackQuery | Message, state: FSMContext):
    """ Возврат в главное меню"""
    await state.clear()
    update_user_state(event.from_user.id, "Main Menu")

    if isinstance(event, CallbackQuery):
        await event.message.delete()
        await show_menu(event.message)
    else:
        await show_menu(event)


def get_recommendations_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Получить новые рекомендации")],
            [KeyboardButton(text="📌 Вернуться в меню рекомендаций")],
            [KeyboardButton(text="🔙 Вернуться в главное меню")]
        ],
        resize_keyboard=True
    )

@router.callback_query(lambda c: c.data == "get_recommendations")
@router.message(RecommendationState.viewing, lambda msg: msg.text == "🔄 Получить новые рекомендации")
async def show_recommendations(event: CallbackQuery | Message, state: FSMContext):
    """ Вывод рекомендаций для пользователя """
    user_id = event.from_user.id
    logging.info(f"Пользователь {user_id} запросил рекомендации")

    update_last_activity(user_id)
    user_settings = get_user_profile(user_id)
    rec_count = user_settings.get("rec_count", 3)
    recommended_games = get_recommendations(user_id, rec_count)

    if len(recommended_games) < rec_count:
        logging.info(f"Пользователь {user_id}: рекомендаций меньше {rec_count}, обновляем список")
        update_recommendations(user_id)
        recommended_games = get_recommendations(user_id, rec_count)

    if not recommended_games:
        logging.info(f"Пользователь {user_id} не получил рекомендаций")
        message_text = "😕 Пока нет рекомендаций. Попробуй позже!"
        if isinstance(event, CallbackQuery):
            await event.message.answer(message_text)
        else:
            await event.answer(message_text)
        return

    game_ids = [game[0] for game in recommended_games]

    for game in recommended_games:
        game_id = game[0]
        message = event.message if isinstance(event, CallbackQuery) else event
        await game_card.show_game_message(message, game_id, from_recommendations=True)

    logging.info(f"Пользователь {user_id} получил {len(game_ids)} рекомендаций: {game_ids}")

    add_to_viewed_games(user_id, game_ids)
    remove_from_recommendations(user_id, game_ids)
    await state.set_state(RecommendationState.viewing)

    final_message = "📌 Может ещё?"
    if isinstance(event, CallbackQuery):
        await event.message.answer(final_message, reply_markup=get_recommendations_keyboard())
    else:
        await event.answer(final_message, reply_markup=get_recommendations_keyboard())


@router.message(RecommendationState.viewing, lambda msg: msg.text == "🔄 Получить новые рекомендации")
async def refresh_recommendations(message: Message, state: FSMContext):
    """ Вывод новых рекомендаций """
    await show_recommendations(message, state)


OPTIONS = {
    "rec_count": [(str(i), f"{i} игр(а)") for i in range(1, 6)],
    "notif_count": [(str(i), f"{i} игр(а)") for i in range(1, 6)],
    "notif_freq": [("never", "Отключить"), ("daily", "Ежедневно"), ("3days", "Раз в 3 дня"), ("weekly", "Еженедельно")]
}


def generate_settings_keyboard(user_settings):

    TRANSLATE = {
        "never": "Отключить",
        "daily": "Ежедневно",
        "3days": "Раз в 3 дня",
        "weekly": "Еженедельно"
    }

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🎛 Количество игр: {user_settings['rec_count']}", callback_data="edit_rec_count")],
        [InlineKeyboardButton(
            text=f"🔔 Уведомления: {TRANSLATE.get(user_settings['notif_freq'], user_settings['notif_freq'])}",
            callback_data="edit_notif_freq")],
        [InlineKeyboardButton(text=f"📩 Игры в уведомлениях: {user_settings['notif_count']}",
                              callback_data="edit_notif_count")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_recommendations")]
    ])


@router.callback_query(lambda c: c.data == "recommendations_settings")
async def show_settings_menu(callback: CallbackQuery):
    """ Открывает меню настроек рекомендаций """
    user_id = callback.from_user.id
    logging.info(f"Пользователь {user_id} открыл настройки рекомендаций")

    user_settings = get_user_profile(user_id)
    update_last_activity(user_id)

    await callback.message.edit_text(
        "🔧 *Выбери параметр для изменения:*",
        reply_markup=generate_settings_keyboard(user_settings),
        parse_mode="Markdown"
    )

@router.callback_query(lambda c: c.data.startswith("edit_"))
async def edit_setting(callback: CallbackQuery):
    """ Настройка выбранного параметра """
    user_id = callback.from_user.id
    param = callback.data.replace("edit_", "")

    logging.info(f"Пользователь {user_id} выбрал редактирование параметра: {param}")

    if param not in OPTIONS:
        await callback.answer(f"Ошибка: неизвестный параметр ({param}).", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"set_{param}_{value}")]
        for value, label in OPTIONS[param]
    ] + [[InlineKeyboardButton(text="🔙 Назад", callback_data="recommendations_settings")]])

    await callback.message.edit_text("🔧 *Выбери новое значение:*", reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("set_"))
async def update_setting(callback: CallbackQuery):
    """ Обновляет выбранный параметр настроек рекомендаций """
    user_id = callback.from_user.id
    _, param_value = callback.data.split("_", maxsplit=1)

    param, _, value = param_value.rpartition("_")

    logging.info(f"Пользователь {user_id} изменил параметр {param} на {value}")

    if param in {"rec_count", "notif_count"}:
        try:
            value = int(value)
        except ValueError:
            await callback.answer("Ошибка: введи число.", show_alert=True)
            return

    if param not in OPTIONS:
        await callback.answer("Ошибка: неизвестный параметр.", show_alert=True)
        return

    update_user_settings(user_id, **{param: value})
    await show_settings_menu(callback)


@router.message(lambda msg: msg.text == "📌 Вернуться в меню рекомендаций")
@router.callback_query(lambda c: c.data == "back_to_recommendations")
async def back_to_recommendations(event: CallbackQuery | Message, state: FSMContext):
    """ Возврат в меню реокмендаций """
    await state.clear()
    user_settings = get_user_profile(event.from_user.id)
    text, keyboard = generate_recommendation_menu(user_settings)

    if isinstance(event, CallbackQuery):
        await event.message.answer("Переход в меню рекомендаций", reply_markup=ReplyKeyboardRemove())
        await event.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await event.answer("Переход в меню рекомендаций", reply_markup=ReplyKeyboardRemove())
        await event.answer(text, reply_markup=keyboard, parse_mode="Markdown")



def register_handlers(dp):
    dp.include_router(router)

