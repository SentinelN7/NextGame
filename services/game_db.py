import psycopg2
from config import DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT

class GameDatabase:
    def __init__(self):
        """Подключение к базе данных."""
        self.conn = psycopg2.connect(
            dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
            host=DB_HOST, port=DB_PORT
        )
        self.cur = self.conn.cursor()

    def insert_game(self, title, release_date, metascore, cover_url):
        """Добавляет игру в базу."""
        self.cur.execute("""
            INSERT INTO games (title, release_date, metascore, cover_url)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (title) DO NOTHING;
        """, (title, release_date, metascore, cover_url))
        self.conn.commit()

    def insert_genre(self, genre):
        """Добавляет жанр в базу."""
        self.cur.execute("INSERT INTO genres (name) VALUES (%s) ON CONFLICT (name) DO NOTHING;", (genre,))
        self.conn.commit()

    def link_game_genre(self, game_title, genre):
        """Привязывает игру к жанру."""
        self.cur.execute("""
            INSERT INTO game_genres (game_id, genre_id)
            SELECT g.id, gr.id FROM games g, genres gr
            WHERE g.title = %s AND gr.name = %s
            ON CONFLICT DO NOTHING;
        """, (game_title, genre))
        self.conn.commit()

    def insert_platform(self, platform):
        """Добавляет платформу в базу."""
        self.cur.execute("INSERT INTO platforms (name) VALUES (%s) ON CONFLICT (name) DO NOTHING;", (platform,))
        self.conn.commit()

    def link_game_platform(self, game_title, platform):
        """Привязывает игру к платформе."""
        self.cur.execute("""
            INSERT INTO game_platforms (game_id, platform_id)
            SELECT g.id, p.id FROM games g, platforms p
            WHERE g.title = %s AND p.name = %s
            ON CONFLICT DO NOTHING;
        """, (game_title, platform))
        self.conn.commit()


    def close(self):
        """Закрывает соединение с БД."""
        self.cur.close()
        self.conn.close()
