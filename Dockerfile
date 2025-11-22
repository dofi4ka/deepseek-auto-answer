FROM python:3.13-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости (если нужны)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Копируем файлы зависимостей
COPY pyproject.toml ./

# Устанавливаем зависимости из pyproject.toml
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir aiogram>=3.22.0 deepseek>=1.0.0 python-dotenv>=1.2.1

# Копируем исходный код приложения
COPY bot.py config.py message_history.py ./

# Устанавливаем переменные окружения по умолчанию
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Запускаем бота
CMD ["python", "bot.py"]

