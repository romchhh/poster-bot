"""Delete the latest published post of a channel or of every channel in a folder."""

from __future__ import annotations

import html
import re

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.runtime import bot
from database_functions.channels_db import get_channel_by_id, get_channels_by_folder
from database_functions.folders_db import get_folder_by_id
from database_functions.posts_db import (
    add_post_deletion_log,
    get_last_published_post,
    list_post_deletion_log,
    mark_published_post_deleted,
)
from texts import Settings
from utils.datetime_ui import format_user_datetime
from utils.ui_emoji import E, Icon

router = Router()

_STATUS_LABEL = {
    "deleted": "видалено",
    "already_gone": "уже відсутній у каналі",
    "error": "помилка",
}


def _plain(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _message_ids(post: dict) -> list[int]:
    settings = post.get("settings") or {}
    stored = settings.get("message_ids") or []
    ids = [int(item) for item in stored if item]
    if post.get("message_id") and int(post["message_id"]) not in ids:
        ids.insert(0, int(post["message_id"]))
    return ids


async def _remove_messages(channel_id: int, message_ids: list[int]) -> tuple[str, str]:
    gone = 0
    for message_id in message_ids:
        try:
            await bot.delete_message(channel_id, message_id)
        except TelegramBadRequest as exc:
            err = str(exc).lower()
            if "not found" in err:
                gone += 1
                continue
            return "error", str(exc)
        except Exception as exc:
            return "error", str(exc)
    if gone == len(message_ids) and message_ids:
        return "already_gone", ""
    return "deleted", ""


def _confirm_text(channel_title: str, post: dict) -> str:
    snippet = html.escape(_plain(post.get("post_text") or "")[:120] or "без тексту")
    return (
        f"<b>Видалити останній пост?</b>\n\n"
        f"Канал: <b>{html.escape(channel_title)}</b>\n"
        f"Час: <code>{html.escape(format_user_datetime(post.get('published_date')))}</code>\n"
        f"message_id: <code>{post.get('message_id')}</code>\n\n"
        f"{snippet}"
    )


@router.callback_query(F.data.startswith("del_last_post:"))
async def delete_last_post_ask(callback: types.CallbackQuery) -> None:
    channel_id = int(callback.data.split(":")[1])
    channel = get_channel_by_id(channel_id, callback.from_user.id)
    if not channel:
        await callback.answer("Канал не знайдено", show_alert=True)
        return
    post = get_last_published_post(channel_id)
    if not post or post.get("is_deleted"):
        await callback.answer("Останнього поста в журналі немає", show_alert=True)
        return
    await callback.message.edit_text(
        _confirm_text(channel[2] or "Канал", post),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=Settings.yes_delete,
                        callback_data=f"del_last_ok:{post['id']}",
                        icon_custom_emoji_id=Icon.trash,
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Назад",
                        callback_data=f"channel_settings_{channel_id}",
                        icon_custom_emoji_id=Icon.back,
                    )
                ],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("del_last_ok:"))
async def delete_last_post_confirm(callback: types.CallbackQuery) -> None:
    post_id = int(callback.data.split(":")[1])
    from database_functions.connection import cursor

    cursor.execute(
        """
        SELECT id, user_id, channel_id, message_id, post_text, published_date, settings, is_deleted
        FROM posts WHERE id = ?
        """,
        (post_id,),
    )
    row = cursor.fetchone()
    if not row:
        await callback.answer("Пост не знайдено", show_alert=True)
        return
    from database_functions.posts_db import _safe_json_loads

    post = {
        "id": row[0],
        "channel_id": row[2],
        "message_id": row[3],
        "post_text": row[4] or "",
        "published_date": row[5] or "",
        "settings": _safe_json_loads(row[6], default={}),
        "is_deleted": bool(row[7]),
    }
    channel = get_channel_by_id(post["channel_id"])
    title = channel[2] if channel else str(post["channel_id"])
    if post["is_deleted"]:
        status, detail = "already_gone", ""
    else:
        status, detail = await _remove_messages(post["channel_id"], _message_ids(post))
        if status in {"deleted", "already_gone"}:
            mark_published_post_deleted(post["id"])
    add_post_deletion_log(
        user_id=callback.from_user.id,
        channel_id=post["channel_id"],
        message_id=post["message_id"],
        post_row_id=post["id"],
        published_date=post["published_date"],
        status=status,
        detail=detail,
    )
    label = _STATUS_LABEL.get(status, status)
    await callback.message.edit_text(
        f"{'✅' if status != 'error' else '❌'} <b>{html.escape(title)}</b>\n"
        f"message_id <code>{post['message_id']}</code>: {label}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=Settings.deletion_log,
                        callback_data=f"del_log:{post['channel_id']}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="До каналу",
                        callback_data=f"channel_settings_{post['channel_id']}",
                        icon_custom_emoji_id=Icon.back,
                    )
                ],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("del_log:"))
