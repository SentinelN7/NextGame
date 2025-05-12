from aiogram import Router, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.fsm.state import State, StatesGroup
from services.database import connect_db, update_recommendations, update_last_activity, update_user_state
from services.game_api import fetch_game_details
from handlers.menu import show_menu
from services import game_card
import logging

router = Router()

class SearchGame(StatesGroup):
    waiting_for_search_query = State()
    waiting_for_game_selection = State()

search_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔄 Поиск новой игры")],
        [KeyboardButton(text="🔙 Вернуться в главное меню")]
    ],
    resize_keyboard=True
)


@router.message(lambda msg: msg.text == "🔍 Поиск игры")
async def start_search(message: Message, state: FSMContext):
    """ Запускает режим поиска игр """
    update_user_state(message.from_user.id, "Search")
    user_id = message.from_user.id
    logging.info(f"Пользователь {user_id} начал поиск игры")
    intro_text = (
        "🔎 *Ты в режиме поиска игр*\n\n"
        "Здесь ты сможешь найти нужную тебе игру из огромного массива игр, "
        "поставить оценку, почитать информацию или добавить в избранное.\n\n"
        "📌 *Правила:*\n"
        "1️⃣ Название игры можно ввести неполностью, ты сможешь выбрать нужную игру из найденных вариантов.\n"
        "2️⃣ Название должно быть на *английском языке*, за исключением редких случаев.\n"
        "3️⃣ Не используй сокращения, например MK, COD, CS и т.д.\n\n"
        "🔄 Для запуска поиска другой игры после того, как ты нашел искомую, нажми *Поиск новой игры* в меню.\n"
        "❗ В случае ошибок или если ты не нашел нужную тебе игру, обратись к разработчику. Его контакты в описании бота\n"
        "🎮 *Удачи!*"
    )

    await message.answer(intro_text, parse_mode="Markdown", reply_markup=search_keyboard)
    await start_new_search(message, state)

@router.message(lambda msg: msg.text == "🔄 Поиск новой игры")
async def restart_search(message: Message, state: FSMContext):
    """ Обработчик кнопки для поиска новой игры """
    await start_new_search(message, state)

@router.message(lambda msg: msg.text == "🔙 Вернуться в главное меню")
async def exit_search_mode(message: Message, state: FSMContext):
    """ Обработчик кнопки выхода в главное меню """
    await state.clear()
    update_user_state(message.from_user.id, "Main Menu")
    await show_menu(message)

async def start_new_search(message: Message, state: FSMContext):
    """ Начало поиска """
    update_last_activity(message.from_user.id)
    await message.answer("Введи название игры для поиска:")
    await state.set_state(SearchGame.waiting_for_search_query)

@router.message(SearchGame.waiting_for_search_query)
async def process_search(message: Message, state: FSMContext):
    """ Обрабатывает введённый пользователем запрос на поиск игры """
    user_id = message.from_user.id
    search_query = message.text.strip().lower()

    logging.info(f"Пользователь {user_id} ищет игру: {search_query}")

    try:
        conn = connect_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, title FROM games 
            WHERE LOWER(title) LIKE %s 
            LIMIT 50;
        """, (f"%{search_query}%",))

        games = cursor.fetchall()
        conn.close()

        if not games:
            logging.info(f"Пользователь {user_id}: игра '{search_query}' не найдена")
            await message.answer("❌ Игр с таким названием не найдено. Попробуй еще раз.")
            return

        if len(games) == 1:
            game_id, game_title = games[0]
            logging.info(f"Пользователь {user_id} нашёл единственную игру: {game_title} (ID {game_id})")
            await game_card.show_game_message(message, game_id)
            await state.clear()
            return

        response = "Найдено несколько игр. Выбери номер из списка:\n"
        game_options = {}
        for index, (game_id, game_title) in enumerate(games, start=1):
            response += f"{index}. {game_title}\n"
            game_options[str(index)] = game_id

        logging.info(f"Пользователь {user_id} получил список игр на выбор ({len(games)} результатов)")

        await state.update_data(game_options=game_options)
        await message.answer(response + "\nОтправь номер нужной игры.")
        await state.set_state(SearchGame.waiting_for_game_selection)

    except Exception as e:
        logging.error(f"Ошибка при поиске игры у пользователя {user_id}: {e}")
        await message.answer("❌ Произошла ошибка при поиске. Попробуй позже.")

@router.message(SearchGame.waiting_for_game_selection)
async def select_game(message: Message, state: FSMContext):
    """ Обрабатывает выбор игры пользователем """
    user_id = message.from_user.id
    update_last_activity(user_id)

    user_data = await state.get_data()
    game_options = user_data.get("game_options", {})

    if message.text not in game_options:
        logging.warning(f"Пользователь {user_id} ввёл некорректный номер игры: {message.text}")
        await message.answer("Некорректный ввод. Введи номер игры из списка или начни новый поиск.")
        return

    game_id = game_options[message.text]
    logging.info(f"Пользователь {user_id} выбрал игру (ID {game_id})")

    await message.answer("Формирую красоту для тебя, подожди чуток...")
    await game_card.show_game_message(message, game_id)
    await state.clear()


def register_handlers(dp):
    dp.include_router(router)
    dp.include_router(game_card.router)
