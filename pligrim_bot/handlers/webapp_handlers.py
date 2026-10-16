from aiogram import F
from aiogram.types import InlineKeyboardButton,InlineKeyboardMarkup
from pligrim_bot.config.constants import dp
from pligrim_bot.web.auth import approve_challenge


async def show_login_confirmation(message,key):
    if not key or len(key)>80:
        await message.answer('Ссылка для входа устарела. Откройте сайт и попробуйте снова.');return
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Подтвердить вход на сайт',callback_data='web_login:'+key)],
        [InlineKeyboardButton(text='Отмена',callback_data='web_login_cancel')]])
    await message.answer('Вход в Hickmet Workspace\n\nПодтвердите вход, если вы только что открыли voucherhickmet.duckdns.org в браузере. После подтверждения вернитесь на сайт.',reply_markup=kb)


@dp.callback_query(F.data.startswith('web_login:'))
async def approve_web_login(callback):
    key=callback.data.split(':',1)[1]
    approve_challenge(key,{'id':callback.from_user.id,'first_name':callback.from_user.first_name,'username':callback.from_user.username or ''})
    await callback.message.edit_text('Вход подтверждён. Вернитесь на сайт — он откроется автоматически.')
    await callback.answer()


@dp.callback_query(F.data=='web_login_cancel')
async def cancel_web_login(callback):
    await callback.message.edit_text('Вход отменён.');await callback.answer()
