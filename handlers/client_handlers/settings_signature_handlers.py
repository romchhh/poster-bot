"""Settings: auto-signatures."""

from utils.ui_emoji import E, Icon
from aiogram import Router, F, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from app.runtime import bot
import asyncio
import html
import re
from keyboards.client_keyboards.settings_keyboards import (
    get_auto_signature_create_keyboard,
    get_auto_signature_manage_keyboard,
    get_auto_signature_save_keyboard,
    get_back_to_auto_signature_keyboard,
    get_channel_admins_list_keyboard,
)
from database_functions.client_db import get_user_language
from database_functions.channels_db import (
    get_channel_by_id,
    get_channel_members,
    get_user_channel_role,
)
from database_functions.auto_signatures_db import (
    add_auto_signature,
    delete_auto_signature,
    get_auto_signature_by_id,
    get_auto_signatures,
    update_auto_signature,
)
from states.client_states import AutoSignatureSettings
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.message_html import safe_truncate_html
from utils.entity_parser import convert_entities_to_html

router = Router()
auto_signature_data = {}
_AUTO_SIG_CPY_SUFFIX = "|cpy"


def _strip_auto_sig_cpy(callback_data: str) -> tuple[str, bool]:
    if callback_data.endswith(_AUTO_SIG_CPY_SUFFIX):
        return (callback_data[: -len(_AUTO_SIG_CPY_SUFFIX)], True)
    return (callback_data, False)


def _channel_folder_id_from_row(channel_info: tuple) -> int | None:
    """folder_id у рядку channels (+ role), зазвичай індекс 11."""
    if not channel_info or len(channel_info) < 12:
        return None
    fid = channel_info[11]
    return int(fid) if fid is not None else None


def _auto_signature_manage_screen_content(
    signature_id: int,
    user_id: int,
    user_language: str = "uk",
    *,
    from_copy_manage: bool = False,
):
    signature_info = get_auto_signature_by_id(signature_id)
    if not signature_info:
        return None
    _sig_id, channel_id, _signature_name, signature_text, _enabled, _ = signature_info
    channel_info = get_channel_by_id(channel_id, user_id=user_id)
    if not channel_info:
        return None
    channel_title = channel_info[2]
    channel_link = channel_info[4] if len(channel_info) > 4 and channel_info[4] else "#"
    display_text = safe_truncate_html(signature_text)
    escaped_channel_title = html.escape(channel_title)
    message_text = {
        "uk": f"""{E.sign} <b>УПРАВЛІННЯ АВТОПІДПИСОМ</b>\n\n{E.channel} Канал: <a href="{channel_link}">{escaped_channel_title}</a>\n\n💬 <b>Прев'ю автопідпису:</b>\n{display_text}"""
    }
    keyboard = get_auto_signature_manage_keyboard(
        signature_id, channel_id, from_copy_manage=from_copy_manage
    )
    return (message_text.get(user_language, message_text["uk"]), keyboard)


def _auto_signature_empty_screen_text(
    channel_id: int, user_id: int, user_language: str = "uk"
):
    channel_info = get_channel_by_id(channel_id, user_id=user_id)
    if not channel_info:
        return None
    channel_link = channel_info[4] if len(channel_info) > 4 and channel_info[4] else "#"
    escaped_channel_title = html.escape(channel_info[2])
    templates = {
        "uk": f'{E.sign} <b>АВТОПІДПИС КАНАЛУ</b>\n\n{E.channel} Канал: <a href="{channel_link}">{escaped_channel_title}</a>\n\n❌ Автопідпис не налаштований\n\nНатисніть «Додати автопідпис», щоб створити його.'
    }
    return templates.get(user_language, templates["uk"])


async def _edit_auto_signature_screen(
    callback: types.CallbackQuery, text: str, reply_markup
) -> bool:
    """Повертає True, якщо повідомлення оновлено; False якщо контент не змінився (вже відповів на callback)."""
    try:
        await callback.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    except TelegramBadRequest as e:
        if "message is not modified" in (e.message or "").lower():
            await callback.answer()
            return False
        raise
    return True


