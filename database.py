import sqlite3
import re

VALID_MEDIA_TYPES = {
    "tv-series": "Сериал",
    "anime": "Аниме",
    "movie": "Фильм",
    "animated-series": "Анимация",
    "cartoon": "Мультфильм"
}

VALID_GENRES = {
    "аниме", "боевик", "вестерн", "военный", "детектив", "детский", "для взрослых",
    "документальный", "драма", "игра", "история", "комедия", "концерт",
    "короткометражка", "криминал", "мелодрама", "музыка", "мультфильм", "мюзикл",
    "новости", "приключения", "реальное тв", "семейный", "спорт", "ток-шоу",
    "триллер", "ужасы", "фантастика", "фильм-нуар", "фэнтези", "церемония"
}

VALID_COUNTRIES = {
    "Австралия", "Австрия", "Азербайджан", "Албания", "Алжир", "Ангола", "Андорра",
    "Антигуа и Барбуда", "Аргентина", "Армения", "Афганистан", "Багамы", "Бангладеш",
    "Барбадос", "Бахрейн", "Белиз", "Белоруссия", "Бельгия", "Бенин", "Болгария",
    "Боливия", "Босния и Герцеговина", "Ботсвана", "Бразилия", "Бруней", "Буркина-Фасо",
    "Бурунди", "Вануату", "Ватикан", "Великобритания", "Венгрия", "Венесуэла", "Восточный Тимор",
    "Вьетнам", "Габон", "Гаити", "Гайана", "Гамбия", "Гана", "Гватемала", "Гвинея",
    "Гвинея-Бисау", "Германия", "Гондурас", "Гренада", "Греция", "Грузия", "Дания",
    "Джибути", "Доминика", "Доминиканская Республика", "Египет", "Замбия", "Зимбабве",
    "Израиль", "Индия", "Индонезия", "Иордания", "Ирак", "Иран", "Ирландия", "Исландия",
    "Испания", "Италия", "Йемен", "Кабо-Верде", "Казахстан", "Камбоджа", "Камерун",
    "Канада", "Катар", "Кения", "Кипр", "Киргизия", "Кирибати", "Китай", "Колумбия",
    "Коморы", "Конго", "Коста-Рика", "Кот-д’Ивуар", "Куба", "Кувейт", "Лаос", "Латвия",
    "Лесото", "Либерия", "Ливан", "Ливия", "Литва", "Лихтенштейн", "Люксембург",
    "Маврикий", "Мавритания", "Мадагаскар", "Македония", "Малави", "Малайзия", "Мали",
    "Мальдивы", "Мальта", "Марокко", "Маршалловы Острова", "Мексика", "Микронезия",
    "Мозамбик", "Молдова", "Монако", "Монголия", "Мьянма", "Намибия", "Науру", "Непал",
    "Нигер", "Нигерия", "Нидерланды", "Никарагуа", "Новая Зеландия", "Норвегия", "ОАЭ",
    "Оман", "Пакистан", "Палау", "Панама", "Папуа — Новая Гвинея", "Парагвай", "Перу",
    "Польша", "Португалия", "Россия", "Руанда", "Румыния", "Сальвадор", "Самоа",
    "Сан-Марино", "Саудовская Аравия", "Северная Корея", "Сейшелы", "Сенегал", "Сент-Винсент и Гренадины",
    "Сент-Китс и Невис", "Сент-Люсия", "Сербия", "Сингапур", "Сирия", "Словакия",
    "Словения", "Соломоновы Острова", "Сомали", "Судан", "Суринам", "США", "Сьерра-Леоне",
    "Таджикистан", "Таиланд", "Танзания", "Того", "Тонга", "Тринидад и Тобаго", "Тувалу",
    "Тунис", "Туркмения", "Турция", "Уганда", "Узбекистан", "Украина", "Уругвай",
    "Фиджи", "Филиппины", "Финляндия", "Франция", "Хорватия", "ЦАР", "Чад", "Черногория",
    "Чехия", "Чили", "Швейцария", "Швеция", "Шри-Ланка", "Эквадор", "Экваториальная Гвинея",
    "Эритрея", "Эсватини", "Эстония", "Эфиопия", "ЮАР", "Южная Корея", "Ямайка", "Япония"
}

