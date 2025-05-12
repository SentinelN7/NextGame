import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.filters import Command
from config import TOKEN
from handlers import start, profile, search, favorites, rated_games, not_interested, recommendations, menu
from handlers.menu import show_menu
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from services.database import user_exists
from services.scheduler import check_inactive_users, send_scheduled_recommendations, clear_viewed_games
from services.game_api import update_games

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Формат логов
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

# Логирование в файл
file_handler = logging.FileHandler("bot_log.log", encoding="utf-8")
file_handler.setFormatter(formatter)

# Логирование в консоль
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# Добавляем обработчики
logger.addHandler(file_handler)
logger.addHandler(console_handler)

async def reset_state(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if not user_exists(user_id):
        await message.answer("❌ Сброс недоступен до завершения анкеты. В случае ошибки удали диалог и начни заново")
        return

    await state.clear()
    logging.info(f"Пользователь {user_id} сбросил состояние через команду reset")
    await message.answer("🔄 *Состояние сброшено. Возвращаем тебя в главное меню...*", parse_mode="Markdown")
    await menu.show_menu(message)

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()

    start.register_handlers(dp)
    profile.register_handlers(dp)
    search.register_handlers(dp)
    favorites.register_handlers(dp)
    rated_games.register_handlers(dp)
    not_interested.register_handlers(dp)
    recommendations.register_handlers(dp)
    menu.register_handlers(dp)

    # Регистрация команды /reset
    dp.message.register(reset_state, Command("reset"))

    scheduler = AsyncIOScheduler()
    scheduler.start()
    scheduler.add_job(check_inactive_users, "interval", minutes=10, args=[bot, dp])
    scheduler.add_job(send_scheduled_recommendations, "interval", hours=1, kwargs={"bot": bot})
    scheduler.add_job(update_games, "cron", day_of_week="mon", hour=1, minute=15)
    scheduler.add_job(clear_viewed_games, "interval", days=3)


    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
