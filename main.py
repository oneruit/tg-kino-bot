import asyncio
import logging
import random
import re

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command

import algorithm
import database
import env_config

# Создаём Bot, Dispatcher и Database
bot = Bot(token=env_config.TELEGRAM_BOT_TOKEN)
app = Dispatcher()
db = database.Database()
db.create_table()


# Функция проверяет, есть ли пользователь написавший сообщений в БД
def user_check_message_mw(handler, event: Message, data: dict):
    db.add_user(event.from_user.id, event.chat.id, event.from_user.username)  # Добавляет в БД если его нет
    return handler(event, data)


app.message.middleware(user_check_message_mw)


# Обработчик команд /films, /filmr, /film.
@app.message(Command("films", "filmr", "film"))
async def send_filtered_movie(message: Message):
    command = message.text.replace(f'{env_config.BOT_USERNAME}', '').split()[0][1:]
    logging.info(f"Get command: {command}")
    try:
        if command == "films":
            await algorithm.handle_films_command(message)
        elif command == "filmr":
            await algorithm.handle_film_random_command(message)
        elif command == "film":
            await algorithm.handle_film_title_command(message)
        else:
            logging.info(f"Unknown command: {command}. Skipping...")
            return
            # await message.reply("Неизвестная команда 😢")
    except Exception as err:
        logging.error(f"[send_filtered_movie] Command processing error {command}: {err}")
        await message.reply("Произошла ошибка 😢")


# Функция для общего уведомления
@app.message(Command("everyone") or F.text.contains('@all'))
async def all_users_mention(message: Message):
    users = db.get_users(message.from_user.id, message.chat.id)
    try:
        if users:
            response_text = f"{', '.join(users)}"
        else:
            response_text = "Я ещё не обновил свою базу данных и пока что Вы в ней один 😔"
        logging.info(
            f"[all_users_mention] A general message has been sent for {response_text if users else 'no users'}")
        await message.reply(response_text, parse_mode="Markdown")
    except Exception as err:
        logging.error(f"[all_users_mention] Error: {err}")
        return


# Создание кнопки для /watching если указано название фильма после команды
@app.callback_query(F.data.startswith('/film'))
async def emulate_user_film_command(callback_query: types.CallbackQuery):
    logging.info(f"Emulate user film command: {callback_query.data}")
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
@app.message(Command("watching"))
async def watching_command(message: Message):
    command = message.text.replace(f'{env_config.BOT_USERNAME}', '').split()[0][1:]
    logging.info(f"Get command: {command}")
    if not command == 'watching':
        logging.info(f"Unknown command: {command}. Skipping...")
        return

    watching_name = ' '.join(message.text.split(' ')[1:])
    inline_keyboard = (
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=f"Узнать о фильме: {watching_name}", callback_data=f'/film {watching_name}')]
            ]
        )
    )

    user_id = message.from_user.id
    chat_id = message.chat.id

    users = db.get_users(user_id, chat_id, watching_only=1)
    requester_name = db.get_user_name(user_id, chat_id)

    try:
        if users:
            response_text = f"{requester_name} зовёт {', '.join(users)} посмотреть фильм"
            if watching_name:
                response_text += f" *{watching_name}*"
        else:
            response_text = "Список пользователей, которые хотят посмотреть кино, пуст 😔"
        logging.info(
            f"[watching_command] A watching message has been sent for {response_text if users else 'no users'}")
        await message.answer(response_text, reply_markup=inline_keyboard if watching_name else None, parse_mode="Markdown")
    except Exception as err:
        logging.error(f"[watching_command] Error: {err}")
        return


# Функция для включения/отключения оповещений о начале просмотра
@app.message(Command('watch', 'unwatch'))
async def watch_unwatch(message: Message):
    command = message.text.replace(f'{env_config.BOT_USERNAME}', '').split()[0][1:]
    logging.info(f"Get command: {command}")
    try:
        if command == 'watch':
            notify_watching = 1
            success_message = "Вы подписались на оповещения 🥳"
            fail_message = "Ошибка, не удалось подписать Вас на оповещения"
        elif command == 'unwatch':
            notify_watching = 0
            success_message = "Вы отписались от оповещений 😔"
            fail_message = "Ошибка, не удалось отписать Вас от оповещений"
        else:
            logging.info(f"[watch_unwatch] Unknown command: {command}. Skipping...")
            return

        if db.update_notify_watching_status(message.from_user.id, message.chat.id, notify_watching):
            await algorithm.send_and_delete(message, success_message, reply=True)
        else:
            await algorithm.send_and_delete(message, fail_message, reply=True)
    except Exception as err:
        logging.error(f"[watch_unwatch] Error: {err}")
        return