class Database:
    def __init__(self, db_name='users.db'):
        self.db_name = db_name


    def connect(self):
        """Create a connection to the SQLite database."""
        return sqlite3.connect(self.db_name)


    def create_table(self):
        """Create the users table if it doesn't exist."""
        query = '''CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER,
                        group_id INTEGER,
                        username TEXT,
                        custom_name TEXT,
                        notify_watching INTEGER DEFAULT 0,
                        PRIMARY KEY (user_id, group_id)
                    )'''
        self.execute_query(query)


    def execute_query(self, query, params=(), fetchone=False, fetchall=False):
        """Execute a query and fetch results if needed."""
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                if fetchone:
                    return cursor.fetchone()
                elif fetchall:
                    return cursor.fetchall()
                conn.commit()
            return None  # Default return for non-fetch queries
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return None


    def check_and_add_user(self, user_id: int, group_id: int, username: str, custom_name: str = None, notify_watching: int = 0):
        """Check if a user exists and add them if necessary, retrieving data in one function."""
        query = '''
        INSERT OR IGNORE INTO users (user_id, group_id, username, custom_name, notify_watching)
        VALUES (?, ?, ?, ?, ?)
        '''
        self.execute_query(query, (user_id, group_id, username, custom_name, notify_watching))


    def update_notify_watching_status(self, user_id: int, group_id: int, notify_watching: int) -> bool:
        """Update the notify_watching status for a user in a specific group."""
        query = 'UPDATE users SET notify_watching = ? WHERE user_id = ? AND group_id = ?'
        result = self.execute_query(query, (notify_watching, user_id, group_id))
        return result is None


    def get_user_name(self, user_id: int, group_id: int) -> str:
        """Retrieve all users in a group except the specified user ID."""
        query = "SELECT user_id, custom_name, username FROM users WHERE user_id = ? AND group_id = ?"
        user = self.execute_query(query, (user_id, group_id), fetchone=True)

        if user:
            user_id, custom_name, username = user
            display_name = custom_name if custom_name else (username if username else str(user_id))
            dict_user = {
                "user_id": user_id,
                "display_name": display_name,
                "username": username if username else str(user_id)
            }
        
            emoji_pattern = re.compile("[\U0001F600-\U0001F64F]")
            if emoji_pattern.search(dict_user['display_name']):
                return f"{dict_user['display_name']} [({dict_user['username']})](tg://user?id={dict_user['user_id']})"
            else:
                return f"[{dict_user['display_name']}](tg://user?id={dict_user['user_id']})"
        return str(user_id)


    def get_users(self, excluded_user_id: int, group_id: int, watching_only: bool = False) -> list:
        """Retrieve users in a group except for the specified user, optionally filtering by watching status."""
        query = "SELECT user_id, custom_name, username FROM users WHERE user_id != ? AND group_id = ?"
        
        if watching_only:
            query += " AND notify_watching = 1"
        
        users = self.execute_query(query, (excluded_user_id, group_id), fetchall=True)
        formatted_users = []
        emoji_pattern = re.compile("[\U0001F600-\U0001F64F]")  # Регулярное выражение для проверки эмодзи
        
        for user_id, custom_name, username in users:
            display_name = custom_name if custom_name else (username if username else str(user_id))
            formatted_user = {
                "user_id": user_id,
                "display_name": display_name,
                "username": username if username else str(user_id)
            }

            # Форматируем упоминание пользователя
            if emoji_pattern.search(formatted_user['display_name']):
                mention = f"{formatted_user['display_name']} [({formatted_user['username']})](tg://user?id={formatted_user['user_id']})"
            else:
                mention = f"[{formatted_user['display_name']}](tg://user?id={formatted_user['user_id']})"

            formatted_users.append(mention)

        return formatted_users


    def set_custom_name(self, user_id: int, group_id: int, custom_name: str = None):
        """Set the custom name for a user."""
        query = 'UPDATE users SET custom_name = ? WHERE user_id = ? AND group_id = ?'
        self.execute_query(query, (custom_name, user_id, group_id))


    def remove_custom_name(self, user_id: int, group_id: int):
        """Remove the custom name for a user."""
        query = 'UPDATE users SET custom_name = NULL WHERE user_id = ? AND group_id = ?'
        self.execute_query(query, (user_id, group_id))


    def get_custom_name(self, user_id: int, group_id: int):
        """Retrieve the custom name of a user."""
        query = 'SELECT custom_name FROM users WHERE user_id = ? AND group_id = ?'
        result = self.execute_query(query, (user_id, group_id), fetchone=True)
        return result[0] if result and result[0] else None
