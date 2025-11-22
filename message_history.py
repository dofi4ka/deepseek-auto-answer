"""Хранение истории сообщений в памяти с персистентностью."""

import json
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

data_path = Path("data")
data_path.mkdir(exist_ok=True)


class MessageHistory:
    """Класс для хранения истории сообщений в памяти с сохранением в JSON."""

    def __init__(
        self, max_messages: int = 50, storage_path: str = "message_history.json"
    ):
        """
        Инициализация хранилища истории.

        Args:
            max_messages: Максимальное количество сообщений для хранения на пользователя
            storage_path: Путь к файлу для сохранения истории
        """
        self.max_messages = max_messages
        self.storage_path = data_path / storage_path
        self._history: Dict[int, List[Dict[str, str]]] = {}

        # Загружаем историю из файла при инициализации
        self._load_from_file()

    def _load_from_file(self) -> None:
        """Загрузить историю сообщений из JSON файла."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Конвертируем ключи из строк обратно в int
                self._history = {
                    int(user_id): messages for user_id, messages in data.items()
                }
        except (json.JSONDecodeError, ValueError, IOError) as e:
            # Если файл поврежден или не может быть прочитан, начинаем с пустой истории
            logger.warning(
                f"Ошибка при загрузке истории из файла {self.storage_path}: {e}"
            )

    def _save_to_file(self) -> None:
        """Сохранить историю сообщений в JSON файл."""
        try:
            # Создаем директорию, если её нет
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self._history, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(
                f"Ошибка при сохранении истории в файл {self.storage_path}: {e}"
            )

    def add_message(self, user_id: int, role: str, content: str) -> None:
        """
        Добавить сообщение в историю пользователя.

        Args:
            user_id: ID пользователя
            role: Роль сообщения ('user' или 'assistant')
            content: Содержимое сообщения
        """
        if user_id not in self._history:
            self._history[user_id] = []

        self._history[user_id].append({"role": role, "content": content})

        # Удаляем старые сообщения, если превышен лимит
        if len(self._history[user_id]) > self.max_messages:
            self._history[user_id] = self._history[user_id][-self.max_messages :]

        # Сохраняем в файл после каждого добавления
        self._save_to_file()

    def get_history(self, user_id: int) -> List[Dict[str, str]]:
        """
        Получить историю сообщений пользователя.

        Args:
            user_id: ID пользователя

        Returns:
            Список словарей с ключами 'role' и 'content'
        """
        return self._history.get(user_id, []).copy()

    def clear_history(self, user_id: int) -> None:
        """
        Очистить историю сообщений пользователя.

        Args:
            user_id: ID пользователя
        """
        if user_id in self._history:
            del self._history[user_id]
            # Сохраняем в файл после очистки
            self._save_to_file()
