import logging
import os
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO,  # Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(levelname)s - %(message)s",  # Формат сообщений
    handlers=[
        logging.FileHandler("app.log"),  # Запись в файл
        logging.StreamHandler()          # Вывод в консоль
    ]
)


load_dotenv()

KINOPOISK_API_TOKEN = os.getenv("KINOPOISK_API_TOKEN")
TENOR_API_KEY = os.getenv("TENOR_API_KEY")
BOT_USERNAME = os.getenv("BOT_USERNAME")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_USER_ID = [ids.strip() for ids in os.getenv("ADMIN_USER_ID", "").split(",")] if os.getenv("ADMIN_USER_ID") else []