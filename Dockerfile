# Базовый образ с Python
FROM python:3.11-slim

# Настройки Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Рабочая директория внутри контейнера
WORKDIR /app

# Устанавливаем зависимости
# Сначала копируем только requirements — так кеш лучше работает
COPY pligrim_bot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходники бота
COPY pligrim_bot /app/pligrim_bot

# Если хочешь копировать credentials внутрь контейнера ЛОКАЛЬНО:
# (на проде лучше передавать как secret/volume)
# COPY pligrim_bot/credentials /app/pligrim_bot/credentials

# Команда запуска бота
CMD ["python", "-m", "pligrim_bot.main"]
