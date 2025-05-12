from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from services.database import save_survey, get_user_profile, update_recommendations, user_exists, update_user_state
from handlers.menu import show_menu
import logging

router = Router()

user_data = {}

PLATFORMS = ["PlayStation 5", "PlayStation 4", "PlayStation 3", "Xbox Series X/S", "Xbox One", "Xbox 360", "PC", "Nintendo Switch"]
GENRES = ["Action", "RPG", "Shooter", "Strategy", "Simulation", "Arcade", "Fighting", "Adventure", "Puzzle"]

class SurveyStates(StatesGroup):
    choosing_platform = State()
    choosing_genre = State()
    entering_favorite_games = State()

def generate_survey_keyboard(user_id):
    data = user_data.get(user_id, {"platform": "не выбрано", "genre": "не выбрано", "games": "не указаны"})
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🕹 Платформа: {data['platform']}", callback_data="choose_platform")],
        [InlineKeyboardButton(text=f"🎮 Любимый жанр: {data['genre']}", callback_data="choose_genre")],
        [InlineKeyboardButton(text=f"🏆 Любимые игры: {data['games']}", callback_data="choose_games")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data="finish_survey")]
    ])
    return keyboard

@router.message(Command("start"))
async def start_command(message: Message, state: FSMContext, edit: bool = False):
    """ Обрабатывает команду /start, отправляет анкету или меню """
    user_id = message.from_user.id
    update_user_state(user_id, "Survey")
    logging.info(f"Пользователь {user_id} отправил команду /start или перешел к редактированию анкеты")

    if not edit and user_exists(user_id):
        username = message.from_user.first_name
        await message.answer(f"Мы тебя вспомнили. С возвращением, {username}!")
        await show_menu(message)
        return

    user_data.setdefault(user_id, {"platform": "не выбрано", "genre": "не выбрано", "games": "не указаны"})

    text = ("📋 Анкета\n\n"
            "Поля 'Платформа' и 'Жанр' должны быть обязательно заполнены!")
    reply_markup = generate_survey_keyboard(user_id)

    if edit:
        await message.edit_text(text, reply_markup=reply_markup)
    else:
        await message.answer(text, reply_markup=reply_markup)

@router.callback_query(lambda c: c.data == "choose_platform")
async def choose_platform(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=platform, callback_data=f"set_platform:{platform}")] for platform in PLATFORMS
    ])
    await callback.message.edit_text("Выберите платформу:", reply_markup=keyboard)
    await state.set_state(SurveyStates.choosing_platform)

@router.callback_query(lambda c: c.data.startswith("set_platform:"))
async def set_platform(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    platform = callback.data.split(":")[1]
    user_data[user_id]["platform"] = platform

    logging.info(f"Пользователь {user_id} выбрал платформу: {platform}")

    await callback.message.edit_text("📋 Анкета", reply_markup=generate_survey_keyboard(callback.from_user.id))
    await state.clear()

@router.callback_query(lambda c: c.data == "choose_genre")
async def choose_genre(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=genre, callback_data=f"set_genre:{genre}")] for genre in GENRES
    ])
    await callback.message.edit_text("Выберите жанр:", reply_markup=keyboard)
    await state.set_state(SurveyStates.choosing_genre)

@router.callback_query(lambda c: c.data.startswith("set_genre:"))
async def set_genre(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    genre = callback.data.split(":")[1]
    user_data[user_id]["genre"] = genre

    logging.info(f"Пользователь {user_id} выбрал жанр: {genre}")

    await callback.message.edit_text("📋 Анкета", reply_markup=generate_survey_keyboard(callback.from_user.id))
    await state.clear()

@router.callback_query(lambda c: c.data == "choose_games")
async def choose_games(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Введите любимые игры через запятую:")
    await state.set_state(SurveyStates.entering_favorite_games)

@router.message(SurveyStates.entering_favorite_games)
async def set_games(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_data[user_id]["games"] = message.text

    logging.info(f"Пользователь {user_id} указал любимые игры: {message.text}")

    await message.answer("📋 Анкета", reply_markup=generate_survey_keyboard(message.from_user.id))
    await state.clear()

@router.callback_query(lambda c: c.data == "finish_survey")
async def finish_survey(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = user_data.get(callback.from_user.id, {})
    if data.get("platform") == "не выбрано":
        await callback.answer("⚠️ Сначала выберите платформу!", show_alert=True)
        return
    if data.get("genre") == "не выбрано":
        await callback.answer("⚠️ Сначала выберите жанр!", show_alert=True)
        return

    save_survey(
        telegram_id=user_id,
        platform=data.get("platform", ""),
        genre=data.get("genre", ""),
        favorite_games=data.get("games", "")
    )

    logging.info(f"Пользователь {user_id} завершил анкету: {data}")
    update_recommendations(user_id)


    text = (f"✅ Анкета заполнена!\n\n"
            f"🕹 Платформа: {data['platform']}\n"
            f"🎮 Любимый жанр: {data['genre']}\n"
            f"🏆 Любимые игры: {data['games']}")
    await callback.message.delete()
    await callback.message.answer(text)

    await show_menu(callback.message)
    update_user_state(user_id, "Main Menu")

def register_handlers(dp):
    dp.include_router(router)
