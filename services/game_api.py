import aiohttp
import asyncio
import logging
from config import RAWG_API_KEY
from datetime import datetime, timedelta
from services.database import connect_db
from services.game_db import GameDatabase

# Словарь платформ (RAWG API → наша БД)
PLATFORMS = {
    "PC": 4,
    "PS5": 187,
    "PS4": 18,
    "PS3": 16,
    "Nintendo Switch": 7,
    "XBOX 360": 14,
    "XBOX ONE": 1,
    "XBOX SERIES X/S": 186
}

BASE_URL = "https://api.rawg.io/api/games"

async def fetch_games(session, platform_id,  date_from, date_to):
    """Получает список игр с API RAWG."""
    params = {
        "key": RAWG_API_KEY,
        "platforms": platform_id,
        "dates": f"{date_from},{date_to}",
        "page_size": 20
    }

    async with session.get(BASE_URL, params=params) as response:
        if response.status != 200:
            logging.error(f"Ошибка запроса: {response.status}")
            return None
        return await response.json()

async def update_games():
    """Обновляет базу данных новыми играми за прошедшую неделю."""
    db = GameDatabase()
    async with aiohttp.ClientSession() as session:
        today = datetime.today().date()
        week_ago = today - timedelta(days=7)

        for platform, platform_id in PLATFORMS.items():
            logging.info(f"Еженедельное обновление базы данных: Загрузка игр для {platform}")

            data = await fetch_games(session, platform_id, week_ago, today)
            if not data or "results" not in data:
                continue

            for game in data["results"]:
                db.insert_game(
                    title=game["name"],
                    release_date=game.get("released"),
                    metascore=game.get("metacritic"),
                    cover_url=game.get("background_image")
                )

                # Привязываем игру к жанрам
                for genre in game.get("genres", []):
                    db.insert_genre(genre["name"])
                    db.link_game_genre(game["name"], genre["name"])

                # Привязываем игру к платформам
                db.insert_platform(platform)
                db.link_game_platform(game["name"], platform)

        logging.info("Удаление неподходящих игр...")
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM games
            WHERE 
                -- Условие 1: Название содержит запрещённые слова
                title ILIKE ANY (ARRAY['%hentai%', '%sex%', '%porn%', '%fuck%', '%incest%', '%futa%', '%milf%', '%lust%','%furry%'])

                OR 

                -- Условие 2: В названии нет ни одной буквы латинского (a-z) или русского (а-я)
                title !~* '[a-zа-я]';
        """)
        conn.commit()
        conn.close()
        logging.info("Удаление завершено.")
    logging.info(f"База данных игр дополнена новинками с {week_ago} по {today}")

async def fetch_game_details(title: str):
    """Ищет игру по названию, получает её ID и загружает подробную информацию."""
    async with aiohttp.ClientSession() as session:
        search_url = f"https://api.rawg.io/api/games?key={RAWG_API_KEY}&search={title}"
        async with session.get(search_url) as search_response:
            if search_response.status != 200:
                logging.error(f"Ошибка при поиске игры: {search_response.status}")
                return None
            search_data = await search_response.json()

            if not search_data.get("results"):
                logging.warning(f"Игра '{title}' не найдена.")
                return None

            game_id = search_data["results"][0]["id"]

        game_url = f"https://api.rawg.io/api/games/{game_id}?key={RAWG_API_KEY}"
        async with session.get(game_url) as response:
            if response.status != 200:
                logging.error(f"Ошибка при получении данных: {response.status}")
                return None
            data = await response.json()

    return {
        "developer": data.get("developers")[0]["name"] if data.get("developers") else "Нет данных",
        "publisher": data.get("publishers")[0]["name"] if data.get("publishers") else "Нет данных",
        "slug": data.get("slug"),
    }

