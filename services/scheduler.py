from datetime import datetime, timedelta
from aiogram.types import Message, Chat, User
from aiogram import Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from services.database import *
from handlers.menu import show_menu
from services import game_card
from services.game_api import fetch_games
from services.game_db import GameDatabase
import logging

db = GameDatabase()

async def check_inactive_users(bot: Bot, dp: Dispatcher):
    """ Проверяет неактивных пользователей и возвращает их в главное меню """
    conn = connect_db()
    cursor = conn.cursor()

    inactive_threshold = datetime.datetime.now() - timedelta(hours=1)
    cursor.execute("""
        SELECT telegram_id FROM users 
        WHERE last_activity < %s AND current_state != 'Main Menu'
    """, (inactive_threshold,))

    inactive_users = cursor.fetchall()
    conn.close()

    for user in inactive_users:
        user_id = user[0]
        logging.info(f"Пользователь {user_id} был неактивен более 60 минут, переводим в главное меню")

        state = dp.fsm.get_context(bot, user_id, user_id)

        await state.clear()

        update_user_state(user_id, "Main Menu")

        await bot.send_message(user_id, "Вы были неактивны более 60 минут. Возвращаем вас в главное меню.")

        fake_message = Message(
            message_id=0,
            date=datetime.datetime.now(),
            chat=Chat(id=user_id, type="private"),
            from_user=User(id=user_id, is_bot=False, first_name="User"),
            text="🏠 Главное меню"
        )

        await show_menu(fake_message, bot)


async def send_scheduled_recommendations(bot):
    """ Отправляет запланированные рекомендации пользователям """
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT telegram_id, last_notification FROM users 
        WHERE notification_frequency != 'never' AND current_state = 'Main Menu'
    """)
    users = cursor.fetchall()

    current_time = datetime.datetime.now()

    for user_id, last_notification in users:
        user_settings = get_user_profile(user_id)
        notif_freq = user_settings.get("notif_freq", 4)
        notif_count = user_settings.get("notif_count", 5)

        if isinstance(last_notification, str):
            last_notification = datetime.strptime(last_notif, "%Y-%m-%d %H:%M:%S")
        elif last_notification is None:
            last_notification = datetime.datetime.min  # Если уведомлений не было, отправим первое сразу

        if notif_freq == "daily":
            delta = timedelta(days=1)
        elif notif_freq == "3days":
            delta = timedelta(days=3)
        elif notif_freq == "weekly":
            delta = timedelta(weeks=1)
        else:
            continue

        if (current_time - last_notification) < delta:
            continue

        logging.info(f"Отправляем интервальные рекомендации пользователю {user_id}")

        recommended_games = get_recommendations(user_id, notif_count)
        if len(recommended_games) < notif_count:
            update_recommendations(user_id)
            recommended_games = get_recommendations(user_id, notif_count)

        game_ids = [game[0] for game in recommended_games]

        for game_id in game_ids:
            await game_card.show_game_bot(user_id, game_id, bot)

        add_to_viewed_games(user_id, game_ids)
        remove_from_recommendations(user_id, game_ids)

        cursor.execute("UPDATE users SET last_notification = %s WHERE telegram_id = %s", (current_time, user_id))
        conn.commit()

    conn.close()

async def clear_viewed_games():
    """ Очищает таблицу просмотренных игр """
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("TRUNCATE TABLE viewed_games")
    conn.commit()
    conn.close()

    logging.info("Таблица viewed_games очищена.")

