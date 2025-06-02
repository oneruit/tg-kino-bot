import sqlite3
import re

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


    def check_and_add_user(self, user_id: int, group_id: int, username: str, custom_name: str = None):
        """Check if a user exists and add them if necessary."""
        user = self.get_user_data(user_id, group_id)
        if not user:
            self.add_user(user_id, group_id, username, custom_name)


    def add_user(self, user_id: int, group_id: int, username: str, custom_name: str = None, notify_watching: int = 0):
        """Add a new user to the database for a specific group, if they don't already exist."""
        query = 'SELECT * FROM users WHERE user_id = ? AND group_id = ?'
        user = self.execute_query(query, (user_id, group_id), fetchone=True)
        if not user:
            query = '''INSERT INTO users (user_id, group_id, username, custom_name, notify_watching)
                    VALUES (?, ?, ?, ?, ?)'''
            self.execute_query(query, (user_id, group_id, username, custom_name, notify_watching))


    def update_notify_watching_status(self, user_id: int, group_id: int, subscribe: bool) -> bool:
        """Update the notify_watching status for a user in a specific group."""
        notify_watching_status = 1 if subscribe else 0
        query = 'UPDATE users SET notify_watching = ? WHERE user_id = ? AND group_id = ?'
        result = self.execute_query(query, (notify_watching_status, user_id, group_id))
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


    def get_all_users_except(self, excluded_user_id: int, group_id: int) -> list:
        """Retrieve all users in a group except the specified user ID."""
        query = "SELECT user_id, custom_name, username FROM users WHERE user_id != ? AND group_id = ?"
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

        return formatted_users  # Возвращаем список отформатированных упоминаний


    def get_all_users_watching(self, excluded_user_id: int, group_id: int) -> list:
        """Retrieve users in a group who are watching (notify_watching == 1), except for the specified user."""
        query = "SELECT custom_name, username, user_id FROM users WHERE notify_watching = 1 AND user_id != ? AND group_id = ?"
        users = self.execute_query(query, (excluded_user_id, group_id), fetchall=True)
        formatted_users = []
        for custom_name, username, user_id in users:
            display_name = custom_name if custom_name else username if username else str(user_id)
            formatted_users.append({
                "display_name": display_name,
                "username": username if username else str(user_id),
                "user_id": user_id
            })
        return formatted_users


    def get_user_data(self, user_id: int, group_id: int):
        """Retrieve data of a user from the database by user_id."""
        query = 'SELECT * FROM users WHERE user_id = ? AND group_id = ?'
        return self.execute_query(query, (user_id, group_id), fetchone=True)


    def set_custom_name(self, user_id, group_id, custom_name):
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
