import aiohttp
import requests
import logging
import time
from io import BytesIO
from PIL import Image
from aiogram import Router, types, Bot
from aiogram.types import Message, BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.fsm.state import State, StatesGroup
from services.database import connect_db, update_recommendations
from services.game_api import fetch_game_details

router = Router()

class ShowingGame(StatesGroup):
    waiting_for_rating = State()


async def process_game_image(cover_url: str):
    """Обработка изображений (обложек игр) с автоповтором при ошибках"""
    if not cover_url:
        return None

    max_retries = 3
    delay_between_retries = 2

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(cover_url, timeout=10)
            if response.status_code == 200:
                image_data = response.content
                file_size = len(image_data)

                if file_size > 5 * 1024 * 1024:
                    img = Image.open(BytesIO(image_data))
                    img_format = img.format if img.format else "JPEG"

                    output_buffer = BytesIO()
                    img.thumbnail((1280, 720))
                    img.save(output_buffer, format=img_format, quality=85)
                    image_data = output_buffer.getvalue()

                return BufferedInputFile(image_data, filename="cover.jpg")

            else:
                print(f"[{attempt}/{max_retries}] Ошибка загрузки изображения: {response.status_code}")
                break  # нет смысла повторять, если ошибка HTTP (например, 404)

        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.ChunkedEncodingError,
                requests.exceptions.RequestException) as e:
            print(f"[{attempt}/{max_retries}] Ошибка при обработке изображения: {e}")
            if attempt < max_retries:
                await asyncio.sleep(delay_between_retries)
            else:
                return None

    return None


