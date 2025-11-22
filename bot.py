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

answering_to: dict[int, bool] = {}


async def answer_message(message_obj: Message, response: str):
    answering_to[message_obj.from_user.id] = True
    try:
        paragraphs = response.split("\n\n")
        for paragraph in paragraphs:
            words = paragraph.split()
            time_to_wait = len(words) / Config.WORDS_PER_MINUTE * 60
            await asyncio.sleep(time_to_wait)
            await message_obj.answer(paragraph, parse_mode="Markdown")
    finally:
        answering_to[message_obj.from_user.id] = False


async def wait_for_answer_completion(user_id: int, check_interval: float = 0.5) -> None:
    """
    Ждет, пока бот не закончит отвечать пользователю.

    Args:
        user_id: ID пользователя
        check_interval: Интервал проверки в секундах
    """
    while answering_to.get(user_id, False):
        await asyncio.sleep(check_interval)
        logger.debug(f"Ожидание завершения ответа для пользователя {user_id}")


async def process_buffered_message(user_id: int, message_obj: Message):
    """
    Обрабатывает накопленное сообщение из буфера и отправляет ответ.

    Args:
        user_id: ID пользователя
        message_obj: Объект последнего сообщения (для ответа)
    """
    if user_id not in message_buffers:
        return

    # Ждем, пока бот не закончит отвечать этому пользователю
    if answering_to.get(user_id, False):
        logger.info(
            f"Бот уже отвечает пользователю {user_id}, ожидание завершения ответа..."
        )
        await wait_for_answer_completion(user_id)

    # Проверяем еще раз после ожидания (на случай, если пришли новые сообщения)
    if user_id not in message_buffers:
        logger.debug(f"Буфер для пользователя {user_id} был очищен во время ожидания")
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

        await answer_message(message_obj, response)

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}", exc_info=True)


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
        # Сохраняем ссылку на текущую задачу для проверки актуальности
        current_task = asyncio.current_task()
        try:
            await asyncio.sleep(Config.MESSAGE_WAIT_SECONDS)
            # Проверяем, что таймер все еще активен (не был заменен новым)
            if user_id not in timer_tasks or timer_tasks[user_id] != current_task:
                logger.debug(
                    f"Таймер для пользователя {user_id} был заменен новым, прерываем обработку"
                )
                return

            # Если таймер не был отменен, проверяем возможность обработки
            if user_id in message_buffers and user_id in last_messages:
                # Если бот уже отвечает, ждем завершения ответа
                if answering_to.get(user_id, False):
                    logger.debug(
                        f"Таймер истек для пользователя {user_id}, но бот уже отвечает. Ожидание..."
                    )
                    await wait_for_answer_completion(user_id)

                    # Проверяем, что таймер все еще актуален после ожидания
                    if (
                        user_id not in timer_tasks
                        or timer_tasks[user_id] != current_task
                    ):
                        logger.debug(
                            f"Таймер для пользователя {user_id} был заменен во время ожидания"
                        )
                        return

                    # Проверяем еще раз после ожидания
                    if user_id not in message_buffers or user_id not in last_messages:
                        logger.debug(
                            f"Буфер или сообщение для пользователя {user_id} были удалены во время ожидания"
                        )
                        return

                # Обрабатываем сообщение только если бот не отвечает и таймер все еще актуален
                if not answering_to.get(user_id, False):
                    # Еще раз проверяем актуальность таймера перед обработкой
                    if user_id in timer_tasks and timer_tasks[user_id] == current_task:
                        await process_buffered_message(user_id, last_messages[user_id])
                        # Очищаем таймер только если он все еще актуален
                        if (
                            user_id in timer_tasks
                            and timer_tasks[user_id] == current_task
                        ):
                            del timer_tasks[user_id]
                        if user_id in last_messages:
                            del last_messages[user_id]
                else:
                    logger.debug(
                        f"Бот все еще отвечает пользователю {user_id}, обработка отложена"
                    )
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
