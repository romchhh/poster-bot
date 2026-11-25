"""Фонова перевірка: чи схвалено запит на вхід у закритий канал-донор."""

from __future__ import annotations

import html
import logging

from aiogram import Bot

from database_functions.copy_mirror_db import (
    delete_copy_mirror_donor_pending,
    list_pending_copy_mirror_donor_joins,
    try_add_copy_donor,
)
from keyboards.client_keyboards.client_keyboards import get_start_keyboard
from keyboards.client_keyboards.copy_mirror_keyboards import get_copy_manage_keyboard

from .telethon_copy_client import get_telethon_client
from .copy_donor_join import JoinDonorKind, check_invite_already_member
from .copy_mirror_format import format_manage_html

logger = logging.getLogger(__name__)


async def deliver_manage_ui_plain(
    tg_bot: Bot,
    chat_id: int,
    user_id: int,
    scope_type: str,
    scope_id: int,
    *,
    success_intro: str | None = None,
):
    """Показує керування копіюванням без оновлення FSM (для фону)."""
    from aiogram.types import ReplyKeyboardRemove

    txt = format_manage_html(
        user_id, scope_type, scope_id, success_dest_html=success_intro
    )
    sent = await tg_bot.send_message(
        chat_id,
        txt,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=ReplyKeyboardRemove(),
    )
    try:
        await tg_bot.edit_message_reply_markup(
            chat_id=sent.chat.id,
            message_id=sent.message_id,
            reply_markup=get_copy_manage_keyboard(
                scope_type, scope_id, user_id=user_id
            ),
        )
    except Exception:
        logger.exception("deliver_manage_ui_plain edit reply markup")
    await tg_bot.send_message(
        chat_id, "Головне меню:", reply_markup=get_start_keyboard(user_id)
    )


async def poll_pending_copy_mirror_donors(bot: Bot) -> None:
    client = await get_telethon_client()
    if not client:
        return
    rows = list_pending_copy_mirror_donor_joins()
    if not rows:
        return
    for row in rows:
        (
            pending_id,
            user_id,
            scope_type,
            scope_id,
            _fingerprint,
            invite_hash,
            _preview_title,
            notify_chat_id,
            notify_message_id,
            _created,
        ) = row
        if not invite_hash:
            continue
        try:
            outcome = await check_invite_already_member(client, invite_hash)
        except Exception:
            logger.exception("check_invite_already_member poll")
            continue
        if outcome is None or outcome.kind != JoinDonorKind.JOINED:
            continue
        if not outcome.channel_id:
            continue

        delete_copy_mirror_donor_pending(int(pending_id))
        title = outcome.title or str(outcome.channel_id)
        inserted = try_add_copy_donor(
            user_id, scope_type, int(scope_id), int(outcome.channel_id), title,
        )
        intro = (
            f"Канал-донор підключено: <b>{html.escape(title)}</b>"
            if inserted
            else "Канал уже був у списку донорів — запит схвалено."
        )
        try:
            await bot.edit_message_text(
                chat_id=notify_chat_id,
                message_id=notify_message_id,
                text=(
                    f"{intro}\n\n"
                    "<i>Налаштування каналу оновлено нижче.</i>"
                ),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception:
            logger.exception("edit pending donor message")
        try:
            await deliver_manage_ui_plain(
                bot,
                notify_chat_id,
                user_id,
                scope_type,
                int(scope_id),
                success_intro=intro,
            )
        except Exception:
            logger.exception("deliver_manage after pending donor")