def _channel_editors_screen_payload(
    channel_id: int, viewer_user_id: int
) -> tuple[str, InlineKeyboardMarkup] | None:
    channel_info = get_channel_by_id(channel_id, user_id=viewer_user_id)
    if not channel_info:
        return None
    channel_title = html.escape(channel_info[2])
    channel_link = channel_info[4] if len(channel_info) > 4 and channel_info[4] else "#"
    role = get_user_channel_role(viewer_user_id, channel_id) or "admin"
    members = get_channel_members(channel_id)
    text = f'{E.editors} <b>Редактори</b>\n\n{E.channel} Канал: <a href="{channel_link}">{channel_title}</a>\n\nОберіть учасника для деталей або видалення (лише власник може прибрати редакторів):'
    from database_functions.billing_db import denial

    keyboard = get_channel_admins_list_keyboard(
        channel_id,
        members,
        can_manage_admins=role == "owner",
        is_superadmin=role == "owner" and denial(viewer_user_id, "editors") is None,
    )
    return (text, keyboard)


@router.callback_query(F.data.startswith("auto_signature_settings_"))
async def auto_signature_settings(callback: types.CallbackQuery, state: FSMContext):
    base, from_copy = _strip_auto_sig_cpy(callback.data)
    channel_id = int(base.removeprefix("auto_signature_settings_"))
    user_id = callback.from_user.id
    user_language = get_user_language(user_id) or "uk"
    await state.update_data(auto_sig_from_copy=from_copy)
    channel_info = get_channel_by_id(channel_id, user_id=user_id)
    if not channel_info:
        await callback.answer("❌ Канал не знайдено")
        return
    signatures = get_auto_signatures(channel_id)
    if signatures:
        sid = signatures[0][0]
        payload = _auto_signature_manage_screen_content(
            sid, user_id, user_language, from_copy_manage=from_copy
        )
        if not payload:
            await callback.answer("❌ Канал не знайдено")
            return
        message_text, keyboard = payload
    else:
        message_text = _auto_signature_empty_screen_text(
            channel_id, user_id, user_language
        )
        if not message_text:
            await callback.answer("❌ Канал не знайдено")
            return
        keyboard = get_auto_signature_create_keyboard(
            channel_id, from_copy_manage=from_copy
        )
    if await _edit_auto_signature_screen(callback, message_text, keyboard):
        await callback.answer()


@router.callback_query(F.data.startswith("auto_signature_manage_"))
async def auto_signature_manage(callback: types.CallbackQuery, state: FSMContext):
    base, from_copy = _strip_auto_sig_cpy(callback.data)
    m = re.fullmatch("auto_signature_manage_(\\d+)", base)
    if not m:
        await callback.answer("❌ Некоректні дані")
        return
    signature_id = int(m.group(1))
    user_id = callback.from_user.id
    user_language = get_user_language(user_id) or "uk"
    await state.update_data(auto_sig_from_copy=from_copy)
    payload = _auto_signature_manage_screen_content(
        signature_id, user_id, user_language, from_copy_manage=from_copy
    )
    if not payload:
        await callback.answer("❌ Автопідпис не знайдено")
        return
    message_text, keyboard = payload
    if await _edit_auto_signature_screen(callback, message_text, keyboard):
        await callback.answer()


@router.callback_query(F.data.startswith("auto_signature_create_"))
async def auto_signature_create(callback: types.CallbackQuery, state: FSMContext):
    base, from_copy = _strip_auto_sig_cpy(callback.data)
    channel_id = int(base.removeprefix("auto_signature_create_"))
    user_id = callback.from_user.id
    user_language = get_user_language(user_id) or "uk"
    await state.update_data(auto_sig_from_copy=from_copy)
    auto_signature_data[user_id] = {"channel_id": channel_id}
    create_text_prompts = {
        "uk": f"{E.sign} <b>СТВОРЕННЯ АВТОПІДПИСУ</b>\n\nВведіть текст автопідпису:"
    }
    await callback.message.edit_text(
        text=create_text_prompts.get(user_language, create_text_prompts["uk"]),
        parse_mode="HTML",
        reply_markup=get_back_to_auto_signature_keyboard(
            channel_id, from_copy_manage=from_copy
        ),
    )
    await state.set_state(AutoSignatureSettings.waiting_for_text)
    await callback.answer()


