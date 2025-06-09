import asyncio
import datetime
import logging
import re

import database as db
import env_config

from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiohttp import TCPConnector, ClientSession


async def send_and_delete(message, text=None, timeout=15, reply=False):
    """
    Отправляет сообщение или отвечает на него, и удаляет через timeout.
    
    - Если text указан, отправляет ответ на сообщение (reply=False - обычное, reply=True - reply).
    - Если text не указан, просто удаляет исходное message через timeout.
    """
    if text is not None:
        if reply:
            sent_message = await message.reply(text)
        else:
            sent_message = await message.answer(text)
        await asyncio.sleep(timeout)
        await sent_message.delete()
        await message.delete()
    else:
        await asyncio.sleep(timeout)
        await message.delete()


async def variables_films_logic(message):
    """ Логика переменных фильмов. """
    variables = re.sub(rf"^/(filmr|films)({env_config.BOT_USERNAME})?\s*", "", message.text) \
        .replace(",", " ") \
        .strip() \
        .split()

    try:
        current_year = datetime.datetime.now().year  # Текущий год

        rating = '1-10'
        year = f'1890-{current_year}'
        media_type = 'movie'
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
            elif value_lower in {v.lower() for v in db.VALID_MEDIA_TYPES.values()}:
                value_lower = value.lower()  # Игнорируем регистр
                media_type = next(k for k, v in db.VALID_MEDIA_TYPES.items() if v.lower() == value_lower)

            # Проверка жанра
            if value.startswith("+") or value.startswith("-"):
                clean_genre = value[1:].lower()  # Убираем + или - для проверки
                if clean_genre in {genre.lower() for genre in db.VALID_GENRES}:
                    matched_genre = next(g for g in db.VALID_GENRES if g.lower() == clean_genre)
                    genres.append(value[0] + matched_genre)  # Сохраняем префикс + или -

            elif value_lower in {genre.lower() for genre in db.VALID_GENRES}:
                matched_genre = next(g for g in db.VALID_GENRES if g.lower() == value_lower)
                genres.append(f"+{matched_genre}")  # Жанру без префикса добавляем +

            # Проверка страны
            if value.startswith("+") or value.startswith("-"):
                clean_country = value[1:].lower()  # Убираем + или - для проверки
                for country in db.VALID_COUNTRIES:
                    country_words = {word.lower() for word in country.split() if
                                     len(word) > 2}  # Учитываем слова > 2 символов
                    if clean_country in country_words:
                        countries.append(value[0] + country)  # Сохраняем префикс + или -

            elif value_lower in {word.lower() for country in db.VALID_COUNTRIES for word in country.split() if
                                 len(word) > 2}:
                matched_country = next(country for country in db.VALID_COUNTRIES
                                       if value_lower in {word.lower() for word in country.split() if len(word) > 2})
                countries.append(f"+{matched_country}")  # Стране без префикса добавляем +

        # Формируем строки для URL
        genre = "&genres.name=".join(genres) if genres else None
        country = "&countries.name=".join(countries) if countries else None

        # Логирование результатов
        # logging.info(f"Результаты анализа: R: {rating}, Y: {year}, T: {media_type}, G: {genre}, C: {country}")
        return rating, year, media_type, genre, country
    except Exception as err:
        logging.error(f"Ошибка анализа данных variables_films_logic: {err}")
        return None


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

        result = url_base + "&".join(filter(None, url_params))
        logging.info(f'Generated link {result}')
        # Возвращаем итоговый URL, соединяя параметры
        return result
    except Exception as err:
        logging.error(f"Ошибка при создании URL make_url: {err}")
        return None


async def fetch_movie_data(url):
    """Получает данные о фильме по-указанному URL API Kinopoisk с обработкой ошибок."""
    try:
        headers = {"X-API-KEY": env_config.KINOPOISK_API_TOKEN}
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
    except Exception as err:
        logging.error(f"Неожиданная ошибка fetch_movie_data: {err}")
        return None


def format_movie_common(movie):
    """Общая логика форматирования данных фильма."""
    title = movie.get("name", "")
    title_alt = movie.get("alternativeName", "")
    title_id = movie.get("id", "")
    title_type = movie.get("type", "")
    title_type_rus = db.VALID_MEDIA_TYPES.get(title_type, "")
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
    except Exception as err:
        logging.error(f"Ошибка форматирования списка фильмов format_films_response: {err}")
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

    except Exception as err:
        logging.error(f"Ошибка форматирования фильма format_film_response: {err}")
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
    except Exception as err:
        logging.error(f"Ошибка форматирования фильма format_filmr_response для /filmr: {err}")
        return None


async def handle_films_command(message: Message):
    """Обработка команды /films: выводит список фильмов."""
    rating, year, media_type, genre, country = await variables_films_logic(message)
    url_base = "https://api.kinopoisk.dev/v1.4/movie/random?"

    data = []
    seen_ids = set()  # Множество для уникальных ID фильмов

    for attempt in range(3):  # Пытаемся получить до 3 уникальных фильмов
        url = make_url(url_base, rating, year, media_type, genre, country)
        logging.info("Url generated:", url)
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
    query = re.sub(rf"^/film({env_config.BOT_USERNAME})?\s*", "", message.text)
    url = f"https://api.kinopoisk.dev/v1.4/movie/search?query={query}"
    logging.info(f'Generated link {url}')

    data = await fetch_movie_data(url)
    if not data or data['total'] == 0:
        await message.reply("Фильм не найден 😢")
        return

    response, films_keyboard = format_film_response(data)
    if response:
        await message.reply(response, reply_markup=films_keyboard, parse_mode="Markdown")
    else:
        await message.reply("Ошибка при форматировании фильма 😢")


async def get_random_gif(query: str):
    """Получение случайного gif по запросу."""
    try:
        url = f"https://tenor.googleapis.com/v2/search?q={query}&key={env_config.TENOR_API_KEY}&random=True&limit=1"
        async with ClientSession(connector=TCPConnector(ssl=False)) as session:
            async with session.get(url) as response:
                # logging.info(f"Отправлен запрос, на gif: {response.url}")
                data = await response.json()
                return data['results'][0]['media_formats']['gif']['url']
    except Exception as err:
        logging.error(f"[get_random_gif] Error: {err}")
        return None
