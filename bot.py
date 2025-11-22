"""Основной файл Telegram бота."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

from config import Config
from deepseek import DeepSeekAPI
from message_history import MessageHistory

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=Config.BOT_TOKEN)
dp = Dispatcher()

# Инициализация клиента DeepSeek и хранилища истории
deepseek_client = DeepSeekAPI(api_key=Config.DEEPSEEK_API_KEY)
message_history = MessageHistory(max_messages=Config.MAX_HISTORY_MESSAGES)

# Буферы сообщений для каждого пользователя (ожидают обработки)
message_buffers: dict[int, str] = {}

# Последние объекты сообщений для каждого пользователя (для ответа)
last_messages: dict[int, Message] = {}

# Активные задачи таймеров для каждого пользователя
timer_tasks: dict[int, asyncio.Task] = {}


async def process_buffered_message(user_id: int, message_obj: Message):
    """
    Обрабатывает накопленное сообщение из буфера и отправляет ответ.

    Args:
        user_id: ID пользователя
        message_obj: Объект последнего сообщения (для ответа)
    """
    if user_id not in message_buffers:
        return

    # Получаем накопленное сообщение
    merged_text = message_buffers[user_id]
    del message_buffers[user_id]

    logger.info(
        f"Обработка накопленного сообщения от пользователя {user_id}: {merged_text}"
    )

    try:
        message_history.add_message(user_id, "user", merged_text)

        prompt = [
            {"role": "system", "content": Config.SYSTEM_PROMPT or ""},
            *message_history.get_history(user_id),
        ]

        response = await asyncio.to_thread(deepseek_client.chat_completion, prompt)

        logger.info(f"Ответ DeepSeek для пользователя {user_id}: {response}")

        message_history.add_message(user_id, "assistant", response)

        await message_obj.answer(response, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}", exc_info=True)
        await message_obj.answer("Произошла ошибка при обработке вашего сообщения.")


async def handle_user_message(message: Message, user_id: int, text: str):
    """
    Обрабатывает входящее сообщение пользователя с буферизацией.

    Если есть активный таймер, отменяет его и мерджит сообщения.
    Создает новый таймер для ожидания дополнительных сообщений.

    Args:
        message: Объект сообщения
        user_id: ID пользователя
        text: Текст сообщения
    """
    # Проверяем, разрешен ли пользователь
    if user_id not in Config.ALLOWED_USER_IDS:
        logger.info(f"Сообщение от неразрешенного пользователя {user_id}")
        return

    # Если есть активный таймер, отменяем его
    if user_id in timer_tasks:
        timer_tasks[user_id].cancel()
        del timer_tasks[user_id]
        logger.debug(f"Отменен таймер для пользователя {user_id}")

    # Мерджим новое сообщение с существующим буфером
    if user_id in message_buffers:
        message_buffers[user_id] = f"{message_buffers[user_id]}\n\n{text}"
        logger.debug(f"Сообщение добавлено в буфер для пользователя {user_id}")
    else:
        message_buffers[user_id] = text
        logger.debug(f"Создан новый буфер для пользователя {user_id}")

    # Сохраняем ссылку на последнее сообщение для ответа
    last_messages[user_id] = message

    # Создаем новую задачу таймера
    async def timer_task():
        try:
            await asyncio.sleep(Config.MESSAGE_WAIT_SECONDS)
            # Если таймер не был отменен, обрабатываем сообщение
            if user_id in message_buffers and user_id in last_messages:
                await process_buffered_message(user_id, last_messages[user_id])
                if user_id in timer_tasks:
                    del timer_tasks[user_id]
                if user_id in last_messages:
                    del last_messages[user_id]
        except asyncio.CancelledError:
            # Таймер был отменен, это нормально
            pass

    timer_tasks[user_id] = asyncio.create_task(timer_task())
    logger.debug(
        f"Создан таймер на {Config.MESSAGE_WAIT_SECONDS} секунд для пользователя {user_id}"
    )


@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    await message.answer(
        "Привет! Я бот, который отвечает на ваши сообщения с помощью DeepSeek API."
    )


# @dp.message(F.text)
# async def handle_text_message(message: Message):
#     """
#     Обработчик текстовых сообщений от пользователей.

#     Отвечает только разрешенным пользователям и игнорирует медиа.
#     """
#     user_id = message.from_user.id
#     text = message.text

#     if not text:
#         return

#     await process_message(message, user_id, text)


@dp.business_message()
async def handle_business_message(business_message: Message):
    """
    Обработчик текстовых сообщений из бизнес-аккаунта.

    Отвечает только разрешенным пользователям и игнорирует медиа.
    """
    # Обрабатываем только текстовые сообщения
    if not business_message.text:
        return

    user_id = business_message.from_user.id
    text = business_message.text

    logger.info(f"Получено бизнес-сообщение от пользователя {user_id}: {text}")
    await handle_user_message(business_message, user_id, text)


async def main():
    """Главная функция для запуска бота."""
    logger.info("Запуск бота...")
    logger.info(f"Разрешенные пользователи: {Config.ALLOWED_USER_IDS}")
    logger.info(
        f"Максимальное количество сообщений в истории: {Config.MAX_HISTORY_MESSAGES}"
    )
    logger.info(f"Время ожидания перед ответом: {Config.MESSAGE_WAIT_SECONDS} секунд")
    logger.info(f"System prompt: {Config.SYSTEM_PROMPT or 'Не установлен'}")

    # Запускаем бота
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
