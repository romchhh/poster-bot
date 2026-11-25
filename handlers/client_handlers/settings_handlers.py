"""Settings top-level menu; includes account / channel / signature routers."""

from texts import Main
from texts.messages import settings as settings_msg
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from database_functions.client_db import update_user_activity
from keyboards.client_keyboards.settings_keyboards import get_settings_main_keyboard

from handlers.client_handlers.settings_account_handlers import (
    router as account_router,
)
from handlers.client_handlers.settings_channel_handlers import (
    router as channel_router,
)
from handlers.client_handlers.settings_signature_handlers import (
    router as signature_router,
)

router = Router()
router.include_router(channel_router)
router.include_router(signature_router)
router.include_router(account_router)


@router.message(F.text.in_([Main.settings, "Настройки", "Settings", "/settings"]))
async def settings_menu(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    update_user_activity(user_id)
    await state.clear()
    await message.answer(
        text=settings_msg.HUB_FROM_MENU,
        parse_mode="HTML",
        reply_markup=get_settings_main_keyboard(user_id),
    )


@router.callback_query(F.data == "back_to_settings")
async def back_to_settings(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    update_user_activity(user_id)
    await callback.message.edit_text(
        text=settings_msg.HUB_BACK,
        parse_mode="HTML",
        reply_markup=get_settings_main_keyboard(user_id),
    )
    await callback.answer()
