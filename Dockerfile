# Базовый образ
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Устанавливаем зависимости
COPY pligrim_bot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY pligrim_bot /app/pligrim_bot

# Копируем assets (фон, шрифты)
COPY pligrim_bot/assets /app/pligrim_bot/assets

# Запуск бота
CMD ["python", "-m", "pligrim_bot.main"]
