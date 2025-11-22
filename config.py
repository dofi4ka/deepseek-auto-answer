"""Конфигурация бота через переменные окружения."""

import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Класс для хранения конфигурации бота."""

    # Telegram Bot Token
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не установлен в переменных окружения")

    # DeepSeek API Key
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    if not DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY не установлен в переменных окружения")

    # Разрешенные пользователи (список ID через запятую)
    ALLOWED_USER_IDS: list[int] = []
    _allowed_users_str = os.getenv("ALLOWED_USER_IDS", "")
    if _allowed_users_str:
        ALLOWED_USER_IDS = [
            int(uid.strip()) for uid in _allowed_users_str.split(",") if uid.strip()
        ]
    if not ALLOWED_USER_IDS:
        raise ValueError("ALLOWED_USER_IDS не установлен в переменных окружения")

    # System prompt (может быть None)
    SYSTEM_PROMPT: Optional[str] = os.getenv("SYSTEM_PROMPT", None)
    if SYSTEM_PROMPT == "":
        SYSTEM_PROMPT = None

    # Количество сообщений для хранения в истории
    MAX_HISTORY_MESSAGES: int = int(os.getenv("MAX_HISTORY_MESSAGES", "50"))

    # Время ожидания перед отправкой ответа (в секундах)
    # Если в течение этого времени приходит новое сообщение, таймер сбрасывается
    MESSAGE_WAIT_SECONDS: int = int(os.getenv("MESSAGE_WAIT_SECONDS", "30"))