async def deletion_log(callback: types.CallbackQuery) -> None:
    channel_id = int(callback.data.split(":")[1])
    channel = get_channel_by_id(channel_id)
    title = html.escape(channel[2] if channel else str(channel_id))
    rows = list_post_deletion_log(channel_id)
    if not rows:
        body = "Журнал порожній."
    else:
        lines = []
        for deleted_at, status, message_id, published_date, detail in rows:
            label = _STATUS_LABEL.get(status, status)
            extra = f" · {html.escape(detail[:80])}" if detail and status == "error" else ""
            lines.append(
                f"• {format_user_datetime(deleted_at)} — {label}\n"
                f"  msg <code>{message_id}</code>, опубліковано "
                f"{format_user_datetime(published_date)}{extra}"
            )
        body = "\n".join(lines)
    await callback.message.edit_text(
        f"{E.list} <b>Журнал видалень</b>\n{title}\n\n{body}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="До каналу",
                        callback_data=f"channel_settings_{channel_id}",
                        icon_custom_emoji_id=Icon.back,
                    )
                ]
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("del_last_folder:"))
async def delete_last_folder_ask(callback: types.CallbackQuery) -> None:
    folder_id = int(callback.data.split(":")[1])
    folder = get_folder_by_id(folder_id)
    if not folder:
        await callback.answer("Папку не знайдено", show_alert=True)
        return
    lines = []
    found = 0
    for channel in get_channels_by_folder(folder_id):
        post = get_last_published_post(channel[1])
        if not post or post.get("is_deleted"):
            continue
        found += 1
        lines.append(
            f"• {html.escape(channel[2] or 'Канал')} — "
            f"{html.escape(format_user_datetime(post['published_date']))}, "
            f"msg <code>{post['message_id']}</code>"
        )
    if not found:
        await callback.answer("У папці немає постів для видалення", show_alert=True)
        return
    preview = "\n".join(lines[:12])
    await callback.message.edit_text(
        f"<b>Видалити останній пост з усіх каналів?</b>\n\n"
        f"Папка: <b>{html.escape(folder[1])}</b>\n"
        f"Каналів: {found}\n\n{preview}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=Settings.yes_delete,
                        callback_data=f"del_last_folder_ok:{folder_id}",
                        icon_custom_emoji_id=Icon.trash,
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Назад",
                        callback_data=f"settings_folder_panel:{folder_id}",
                        icon_custom_emoji_id=Icon.back,
                    )
                ],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("del_last_folder_ok:"))
async def delete_last_folder_confirm(callback: types.CallbackQuery) -> None:
    folder_id = int(callback.data.split(":")[1])
    deleted = gone = errors = 0
    for channel in get_channels_by_folder(folder_id):
        post = get_last_published_post(channel[1])
        if not post or post.get("is_deleted"):
            continue
        status, detail = await _remove_messages(channel[1], _message_ids(post))
        if status in {"deleted", "already_gone"}:
            mark_published_post_deleted(post["id"])
        add_post_deletion_log(
            user_id=callback.from_user.id,
            channel_id=channel[1],
            message_id=post["message_id"],
            post_row_id=post["id"],
            published_date=post["published_date"],
            status=status,
            detail=detail,
        )
        if status == "deleted":
            deleted += 1
        elif status == "already_gone":
            gone += 1
        else:
            errors += 1
    await callback.message.edit_text(
        "<b>Готово</b>\n\n"
        f"Видалено: {deleted}\n"
        f"Уже відсутні в каналі: {gone}\n"
        f"Помилки: {errors}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="До папки",
                        callback_data=f"settings_folder_panel:{folder_id}",
                        icon_custom_emoji_id=Icon.back,
                    )
                ]
            ]
        ),
    )
    await callback.answer()
