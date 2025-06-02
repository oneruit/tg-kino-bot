import asyncio
import datetime
import random
import os
import re
import logging

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiohttp import TCPConnector, ClientSession
from dotenv import load_dotenv

from database import Database  # Импортируем условия для БД
from valid_variables import *

logging.basicConfig(
    level=logging.INFO,  # Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(levelname)s - %(message)s",  # Формат сообщений
    handlers=[
        logging.FileHandler("app.log"),  # Запись в файл
        logging.StreamHandler()          # Вывод в консоль
    ]
)

# Загружаем папку .env для хранения ключей
load_dotenv()
KINOPOISK_API_TOKEN = os.getenv("KINOPOISK_API_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TENOR_API_KEY = os.getenv("TENOR_API_KEY")
BOT_USERNAME = os.getenv("BOT_USERNAME")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")

# Создаём Bot, Dispatcher и Database
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
db = Database()  # Привязываем БД к переменной db
db.create_table()  # Создаёт таблицу, если её нет

# Функция проверяет, есть ли пользователь написавший сообщений в БД
def user_check_message_mw(handler, event: Message, data: dict):
    user_id = event.from_user.id
    username = event.from_user.username
    db.check_and_add_user(user_id, username)  # Добавляет в БД если его нет
    return handler(event, data)


dp.message.middleware(user_check_message_mw)

# Функция для получения никнейма из базы данных
async def get_user_name(user_id: int, username: str) -> str:
    # Retrieve user data from the database
    user = db.get_user_data(user_id)
    return user[2] if user[2] else (user[1] if user[1] else str(user[0]))

# Функция удаления сообщения с таймером
async def delete_message_after_timeout(message, timeout=30):
    await asyncio.sleep(timeout)
    await message.delete()


async def send_reply_with_timeout(message, text, timeout=15):
    """Отправляет сообщение и удаляет его через заданное время."""
    sent_message = await message.reply(text)
    await delete_message_after_timeout(sent_message, timeout=timeout)
    await message.delete()


async def variables_films_logic(message):
    variables = re.sub(rf"^/(filmr|films)({BOT_USERNAME})?\s*", "", message.text) \
        .replace(",", " ") \
        .strip() \
        .split()

    try:
        current_year = datetime.datetime.now().year  # Текущий год

        rating = '1-10'
        year = f'1890-{current_year}'
        media_type = None
        genres = []
        countries = []

        for value in variables:
            value_lower = value.lower()  # Игнорируем регистр

            # Проверка рейтинга
            if (value.isdigit() and 1 <= int(value) <= 10) or (
                    "-" in value and len(value.split("-")) == 2 and
                    all(v.isdigit() for v in value.split("-")) and
                    1 <= int(value.split("-")[0]) <= 10 and
                    1 <= int(value.split("-")[1]) <= 10):
                rating = value

            # Проверка года
            elif (len(value) == 4 and value.isdigit() and 1890 <= int(value) <= current_year) or (
                    "-" in value and len(value.split("-")) == 2 and
                    all(v.isdigit() for v in value.split("-")) and
                    1890 <= int(value.split("-")[0]) <= current_year and
                    1890 <= int(value.split("-")[1]) <= current_year):
                year = value

            # Проверка типа
            elif value_lower in {v.lower() for v in valid_media_types.values()}:
                value_lower = value.lower()  # Игнорируем регистр
                media_type = next(k for k, v in valid_media_types.items() if v.lower() == value_lower)

            # Проверка жанра
            if value.startswith("+") or value.startswith("-"):
                clean_genre = value[1:].lower()  # Убираем + или - для проверки
                if clean_genre in {genre.lower() for genre in valid_genres}:
                    matched_genre = next(g for g in valid_genres if g.lower() == clean_genre)
                    genres.append(value[0] + matched_genre)  # Сохраняем префикс + или -

            elif value_lower in {genre.lower() for genre in valid_genres}:
                matched_genre = next(g for g in valid_genres if g.lower() == value_lower)
                genres.append(f"+{matched_genre}")  # Жанру без префикса добавляем +

            # Проверка страны
            if value.startswith("+") or value.startswith("-"):
                clean_country = value[1:].lower()  # Убираем + или - для проверки
                for country in valid_countries:
                    country_words = {word.lower() for word in country.split() if len(word) > 2}  # Учитываем слова > 2 символов
                    if clean_country in country_words:
                        countries.append(value[0] + country)  # Сохраняем префикс + или -

            elif value_lower in {word.lower() for country in valid_countries for word in country.split() if len(word) > 2}:
                matched_country = next(country for country in valid_countries
                                       if value_lower in {word.lower() for word in country.split() if len(word) > 2})
                countries.append(f"+{matched_country}")  # Стране без префикса добавляем +

        # Формируем строки для URL
        genre = "&genres.name=".join(genres) if genres else None
        country = "&countries.name=".join(countries) if countries else None

        # Логирование результатов
        # logging.info(f"Результаты анализа: R: {rating}, Y: {year}, T: {media_type}, G: {genre}, C: {country}")
        return rating, year, media_type, genre, country
    except Exception as e:
        logging.error(f"Ошибка анализа данных variables_films_logic: {e}")
        return

# Создание URL адреса
def make_url(url_base, rating, year, media_type, genre, country):
    """Создаёт URL с учётом всех параметров, включая замену символов + и - на %2B и %21."""
    try:
        def encode_param(param):
            if param:
                return param.replace("+", "%2B").replace("-", "%21")
            return param

        # Формирование параметров URL с учётом правил
        url_params = [
            f"rating.kp={rating if len(rating) != 1 else rating + '-10'}",
            f"year={year if len(year) != 4 else year + '-' + str(datetime.datetime.now().year)}",
            f"type={media_type}" if media_type else "",
            f"countries.name={encode_param(country)}" if country else "",
            f"genres.name={encode_param(genre)}" if genre else ""
        ]

        # Возвращаем итоговый URL, соединяя параметры
        return url_base + "&".join(filter(None, url_params))
    except Exception as e:
        logging.error(f"Ошибка при создании URL make_url: {e}")
        return None

# Запрос к API Kinopoisk
async def fetch_movie_data(url):
    """Получает данные о фильме по-указанному URL с обработкой ошибок."""
    try:
        headers = {"X-API-KEY": KINOPOISK_API_TOKEN}
        async with ClientSession(connector=TCPConnector(ssl=False)) as session:
            async with session.get(url, headers=headers) as response:
                # logging.info(f"Отправлен запрос fetch_movie_data: {response.url}")

                # Обработка статуса ответа
                if response.status == 403:
                    logging.error("fetch_movie_data: Достигнут лимит запросов")
                    return {
                        "statusCode": 403,
                        "message": "Вы израсходовали лимит запросов. Обновите тариф.",
                    }
                elif response.status != 200:
                    logging.error(f"fetch_movie_data: Ошибка при запросе. Статус: {response.status}")
                    return None

                # Проверка на JSON
                if "application/json" in response.headers.get("Content-Type", ""):
                    data = await response.json()
                    if not data:  # Проверка на пустой ответ
                        logging.error("fetch_movie_data: Пустой ответ от API")
                        return None
                    return data
                else:
                    logging.error("fetch_movie_data: Некорректный формат ответа (не JSON)")
                    return None
    except Exception as e:
        logging.error(f"Неожиданная ошибка fetch_movie_data: {e}")
        return None


def format_movie_common(movie):
    """Общая логика форматирования данных фильма."""
    title = movie.get("name", "")
    title_alt = movie.get("alternativeName", "")
    title_id = movie.get("id", "")
    title_type = movie.get("type", "")
    title_type_rus = valid_media_types.get(title_type, "")
    year = movie.get("year", "")
    description = movie.get("description", "Описание отсутствует.")
    short_description = movie.get("shortDescription", "Описание отсутствует.")
    rating_kp = movie.get("rating", {}).get("kp", "") if movie.get("rating") else None
    rating_imdb = movie.get("rating", {}).get("imdb", "") if movie.get("rating") else None
    imdb_id = movie.get("externalId", {}).get("imdb") if movie.get("externalId") else None
    poster_url = movie.get("backdrop", {}).get("url") if movie.get("backdrop") else None
    movie_length = movie.get("movieLength")
    link = f"https://www.kinopoisk.ru/{'series' if title_type == 'tv-series' else 'film'}/{title_id}"
    link_imdb = f'https://www.imdb.com/title/{imdb_id}' if imdb_id else f'https://www.imdb.com/'
    link_watch = f"https://reyohoho.github.io/reyohoho/#{title_id}"

    title_movie_info = f'*{title}* / *{title_alt}*' \
        if title and title_alt else f'*{title}*' \
        if title and not title_alt else f'*{title_alt}*' \
        if not title and title else 'У фильма нет названия'

    return {
        "title": title,
        "title_movie_info": title_movie_info,
        "title_alt": title_alt,
        "title_id": title_id,
        "title_type_rus": title_type_rus,
        "year": year,
        "description": description,
        "short_description": short_description,
        "rating_kp": rating_kp,
        "rating_imdb": rating_imdb,
        "link": link,
        "link_imdb": link_imdb,
        "link_watch": link_watch,
        "imdb_id": imdb_id,
        "poster_url": poster_url,
        "movie_length": movie_length
    }


def format_films_response(data):
    """Форматирует список фильмов для команды /films."""
    try:
        response = []
        films_keyboard = InlineKeyboardMarkup(inline_keyboard=[], row_width=3)
        buttons = []

        for movie in data:
            movie_info = format_movie_common(movie)

            # Формируем описание фильма
            response.append(
                f"{movie_info['title_movie_info']}, {movie_info['title_type_rus']}, {movie_info['year']}\n"
                f"{'Продолжительность фильма *' + str(movie_info['movie_length']) + '* мин.\n' if movie_info['movie_length'] else ''}"
                f"[Кинопоиск]({movie_info['link']}) *{movie_info['rating_kp']}*, [IMDB]({movie_info['link_imdb']}) "
                f"*{movie_info['rating_imdb']}*\n"
                f"`{movie_info['short_description'] if movie_info['short_description'] else ''}`"
            )

            # Добавляем кнопки для клавиатуры
            button = InlineKeyboardButton(
                text=f"{movie_info['title']} ({movie_info['year']})",
                url=movie_info['link_watch']
            )
            buttons.append(button)

        # Добавляем кнопки на клавиатуру
        for i in range(0, len(buttons), 3):
            films_keyboard.inline_keyboard.append(buttons[i:i + 3])

        return "\n\n".join(response), films_keyboard
    except Exception as e:
        logging.error(f"Ошибка форматирования списка фильмов format_films_response: {e}")
        return None, None


def format_film_response(data):
    """Форматирует данные одного фильма для команды /film."""
    try:
        movie = data['docs'][0] if 'docs' in data else data
        movie_info = format_movie_common(movie)

        # Формируем описание фильма
        response = (
            f"{movie_info['title_movie_info']}, {movie_info['title_type_rus']}, {movie_info['year']}\n"
            f"{'Продолжительность фильма *' + str(movie_info['movie_length']) + '* мин.\n' if movie_info['movie_length'] else ''}"
            f"[Кинопоиск]({movie_info['link']}) *{movie_info['rating_kp']}*, [IMDB]({movie_info['link_imdb']}) "
            f"*{movie_info['rating_imdb']}*\n"
            f"`{movie_info['description']}`"
        )

        # Создаем клавиатуру с двумя кнопками в ряду
        film_keyboard = InlineKeyboardMarkup(inline_keyboard=[], row_width=2)
        button_link = InlineKeyboardButton(
            text="Кинопоиск",
            url=movie_info['link']
        )
        button_watch = InlineKeyboardButton(
            text="Смотреть",
            url=movie_info['link_watch']
        )

        # Добавляем кнопки на клавиатуру
        film_keyboard.inline_keyboard.append([button_link, button_watch])  # Добавляем пару кнопок в один ряд

        # Возвращаем текст и клавиатуру
        return response, film_keyboard

    except Exception as e:
        logging.error(f"Ошибка форматирования фильма format_film_response: {e}")
        return None, None


def format_filmr_response(data):
    """Форматирует данные одного фильма для команды /filmr."""
    try:
        movie = data['docs'][0] if 'docs' in data else data
        movie_info = format_movie_common(movie)

        response = (
            f"{movie_info['title_movie_info']}, {movie_info['title_type_rus']}, {movie_info['year']}\n"
            f"{'Продолжительность фильма *' + str(movie_info['movie_length']) + '* мин.\n' if movie_info['movie_length'] else ''}"
            f"[Кинопоиск]({movie_info['link']}) *{movie_info['rating_kp']}*, [IMDB]({movie_info['link_imdb']}) "
            f"*{movie_info['rating_imdb']}*\n"
            f"`{movie_info['description']}`"
        )

        # Создаем клавиатуру с двумя кнопками в ряду
        filmr_keyboard = InlineKeyboardMarkup(inline_keyboard=[], row_width=2)
        button_link = InlineKeyboardButton(
            text="Кинопоиск",
            url=movie_info['link']
        )
        button_watch = InlineKeyboardButton(
            text="Смотреть",
            url=movie_info['link_watch']
        )

        # Добавляем кнопки на клавиатуру
        filmr_keyboard.inline_keyboard.append([button_link, button_watch])  # Добавляем пару кнопок в один ряд

        # Возвращаем текст и клавиатуру
        return response, filmr_keyboard
    except Exception as e:
        logging.error(f"Ошибка форматирования фильма format_filmr_response для /filmr: {e}")
        return None


@dp.message(F.text.startswith(("/films", "/filmr", "/film")))
async def send_filtered_movie(message: Message):
    """Обработчик команд /films, /filmr, /film."""
    command = message.text.replace(f'{BOT_USERNAME}', '').split()[0][1:]
    try:
        if command == "films":
            await handle_films_command(message)
        elif command == "filmr":
            await handle_film_random_command(message)
        elif command == "film":
            await handle_film_title_command(message)
        else:
            await message.reply("Неизвестная команда 😢")
    except Exception as e:
        logging.error(f"Ошибка обработки команды {command}: {e}")
        await message.reply("Произошла ошибка 😢")


async def handle_films_command(message: Message):
    """Обработка команды /films: выводит список фильмов."""
    rating, year, media_type, genre, country = await variables_films_logic(message)
    url_base = "https://api.kinopoisk.dev/v1.4/movie/random?"

    data = []
    seen_ids = set()  # Множество для уникальных ID фильмов

    for attempt in range(3):  # Пытаемся получить до 3 уникальных фильмов
        url = make_url(url_base, rating, year, media_type, genre, country)
        movie_data = await fetch_movie_data(url)

        # Проверяем, нет ли ошибки 403
        if isinstance(movie_data, dict) and movie_data.get("statusCode") == 403:
            await message.reply("Ошибка: вы израсходовали лимит запросов. Обновите тариф в @kinopoiskdev_bot 😢")
            return

        # Проверяем, пуст ли результат
        if not movie_data:
            if attempt == 0:  # Если первый запрос пустой, завершаем выполнение
                await message.reply("Фильмы не найдены 😢")
                return
            continue

        # Проверяем уникальность ID фильма
        movie_id = movie_data.get("id")
        if movie_id and movie_id not in seen_ids:
            data.append(movie_data)
            seen_ids.add(movie_id)

    # Формируем ответ
    response, films_keyboard = format_films_response(data)
    if response:
        await message.reply(response, reply_markup=films_keyboard, parse_mode="Markdown")
    else:
        await message.reply("Фильмы не найдены 😢")


async def handle_film_random_command(message: Message):
    """Обработка команды /filmr: выводит случайный фильм."""
    rating, year, media_type, genre, country = await variables_films_logic(message)
    url_base = "https://api.kinopoisk.dev/v1.4/movie/random?"
    url = make_url(url_base, rating, year, media_type, genre, country)

    data = await fetch_movie_data(url)

    # Проверяем ошибки и отсутствие данных
    if isinstance(data, dict) and data.get("statusCode") == 403:
        await message.reply("Ошибка: вы израсходовали лимит запросов. Обновите тариф в @kinopoiskdev_bot 😢")
        return

    if not data:
        await message.reply("Не удалось найти фильм 😢")
        return

    response, filmr_keyboard = format_filmr_response(data)
    if response:
        await message.reply(response, reply_markup=filmr_keyboard, parse_mode="Markdown")
    else:
        await message.reply("Ошибка при форматировании фильма 😢")


async def handle_film_title_command(message: Message):
    """Обработка команды /film: поиск фильма по запросу."""
    query = re.sub(rf"^/film({BOT_USERNAME})?\s*", "", message.text)
    url = f"https://api.kinopoisk.dev/v1.4/movie/search?query={query}"
    data = await fetch_movie_data(url)
    if not data or data['total'] == 0:
        await message.reply("Фильм не найден 😢")
        return

    response, films_keyboard = format_film_response(data)
    if response:
        await message.reply(response, reply_markup=films_keyboard, parse_mode="Markdown")
    else:
        await message.reply("Ошибка при форматировании фильма 😢")

# Общая логика получения списка пользователей
async def get_mentions(users, requester_name):
    emoji_pattern = re.compile("[\U0001F600-\U0001F64F]")
    return [
        f"{user['display_name']} [(@{user['username']})](tg://user?id={user['user_id']})"
        if emoji_pattern.search(user['display_name'])
        else f"[@{user['display_name']}](tg://user?id={user['user_id']})"
        for user in users
    ]

# Функция для общего уведомления
@dp.message(F.text.startswith('/everyone') | F.text.contains('@all') | F.text.contains('ривет все'))
async def all_users_mention(message: Message):
    users = db.get_all_users_except(message.from_user.id)
    requester_name = await get_user_name(message.from_user.id, message.from_user.username)
    try:
        if users:
            mentions = await get_mentions(users, requester_name)
            response_text = f"{', '.join(mentions)}"
        else:
            response_text = "Пустая база данных, либо вы там один 😔"
        await message.reply(response_text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка all_users_mention: {e}")
        await message.reply(f"Ошибка отправки общего уведомления")

# Создание кнопки для /watching если указано название фильма после команды
@dp.callback_query(F.data.startswith('/film'))
async def emulate_user_film_command(callback_query: types.CallbackQuery):
    command_text = callback_query.data
    # Эмулируем сообщение от пользователя
    fake_message = types.Message(
        message_id=callback_query.message.message_id,
        date=callback_query.message.date,
        chat=callback_query.message.chat,
        from_user=callback_query.from_user,
        text=command_text,
    )
    # Передаём сообщение с привязкой к боту
    await send_filtered_movie(fake_message.as_(bot))

# Функция для уведомления о фильме
@dp.message(F.text.startswith('/watching'))
async def watching_command(message: Message):
    watching_name = ' '.join(message.text.split(' ')[1:])
    inline_keyboard = (
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"Узнать о фильме: {watching_name}", callback_data=f'/film {watching_name}')]
            ]
        )
        if watching_name else None
    )
    users = db.get_all_users_watching(message.from_user.id)
    requester_name = await get_user_name(message.from_user.id, message.from_user.username)

    try:
        if users:
            mentions = await get_mentions(users, requester_name)
            response_text = f"{requester_name} зовёт {', '.join(mentions)} посмотреть фильм"
            if watching_name:
                response_text += f" *{watching_name}*"
        else:
            response_text = "Список пользователей, которые хотят посмотреть кино, пуст"
        await message.answer(response_text, reply_markup=inline_keyboard, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка watching_command: {e}")

# Функция для включения/отключения оповещений о начале просмотра
@dp.message(F.text.startswith('/watch') | F.text.startswith('/unwatch'))
async def watch_unwatch(message: Message):
    command = message.text.split('@')[0].strip()  # Извлекаем команду без префикса @
    user_id = message.from_user.id

    if command == '/watch':
        subscribe = True
        success_message = "Вы подписались на оповещения 🥳"
        fail_message = "Ошибка, не удалось подписать Вас на оповещения"
    elif command == '/unwatch':
        subscribe = False
        success_message = "Вы отписались от оповещений 😔"
        fail_message = "Ошибка, не удалось отписать Вас от оповещений"
    else:
        await send_reply_with_timeout(
            message, "Возможно Вы имели ввиду команду /watch или /unwatch?\n"
                     "Также можно использовать команду /watching чтобы позвать людей на просмотр фильма"
        )
        return

    if db.update_notify_watching_status(user_id, subscribe=subscribe):
        await send_reply_with_timeout(message, success_message)
    else:
        await send_reply_with_timeout(message, fail_message)

# Функция добавления/удаления пользовательского имени
@dp.message(F.text.regexp(rf"(?i)^({BOT_USERNAME}\s*)?/(setname|removename|myname)"))
async def setname_remove(message: Message):
    command_pattern = rf"(?i)^/?(setname|removename|myname)(?:{BOT_USERNAME})?\s*(?P<after>.*)"
    match = re.match(command_pattern, message.text)
    user_id = message.from_user.id

    if match:
        command = match.group(1).lower()
        after_command = match.group("after").strip()
        try:
            if command == "setname":
                if not after_command:
                    await send_reply_with_timeout(
                        message,
                        "Ошибка: пустое сообщение, пример команды:\n/setname Ваше имя"
                    )
                    return
                # Проверка на недопустимые символы
                if invalid_match := re.search(r"[\\;:,?/=@&<>+$%|[\]()'\"!{}]", after_command):
                    invalid_char = invalid_match.group(0)
                    await send_reply_with_timeout(
                        message,
                        f"Ошибка: найден недопустимый символ: {invalid_char}\n"
                        f"Запрещено использовать: \\;:,<>?/=@&+$%|[]()\'\"!" + "{}"
                    )
                    return
                db.set_custom_name(user_id, after_command)  # Сохранение имени в базе данных
                await send_reply_with_timeout(message, f"Ваше имя *{after_command}* сохранено")
            elif command == "removename":
                db.remove_custom_name(user_id)
                await send_reply_with_timeout(message, "Ваше имя удалено")
            elif command == "myname":
                current_name = db.get_custom_name(user_id)  # Получаем текущее имя из базы данных
                if current_name:
                    await send_reply_with_timeout(message, f"Ваше текущее имя: *{current_name}*")
                else:
                    await send_reply_with_timeout(message, "Вы ещё не установили кастомное имя.")
        except Exception as e:
            await send_reply_with_timeout(message, f"Произошла ошибка: {e}")
    else:
        await send_reply_with_timeout(
            message,
            "Хотите удалить имя? Нажмите: /removename\nХотите установить имя? Напишите:\n/setname Ваше имя"
        )

# Команды случайностей
@dp.message(F.text.startswith(('/coin', '/randomgirl')))
async def coin_flip(message: Message):
    command = message.text.split()[0]
    if command in ["/coingirl", "/randomgirl", f'/coingirl{BOT_USERNAME}', f'/randomgirl{BOT_USERNAME}']:
        girls = ["Даши", "Саши", "Крис"]
        emojis = ["😊", "😍", "😘", "❤️", "😜"]
        girl = random.choice(girls)
        emoji = random.choice(emojis)
        await message.answer(f"Ой, кто-то из чата отправил {emoji} для {girl}")
    elif command in ["/coin", f'/coin{BOT_USERNAME}']:  # Если команда просто /coin
        result = random.choice(["Орёл", "Решка"])
        user_name = await get_user_name(message.from_user.id,
                                        message.from_user.username)  # Запрос имени для команды /coin
        user_link = f"[{user_name}](tg://user?id={message.from_user.id})"
        await message.answer(f"{user_link} подбросил монетку, поймал... и там {result}", parse_mode="Markdown")
    else:
        await message.answer("Возможно Вы имели ввиду /coin или /coingirl?")
    await message.delete()

# Команды для голосования
@dp.message(F.text.startswith(('/vote', '/poll')))
async def vote_msg(message: Message):
    options_text = re.sub(rf"^/(poll|vote)({BOT_USERNAME})?\s*", "", message.text).strip()  # Отделяем команду
    options = [option.strip() for option in options_text.split(",") if
               option.strip()]  # Создаём список вариантов указанных через ","
    options = list({option.lower(): option for option in options}.values())  # Фильтр для удаления дубликатов
    if len(options) < 2:
        await message.answer(
            f"{message.from_user.username}, Вам необходимо указать хотя бы два варианта для голосования")
    elif len(options) > 10:
        await message.answer(f"{message.from_user.username}, Вы можете добавить не более 10 вариантов в голосовании")
    else:
        await message.answer_poll(
            question=f'"{message.from_user.username}" предлагает проголосовать:',
            options=options, is_anonymous=False, type="regular"
        )
    await delete_message_after_timeout(message, timeout=15)

# Функция отправки запроса
async def get_random_gif(query: str):
    try:
        url = f"https://tenor.googleapis.com/v2/search?q={query}&key={TENOR_API_KEY}&random=True&limit=1"
        async with ClientSession(connector=TCPConnector(ssl=False)) as session:
            async with session.get(url) as response:
                # logging.info(f"Отправлен запрос, на gif: {response.url}")
                data = await response.json()
                if data['results']:
                    return data['results'][0]['media_formats']['gif']['url']
    except Exception as e:
        logging.error(f"Статус get_random_gif: {response.status}, ошибка: {e}")
        return

# Функция случайной gif
@dp.message(F.text.startswith('/gif'))
async def send_random_gif(message: Message):
    query = message.text.split(' ', 1)[1].strip() if len(message.text.split(' ', 1)) > 1 else ""
    if not query:
        await message.reply("Пожалуйста, укажите запрос. Например:\n/gif cat")
        return
    try:
        gif_url = await get_random_gif(query)
        await message.reply_animation(gif_url)
    except Exception as e:
        logging.error(f"Ошибка при получении GIF: {e}")
        await message.reply("Произошла ошибка при обработке запроса.")


@dp.message(F.text.startswith(('/help_film', '/help_film_genres', '/help_film_countries')))
async def film_command_help(message: Message):
    if '/help_film_countries' in message.text:
        help_text = f'*Список доступных стран*:\n{", ".join(map(str, sorted(valid_countries)))}'
    elif '/help_film_genres' in message.text:
        help_text = f'*Список доступных жанров*:\n{", ".join(map(str, sorted(valid_genres)))}'
    else:
        help_text = (
            "*Гайд по использованию команд:*\n\n"
    
            "/film название - Получить информацию о фильме по конкретному запросу.\n"
            "Используйте команду с названием фильма. Пример:\n"
            "`/film Шерлок Холмс`\n\n"
    
            "/filmr - Получить информацию о случайном фильме по расширенному запросу.\n"
            "Используйте команду с необязательными фильтрами (жанр, страна, год, рейтинг). Пример:\n"
            "`/filmr 2-5 2009-2020 +фантастика -драма Россия фильм`\n"
            "`/filmr 5 2020 +фантастика +ужасы -драма США -Россия мультфильм`\n\n"
    
            "/films - Получите информацию о 6 случайных фильмах, соответствующих вашему расширенному запросу.\n"
            "Используйте команду с необязательными фильтрами (жанр, страна, год, рейтинг). Пример:\n"
            "`/films 2-5 2009-2020 +фантастика -драма Россия фильм`\n"
            "`/films 5 2020 +фантастика +ужасы -драма США -Россия мультфильм`\n\n"
    
            "*Подсказки:*\n"
            "- Используйте `+` для включения жанра или страны.\n"
            "- Используйте `-` для исключения жанра или страны.\n"
            "- Указывайте год в формате `YYYY` или диапазон `YYYY-YYYY`.\n"
            "- Рейтинг можно указать как число `от 1 до 10` или диапазон, например `1-5`. Если указано одно число `N`, то "
            "рейтинг будет выставлен `от N до 10`"
        )
    sent_message = await message.answer(help_text, parse_mode="Markdown")
    try:
        sent_message
    except Exception as e:
        logging.error(f"Ошибка команды /help_film /help_film_genres /help_film_countries: {e}")
    await delete_message_after_timeout(sent_message)
    await message.delete()

# Удаления сообщения! Используйте только для админа
@dp.message(F.text.startswith('/help'))
async def help_msg(message: Message):
    sent_message = await message.reply(
        "/everyone или @all - Уведомить всех участников\n"
        "/vote или /poll <варианты через запятую> - Создать голосование от 2 до 10 вариантов\n"
        "/film <название фильма> - Поиск фильма по названию\n"
        "/filmr <рейтинг, год, жанр, тип> - Поиск случайного фильма\n"
        "/films <рейтинг, год, жанр, тип> - Поиск 10 фильмов\n"
        "/setname <имя> - Установить кастомное имя\n"
        "/removename - Удалить кастомное имя\n"
        "/watching <название фильма> - Позвать на просмотр фильма\n"
        "/watch - Включить оповещения о начале фильма\n"
        "/unwatch - Отключить оповещения о начале фильма\n"
        "/coin - Подбросить монетку (Орёл, Решка)\n"
        "/coingirl или /randomgirl - Подбросить девушку 😂 шучу или нет 🤔\n"
        "/gif <название> - Отправить случайную гифку по названию\n\n"
        "/help - Помощь по всем командам\n"
        "/help_film - Помощь по командам film\n"
        "/help_film_genres - Показать доступные жанры для команд film\n"
        "/help_film_countries - Показать доступные страны для команд film\n"
    )
    try:
        sent_message
    except Exception as e:
        logging.error(f"Ошибка команды /help: {e}")
    await delete_message_after_timeout(sent_message)
    await message.delete()

# Удаления сообщений! Используйте только для администраторов!
@dp.message(F.text.startswith('/dm'))
async def delete_replied_message(message: Message):
    if str(message.from_user.id) in ADMIN_USER_ID:
        try:
            await message.reply_to_message.delete()
            # logging.info(
            #     f"Администратор <{message.from_user.username}> от <{message.reply_to_message.from_user.username}>"
            #     f"удалил <{message.reply_to_message.text 
            #     if message.reply_to_message.text else message.reply_to_message.poll.question}>"
            # )
        except Exception as e:
            logging.error(f"Не указано какое сообщение удалить, ошибка: {e}")
    else:
        logging.info(
            f'Пользователь <{message.reply_to_message.from_user.username}> попытался использовать команду /dm'
        )
    await message.delete()

# Приветствие
@dp.message(F.new_chat_members)
async def somebody_added(message: Message):
    for user in message.new_chat_members:
        await message.reply(f"Привет, {user.full_name}")

# Проверка наличия пользователя в базе данных
@dp.message()
async def check_db_user(message: Message):
    return

# Основные функции запуска бота
async def main():
    logging.info(f"Bot {BOT_USERNAME} is running...")
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logging.error("Bot was stopped by the user")
    except asyncio.CancelledError:
        logging.error("Bot has been cancelled")
    except Exception as e:
        logging.critical(f"Critical error: {e}", exc_info=True)
    finally:
        logging.critical(f"Bot {BOT_USERNAME} was stopped...")
        await bot.session.close()

# Запуск бота
if __name__ == '__main__':
    asyncio.run(main())
