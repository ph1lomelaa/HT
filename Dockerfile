# Базовый образ
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# --- ВАЖНО: Устанавливаем системные библиотеки (Git, GCC и др) ---
RUN apt-get update && apt-get install -y \
    gcc \
    libkrb5-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем зависимости
# Обратите внимание: путь к файлу внутри папки pligrim_bot
COPY pligrim_bot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY pligrim_bot /app/pligrim_bot

# Копируем assets (фон, шрифты)
COPY pligrim_bot/assets /app/pligrim_bot/assets

# Запуск бота
CMD ["python", "-m", "pligrim_bot.main"]
