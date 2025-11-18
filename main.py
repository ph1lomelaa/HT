import logging
import sys
import os
import asyncio

# Добавляем пути для импортов
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    from pligrim_bot.config.settings import get_google_client, refresh_sheets
    from pligrim_bot.config.constants import bot, dp

    # Импортируем все хендлеры
    from pligrim_bot.handlers.flight_handlers import *
    from pligrim_bot.handlers.pilgrim_handlers import *
    from pligrim_bot.handlers.preview_handlers import *
    from pligrim_bot.handlers.debug_handlers import *
    from pligrim_bot.handlers.palm_edit_handlers import *
    from pligrim_bot.handlers.palm_restart_handlers import *
    from pligrim_bot.handlers.indv_voucher_handlers import *

    print("✅ Все модули успешно импортированы")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    sys.exit(1)

async def main():
    print("✅ Бот запускается…")
    await bot.delete_webhook(drop_pending_updates=True)

    # Создаем временные директории
    os.makedirs("tmp", exist_ok=True)
    os.makedirs("assets/fonts", exist_ok=True)
    os.makedirs("assets/images", exist_ok=True)

    print("🚀 Polling started…")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Бот остановлен.")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")