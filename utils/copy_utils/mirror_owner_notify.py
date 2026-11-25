"""DM власнику, коли mirror preview не доходить до групи-отримувача (без спаму)."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from database_functions.copy_mirror_db import (
    SCOPE_FOLDER,
    get_copy_destination,
    mark_mirror_dest_owner_notified,
    mirror_dest_owner_notify_due,
)
from utils.ui_emoji import E

logger = logging.getLogger(__name__)

_OWNER_NOTIFY_COOLDOWN_HOURS = 6.0


def is_mirror_dest_unreachable(exc: BaseException) -> bool:
    parts: list[str] = []
    cur: BaseException | None = exc
    while cur is not None:
        if isinstance(cur, TelegramBadRequest):
            parts.append(cur.message or "")
        parts.append(str(cur))
        cur = cur.__cause__
    text = " ".join(parts).lower()
    markers = (
        "chat not found",
        "chat_not_found",
        "bot was kicked",
        "bot is not a member",
        "group chat was deactivated",
        "need administrator rights",
        "not enough rights",
        "have no rights to send",
    )
    return any(m in text for m in markers)


def _dest_unreachable_html(
    *,
    donor_title: str | None,
    destination_title: str | None,
    destination_group_id: int,
    scope_type: str,
) -> str:
    donor = (donor_title or "канал-донор").strip() or "канал-донор"
    if destination_title and destination_title.strip():
        dest_line = f"<b>{destination_title.strip()}</b>"
    else:
        dest_line = f"<code>{destination_group_id}</code>"
    scope_hint = (
        "налаштуванні копіювання для папки"
        if scope_type == SCOPE_FOLDER
        else "налаштуванні копіювання для каналу"
    )
    return (
        f"{E.warn} <b>Копія не потрапила в групу</b>\n\n"
        f"Донор: {donor}\n"
        f"Група-отримувач: {dest_line}\n\n"
        f"Бот не може писати в цю групу — чат недоступний, бота видалили "
        f"або змінились права.\n\n"
        f"• Додайте бота <b>адміністратором</b> у групу з правом публікації\n"
        f"• Або в {scope_hint} оберіть іншу «групу для копії»\n\n"
        f"{E.info} Наступне таке повідомлення — не раніше ніж через "
        f"{int(_OWNER_NOTIFY_COOLDOWN_HOURS)} год."
    )


async def notify_mirror_destination_unreachable(
    bot: Bot,
    *,
    owner_user_id: int,
    destination_group_id: int,
    donor_title: str | None,
    scope_type: str,
    scope_id: int,
) -> None:
    if not mirror_dest_owner_notify_due(
        owner_user_id,
        destination_group_id,
        cooldown_hours=_OWNER_NOTIFY_COOLDOWN_HOURS,
    ):
        return
    dest_title: str | None = None
    row = get_copy_destination(owner_user_id, scope_type, scope_id)
    if row and len(row) > 1:
        dest_title = row[1]
    text = _dest_unreachable_html(
        donor_title=donor_title,
        destination_title=dest_title,
        destination_group_id=int(destination_group_id),
        scope_type=scope_type,
    )
    try:
        await bot.send_message(int(owner_user_id), text, parse_mode="HTML")
        mark_mirror_dest_owner_notified(owner_user_id, destination_group_id)
    except Exception:
        logger.debug(
            "mirror dest notify skipped owner=%s dest=%s",
            owner_user_id,
            destination_group_id,
            exc_info=True,
        )