async def show_game_message(message: Message, game_id: int, from_recommendations=False):
    """ Отображает карточку игры пользователю (только для игр из поиска и списка рекомендаций) """
    user_id = message.from_user.id

    try:
        conn = connect_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                g.title, 
                TO_CHAR(g.release_date, 'DD.MM.YYYY') AS release_date, 
                COALESCE(string_agg(DISTINCT ge.name, ', '), 'Не указано') AS genre,
                COALESCE(string_agg(DISTINCT pl.name, ', '), 'Не указано') AS platforms,
                g.metascore, 
                g.cover_url
            FROM games g
            LEFT JOIN game_genres gg ON g.id = gg.game_id
            LEFT JOIN genres ge ON gg.genre_id = ge.id
            LEFT JOIN game_platforms gp ON g.id = gp.game_id
            LEFT JOIN platforms pl ON gp.platform_id = pl.id
            WHERE g.id = %s
            GROUP BY g.id;
        """, (game_id,))

        game = cursor.fetchone()
        conn.close()

        if not game:
            logging.warning(f"Игра (ID {game_id}) не найдена в базе")
            await message.answer("❌ Произошла ошибка. Игра не найдена в базе.")
            return

        title, release_date, genre, platforms, rating, cover_url = game
        logging.info(f"Пользователь {user_id} получил карточку игры: {title}")

        details = await fetch_game_details(title)
        if not details:
            logging.error(f"Ошибка загрузки деталей игры: {title}")
            await message.answer("❌ Ошибка загрузки информации.")
            return

        developer = details.get("developer", "Не указано")
        publisher = details.get("publisher", "Не указано")
        slug = details.get("slug")

        text = (f"<b>{title}</b>\n"
                f"🛠 Разработчик: {developer}\n"
                f"🏢 Издатель: {publisher}\n"
                f"📅 Дата релиза: {release_date}\n"
                f"🎮 Жанр: {genre}\n"
                f"🖥 Платформы: {platforms}\n"
                f"⭐ Оценка: {rating if rating else 'Нет'}\n\n"
                "Для более детальной информации нажмите 'Подробнее'.")

        keyboard_buttons = []
        if slug:
            keyboard_buttons.append([types.InlineKeyboardButton(text="Подробнее", url=f"https://rawg.io/games/{slug}")])
        keyboard_buttons.append([types.InlineKeyboardButton(text="Добавить в избранное", callback_data=f"favorite_{game_id}")])
        keyboard_buttons.append([types.InlineKeyboardButton(text="Оценить", callback_data=f"rate_{game_id}")])

        if from_recommendations:
            keyboard_buttons.append([types.InlineKeyboardButton(text="Неинтересно", callback_data=f"not_interested_{game_id}")])

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        image = await process_game_image(cover_url)
        if image:
            await message.answer_photo(photo=image, caption=text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Ошибка в show_game_message у пользователя {user_id}: {e}")
        await message.answer("❌ Ошибка при загрузке информации об игре.")


async def show_game_bot(user_id: int, game_id: int, bot):
    """ Отображает карточку игры пользователю (только для игр из интервальных рекомендаций) """
    try:
        conn = connect_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                g.title, 
                TO_CHAR(g.release_date, 'DD.MM.YYYY') AS release_date, 
                COALESCE(string_agg(DISTINCT ge.name, ', '), 'Не указано') AS genre,
                COALESCE(string_agg(DISTINCT pl.name, ', '), 'Не указано') AS platforms,
                g.metascore, 
                g.cover_url
            FROM games g
            LEFT JOIN game_genres gg ON g.id = gg.game_id
            LEFT JOIN genres ge ON gg.genre_id = ge.id
            LEFT JOIN game_platforms gp ON g.id = gp.game_id
            LEFT JOIN platforms pl ON gp.platform_id = pl.id
            WHERE g.id = %s
            GROUP BY g.id;
        """, (game_id,))

        game = cursor.fetchone()
        conn.close()

        if not game:
            await message.answer("❌ Произошла ошибка. Игра не найдена в базе.")
            return

        title, release_date, genre, platforms, rating, cover_url = game

        details = await fetch_game_details(title)
        if not details:
            await message.answer("❌ Ошибка загрузки информации.")
            return

        developer = details.get("developer", "Не указано")
        publisher = details.get("publisher", "Не указано")
        slug = details.get("slug")

        text = (f"<b>{title}</b>\n"
                f"🛠 Разработчик: {developer}\n"
                f"🏢 Издатель: {publisher}\n"
                f"📅 Дата релиза: {release_date}\n"
                f"🎮 Жанр: {genre}\n"
                f"🖥 Платформы: {platforms}\n"
                f"⭐ Оценка: {rating if rating else 'Нет'}\n\n"
                "Для более детальной информации нажмите 'Подробнее'.")

        keyboard_buttons = []
        if slug:
            keyboard_buttons.append([types.InlineKeyboardButton(text="Подробнее", url=f"https://rawg.io/games/{slug}")])
        keyboard_buttons.append([types.InlineKeyboardButton(text="Добавить в избранное", callback_data=f"favorite_{game_id}")])
        keyboard_buttons.append([types.InlineKeyboardButton(text="Неинтересно", callback_data=f"not_interested_{game_id}")])

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

        image = await process_game_image(cover_url)
        if image:
            await bot.send_photo(user_id, photo=image, caption=text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await bot.send_message(user_id, text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Ошибка в show_game_bot у пользователя {user_id}: {e}")
        await bot.send_message(user_id, "❌ Ошибка при загрузке информации об игре.")


@router.callback_query(lambda c: c.data.startswith("favorite_"))
async def add_to_favorites(callback: CallbackQuery, bot: Bot):
    game_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id FROM users WHERE telegram_id = %s
    """, (user_id,))
    user_record = cursor.fetchone()

    real_user_id = user_record[0]

    cursor.execute("""
        SELECT 1 FROM favorite_games 
        WHERE user_id = %s AND game_id = %s
    """, (real_user_id, game_id))
    already_favorited = cursor.fetchone()

    cursor.execute("SELECT title FROM games WHERE id = %s", (game_id,))
    game_record = cursor.fetchone()
    game_title = game_record[0]

    if not already_favorited:
        cursor.execute("""
            INSERT INTO favorite_games (user_id, game_id)
            VALUES (%s, %s)
        """, (real_user_id, game_id))
        conn.commit()
        logging.info(f"Игра {game_title} добавлена в избранное пользователем {user_id}")
        status_text = "✅ Игра добавлена в избранное ✅"
        update_recommendations(user_id)
    else:
        logging.info(f"Пользователь {user_id} пытался повторно добавить игру {game_title} в избранное")
        status_text = "❌ Игра уже есть в избранном ❌"

    conn.close()

    old_keyboard = callback.message.reply_markup
    new_keyboard = []

    for row in old_keyboard.inline_keyboard:
        new_row = []
        for btn in row:
            if btn.callback_data == f"favorite_{game_id}":
                # Заменим текст, деактивируем кнопку
                new_row.append(InlineKeyboardButton(text=status_text, callback_data="noop"))
            else:
                new_row.append(btn)
        new_keyboard.append(new_row)

    await bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=new_keyboard)
    )

    await callback.answer()



@router.callback_query(lambda c: c.data.startswith("rate_"))
async def rate_game(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    game_id = int(callback.data.split("_")[1])

    logging.info(f"Пользователь {user_id} хочет оценить игру (ID {game_id})")

    await state.update_data(game_id=game_id, message_id=callback.message.message_id, original_markup=callback.message.reply_markup.model_dump())


    rating_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=str(i), callback_data=f"set_rating_{i}") for i in range(1, 6)],
        [InlineKeyboardButton(text=str(i), callback_data=f"set_rating_{i}") for i in range(6, 11)],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_rating")]
    ])


    await callback.message.edit_reply_markup(reply_markup=rating_keyboard)
    await callback.answer()
    await state.set_state(ShowingGame.waiting_for_rating)



@router.callback_query(lambda c: c.data.startswith("set_rating_"), StateFilter(ShowingGame.waiting_for_rating))
async def set_rating(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    rating = int(callback.data.split("_")[2])

    user_data = await state.get_data()
    game_id = user_data.get("game_id")
    message_id = user_data.get("message_id")
    original_markup_data = user_data.get("original_markup")

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()

    if user_record:
        real_user_id = user_record[0]

        cursor.execute("SELECT title FROM games WHERE id = %s", (game_id,))
        game_record = cursor.fetchone()
        game_title = game_record[0]

        cursor.execute("""
            INSERT INTO rated_games (user_id, game_id, rating)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, game_id)
            DO UPDATE SET rating = EXCLUDED.rating;
        """, (real_user_id, game_id, rating))

        conn.commit()
        conn.close()

        original_markup = InlineKeyboardMarkup(**original_markup_data)
        updated_buttons = []

        for row in original_markup.inline_keyboard:
            new_row = []
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("rate_"):
                    new_row.append(InlineKeyboardButton(
                        text=f"✅ Ты оценил(-а) игру на {rating}/10 ✅",
                        callback_data=f"rate_{game_id}"
                    ))
                else:
                    new_row.append(btn)
            updated_buttons.append(new_row)

        await bot.edit_message_reply_markup(
            chat_id=callback.message.chat.id,
            message_id=message_id,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=updated_buttons)
        )

        logging.info(f"Пользователь {user_id} оценил игру {game_title} (ID {game_id}) на {rating}/10")
        update_recommendations(user_id)
    else:
        conn.close()
        await callback.answer("Ошибка сохранения оценки.")

    await state.clear()


@router.callback_query(lambda c: c.data == "cancel_rating", StateFilter(ShowingGame.waiting_for_rating))
async def cancel_rating(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user_data = await state.get_data()
    message_id = user_data.get("message_id")
    original_markup_data = user_data.get("original_markup")

    original_markup = InlineKeyboardMarkup(**original_markup_data)
    await bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=message_id,
        reply_markup=original_markup
    )

    logging.info(f"Оценивание отменено")
    await state.clear()


@router.callback_query(lambda c: c.data.startswith("not_interested_"))
async def mark_not_interested(callback: CallbackQuery, bot: Bot):
    """ Добавляет игру в список неинтересных пользователю """
    game_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT 1 FROM not_interested_games WHERE user_id = (SELECT id FROM users WHERE telegram_id = %s) AND game_id = %s",
        (user_id, game_id))
    already_not_interested = cursor.fetchone()

    cursor.execute("SELECT title FROM games WHERE id = %s", (game_id,))
    game_record = cursor.fetchone()
    game_title = game_record[0]

    if not already_not_interested:
        cursor.execute(
            "INSERT INTO not_interested_games (user_id, game_id) VALUES ((SELECT id FROM users WHERE telegram_id = %s), %s)",
            (user_id, game_id))
        conn.commit()
        conn.close()
        logging.info(f"Игра {game_title} добавлена в неинтересные пользователем {user_id}")
        status_text = "✅ Игра больше не будет тебе рекомендоваться ✅"
        update_recommendations(user_id)
    else:
        logging.info(f"Пользователь {user_id} пытался добавить в неинтересные уже ранее добавленную игру: {game_title}")
        status_text = "❌ Игра уже помечена как неинтересная ❌"

    old_keyboard = callback.message.reply_markup
    new_keyboard = []

    for row in old_keyboard.inline_keyboard:
        new_row = []
        for btn in row:
            if btn.callback_data == f"not_interested_{game_id}":
                new_row.append(InlineKeyboardButton(text=status_text, callback_data="noop"))
            else:
                new_row.append(btn)
        new_keyboard.append(new_row)

    await bot.edit_message_reply_markup(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=new_keyboard)
    )

    await callback.answer()



