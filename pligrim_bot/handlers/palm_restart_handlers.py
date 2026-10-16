from aiogram import F
from aiogram.fsm.context import FSMContext
from pligrim_bot.config.constants import dp,PREVIEW_CACHE,EDIT_STATE
from pligrim_bot.config.keyboards import main_scenario_kb
from pligrim_bot.handlers.palm_edit_handlers import EDIT_SESSIONS

async def reset_user(user_id,chat_id,state):
    await state.clear();EDIT_STATE.pop(user_id,None)
    sess=EDIT_SESSIONS.get(chat_id)
    if sess and sess.get('owner_id')==user_id:EDIT_SESSIONS.pop(chat_id,None)
    for key,data in list(PREVIEW_CACHE.items()):
        if data.get('owner_id')==user_id and data.get('chat_id')==chat_id:PREVIEW_CACHE.pop(key,None)

@dp.callback_query(F.data=='palm_restart')
async def palm_restart(callback,state:FSMContext):
    await reset_user(callback.from_user.id,callback.message.chat.id,state)
    await callback.message.answer('Выберите действие:',reply_markup=main_scenario_kb());await callback.answer()
