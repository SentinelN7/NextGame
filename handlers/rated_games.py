from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from services.database import get_rated_games, update_game_rating, remove_game_rating, update_last_activity, update_user_state
from handlers.profile import ProfileState, show_profile
import logging

router = Router()

@router.callback_query(lambda c: c.data == "rated_games")
async def show_rated_games(callback: CallbackQuery, state: FSMContext):
    """ Отображает список оцененных игр пользователя """
    user_id = callback.from_user.id
    logging.info(f"Пользователь {user_id} открыл список оцененных игр")

    update_last_activity(user_id)
    update_user_state(user_id, "Rated games")
    rated_games = get_rated_games(user_id)

    if not rated_games:
        text = "❌ *У тебя пока нет оцененных игр*"
    else:
        text = format_rated_games(rated_games)

    keyboard_buttons = []
    if rated_games:
        keyboard_buttons.append([InlineKeyboardButton(text="📝 Удалить/изменить оценку", callback_data="modify_rating")])
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Вернуться в личный кабинет", callback_data="back_to_profile")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    message = await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await state.update_data(last_rated_message=message.message_id)


def format_rated_games(rated_games):
    """ Форматирует список оцененных игр для отображения пользователю """
    sorted_games = sorted(rated_games, key=lambda x: x[1])
    text = "⭐ *Оцененные тобой игры:*\n\n"

    for i, (_, game_name, rating) in enumerate(sorted_games, start=1):
        text += f"{i}. {game_name}: {rating}/10\n"

    return text


@router.callback_query(lambda c: c.data == "modify_rating")
async def ask_game_number(callback: CallbackQuery, state: FSMContext):
    """ Запрашивает у пользователя номер игры для изменения оценки """
    user_id = callback.from_user.id
    logging.info(f"Пользователь {user_id} выбрал изменение оценки игры")

    update_last_activity(user_id)
    await callback.answer()
    await callback.message.answer("Введи номер игры, оценку которой хочешь изменить:")
    await state.set_state(ProfileState.waiting_for_rating_change)


@router.message(ProfileState.waiting_for_rating_change)
async def modify_rating(message: Message, state: FSMContext):
    """ Запрашивает у пользователя новую оценку для выбранной игры """
    user_id = message.from_user.id
    rated_games = get_rated_games(user_id)

    sorted_games = sorted(rated_games, key=lambda x: x[1])

    try:
        game_index = int(message.text) - 1
        if game_index < 0 or game_index >= len(sorted_games):
            logging.warning(f"Пользователь {user_id} ввёл неверный номер игры: {message.text}")
            await message.answer("❌ Неверный номер игры. Попробуй снова.")
            return
    except ValueError:
        logging.warning(f"Пользователь {user_id} ввёл некорректный ввод для изменения оценки: {message.text}")
        await message.answer("❌ Введи число, соответствующее номеру игры.")
        return

    game_id, game_name, _ = sorted_games[game_index]
    logging.info(f"Пользователь {user_id} выбрал игру для изменения оценки: {game_name} (ID {game_id})")

    await state.update_data(selected_game_id=game_id, selected_game_name=game_name)
    await message.answer(f"Введи новую оценку для игры «{game_name}» (от 1 до 10) или 0 для удаления:")
    await state.set_state(ProfileState.waiting_for_new_rating)


@router.message(ProfileState.waiting_for_new_rating)
async def set_new_rating(message: Message, state: FSMContext):
    """ Сохраняет новую оценку игры или удаляет её из списка оцененных """
    user_id = message.from_user.id
    data = await state.get_data()
    game_id = data.get("selected_game_id")
    game_name = data.get("selected_game_name")

    try:
        new_rating = int(message.text)
        if new_rating < 0 or new_rating > 10:
            logging.warning(f"Пользователь {user_id} ввёл некорректную новую оценку: {message.text}")
            await message.answer("❌ Введи число от 1 до 10 или 0 для удаления.")
            return
    except ValueError:
        logging.warning(f"Пользователь {user_id} ввёл некорректный тип новой оценки: {message.text}")
        await message.answer("❌ Введи корректное число.")
        return

    if new_rating == 0:
        remove_game_rating(user_id, game_id)
        action_text = "удалена из списка оцененных игр."
        logging.info(f"Пользователь {user_id} удалил оценку игры: {game_name} (ID {game_id})")
    else:
        update_game_rating(user_id, game_id, new_rating)
        action_text = f"обновлена до {new_rating}/10."
        logging.info(f"Пользователь {user_id} изменил оценку игры {game_name} (ID {game_id}) на {new_rating}/10")

    last_message_id = data.get("last_rated_message")
    if last_message_id:
        try:
            await message.chat.delete_message(last_message_id)
        except Exception:
            logging.warning(f"Не удалось удалить сообщение {last_message_id} у пользователя {user_id}")

    await message.answer(f"✅ *Оценка игры «{game_name}» {action_text}*", parse_mode="Markdown")
    await show_profile(message, state)


def register_handlers(dp):
    dp.include_router(router)