@router.callback_query(F.data.startswith("auto_signature_edit_"))
async def auto_signature_edit(callback: types.CallbackQuery, state: FSMContext):
    base, from_copy = _strip_auto_sig_cpy(callback.data)
    m = re.fullmatch("auto_signature_edit_(\\d+)_(-?\\d+)", base)
    if not m:
        await callback.answer("❌ Некоректні дані")
        return
    signature_id = int(m.group(1))
    channel_id = int(m.group(2))
    user_id = callback.from_user.id
    user_language = get_user_language(user_id) or "uk"
    await state.update_data(auto_sig_from_copy=from_copy)
    signature_info = get_auto_signature_by_id(signature_id)
    if not signature_info:
        await callback.answer("❌ Автопідпис не знайдено")
        return
    signature_name = signature_info[2]
    signature_text = signature_info[3]
    auto_signature_data[user_id] = {
        "channel_id": channel_id,
        "signature_id": signature_id,
        "name": signature_name,
        "text": signature_text,
        "is_editing": True,
    }
    preview_text = safe_truncate_html(signature_text)
    edit_text_prompts = {
        "uk": f"{E.sign} <b>РЕДАГУВАННЯ АВТОПІДПИСУ</b>\n\n💬 <b>Поточний текст:</b>\n{preview_text}\n\nВведіть новий текст автопідпису:"
    }
    await callback.message.edit_text(
        text=edit_text_prompts.get(user_language, edit_text_prompts["uk"]),
        parse_mode="HTML",
        reply_markup=get_back_to_auto_signature_keyboard(
            channel_id, from_copy_manage=from_copy
        ),
        disable_web_page_preview=True,
    )
    await state.set_state(AutoSignatureSettings.waiting_for_text)
    await callback.answer()


