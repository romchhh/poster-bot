from __future__ import annotations

from utils.ui_emoji import E, Icon
from texts import Main
import asyncio
import html
from datetime import datetime

from aiogram import Router, F, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.runtime import bot
from database_functions.client_db import update_user_activity
from database_functions.channels_db import get_channel_by_id
from keyboards.client_keyboards.post_keyboards import (
    get_post_editing_keyboard,
    get_step_cancel_keyboard,
    get_url_buttons_prompt_keyboard,
)
from utils.entity_parser import convert_entities_to_html
from utils.message_html import safe_truncate_html
from texts.messages.post import URL_BUTTONS_INSTRUCTION
from utils.album import album_to_post_parts, clear_url_buttons, take_album
from utils.post_utils import (
    MAX_URL_BUTTONS,
    apply_palette_style,
    parse_url_buttons_with_entities,
    send_post_preview,
    url_button_count,
    validate_post_data,
)
from states.client_states import PostEditing


router = Router()

_IGNORE_TEXTS = {
    "/start", "/help", "Налаштування", "Настройки", "Settings",
    "Контент-план", "Контент план", "Адмін панель",
    "Редагувати пост", "Редактировать пост", "Edit Post",
    "Допомога", "Помощь", "Автолінкування", "Автолинкование",
    "Додати канал", "Добавить канал", "Создать пост", "Створити пост",
    "Клонування", "Клонирование", "Back to menu",
    "Копіювання",
    "Пошук постів",
}


# ---------------------------------------------------------------------------
# Старт
# ---------------------------------------------------------------------------