# Функция добавления/удаления пользовательского имени
@app.message(Command("setname", "removename", "myname"))
async def setname_remove(message: Message):
    command = message.text.replace(f'{env_config.BOT_USERNAME}', '').split()[0][1:]
    logging.info(f"Get command: {command}")

    user_id = message.from_user.id
    group_id = message.chat.id
    custom_name = ' '.join(message.text.split(' ')[1:])

    try:
        if command == 'setname':
            if not custom_name:
                await algorithm.send_and_delete(
                    message,
                    "Ошибка: пустое сообщение, пример команды:\n/setname Ваше имя",
                    reply=True
                )
                return
            # Проверка на недопустимые символы
            if invalid_match := re.search(r"[\\;:,?/=@&<>+$%|[\]()'\"!{}]", custom_name):
                invalid_char = invalid_match.group(0)
                await algorithm.send_and_delete(
                    message,
                    f"Ошибка: найден недопустимый символ: {invalid_char}\n"
                    f"Запрещено использовать: \\;:,<>?/=@&+$%|[]()\'\"!" + "{}",
                    reply=True
                )
                return
            elif len(custom_name) > 20:
                await algorithm.send_and_delete(
                    message,
                    "Ошибка: имя слишком длинное, максимальная длина 20 символов",
                    reply=True
                )
                return
            db.update_custom_name(user_id, group_id, custom_name)  # Сохранение имени в базе данных
            await algorithm.send_and_delete(message, f"Ваше имя *{custom_name}* сохранено", reply=True)
            return
        elif command == 'removename':
            db.update_custom_name(user_id, group_id)
            await algorithm.send_and_delete(message, "Ваше имя удалено", reply=True)
            return
        elif command == 'myname':
            custom_name = db.get_custom_name(user_id, group_id)
            if custom_name:
                await algorithm.send_and_delete(message, f"Ваше имя: *{custom_name}*", reply=True)
            else:
                await algorithm.send_and_delete(message, "Ваше имя не установлено", reply=True)
            return
        else:
            logging.info(f"[setname_remove] Unknown command: {command}. Skipping...")
    except Exception as err:
        logging.error(f"[setname_remove] Error: {err}")
        return


from aiogram.filters import Command


# Команды случайностей
@app.message(Command("coin", "coingirl", "randomgirl"))
async def coin_flip(message: Message):
    command = message.text.replace(f'{env_config.BOT_USERNAME}', '').split()[0][1:]
    logging.info(f"Get command: {command}")

    try:
        if command == "coin":
            result = random.choice(["Орёл", "Решка"])
            user_name = db.get_user_name(message.from_user.id, message.chat.id)
            await message.answer(f"{user_name} подбросил монетку, поймал... и там {result}", parse_mode="Markdown")
        else:
            girls = ["Даши", "Саши", "Крис"]
            emojis = ["😊", "😍", "😘", "❤️", "😜", "💖", "🌹", "🔥"]
            girl = random.choice(girls)
            emoji = random.choice(emojis)
            await message.answer(f"Ой, кто-то из чата отправил {emoji} для {girl}")
        await message.delete()
        return None
    except Exception as err:
        logging.error(f"[coin_flip] Error: {err}")
        return None


@app.message(Command("coins"))
async def coins_func(message: Message):
    command = message.text.replace(f'{env_config.BOT_USERNAME}', '').split()[0][1:]
    logging.info(f"UNKNOWN COMMAND FIND NEW: {command}")


# Команды для голосования
@app.message(Command("vote", "poll"))
async def vote_msg(message: Message):
    options_text = re.sub(rf"^/(poll|vote)({env_config.BOT_USERNAME})?\s*", "",
                          message.text).strip()  # Отделяем команду
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
    await algorithm.send_and_delete(message, timeout=30, reply=False)


# Функция случайной gif
@app.message(Command("gif"))
async def send_random_gif(message: Message):
    query = message.text.split(' ', 1)[1].strip() if len(message.text.split(' ', 1)) > 1 else ""
    if not query:
        await message.reply("Пожалуйста, укажите запрос. Например:\n/gif cat")
        return
    try:
        gif_url = await algorithm.get_random_gif(query)
        await message.reply_animation(gif_url)
    except Exception as err:
        logging.error(f"Ошибка при получении GIF: {err}")
        await message.reply("Произошла ошибка при обработке запроса.")


