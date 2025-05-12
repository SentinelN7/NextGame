from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from services.database import get_favorite_games, remove_favorite_game, update_last_activity, update_user_state
from handlers.profile import ProfileState, show_profile
import logging

router = Router()

@router.callback_query(lambda c: c.data == "favorites")
async def show_favorites(callback: CallbackQuery, state: FSMContext):
    """ Отображает список избранных игр пользователя """
    user_id = callback.from_user.id
    logging.info(f"Пользователь {user_id} открыл список избранных игр")

    update_last_activity(user_id)
    update_user_state(user_id, "Favorite games")
    favorite_games = get_favorite_games(user_id)

    if not favorite_games:
        text = "❌ *У тебя пока нет избранных игр*"
    else:
        text = format_favorite_games(favorite_games)

    keyboard_buttons = []
    if favorite_games:
        keyboard_buttons.append([InlineKeyboardButton(text="🗑 Удалить игру", callback_data="remove_favorite_game")])
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Вернуться в личный кабинет", callback_data="back_to_profile")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    message = await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await state.update_data(last_favorites_message=message.message_id)


def format_favorite_games(favorite_games):
    """ Форматирует список избранных игр для отображения пользователю """
    sorted_games = sorted(favorite_games, key=lambda x: x[1])
    text = "❤️ *Твои избранные игры:*\n\n"

    for i, (_, game_name) in enumerate(sorted_games, start=1):
        text += f"{i}. {game_name}\n"

    return text


@router.callback_query(lambda c: c.data == "remove_favorite_game")
async def ask_game_number(callback: CallbackQuery, state: FSMContext):
    """ Запрашивает у пользователя номер игры для удаления из избранного """
    user_id = callback.from_user.id
    logging.info(f"Пользователь {user_id} выбрал удаление игры из избранного")

    update_last_activity(user_id)
    await callback.answer()
    await callback.message.answer("Введите номер игры, которую хотите удалить:")
    await state.set_state(ProfileState.waiting_for_game_number)


@router.message(ProfileState.waiting_for_game_number)
async def remove_game(message: Message, state: FSMContext):
    """ Удаляет выбранную пользователем игру из избранного """
    user_id = message.from_user.id
    favorite_games = get_favorite_games(user_id)

    sorted_games = sorted(favorite_games, key=lambda x: x[1])

    try:
        game_index = int(message.text) - 1
        if game_index < 0 or game_index >= len(sorted_games):
            logging.warning(f"Пользователь {user_id} ввёл неверный номер игры: {message.text}")
            await message.answer("❌ Неверный номер игры. Попробуй снова.")
            return
    except ValueError:
        logging.warning(f"Пользователь {user_id} ввёл некорректный ввод для удаления: {message.text}")
        await message.answer("❌ Введи число, соответствующее номеру игры.")
        return

    game_id, game_name = sorted_games[game_index]
    remove_favorite_game(user_id, game_id)
    logging.info(f"Пользователь {user_id} удалил игру из избранного: {game_name} (ID {game_id})")

    data = await state.get_data()
    last_message_id = data.get("last_favorites_message")

    if last_message_id:
        try:
            await message.chat.delete_message(last_message_id)
        except Exception:
            logging.warning(f"Не удалось удалить сообщение {last_message_id} у пользователя {user_id}")

    await message.answer(f"✅ *Игра «{game_name}» удалена из избранного.*", parse_mode="Markdown")
    await show_profile(message, state)


def register_handlers(dp):
    dp.include_router(router)
