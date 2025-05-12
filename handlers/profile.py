from aiogram import Router, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardRemove
from services.database import get_user_profile, update_last_activity, update_user_state
from aiogram.fsm.state import State, StatesGroup
from handlers.start import start_command
from handlers.menu import show_menu
from aiogram.fsm.context import FSMContext
import logging

router = Router()

class ProfileState(StatesGroup):
    main_profile_state = State()
    waiting_for_game_number = State()
    waiting_for_rating_change = State()
    waiting_for_new_rating = State()
    waiting_for_not_interested_game_number = State()



@router.message(lambda msg: msg.text == "🎮 Личный кабинет")
@router.callback_query(lambda c: c.data == "back_to_profile")
async def show_profile(event: Message | CallbackQuery, state: FSMContext):
    """ Отображает профиль пользователя """
    user_id = event.from_user.id
    update_last_activity(user_id)
    update_user_state(user_id, "Profile")
    logging.info(f"Пользователь {user_id} открыл личный кабинет")

    user_data = get_user_profile(user_id)
    await state.set_state(ProfileState.main_profile_state)

    if user_data:
        text = (
            "*Личный кабинет* \n\n"
            f"💾 *Имя:* {event.from_user.full_name}\n"
            f"🎮 *Платформа:* {user_data['platform']}\n"
            f"🔥 *Любимый жанр:* {user_data['genre']}\n"
            f"🌟 *Любимые игры:* {user_data['favorite_games']}"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Оцененные игры", callback_data="rated_games")],
            [InlineKeyboardButton(text="❤️ Избранное", callback_data="favorites")],
            [InlineKeyboardButton(text="🚫 Неинтересные игры", callback_data="not_interested")],
            [InlineKeyboardButton(text="✏️ Редактировать анкету", callback_data="edit_survey")],
            [InlineKeyboardButton(text="🔙 Вернуться в главное меню", callback_data="back_to_menu")]
        ])

        if isinstance(event, Message):
            await event.bot.send_message(event.chat.id, "Открываем твой профиль, секунду...",
                                         reply_markup=ReplyKeyboardRemove())
            await event.bot.send_message(event.chat.id, text, reply_markup=keyboard, parse_mode="Markdown")

        elif isinstance(event, CallbackQuery):
            await event.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        logging.warning(f"Пользователь {user_id} пытался открыть профиль, но анкета не заполнена")
        await event.answer("❌ У тебя пока нет данных анкеты, поэтому профиль открыть не получится!")

@router.callback_query(lambda c: c.data == "edit_survey")
async def edit_survey(callback: CallbackQuery, state: FSMContext):
    """ Редактирование анкеты """
    user_id = callback.from_user.id
    update_last_activity(user_id)
    user_info = get_user_profile(user_id)
    logging.info(f"Пользователь {user_id} начал редактирование анкеты")

    if user_info:
        from handlers.start import user_data
        user_data[user_id] = {
            "platform": user_info["platform"],
            "genre": user_info["genre"],
            "games": user_info["favorite_games"]
        }

    await start_command(callback.message, state, edit=True)

@router.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    """ Возврат пользователя в главное меню """
    await state.clear()
    update_user_state(callback.from_user.id, "Main Menu")
    await callback.message.delete()
    await callback.message.answer("Переходим в главное меню")
    await show_menu(callback.message)

def register_handlers(dp):
    dp.include_router(router)
