import psycopg2
import datetime
import logging
from config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT
from psycopg2.extras import execute_values


PLATFORM_MAPPING = {
    "PlayStation 5": "PS5",
    "PlayStation 4": "PS4",
    "PlayStation 3": "PS3",
    "Xbox Series X/S": "XBOX SERIES X/S",
    "Xbox One": "XBOX ONE",
    "Xbox 360": "XBOX 360",
    "PC": "PC",
    "Nintendo Switch": "Nintendo Switch"
}


def connect_db():
    """ Подключение к БД"""
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )


def save_survey(telegram_id, platform, genre, favorite_games):
    """ Сохранение результатов анкеты """
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO users (telegram_id, platform, genre, favorite_games)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (telegram_id) DO UPDATE 
        SET platform = EXCLUDED.platform, 
            genre = EXCLUDED.genre, 
            favorite_games = EXCLUDED.favorite_games;
    """, (telegram_id, platform, genre, favorite_games))

    conn.commit()
    conn.close()

def update_user_settings(user_id, **kwargs):
    """ Обновление настроек рекомендаций """
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return False

    real_user_id = user_record[0]

    update_fields = []
    values = []

    allowed_params = {"rec_count": "recommendation_count", "notif_freq": "notification_frequency", "notif_count": "notification_count"}

    for key, value in kwargs.items():
        if key in allowed_params:
            update_fields.append(f"{allowed_params[key]} = %s")
            values.append(value)

    if update_fields:
        query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = %s"
        values.append(real_user_id)
        cursor.execute(query, tuple(values))
        conn.commit()

    conn.close()
    return True



def user_exists(telegram_id):
    """ Проверка на существование в базе (для анкеты) """
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM users WHERE telegram_id = %s LIMIT 1;", (telegram_id,))
    exists = cursor.fetchone() is not None

    conn.close()
    return exists


def get_user_profile(telegram_id):
    """ Получение данных о пользователе """
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT platform, genre, favorite_games, recommendation_count, notification_frequency, notification_count, last_notification
        FROM users
        WHERE telegram_id = %s;
    """, (telegram_id,))

    user_data = cursor.fetchone()
    conn.close()

    if user_data:
        return {
            "platform": user_data[0],
            "genre": user_data[1],
            "favorite_games": user_data[2],
            "rec_count": user_data[3],
            "notif_freq": user_data[4],
            "notif_count": user_data[5],
            "last_notif": user_data[6]
        }
    return None

def get_rated_games(user_id):
    """ Получение списка оцененных игр """
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return []

    real_user_id = user_record[0]

    cursor.execute("""
        SELECT g.id, g.title, r.rating  
        FROM rated_games r
        JOIN games g ON r.game_id = g.id
        WHERE r.user_id = %s
        ORDER BY r.rating DESC;
    """, (real_user_id,))

    games = cursor.fetchall()
    conn.close()

    return games


def update_game_rating(user_id, game_id, new_rating):
    """ Обновление оценки игры """
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return False

    real_user_id = user_record[0]

    cursor.execute("""
        UPDATE rated_games
        SET rating = %s
        WHERE user_id = %s AND game_id = %s;
    """, (new_rating, real_user_id, game_id))

    conn.commit()
    conn.close()
    return True


def remove_game_rating(user_id, game_id):
    """ Удаление оценки игры """
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return False

    real_user_id = user_record[0]

    cursor.execute("""
        DELETE FROM rated_games
        WHERE user_id = %s AND game_id = %s;
    """, (real_user_id, game_id))

    conn.commit()
    conn.close()
    return True

def get_favorite_games(user_id):
    """ Получение списка избранных игр """
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return []

    real_user_id = user_record[0]

    cursor.execute("""
        SELECT g.id, g.title 
        FROM favorite_games f
        JOIN games g ON f.game_id = g.id
        WHERE f.user_id = %s
    """, (real_user_id,))

    games = cursor.fetchall()
    conn.close()

    return games


def remove_favorite_game(user_id, game_id):
    """ Удаление игры из списка избранных """
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return False

    real_user_id = user_record[0]

    cursor.execute("""
        DELETE FROM favorite_games
        WHERE user_id = %s AND game_id = %s
    """, (real_user_id, game_id))

    conn.commit()
    conn.close()
    return True


def get_not_interested_games(user_id):
    """ Получение неинтересных игр """
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        return []

    real_user_id = user_record[0]

    cursor.execute("""
        SELECT g.id, g.title 
        FROM not_interested_games n
        JOIN games g ON n.game_id = g.id
        WHERE n.user_id = %s
    """, (real_user_id,))

    games = cursor.fetchall()
    conn.close()

    return games


def remove_not_interested_game(user_id, game_id):
    """ Удаление игры из списка неинтересных """
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return False

    real_user_id = user_record[0]

    cursor.execute("""
        DELETE FROM not_interested_games
        WHERE user_id = %s AND game_id = %s;
    """, (real_user_id, game_id))

    conn.commit()
    conn.close()
    return True


