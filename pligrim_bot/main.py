import asyncio
import logging
import os
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery
from pligrim_bot.config.constants import bot,dp,PREVIEW_CACHE,EDIT_STATE
from pligrim_bot.config import settings
from pligrim_bot.data.sessions import CALLBACKS

# Import handlers once; the shared Dispatcher registers their filters.
from pligrim_bot.handlers import flight_handlers,pilgrim_handlers,preview_handlers,palm_edit_handlers,palm_restart_handlers,indv_voucher_handlers,webapp_handlers

logger=logging.getLogger(__name__)


class BotMiddleware(BaseMiddleware):
    async def __call__(self,handler,event,data):
        user=getattr(event,'from_user',None)
        message=event.message if isinstance(event,CallbackQuery) else event
        allowed={int(v) for v in os.getenv('ALLOWED_USER_IDS','').replace(',', ' ').split() if v.isdigit()}
        if allowed and (not user or user.id not in allowed):
            if isinstance(event,CallbackQuery):await event.answer('Нет доступа',show_alert=True)
            else:await event.answer('Нет доступа к боту.')
            return
        if getattr(getattr(message,'chat',None),'type',None)!='private':
            if isinstance(event,CallbackQuery):await event.answer('Используйте личный чат с ботом',show_alert=True)
            else:await message.answer('Для работы с ваучерами откройте личный чат с ботом.')
            return
        for cache in (PREVIEW_CACHE,EDIT_STATE,CALLBACKS,palm_edit_handlers.EDIT_SESSIONS):cache.purge()
        try:
            return await handler(event,data)
        except (ValueError,KeyError) as exc:
            text=str(exc) if isinstance(exc,ValueError) else 'Данные изменились. Обновите список через /start.'
        except Exception:
            logger.exception('Failed to handle bot update')
            text='Не удалось выполнить действие. Повторите попытку или начните заново через /start.'
        await message.answer(text)
        if isinstance(event,CallbackQuery):
            try:await event.answer()
            except Exception:pass


dp.message.outer_middleware(BotMiddleware())
dp.callback_query.outer_middleware(BotMiddleware())


async def main():
    logging.basicConfig(level=logging.INFO)
    try:
        await asyncio.to_thread(settings.refresh_sheets)
    except Exception:
        logger.exception('Google Sheets unavailable; manual vouchers remain available')
    webapp_url=os.getenv('WEBAPP_URL','')
    if webapp_url.startswith('https://'):
        from aiogram.types import MenuButtonWebApp,WebAppInfo
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text='Ваучеры',web_app=WebAppInfo(url=webapp_url)))
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)


if __name__=='__main__':
    asyncio.run(main())