# Помощь
@app.message(Command("help_film", "help_film_genres", "help_film_countries"))
async def film_command_help(message: Message):
    if '/help_film_countries' in message.text:
        help_text = f'*Список доступных стран*:\n{", ".join(map(str, sorted(database.VALID_COUNTRIES)))}'
    elif '/help_film_genres' in message.text:
        help_text = f'*Список доступных жанров*:\n{", ".join(map(str, sorted(database.VALID_GENRES)))}'
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

            "/films - Получите информацию о 3 случайных фильмах, соответствующих вашему расширенному запросу.\n"
            "Используйте команду с необязательными фильтрами (жанр, страна, год, рейтинг). Пример:\n"
            "`/films 2-5 2009-2020 +фантастика -драма Россия фильм`\n"
            "`/films 5 2020 +фантастика +ужасы -драма США -Россия мультфильм`\n\n"

            "*Подсказки:*\n"
            "- Используйте `+` для включения жанра или страны.\n"
            "- Используйте `-` для исключения жанра или страны.\n"
            "- Указывайте год в формате `YYYY` или диапазон `YYYY-YYYY`.\n"
            "- Рейтинг можно указать как число `от 1 до 10` или диапазон, например `1-5`. Если указано одно число `N`,"
            "то рейтинг будет выставлен `от N до 10`"
        )
    sent_message = await message.answer(help_text, parse_mode="Markdown")
    try:
        sent_message
    except Exception as err:
        logging.error(f"Ошибка команды /help_film /help_film_genres /help_film_countries: {err}")
    await algorithm.send_and_delete(sent_message, timeout=60, reply=False)
    await message.delete()


# Удаления сообщения! Используйте только для админа
@app.message(Command("help"))
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
    except Exception as err:
        logging.error(f"Ошибка команды /help: {err}")
    await algorithm.send_and_delete(sent_message, timeout=60, reply=False)
    await message.delete()


# Удаления сообщений! Используйте только для администраторов!
@app.message(Command("dm"))
async def delete_replied_message(message: Message):
    if str(message.from_user.id) in env_config.ADMIN_USER_ID:
        try:
            await message.reply_to_message.delete()
            # logging.info(
            #     f"Администратор <{message.from_user.username}> от <{message.reply_to_message.from_user.username}>"
            #     f"удалил <{message.reply_to_message.text 
            #     if message.reply_to_message.text else message.reply_to_message.poll.question}>"
            # )
        except Exception as err:
            logging.error(f"[delete_replied_message] Error delete message: {err}")
    else:
        logging.warning(
            f'User <{message.reply_to_message.from_user.username}> from {message.chat.id} tried to use command /dm'
        )
    await message.delete()


# Welcome and goodbye message
@app.message(F.new_chat_members | F.left_chat_member)
async def somebody_added(message: Message):
    if message.new_chat_members:
        for user in message.new_chat_members:
            if user.is_bot:
                return
            # await message.reply(
            #     f"Привет, [{user.full_name if user.full_name else user.username}](tg://user?id={user.id}), "
            #     f"воспользуйся командой /help, чтобы посмотреть все возможности",
            #     parse_mode="Markdown")
            db.add_user(user.id, message.chat.id, user.username)
    elif message.left_chat_member:
        left_member = message.left_chat_member
        if left_member.is_bot:
            return
        # await message.answer(f"[{left_member.full_name}](tg://user?id={left_member.id}) покинул(а) чат", parse_mode="Markdown")
        db.delete_user(left_member.id, group_id=message.chat.id)


# Проверка наличия пользователя в базе данных
@app.message()
async def check_user_in_db(message: Message):
    # logging.info(f'Skipping a message from {message.from_user.id} in {message.chat.id}')
    return None


# Основные функции запуска бота
async def main():
    try:
        await app.start_polling(bot)
    except KeyboardInterrupt:
        logging.error("Bot was stopped by the user")
    except asyncio.CancelledError:
        logging.error("Bot has been cancelled")
    except Exception as err:
        logging.error(f"Critical error: {err}", exc_info=True)
    finally:
        logging.critical(f"Bot {env_config.BOT_USERNAME} was stopped...")
        await bot.session.close()


# Запуск бота
if __name__ == '__main__':
    asyncio.run(main())