def get_recommendation_candidates(user_id):
    """ Получение игр для рекомендаций из базы данных """
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, genre, platform FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return []

    real_user_id = user_record[0]
    genre = user_record[1]
    platform = user_record[2]

    genre_list = genre.split(",") if isinstance(genre, str) else genre
    platform_list = platform.split(",") if isinstance(platform, str) else platform

    platform_list = [PLATFORM_MAPPING.get(p.strip(), p.strip()) for p in platform_list]

    query = """
        SELECT g.id 
        FROM games g
        LEFT JOIN rated_games r ON g.id = r.game_id AND r.user_id = %s
        LEFT JOIN favorite_games f ON g.id = f.game_id AND f.user_id = %s
        LEFT JOIN not_interested_games n ON g.id = n.game_id AND n.user_id = %s
        LEFT JOIN recommendations rec ON g.id = rec.game_id AND rec.user_id = %s
        LEFT JOIN viewed_games v ON g.id = v.game_id AND v.user_id = %s
        LEFT JOIN game_genres gg ON g.id = gg.game_id
        LEFT JOIN genres gen ON gg.genre_id = gen.id
        LEFT JOIN game_platforms gp ON g.id = gp.game_id
        LEFT JOIN platforms p ON gp.platform_id = p.id
        WHERE r.game_id IS NULL  
        AND f.game_id IS NULL    
        AND n.game_id IS NULL    
        AND rec.game_id IS NULL
        AND v.game_id IS NULL  
    """
    params = [real_user_id, real_user_id, real_user_id, real_user_id, real_user_id]

    if genre_list:
        query += " AND gen.name = ANY(%s)"
        params.append(genre_list)

    if platform_list:
        query += " AND p.name = ANY(%s)"
        params.append(platform_list)

    query += " ORDER BY RANDOM() LIMIT 20;"

    cursor.execute(query, params)
    game_ids = [row[0] for row in cursor.fetchall()]

    if game_ids:
        add_recommendations(user_id, game_ids)

    conn.close()
    return game_ids

def add_recommendations(user_id, game_ids):
    """ Добавление игр в пул рекомендаций пользователя """
    if not game_ids:
        return

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return

    real_user_id = user_record[0]

    query = """
        INSERT INTO recommendations (user_id, game_id)
        VALUES %s
        ON CONFLICT (user_id, game_id) DO NOTHING;
    """
    values = [(real_user_id, game_id) for game_id in game_ids]

    logging.info(f"Добавление {len(game_ids)} игр в рекомендации для пользователя {user_id}")

    execute_values(cursor, query, values)

    conn.commit()
    conn.close()

def update_recommendations(user_id):
    """ Обновление пула рекомендаций пользователя """
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return

    real_user_id = user_record[0]

    cursor.execute("DELETE FROM recommendations WHERE user_id = %s", (real_user_id,))
    conn.commit()

    new_game_ids = get_recommendation_candidates(user_id)

    if new_game_ids:
        add_recommendations(user_id, new_game_ids)

    conn.close()


def get_recommendations(user_id, count):
    """ Получение части игр из пула рекомендаций для показа """

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return []

    real_user_id = user_record[0]

    cursor.execute("""
        SELECT
            g.id, 
            g.title, 
            TO_CHAR(g.release_date, 'DD.MM.YYYY') AS release_date, 
            COALESCE(string_agg(DISTINCT ge.name, ', '), 'Не указано') AS genre,
            COALESCE(string_agg(DISTINCT pl.name, ', '), 'Не указано') AS platforms,
            g.metascore, 
            g.cover_url
        FROM recommendations r
        JOIN games g ON r.game_id = g.id
        LEFT JOIN game_genres gg ON g.id = gg.game_id
        LEFT JOIN genres ge ON gg.genre_id = ge.id
        LEFT JOIN game_platforms gp ON g.id = gp.game_id
        LEFT JOIN platforms pl ON gp.platform_id = pl.id
        WHERE r.user_id = %s
        GROUP BY g.id
        LIMIT %s
    """, (real_user_id, count))

    games = cursor.fetchall()
    conn.close()

    logging.info(f"Пользователь {user_id} получил {len(games)} рекомендаций")
    return games


def add_to_viewed_games(user_id, game_ids):
    """ Добавление игр в список просмотренных """
    if not game_ids:
        return

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return

    real_user_id = user_record[0]
    now = datetime.datetime.now()

    query = """
        INSERT INTO viewed_games (user_id, game_id, viewed_at)
        VALUES %s
        ON CONFLICT (user_id, game_id) DO NOTHING;
    """

    from psycopg2.extras import execute_values
    values = [(real_user_id, game_id, now) for game_id in game_ids]
    execute_values(cursor, query, values)

    conn.commit()
    conn.close()

def remove_from_recommendations(user_id, game_ids):
    """ Удаление игр из пула рекомендаций """
    if not game_ids:
        return

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (user_id,))
    user_record = cursor.fetchone()
    if not user_record:
        conn.close()
        return

    real_user_id = user_record[0]

    query = """
        DELETE FROM recommendations
        WHERE user_id = %s AND game_id = ANY(%s);
    """
    cursor.execute(query, (real_user_id, game_ids))

    conn.commit()
    conn.close()

def update_last_activity(user_id):
    """ Обновление активности пользователя """
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_activity = NOW() WHERE telegram_id = %s", (user_id,))
    conn.commit()
    conn.close()


def update_user_state(user_id, state: str):
    """ Обновление текущего статуса пользователя """
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET current_state = %s WHERE telegram_id = %s", (state, user_id))
    conn.commit()
    conn.close()
