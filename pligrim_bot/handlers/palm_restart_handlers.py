from aiogram import F
from aiogram.types import CallbackQuery

# Берём тот же dp, что и в palm_edit_handlers / preview / flight / pilgrim
from pligrim_bot.config.constants import dp
from pligrim_bot.config.keyboards import get_palm_month_buttons
from pligrim_bot.handlers.palm_edit_handlers import EDIT_SESSIONS


@dp.callback_query(F.data == "palm_restart")
async def palm_restart(callback: CallbackQuery):
    """
    Полный «ресет» сценария паломников:
    очищаем сессию редактирования и возвращаемся к выбору месяца.
    """
    chat_id = callback.message.chat.id
    EDIT_SESSIONS.pop(chat_id, None)

    text = "🕋 Выберите месяц для паломников:"

    # если сообщение было текстовым – редактируем, иначе шлём новое
    if callback.message.text:
        await callback.message.edit_text(
            text,
            reply_markup=get_palm_month_buttons(),
        )
    else:
        await callback.message.answer(
            text,
            reply_markup=get_palm_month_buttons(),
        )

    await callback.answer()

