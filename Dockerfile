# 1. Используем легкий образ Python 3.11
FROM python:3.11-slim

# 2. Отключаем создание лишних файлов питоном (.pyc) и буферизацию вывода
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 3. Создаем рабочую папку внутри контейнера
WORKDIR /app

# 4. Устанавливаем СИСТЕМНЫЕ библиотеки (gcc, kerberos)
# Это решает вашу ошибку "krb5-config: not found"
RUN apt-get update && apt-get install -y \
    gcc \
    libkrb5-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# 5. Копируем файл зависимостей
# ВАЖНО: Путь слева — это путь на ВАШЕМ компьютере относительно Dockerfile
COPY pligrim_bot/requirements.txt ./requirements.txt

# 6. Устанавливаем библиотеки Python
RUN pip install --no-cache-dir -r requirements.txt

# 7. Копируем весь код бота внутрь контейнера
COPY pligrim_bot /app/pligrim_bot

# 8. Команда запуска
# Запускаем как модуль (-m), чтобы питон видел все импорты
CMD ["python", "-m", "pligrim_bot.main"]