@router.message(F.text.in_([Main.edit_post, "Редактировать пост", "Edit Post", "/edit_post"]))
async def start_edit_post(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    update_user_activity(user_id)
    await state.clear()

    msg = await message.answer(
        text=(
            f"{E.sign} <b>Редагування поста</b>\n\n"
            "Перешліть пост із каналу, який хочете відредагувати.\n\n"
            "<i>💡 Пост має бути переслано саме з каналу — не з чату.</i>"
        ),
        parse_mode="HTML",
    )
    await state.update_data(request_message_id=msg.message_id)
    await state.set_state(PostEditing.waiting_for_forwarded_post)


# ---------------------------------------------------------------------------
# Отримання пересланого поста
# ---------------------------------------------------------------------------

@router.message(
    PostEditing.waiting_for_forwarded_post,
    ~F.text.in_(_IGNORE_TEXTS),
)
async def forwarded_post_received(message: types.Message, state: FSMContext):
    album = await take_album(message)
    if album is None:
        return

    leader = album[0]
    if not leader.forward_from_chat:
        err = await message.answer(
            "❌ Це не пересланий пост з каналу.\n\nПерешліть повідомлення прямо з каналу.",
            parse_mode="HTML",
        )
        await state.update_data(request_message_id=err.message_id)
        return

    channel_id = leader.forward_from_chat.id
    source_ids: list[int] = []
    source_types: list[str] = []
    for item in album:
        if not item.forward_from_chat or item.forward_from_chat.id != channel_id:
            await message.answer(
                "❌ Усі файли групи мають бути переслані з одного каналу.",
                parse_mode="HTML",
            )
            return
        if item.forward_from_message_id:
            source_ids.append(item.forward_from_message_id)
        text, files, _trimmed = album_to_post_parts([item])
        source_types.append(files[0]["type"] if files else "text")

    original_message_id = source_ids[0] if source_ids else leader.forward_from_message_id

    channel_info = get_channel_by_id(channel_id)
    if not channel_info:
        err = await message.answer(
            "❌ <b>Канал не знайдено</b>\n\n"
            "Цей канал не підключений до бота. Додайте його через «Додати канал».",
            parse_mode="HTML",
        )
        await asyncio.sleep(6)
        try:
            await bot.delete_message(message.chat.id, err.message_id)
        except Exception:
            pass
        return

    channel_title = channel_info[2]
    channel_link = channel_info[4] if len(channel_info) > 4 and channel_info[4] else ""
    text, media_files, trimmed = album_to_post_parts(album)

    post_data: dict = {
        "channel_id": channel_id,
        "original_message_id": original_message_id,
        "source_message_ids": source_ids,
        "source_media_types": source_types,
        "channel_title": channel_title,
        "channel_link": channel_link,
        "text": text,
        "media_files": media_files,
        "url_buttons": [],
        "settings": {
            "notification": True,
            "pin_message": False,
            "disable_comments": False,
        },
    }

    if len(media_files) <= 1 and leader.reply_markup and leader.reply_markup.inline_keyboard:
        rows = []
        for row in leader.reply_markup.inline_keyboard:
            btn_row = [b for b in row if b.url]
            if btn_row:
                rows.append(btn_row)
        if rows:
            post_data["url_buttons"] = rows

    await state.update_data(edit_post_data=post_data)
    if trimmed:
        await message.answer("У групі більше 10 файлів — збережено перші 10.")

    # Показуємо превʼю
    try:
        await send_post_preview(bot, message.chat.id, post_data)
    except Exception as exc:
        print(f"[edit_post] preview error: {exc}")

    await message.answer(
        text="Як ви хочете змінити цей пост?",
        parse_mode="HTML",
        reply_markup=_editing_keyboard(post_data),
        disable_web_page_preview=True,
    )
    await state.set_state(PostEditing.editing_post)


# ---------------------------------------------------------------------------
# Редактор — той самий що у PostCreation, але зі своїм станом
# ---------------------------------------------------------------------------

def _editing_keyboard(post_data: dict) -> InlineKeyboardMarkup:
    """Клавіатура редактора (аналог get_post_editing_keyboard з нашим «Далі»)."""
    has_text = bool(post_data.get("text"))
    has_media = bool(post_data.get("media_files"))
    has_url = bool(post_data.get("url_buttons"))
    album = len(post_data.get("media_files") or []) > 1
    settings = post_data.get("settings", {})

    text_btn = "Редагувати текст" if has_text else "Додати текст"
    media_btn = "Редагувати медіа" if has_media else "Додати медіа"
    url_btn = "Редагувати кнопки" if has_url else "Додати кнопки"
    pin_txt = "Закріпити"
    notify_on = settings.get("notification", True)
    notify_txt = "Звук"
    comments_txt = "Коментарі"

    rows = [
            [
                InlineKeyboardButton(
                    text=text_btn,
                    callback_data="ep_edit_text",
                    icon_custom_emoji_id=Icon.sign if has_text else Icon.add,
                ),
                InlineKeyboardButton(
                    text=media_btn,
                    callback_data="ep_edit_media",
                    icon_custom_emoji_id=Icon.photo if has_media else Icon.add,
                ),
            ],
    ]
    if not album:
        rows.append(
            [
                InlineKeyboardButton(
                    text=url_btn,
                    callback_data="ep_edit_url_buttons",
                    icon_custom_emoji_id=Icon.link if has_url else Icon.add,
                )
            ]
        )
    rows.extend([
            [
                InlineKeyboardButton(
                    text=pin_txt,
                    callback_data="ep_toggle_pin",
                    icon_custom_emoji_id=Icon.ok if settings.get("pin_message") else Icon.pin,
                ),
                InlineKeyboardButton(
                    text=notify_txt,
                    callback_data="ep_toggle_notification",
                    icon_custom_emoji_id=Icon.spark if notify_on else Icon.bell_off,
                ),
                InlineKeyboardButton(
                    text=comments_txt,
                    callback_data="ep_toggle_comments",
                    icon_custom_emoji_id=Icon.ok if not settings.get("disable_comments") else Icon.chat,
                ),
            ],
            [
                InlineKeyboardButton(text="Скасувати", icon_custom_emoji_id=Icon.cancel, callback_data="ep_cancel"),
                InlineKeyboardButton(text="Далі", callback_data="ep_next", icon_custom_emoji_id=Icon.next),
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _refresh_editor(target: types.Message, post_data: dict):
    """Відправляє свіже превʼю і повертає редактор."""
    try:
        await send_post_preview(bot, target.chat.id, post_data)
    except Exception as exc:
        print(f"[edit_post] preview error: {exc}")
    await target.answer(
        text=f"{E.tools} <b>Редагування поста</b>",
        parse_mode="HTML",
        reply_markup=_editing_keyboard(post_data),
    )


@router.callback_query(F.data == "ep_step_cancel")
async def ep_step_cancel(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_data = data.get("edit_post_data") or {}
    await state.set_state(PostEditing.editing_post)
    await callback.message.edit_text(
        text=f"{E.tools} <b>Редагування поста</b>",
        parse_mode="HTML",
        reply_markup=_editing_keyboard(post_data),
    )
    await callback.answer()


# ---- Редагування тексту ----

@router.callback_query(F.data == "ep_edit_text", PostEditing.editing_post)
async def ep_edit_text_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"{E.sign} <b>Новий текст поста</b>\n\nНадішліть текст (HTML-форматування підтримується):",
        parse_mode="HTML",
        reply_markup=get_step_cancel_keyboard("ep_step_cancel"),
    )
    await state.set_state(PostEditing.waiting_for_text)
    await callback.answer()


@router.message(PostEditing.waiting_for_text)
async def ep_text_received(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_data: dict = data.get("edit_post_data", {})
    post_data["text"] = convert_entities_to_html(message.text or "", message.entities)
    await state.update_data(edit_post_data=post_data)
    await _refresh_editor(message, post_data)
    await state.set_state(PostEditing.editing_post)


# ---- Редагування медіа ----

@router.callback_query(F.data == "ep_edit_media", PostEditing.editing_post)
async def ep_edit_media_start(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    has_url = bool(data.get("edit_post_data", {}).get("url_buttons"))
    if has_url:
        text = (
            "🖼 <b>Нове медіа</b>\n\n"
            "⚠️ У посту є кнопки — надішліть тільки <b>одне</b> фото або відео."
        )
    else:
        text = (
            "🖼 <b>Нове медіа</b>\n\n"
            "Надішліть одне фото, відео, документ або медіагрупу до 10 файлів."
        )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_step_cancel_keyboard("ep_step_cancel"),
    )
    await state.set_state(PostEditing.waiting_for_media)
    await callback.answer()


@router.message(PostEditing.waiting_for_media)
async def ep_media_received(message: types.Message, state: FSMContext):
    album = await take_album(message)
    if album is None:
        return

    data = await state.get_data()
    post_data: dict = data.get("edit_post_data", {})
    text, media_files, trimmed = album_to_post_parts(album)
    if not media_files:
        await message.answer(
            "❌ Надішліть фото, відео, документ або медіагрупу.",
            reply_markup=get_step_cancel_keyboard("ep_step_cancel"),
        )
        return

    if len(media_files) > 1 and post_data.get("url_buttons"):
        await message.answer(
            "⚠️ Надішліть тільки один файл (є кнопки).",
            parse_mode="HTML",
            reply_markup=get_step_cancel_keyboard("ep_step_cancel"),
        )
        return

    if text:
        post_data["text"] = text
    post_data["media_files"] = media_files
    if len(media_files) > 1:
        clear_url_buttons(post_data)
    await state.update_data(edit_post_data=post_data)
    if trimmed:
        await message.answer("У групі більше 10 файлів — збережено перші 10.")
    await _refresh_editor(message, post_data)
    await state.set_state(PostEditing.editing_post)


# ---- Редагування URL-кнопок ----

@router.callback_query(F.data == "ep_edit_url_buttons", PostEditing.editing_post)
async def ep_edit_url_buttons_start(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if len(data.get("edit_post_data", {}).get("media_files", [])) > 1:
        await callback.answer(
            "⚠️ URL-кнопки не можна додати до медіагрупи.",
            show_alert=True,
        )
        return
    await callback.message.edit_text(
        text=URL_BUTTONS_INSTRUCTION,
        parse_mode="HTML",
        reply_markup=get_url_buttons_prompt_keyboard(cancel_callback="ep_step_cancel"),
    )
    await state.set_state(PostEditing.waiting_for_url_buttons)
    await callback.answer()


@router.message(PostEditing.waiting_for_url_buttons)
async def ep_url_buttons_received(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_data: dict = data.get("edit_post_data", {})

    text = (message.text or "").strip()

    if text in (".", "-", "–"):
        post_data["url_buttons"] = []
        post_data["url_buttons_raw_text"] = ""
        post_data["url_buttons_entities"] = []
        await state.update_data(edit_post_data=post_data)
        await _refresh_editor(message, post_data)
        await state.set_state(PostEditing.editing_post)
        return

    entities = message.entities or []
    buttons = parse_url_buttons_with_entities(text, entities)
    if buttons and url_button_count(buttons) > MAX_URL_BUTTONS:
        buttons = None
    else:
        buttons = apply_palette_style(buttons, data.get("url_button_style"))
    if not buttons:
        await message.answer(
            "❌ Неправильний формат.\n\n"
            "Приклад: <code>Сайт - https://example.com</code>",
            parse_mode="HTML",
            reply_markup=get_step_cancel_keyboard("ep_step_cancel"),
        )
        return

    post_data["url_buttons"] = buttons
    post_data["url_buttons_raw_text"] = text
    post_data["url_buttons_entities"] = [
        {
            "type": e.type,
            "offset": e.offset,
            "length": e.length,
            "custom_emoji_id": getattr(e, "custom_emoji_id", None),
        }
        for e in entities
    ]
    await state.update_data(edit_post_data=post_data)
    await _refresh_editor(message, post_data)
    await state.set_state(PostEditing.editing_post)


# ---- Перемикання налаштувань ----

@router.callback_query(F.data.startswith("ep_toggle_"), PostEditing.editing_post)
async def ep_toggle_setting(callback: types.CallbackQuery, state: FSMContext):
    setting_key = callback.data.removeprefix("ep_toggle_")
    data = await state.get_data()
    post_data: dict = data.get("edit_post_data", {})
    settings = post_data.setdefault("settings", {})

    if setting_key == "pin":
        settings["pin_message"] = not settings.get("pin_message", False)
    elif setting_key == "notification":
        settings["notification"] = not settings.get("notification", True)
    elif setting_key == "comments":
        settings["disable_comments"] = not settings.get("disable_comments", False)

    await state.update_data(edit_post_data=post_data)
    await callback.message.edit_reply_markup(reply_markup=_editing_keyboard(post_data))
    await callback.answer("✅ Оновлено")


# ---- Скасування ----

@router.callback_query(F.data == "ep_cancel", PostEditing.editing_post)
async def ep_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ <b>Редагування скасовано.</b>",
        parse_mode="HTML",
    )
    await callback.answer()


# ---- Далі → підтвердження ----

@router.callback_query(F.data == "ep_next", PostEditing.editing_post)
async def ep_next(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_data: dict = data.get("edit_post_data", {})

    is_valid, err_msg = validate_post_data(post_data)
    if not is_valid:
        await callback.answer(err_msg, show_alert=True)
        return

    channel_title = html.escape(post_data.get("channel_title", ""))
    channel_link = post_data.get("channel_link", "")
    msg_id = post_data.get("original_message_id", "?")

    link_part = (
        f'<a href="{html.escape(channel_link)}">{channel_title}</a>'
        if channel_link
        else f"<b>{channel_title}</b>"
    )

    preview_lines = []
    if post_data.get("text"):
        preview_lines.append(safe_truncate_html(post_data["text"], 180))
    media_files = post_data.get("media_files") or []
    if len(media_files) > 1:
        preview_lines.append(f"📎 медіагрупа: {len(media_files)} файлів")
    elif media_files:
        mt = media_files[0].get("type", "")
        icons = {"photo": "🖼", "video": "🎥", "document": "📎", "animation": "🎞", "audio": "🎵"}
        preview_lines.append(f"{icons.get(mt, '📎')} медіафайл")
    if post_data.get("url_buttons"):
        btn_count = sum(len(r) for r in post_data["url_buttons"])
        preview_lines.append(f"🔗 кнопок: {btn_count}")

    preview_text = "\n".join(preview_lines) or "<i>(порожній пост)</i>"

    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Підтвердити редагування",
                    callback_data="ep_confirm",
                icon_custom_emoji_id=Icon.ok,
            ),
            ],
            [
                InlineKeyboardButton(
                    text="Назад",
                    callback_data="ep_back_to_editor",
                icon_custom_emoji_id=Icon.back,
            ),
            ],
        ]
    )

    await callback.message.edit_text(
        text=(
            f"{E.list} <b>Підтвердження редагування</b>\n\n"
            f"{E.channel} Канал: {link_part}\n"
            f"🔢 ID поста: <code>{msg_id}</code>\n\n"
            f"<b>Новий вміст:</b>\n{preview_text}\n\n"
            "⚠️ <i>Пост буде відредаговано на каналі.</i>"
        ),
        parse_mode="HTML",
        reply_markup=confirm_kb,
        disable_web_page_preview=True,
    )
    await state.set_state(PostEditing.confirming_edit)
    await callback.answer()


@router.callback_query(F.data == "ep_back_to_editor", PostEditing.confirming_edit)
async def ep_back_to_editor(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_data: dict = data.get("edit_post_data", {})

    try:
        await send_post_preview(bot, callback.message.chat.id, post_data)
    except Exception:
        pass

    await callback.message.answer(
        text=f"{E.tools} <b>Редагування поста</b>",
        parse_mode="HTML",
        reply_markup=_editing_keyboard(post_data),
    )
    await state.set_state(PostEditing.editing_post)
    await callback.answer()


# ---------------------------------------------------------------------------
# Підтвердження → edit_message на каналі
# ---------------------------------------------------------------------------

def _album_kind(media_type: str) -> str:
    if media_type in {"photo", "video", "animation"}:
        return "visual"
    return media_type


def _can_edit_album_in_place(post_data: dict, media_files: list) -> bool:
    source_ids = [mid for mid in (post_data.get("source_message_ids") or []) if mid]
    source_types = post_data.get("source_media_types") or []
    if len(media_files) < 2 or len(media_files) != len(source_ids) or len(media_files) != len(source_types):
        return False
    editable = {"photo", "video", "animation", "document", "audio"}
    for item, old in zip(media_files, source_types):
        kind = item.get("type") or ""
        if kind not in editable or old not in editable:
            return False
        if _album_kind(kind) != _album_kind(old):
            return False
    return True


async def _edit_album_messages(channel_id: int, source_ids: list, media_files: list, text: str) -> None:
    from aiogram.types import (
        InputMediaAnimation,
        InputMediaAudio,
        InputMediaDocument,
        InputMediaPhoto,
        InputMediaVideo,
    )

    media_map = {
        "photo": InputMediaPhoto,
        "video": InputMediaVideo,
        "document": InputMediaDocument,
        "animation": InputMediaAnimation,
        "audio": InputMediaAudio,
    }
    for index, (mid, item) in enumerate(zip(source_ids, media_files)):
        caption = text if index == 0 else None
        media = media_map[item["type"]](
            media=item["file_id"],
            caption=caption,
            parse_mode="HTML" if caption else None,
        )
        await bot.edit_message_media(chat_id=channel_id, message_id=mid, media=media)


@router.callback_query(F.data == "ep_confirm", PostEditing.confirming_edit)
async def ep_confirm(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_data: dict = data.get("edit_post_data", {})

    channel_id: int = post_data["channel_id"]
    message_id: int = post_data["original_message_id"]
    text: str = post_data.get("text") or ""
    media_files: list = post_data.get("media_files", [])
    url_buttons_raw: str = post_data.get("url_buttons_raw_text", "")
    url_buttons: list = post_data.get("url_buttons", [])
    settings: dict = post_data.get("settings", {})

    # Відновлюємо кнопки з raw_text + entities (якщо треба)
    if url_buttons_raw and not url_buttons:
        from aiogram.types import MessageEntity

        entities_data = post_data.get("url_buttons_entities", [])
        entities = []
        for ed in entities_data:
            e = MessageEntity(type=ed["type"], offset=ed["offset"], length=ed["length"])
            if ed.get("custom_emoji_id"):
                e.custom_emoji_id = ed["custom_emoji_id"]
            entities.append(e)
        url_buttons = parse_url_buttons_with_entities(url_buttons_raw, entities) or []

    if len(media_files) > 1:
        url_buttons = []
    reply_markup = InlineKeyboardMarkup(inline_keyboard=url_buttons) if url_buttons else None
    source_ids = [mid for mid in (post_data.get("source_message_ids") or []) if mid]
    if not source_ids and message_id:
        source_ids = [message_id]

    # Відмітка прогресу
    await callback.message.edit_text(
        "⏳ <b>Відправляю зміни на канал…</b>",
        parse_mode="HTML",
    )

    try:
        if _can_edit_album_in_place(post_data, media_files):
            await _edit_album_messages(channel_id, source_ids, media_files, text)
            message_id = source_ids[0]
        elif len(source_ids) > 1 or len(media_files) > 1:
            for mid in source_ids:
                try:
                    await bot.delete_message(channel_id, mid)
                except Exception:
                    pass
            sent = await send_post_preview(bot, channel_id, post_data)
            if sent is None:
                raise RuntimeError("Не вдалося надіслати оновлений пост")
            message_id = sent.message_id
        elif media_files:
            media = media_files[0]
            from aiogram.types import InputMediaAnimation, InputMediaAudio, InputMediaDocument, InputMediaPhoto, InputMediaVideo

            media_map = {
                "photo": InputMediaPhoto,
                "video": InputMediaVideo,
                "document": InputMediaDocument,
                "animation": InputMediaAnimation,
                "audio": InputMediaAudio,
            }
            MediaClass = media_map.get(media["type"])
            if MediaClass is None or not message_id:
                if message_id:
                    try:
                        await bot.delete_message(channel_id, message_id)
                    except Exception:
                        pass
                sent = await send_post_preview(bot, channel_id, post_data)
                if sent is None:
                    raise RuntimeError("Не вдалося надіслати оновлений пост")
                message_id = sent.message_id
            else:
                input_media = MediaClass(
                    media=media["file_id"],
                    caption=text or None,
                    parse_mode="HTML" if text else None,
                )
                await bot.edit_message_media(
                    chat_id=channel_id,
                    message_id=message_id,
                    media=input_media,
                    reply_markup=reply_markup,
                )
        else:
            await bot.edit_message_text(
                chat_id=channel_id,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )

        channel_title_esc = html.escape(post_data.get("channel_title", ""))
        channel_link = post_data.get("channel_link", "")
        link_part = (
            f'<a href="{html.escape(channel_link)}">{channel_title_esc}</a>'
            if channel_link
            else f"<b>{channel_title_esc}</b>"
        )

        channel_info = get_channel_by_id(channel_id)
        post_link = None
        if channel_info and len(channel_info) > 3 and channel_info[3]:
            post_link = f"https://t.me/{channel_info[3]}/{message_id}"
        else:
            chat_id_str = str(channel_id)
            chat_id_for_link = chat_id_str[4:] if chat_id_str.startswith("-100") else str(abs(channel_id))
            post_link = f"https://t.me/c/{chat_id_for_link}/{message_id}"

        success_kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Відкрити пост", url=post_link, icon_custom_emoji_id=Icon.link)]]
        )

        await callback.message.edit_text(
            text=(
                "✅ <b>Пост успішно відредаговано!</b>\n\n"
                f"{E.channel} Канал: {link_part}"
            ),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=success_kb,
        )

    except TelegramBadRequest as e:
        err = str(e)
        hint = ""
        if "message is not modified" in err:
            hint = "\n\nВміст поста не змінився — оновлення не потрібне."
        elif "message can't be edited" in err:
            hint = "\n\nПост занадто старий або не належить боту."
        elif "message to edit not found" in err:
            hint = "\n\nПост не знайдено на каналі."
        elif "have no rights" in err.lower() or "not enough rights" in err.lower():
            hint = "\n\nУ бота немає прав на редагування. Перевірте права адміна."

        await callback.message.edit_text(
            f"❌ <b>Помилка Telegram</b>\n\n<code>{html.escape(err)}</code>{hint}",
            parse_mode="HTML",
        )

    except Exception as e:
        await callback.message.edit_text(
            f"❌ <b>Невідома помилка</b>\n\n<code>{html.escape(str(e))}</code>",
            parse_mode="HTML",
        )

    finally:
        await state.clear()

    await callback.answer()