@router.callback_query(
    F.data.startswith("auto_signature_delete_")
    & ~F.data.startswith("auto_signature_delete_confirmed_")
    & ~F.data.startswith("auto_signature_delete_confirm_")
)
async def auto_signature_delete(callback: types.CallbackQuery, state: FSMContext):
    base, from_copy = _strip_auto_sig_cpy(callback.data)
    m = re.fullmatch("auto_signature_delete_(\\d+)", base)
    if not m:
        await callback.answer("❌ Некоректні дані")
        return
    signature_id = int(m.group(1))
    user_id = callback.from_user.id
    user_language = get_user_language(user_id) or "uk"
    await state.update_data(auto_sig_from_copy=from_copy)
    signature_info = get_auto_signature_by_id(signature_id)
    if not signature_info:
        await callback.answer("❌ Автопідпис не знайдено")
        return
    channel_id = signature_info[1]
    signature_name = signature_info[2]
    confirm_texts = {
        "uk": {
            "title": "❗️ Підтвердження видалення",
            "message": f"Ви впевнені, що хочете видалити автопідпис «{html.escape(signature_name)}»?",
            "confirm": "Так, видалити",
            "cancel": "Ні, скасувати",
        }
    }
    text = confirm_texts.get(user_language, confirm_texts["uk"])
    sfx = _AUTO_SIG_CPY_SUFFIX if from_copy else ""
    keyboard = [
        [
            InlineKeyboardButton(
                text=text["confirm"],
                callback_data=f"auto_signature_delete_confirmed_{signature_id}{sfx}",
                icon_custom_emoji_id=Icon.trash,
            ),
            InlineKeyboardButton(
                text=text["cancel"],
                callback_data=f"auto_signature_settings_{channel_id}{sfx}",
                icon_custom_emoji_id=Icon.cancel,
            ),
        ]
    ]
    await callback.message.edit_text(
        f"{text['title']}\n\n{text['message']}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("auto_signature_delete_confirmed_"))
async def auto_signature_delete_confirmed(
    callback: types.CallbackQuery, state: FSMContext
):
    base, from_copy = _strip_auto_sig_cpy(callback.data)
    m = re.fullmatch("auto_signature_delete_confirmed_(\\d+)", base)
    if not m:
        await callback.answer("❌ Некоректні дані")
        return
    signature_id = int(m.group(1))
    user_id = callback.from_user.id
    user_language = get_user_language(user_id) or "uk"
    await state.update_data(auto_sig_from_copy=from_copy)
    signature_info = get_auto_signature_by_id(signature_id)
    if not signature_info:
        await callback.answer("❌ Автопідпис не знайдено")
        return
    channel_id = signature_info[1]
    delete_auto_signature(signature_id)
    signatures = get_auto_signatures(channel_id)
    channel_info = get_channel_by_id(channel_id, user_id=user_id)
    if not channel_info:
        await callback.answer("❌ Канал не знайдено")
        return
    feedback_texts = {"uk": "✅ Автопідпис видалено"}
    if signatures:
        sid = signatures[0][0]
        payload = _auto_signature_manage_screen_content(
            sid, user_id, user_language, from_copy_manage=from_copy
        )
        if not payload:
            await callback.answer("❌ Канал не знайдено")
            return
        message_text, keyboard = payload
    else:
        message_text = _auto_signature_empty_screen_text(
            channel_id, user_id, user_language
        )
        if not message_text:
            await callback.answer("❌ Канал не знайдено")
            return
        keyboard = get_auto_signature_create_keyboard(
            channel_id, from_copy_manage=from_copy
        )
    await callback.message.edit_text(
        text=message_text,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    await callback.answer(feedback_texts.get(user_language, feedback_texts["uk"]))


def get_auto_signature_delete_keyboard(signature_id: int, language: str = "uk"):
    texts = {"uk": {"yes": "Так, видалити", "no": "Скасувати"}}
    text = texts.get(language, texts["uk"])
    keyboard = [
        [
            InlineKeyboardButton(
                text=text["yes"],
                callback_data=f"auto_signature_delete_confirm_{signature_id}",
                icon_custom_emoji_id=Icon.trash,
            ),
            InlineKeyboardButton(
                text=text["no"],
                callback_data=f"auto_signature_manage_{signature_id}",
                icon_custom_emoji_id=Icon.cancel,
            ),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.callback_query(F.data.startswith("auto_signature_delete_confirm_"))
async def auto_signature_delete_execute(
    callback: types.CallbackQuery, state: FSMContext
):
    signature_id = int(callback.data.split("_")[4])
    user_id = callback.from_user.id
    user_language = get_user_language(user_id) or "uk"
    fsm_data = await state.get_data()
    from_copy = bool(fsm_data.get("auto_sig_from_copy", False))
    texts = {
        "deleted_success": "✅ <b>Автопідпис успішно видалено!</b>",
        "save_cancelled": "❌ <b>Збереження автопідпису скасовано</b>",
    }
    signature_info = get_auto_signature_by_id(signature_id)
    if not signature_info:
        await callback.answer("❌ Автопідпис не знайдено")
        return
    channel_id = signature_info[1]
    success = delete_auto_signature(signature_id)
    if success:
        await callback.message.edit_text(
            text=texts["deleted_success"], parse_mode="HTML"
        )
        await asyncio.sleep(2)
        channel_info = get_channel_by_id(channel_id, user_id=user_id)
        if not channel_info:
            await callback.answer("❌ Канал не знайдено")
            return
        signatures = get_auto_signatures(channel_id)
        if signatures:
            sid = signatures[0][0]
            payload = _auto_signature_manage_screen_content(
                sid, user_id, user_language, from_copy_manage=from_copy
            )
            if not payload:
                await callback.answer("❌ Канал не знайдено")
                return
            message_text, keyboard = payload
        else:
            message_text = _auto_signature_empty_screen_text(
                channel_id, user_id, user_language
            )
            if not message_text:
                await callback.answer("❌ Канал не знайдено")
                return
            keyboard = get_auto_signature_create_keyboard(
                channel_id, from_copy_manage=from_copy
            )
        await callback.message.edit_text(
            text=message_text,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
        await callback.answer()
    else:
        await callback.answer("❌ Помилка при видаленні")


@router.message(AutoSignatureSettings.waiting_for_text)
async def auto_signature_text_received(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_language = get_user_language(user_id) or "uk"
    signature_text = message.text.strip()
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    except:
        pass
    if not signature_text:
        error_msg = await message.answer("❌ Текст не може бути порожнім")
        await asyncio.sleep(3)
        try:
            await bot.delete_message(
                chat_id=message.chat.id, message_id=error_msg.message_id
            )
        except:
            pass
        return
    if message.entities:
        signature_text_html = convert_entities_to_html(signature_text, message.entities)
    else:
        signature_text_html = signature_text
    auto_generated_name = generate_signature_name_from_text(signature_text_html)
    auto_signature_data[user_id]["text"] = signature_text_html
    auto_signature_data[user_id]["name"] = auto_generated_name
    preview_text = safe_truncate_html(signature_text_html)
    is_editing = auto_signature_data[user_id].get("is_editing", False)
    if is_editing:
        confirmation_base_texts = {
            "uk": f"{E.sign} <b>Підтвердження оновлення</b>\n\n💬 <b>Прев'ю автопідпису:</b>\n{text}\n\n❓ Зберегти зміни?"
        }
    else:
        confirmation_base_texts = {
            "uk": "✅ <b>Підтвердження збереження</b>\n\n💬 <b>Прев'ю автопідпису:</b>\n{text}\n\n❓ Зберегти автопідпис?"
        }
    confirmation_text = confirmation_base_texts.get(
        user_language, confirmation_base_texts["uk"]
    ).format(text=preview_text)
    keyboard = get_auto_signature_save_keyboard()
    await message.answer(
        text=confirmation_text,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    await state.set_state(AutoSignatureSettings.confirming_save)


@router.callback_query(F.data == "auto_signature_save")
async def auto_signature_save(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_language = get_user_language(user_id) or "uk"
    texts = {
        "deleted_success": "✅ <b>Автопідпис успішно видалено!</b>",
        "save_cancelled": "❌ <b>Збереження автопідпису скасовано</b>",
    }
    fsm_data = await state.get_data()
    from_copy_manage = bool(fsm_data.get("auto_sig_from_copy", False))
    if user_id not in auto_signature_data:
        await callback.answer("❌ Дані втрачено, спробуйте ще раз")
        return
    data = auto_signature_data[user_id]
    channel_id = data["channel_id"]
    signature_name = data["name"]
    signature_text = data["text"]
    is_editing = data.get("is_editing", False)
    signature_id = data.get("signature_id")
    try:
        if is_editing and signature_id:
            success = update_auto_signature(
                signature_id, signature_name, signature_text
            )
        else:
            success = add_auto_signature(channel_id, signature_name, signature_text)
    except Exception:
        await callback.answer("❌ Помилка при збереженні")
        return
    if success:
        if is_editing:
            success_texts = {"uk": "✅ <b>Автопідпис успішно оновлено!</b>"}
        else:
            success_texts = {"uk": "✅ <b>Автопідпис успішно створено!</b>"}
        success_text = success_texts.get(user_language, success_texts["uk"])
        await callback.message.edit_text(text=success_text, parse_mode="HTML")
        del auto_signature_data[user_id]
        await state.clear()
        await asyncio.sleep(1)
        channel_info = get_channel_by_id(channel_id, user_id=user_id)
        if not channel_info:
            await callback.answer("❌ Канал не знайдено")
            return
        signatures = get_auto_signatures(channel_id)
        if signatures:
            sid = signatures[0][0]
            payload = _auto_signature_manage_screen_content(
                sid, user_id, user_language, from_copy_manage=from_copy_manage
            )
            if not payload:
                await callback.answer("❌ Канал не знайдено")
                return
            message_text, keyboard = payload
        else:
            message_text = _auto_signature_empty_screen_text(
                channel_id, user_id, user_language
            )
            if not message_text:
                await callback.answer("❌ Канал не знайдено")
                return
            keyboard = get_auto_signature_create_keyboard(
                channel_id, from_copy_manage=from_copy_manage
            )
        await callback.message.edit_text(
            text=message_text,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
        await callback.answer()
    else:
        if is_editing:
            error_texts = {"uk": "❌ Помилка при оновленні автопідпису"}
        else:
            error_texts = {"uk": "❌ Помилка при створенні автопідпису"}
        error_text = error_texts.get(user_language, error_texts["uk"])
        await callback.answer(error_text)


@router.callback_query(F.data == "auto_signature_cancel")
async def auto_signature_cancel(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_language = get_user_language(user_id) or "uk"
    texts = {
        "deleted_success": "✅ <b>Автопідпис успішно видалено!</b>",
        "save_cancelled": "❌ <b>Збереження автопідпису скасовано</b>",
    }
    fsm_data = await state.get_data()
    from_copy_manage = bool(fsm_data.get("auto_sig_from_copy", False))
    if user_id in auto_signature_data:
        channel_id = auto_signature_data[user_id]["channel_id"]
        del auto_signature_data[user_id]
    else:
        await callback.answer("❌ Дані втрачено")
        return
    await state.clear()
    await callback.message.edit_text(text=texts["save_cancelled"], parse_mode="HTML")
    await asyncio.sleep(1)
    channel_info = get_channel_by_id(channel_id, user_id=user_id)
    if not channel_info:
        await callback.answer("❌ Канал не знайдено")
        return
    signatures = get_auto_signatures(channel_id)
    if signatures:
        sid = signatures[0][0]
        payload = _auto_signature_manage_screen_content(
            sid, user_id, user_language, from_copy_manage=from_copy_manage
        )
        if not payload:
            await callback.answer("❌ Канал не знайдено")
            return
        message_text, keyboard = payload
    else:
        message_text = _auto_signature_empty_screen_text(
            channel_id, user_id, user_language
        )
        if not message_text:
            await callback.answer("❌ Канал не знайдено")
            return
        keyboard = get_auto_signature_create_keyboard(
            channel_id, from_copy_manage=from_copy_manage
        )
    await callback.message.edit_text(
        text=message_text,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    await callback.answer()
