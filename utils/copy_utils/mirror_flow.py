from __future__ import annotations

from utils.ui_emoji import E, Icon
import html as html_lib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Iterable, Union
from zoneinfo import ZoneInfo

from aiogram import Bot, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from database_functions.channels_db import (
    channel_title_html_link,
    chat_title_html_link_by_id,
    get_all_channels,
    get_channel_by_id,
    get_mirror_publish_target_channel_ids,
)
from database_functions.client_db import (
    get_user_confirm_publish_status,
    get_user_timezone,
    user_timezone_label,
)
from database_functions.copy_mirror_db import (
    get_copy_mirror_pending_extras,
    get_copy_mirror_pending_publish,
    insert_copy_mirror_ai_image,
    merge_copy_mirror_pending_extras,
    set_copy_mirror_pending_publish_status,
)
from database_functions.posts_db import add_scheduled_post
from keyboards.client_keyboards.copy_mirror_keyboards import get_mirror_pending_ui_keyboard
from keyboards.client_keyboards.post_keyboards import (
    get_post_editing_keyboard,
    get_schedule_calendar_keyboard,
)
from app.runtime import bot
from states.client_states import PostCreation
from utils.post_utils import send_post_preview
from utils.copy_utils.copy_mirror_bot_delivery import caption_html, download_bytes
from utils.copy_utils.telethon_copy_client import get_telethon_client
from utils.copy_utils.mirror_publish_delivery import (
    mirror_file_id_for_photo_bytes,
    mirror_format_caption_html,
    mirror_plain_text_from_caption_html,
    mirror_try_watermark_photo_bytes,
    publish_mirror_messages_to_targets,
)

logger = logging.getLogger(__name__)

_POST_PREVIEW_IDS_KEY = "post_editing_preview_message_ids"


def folder_id_cell(row: tuple) -> int | None:
    if len(row) > 11 and row[11] is not None:
        return int(row[11])
    return None


def channels_pairs_in_folder(owner_uid: int, folder_id: int) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for r in get_all_channels(user_id=owner_uid, only_active=True):
        fid = folder_id_cell(r)
        if fid is not None and fid == int(folder_id):
            out.append((int(r[1]), r[2] or str(r[1])))
    return out


async def group_admin_guard_user(user_id: int, dest_group_id: int) -> bool:
    try:
        cm = await bot.get_chat_member(dest_group_id, user_id)
        return getattr(cm, "status", "") in ("creator", "administrator")
    except TelegramBadRequest:
        return False


async def load_tl_messages(donor_chat_id: int, mids: list[int]) -> list | None:
    tl = await get_telethon_client()
    if not tl:
        return None
    msgs = await tl.get_messages(donor_chat_id, ids=mids)
    if msgs is None:
        return None
    if not isinstance(msgs, list):
        msgs = [msgs]
    out = sorted([m for m in msgs if m is not None], key=lambda z: z.id)
    if len(out) != len(set(mids)):
        return None
    return out


def extras_extra_channel_ids(extras: dict) -> list[int]:
    raw = extras.get("extra_channel_ids") or []
    if not isinstance(raw, list):
        return []
    ids: list[int] = []
    for x in raw:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    return ids


def merge_mirror_targets(owner_uid: int, scope_type: str, scope_id: int, extras: dict) -> list[int]:
    base = get_mirror_publish_target_channel_ids(owner_uid, scope_type, scope_id)
    extra = extras_extra_channel_ids(extras)
    return list(dict.fromkeys([*base, *extra]))


def mirror_confirmation_html(
    *,
    owner_uid: int,
    donor_title: str | None,
    donor_chat_id: int,
    posted_at,
    scope_type: str,
    scope_id: int,
) -> str:
    donor_label = (donor_title or "").strip()
    donor_html = chat_title_html_link_by_id(donor_label or None, int(donor_chat_id))

    tz_name = get_user_timezone(owner_uid)
    zi = ZoneInfo(tz_name)
    dt = posted_at
    if getattr(dt, "tzinfo", None) is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(zi)
    time_line = local.strftime("%d.%m.%Y %H:%M")
    tz_hint = html_lib.escape(user_timezone_label(owner_uid), quote=False)

    targets = get_mirror_publish_target_channel_ids(owner_uid, scope_type, scope_id)
    max_lines = 12
    lines: list[str] = []
    for cid in targets[:max_lines]:
        ch_row = get_channel_by_id(cid, owner_uid)
        lines.append(f"• {channel_title_html_link(ch_row, fallback_chat_id=cid)}")
    targets_block = "\n".join(lines) if lines else "• <i>немає цільових каналів</i>"
    if len(targets) > max_lines:
        targets_block += f"\n• <i>… ще {len(targets) - max_lines}</i>"

    return (
        "Підтвердіть публікацію у вибрані канали SkyPost або оберіть іншу дію.\n\n"
        f"📢 <b>Канал-донор:</b> {donor_html}\n"
        f"{E.clock} <b>Опубліковано у джерелі:</b> {time_line} ({tz_hint})\n\n"
        f"<b>Канали призначення ({len(targets)}):</b>\n{targets_block}"
    )


async def mirror_delete_group_preview_messages(bot: Bot, chat_id: int, extras: dict) -> None:
    ids: list[int] = []
    raw = extras.get("preview_message_ids")
    if isinstance(raw, list):
        for x in raw:
            try:
                ids.append(int(x))
            except (TypeError, ValueError):
                pass
    pm = extras.get("preview_photo_message_id")
    if pm is not None:
        try:
            ids.append(int(pm))
        except (TypeError, ValueError):
            pass
    cmid = extras.get("confirmation_message_id")
    for mid in dict.fromkeys(ids):
        if cmid is not None and int(mid) == int(cmid):
            continue
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except TelegramBadRequest:
            pass


async def mirror_restore_group_confirmation(bot: Bot, pk: int) -> None:
    row = get_copy_mirror_pending_publish(pk)
    if not row or str(row[8]) != "pending":
        return
    dest_gid = int(row[7])
    extras = get_copy_mirror_pending_extras(pk)
    mids = sorted(int(x) for x in json.loads(row[6] or "[]"))
    tg_msgs = await load_tl_messages(int(row[4]), mids)
    if not tg_msgs:
        return
    tl_list = sorted(list(tg_msgs), key=lambda x: getattr(x, "id", 0))
    msg0 = tl_list[0]
    posted_at = getattr(msg0, "date", None) or datetime.now(timezone.utc)
    text = mirror_confirmation_html(
        owner_uid=int(row[1]),
        donor_title=row[5],
        donor_chat_id=int(row[4]),
        posted_at=posted_at,
        scope_type=str(row[2]),
        scope_id=int(row[3]),
    )
    await mirror_refresh_ui_kb(
        dest_gid,
        pk=pk,
        extras=extras,
        tl_msgs_hint=tl_list,
        text_override=text,
    )


async def short_summary_uk_async(plain: str) -> str:
    p = plain.strip()
    if not p:
        return ""
    if len(p) <= 240:
        return p
    try:
        from utils.copy_utils.ai import Ai

        a = Ai()
        return (
            (
                await a.async_get_response(
                    f"Коротко українською до 240 символів: {p[:2800]}",
                    "Лише вижимка без вступних слів.",
                )
                or ""
            ).strip()
        )[:480]
    except Exception:
        logger.exception("mirror AI summary")
        return p[:240]


def search_blob(summary: str) -> str:
    words = [w.lower() for w in re.findall(r"[A-Za-zА-Яа-яЇїІіЄєҐґ0-9]+", summary)]
    words = sorted({w for w in words if len(w) >= 2})
    return " ".join(words[:80])


async def store_mirror_ai_media(
    *,
    uid: int,
    pk: int,
    tg_msg: types.Message,
    caption_plain_hint: str,
    source_key: str,
) -> None:
    photo = tg_msg.photo[-1] if getattr(tg_msg, "photo", None) else None
    fid = getattr(photo, "file_id", None) if photo else None
    unique = getattr(photo, "file_unique_id", None) if photo else None
    if not fid:
        return
    summary = await short_summary_uk_async(caption_plain_hint or "")
    insert_copy_mirror_ai_image(
        user_id=uid,
        pending_publish_id=pk,
        telegram_file_id=fid,
        telegram_file_unique_id=unique,
        summary_text=summary,
        search_blob=search_blob(summary + " " + caption_plain_hint),
        source=source_key,
    )


async def mirror_refresh_ui_kb(
    dest_gid: int,
    *,
    pk: int,
    extras: dict | None,
    tl_msgs_hint: Iterable | None = None,
    text_override: str | None = None,
) -> None:
    extras = extras or get_copy_mirror_pending_extras(pk)
    cmid = extras.get("confirmation_message_id")
    if not cmid:
        return

    tg_msgs = tl_msgs_hint
    if tg_msgs is None:
        row = get_copy_mirror_pending_publish(pk)
        if not row:
            return
        mids = json.loads(row[6] or "[]")
        mids = [int(x) for x in mids]
        tg_msgs = await load_tl_messages(int(row[4]), mids)
        if not tg_msgs:
            return

    tl_list = sorted(list(tg_msgs), key=lambda x: getattr(x, "id", 0))
    is_grp = len(tl_list) > 1

    def _has_any(media_list: list) -> bool:
        for m in media_list:
            if getattr(m, "photo", None) or getattr(m, "video", None):
                return True
            if getattr(m, "document", None) or getattr(m, "animation", None):
                return True
        return False

    pm = extras.get("preview_photo_message_id")
    if pm:
        try:
            pm = int(pm)
        except (TypeError, ValueError):
            pm = None
    has_photo_single = len(tl_list) == 1 and bool(getattr(tl_list[0], "photo", None))

    me = await bot.get_me()
    bot_uname = (me.username or "").strip().lstrip("@") or None
    kb = get_mirror_pending_ui_keyboard(
        pk,
        has_any_media=_has_any(tl_list),
        has_photo_single=has_photo_single,
        photo_message_id=pm,
        is_media_group=is_grp,
        bot_username=bot_uname,
    )
    try:
        if text_override is not None:
            await bot.edit_message_text(
                chat_id=int(dest_gid),
                message_id=int(cmid),
                text=text_override,
                parse_mode="HTML",
                reply_markup=kb,
            )
        else:
            await bot.edit_message_reply_markup(
                chat_id=int(dest_gid), message_id=int(cmid), reply_markup=kb
            )
    except TelegramBadRequest:
        pass


async def mirror_do_publish(callback: types.CallbackQuery, pk: int) -> None:
    row = get_copy_mirror_pending_publish(pk)
    if not row or str(row[8]) != "pending":
        await callback.answer("Запис недійсний.", show_alert=True)
        return
    dest_group_id = int(row[7])
    if int(callback.message.chat.id) != dest_group_id:
        await callback.answer("Неправильний чат.", show_alert=True)
        return
    if not await group_admin_guard_user(callback.from_user.id if callback.from_user else 0, dest_group_id):
        await callback.answer("Потрібні права адміністратора.", show_alert=True)
        return

    extras = get_copy_mirror_pending_extras(pk)
    owner_uid = int(row[1])
    scope_type = str(row[2])
    scope_id = int(row[3])
    donor_chat_id = int(row[4])

    mids = json.loads(row[6] or "[]")
    mids = sorted(int(x) for x in mids)
    targets = merge_mirror_targets(owner_uid, scope_type, scope_id, extras)
    if not targets:
        await callback.answer("Немає цільових каналів.", show_alert=True)
        return

    msgs = await load_tl_messages(donor_chat_id, mids)
    if not msgs:
        await callback.answer("Не вдалося прочитати джерело.", show_alert=True)
        return

    strip_media = bool(extras.get("strip_media"))
    replaced_photo_file_id = extras.get("replaced_photo_file_id")
    if replaced_photo_file_id is not None:
        replaced_photo_file_id = str(replaced_photo_file_id)
    tl_client = await get_telethon_client()
    if not tl_client:
        await callback.answer("Сервіс публікації недоступний (Telethon).", show_alert=True)
        return

    failed = await publish_mirror_messages_to_targets(
        bot,
        tl_client,
        owner_user_id=owner_uid,
        msgs=msgs,
        target_channel_ids=targets,
        strip_media=strip_media,
        upload_chat_id=owner_uid,
        replaced_photo_file_id=replaced_photo_file_id,
    )

    if failed:
        set_copy_mirror_pending_publish_status(pk, "partial_failed")
    else:
        set_copy_mirror_pending_publish_status(pk, "published")

    merge_copy_mirror_pending_extras(
        pk, {"extra_channel_ids": [], "cross_pick_keys": [], "strip_media": False}
    )
    extras_after = get_copy_mirror_pending_extras(pk)
    await mirror_delete_group_preview_messages(bot, dest_group_id, extras_after)
    cmid = extras_after.get("confirmation_message_id")
    if failed:
        summary = (
            f"{E.warn} <b>Копію частково опубліковано</b>\n\n"
            f"Не вдалося надіслати в <b>{len(failed)}</b> канал(ів)."
        )
    else:
        summary = "✅ <b>Копію опубліковано</b>"
    if cmid:
        try:
            await bot.edit_message_text(
                chat_id=dest_group_id,
                message_id=int(cmid),
                text=summary,
                parse_mode="HTML",
                reply_markup=None,
            )
        except TelegramBadRequest:
            pass
    aux = callback.message
    if aux and cmid and int(aux.message_id) != int(cmid):
        try:
            await bot.delete_message(dest_group_id, aux.message_id)
        except TelegramBadRequest:
            pass

    if failed:
        await callback.answer(
            f"Не вдалося опублікувати в {len(failed)} канал(ів).", show_alert=True
        )
    else:
        await callback.answer("Опубліковано.")


async def mirror_build_schedule_payload(
    tl,
    msgs: list,
    *,
    strip_media: bool,
    owner_uid: int,
    channel_id: int,
    replaced_photo_file_id: str | None = None,
) -> dict:
    cap0 = mirror_format_caption_html(
        caption_html(msgs[0]) if msgs else "", channel_id
    )
    if strip_media or not msgs:
        return {"text": cap0, "media_files": [], "url_buttons": [], "settings": {}}

    if replaced_photo_file_id:
        return {
            "text": cap0,
            "media_files": [
                {
                    "type": "photo",
                    "file_id": str(replaced_photo_file_id),
                    "caption": cap0,
                }
            ],
            "url_buttons": [],
            "settings": {},
        }

    media_files = []
    for i, m in enumerate(sorted(msgs, key=lambda z: getattr(z, "id", 0))):
        if getattr(m, "photo", None):
            raw, _ = await download_bytes(tl, m)
            wb = mirror_try_watermark_photo_bytes(owner_uid, channel_id, raw)
            fid = await mirror_file_id_for_photo_bytes(
                bot, owner_uid, wb or raw, filename=f"p{i}.jpg"
            )
            if not fid:
                continue
            media_files.append(
                {
                    "type": "photo",
                    "file_id": fid,
                    "caption": cap0 if i == 0 else "",
                }
            )
        elif i == 0:
            continue

    return {
        "text": cap0,
        "media_files": media_files,
        "url_buttons": [],
        "settings": {},
    }


def mirror_resolve_cross_pick_keys(owner_uid: int, keys: list[str]) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for k in keys:
        try:
            _fid, cid = k.split("_", 1)
            cid_i = int(cid)
        except ValueError:
            continue
        if cid_i not in seen:
            seen.add(cid_i)
            ids.append(cid_i)
    owned = {int(r[1]) for r in get_all_channels(user_id=owner_uid, only_active=True)}
    return [i for i in ids if i in owned]


async def mirror_merge_cross_pick_into_extras(callback: types.CallbackQuery, pk: int) -> bool:
    row = get_copy_mirror_pending_publish(pk)
    if not row:
        await callback.answer()
        return False
    if int(callback.message.chat.id) != int(row[7]):
        await callback.answer()
        return False
    uid = callback.from_user.id if callback.from_user else 0
    if not await group_admin_guard_user(uid, int(row[7])):
        await callback.answer("Немає прав.", show_alert=True)
        return False
    extras = get_copy_mirror_pending_extras(pk)
    keys = extras.get("cross_pick_keys") or []
    extra_ids = mirror_resolve_cross_pick_keys(int(row[1]), list(keys))
    merge_copy_mirror_pending_extras(pk, {"extra_channel_ids": extra_ids})
    return True


async def mirror_ai_news_context(row: tuple) -> str:
    mids = sorted(int(x) for x in json.loads(row[6] or "[]"))
    tl_msgs = await load_tl_messages(int(row[4]), mids)
    if not tl_msgs:
        return ""
    parts = [
        mirror_plain_text_from_caption_html(caption_html(m))
        for m in sorted(tl_msgs, key=lambda z: getattr(z, "id", 0))
    ]
    return " ".join(p for p in parts if p).strip()


async def mirror_ai_store_generated(
    *,
    owner_uid: int,
    pk: int,
    img_bytes: bytes,
    caption_plain: str,
    source: str,
) -> None:
    try:
        msg_st = await bot.send_photo(
            owner_uid,
            photo=BufferedInputFile(img_bytes, filename="ai_gen.png"),
        )
        await store_mirror_ai_media(
            uid=owner_uid,
            pk=pk,
            tg_msg=msg_st,
            caption_plain_hint=caption_plain,
            source_key=source,
        )
        await bot.delete_message(owner_uid, msg_st.message_id)
    except Exception:
        logger.exception("mirror_ai_store_generated")


async def mirror_try_handle_schedule_time_message(
    message: types.Message,
    state: FSMContext,
    *,
    hours: int,
    minutes: int,
    date_str: str,
) -> bool:
    """Якщо в state є mirror-планування — обробити ввід часу; інакше повернути False."""
    data = await state.get_data()
    mirror_pk = data.get("mirror_schedule_pk")
    owner_uid_mirror = data.get("mirror_schedule_owner_uid")
    if not mirror_pk or not owner_uid_mirror:
        return False

    row = get_copy_mirror_pending_publish(int(mirror_pk))
    if not row or str(row[8]) != "pending":
        await state.clear()
        await message.answer("❌ Запис копії вже недійсний.")
        return True
    if int(message.chat.id) != int(row[7]):
        await message.answer("❌ Планування потрібно завершувати в групі отримувача.")
        return True
    if not await group_admin_guard_user(message.from_user.id, int(row[7])):
        await message.answer("❌ Потрібні права адміністратора.")
        return True

    tz_name = get_user_timezone(int(owner_uid_mirror))
    zi = ZoneInfo(tz_name)
    schedule_local = datetime.strptime(
        f"{date_str} {hours:02d}:{minutes:02d}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=zi)
    now_local = datetime.now(zi)
    if schedule_local <= now_local:
        await message.answer(
            "❌ <b>Помилка!</b>\n\n"
            "Час публікації має бути в майбутньому "
            f"(за вашим поясом: {user_timezone_label(int(owner_uid_mirror))}).\n"
            "Введіть інший час:",
            parse_mode="HTML",
        )
        return True

    schedule_datetime_naive = schedule_local.replace(tzinfo=None)
    await state.update_data(
        schedule_datetime=schedule_datetime_naive.strftime("%Y-%m-%d %H:%M:%S")
    )

    extras = get_copy_mirror_pending_extras(int(mirror_pk))
    targets = merge_mirror_targets(int(row[1]), str(row[2]), int(row[3]), extras)
    if not targets:
        await message.answer("Немає цільових каналів.")
        return True

    owner_id = int(row[1])
    ch_lines: list[str] = []
    for channel_id in targets[:5]:
        ch_row = get_channel_by_id(channel_id, owner_id)
        ch_lines.append(f"• {channel_title_html_link(ch_row, fallback_chat_id=channel_id)}")
    channels_text = "\n".join(ch_lines) if ch_lines else "• <i>немає каналів</i>"
    if len(targets) > 5:
        channels_text += f"\n• <i>… і ще {len(targets) - 5}</i>"

    time_formatted = schedule_datetime_naive.strftime("%d.%m.%Y о %H:%M")
    tz_note = html_lib.escape(user_timezone_label(int(owner_uid_mirror)), quote=False)

    time_delta = schedule_local - now_local
    hours_until = int(time_delta.total_seconds() // 3600)
    minutes_until = int((time_delta.total_seconds() % 3600) // 60)
    if hours_until > 0:
        time_until_text = f"через {hours_until} год {minutes_until} хв"
    else:
        time_until_text = f"через {minutes_until} хв"

    confirmation_text = f"""{E.calendar} <b>Підтвердження планування</b>

<b>Дата і час публікації:</b>
{time_formatted} ({time_until_text})
{E.clock} <b>Часовий пояс:</b> {tz_note}

<b>Канали для публікації ({len(targets)}):</b>
{channels_text}

<b>Справді запланувати публікацію цього поста?</b>"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Так, запланувати", callback_data="confirm_schedule",
                icon_custom_emoji_id=Icon.ok,
            ),
                InlineKeyboardButton(text="Скасувати", callback_data="cancel_schedule", icon_custom_emoji_id=Icon.cancel),
            ]
        ]
    )

    if get_user_confirm_publish_status(int(owner_uid_mirror)):
        pmid = data.get("schedule_prompt_message_id")
        if pmid:
            try:
                await bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=int(pmid),
                    text=confirmation_text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            except TelegramBadRequest:
                await message.answer(
                    text=confirmation_text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
        else:
            await message.answer(
                text=confirmation_text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        try:
            await bot.delete_message(message.chat.id, message.message_id)
        except TelegramBadRequest:
            pass
    else:
        await mirror_finalize_schedule_save(message, state)
    return True


async def mirror_begin_schedule_calendar(
    callback: types.CallbackQuery,
    state: FSMContext,
    *,
    pk: int,
) -> None:
    row = get_copy_mirror_pending_publish(pk)
    if not row or str(row[8]) != "pending":
        await callback.answer("Недійсно.", show_alert=True)
        return
    if int(callback.message.chat.id) != int(row[7]):
        await callback.answer()
        return
    if not await group_admin_guard_user(callback.from_user.id if callback.from_user else 0, int(row[7])):
        await callback.answer("Немає прав.", show_alert=True)
        return

    owner_uid = int(row[1])
    await state.clear()
    prompt_mid = int(callback.message.message_id)
    await state.update_data(
        mirror_schedule_pk=pk,
        mirror_schedule_owner_uid=owner_uid,
        schedule_prompt_message_id=prompt_mid,
    )

    tz_hint = user_timezone_label(owner_uid)
    cal_text = (
        f"{E.calendar} <b>Планування публікації</b>\n\n"
        "Оберіть дату публікації.\n\n"
        f"{E.clock} <b>Час у календарі та для поста</b> — за вашим поясом: {tz_hint}\n"
        "<i>Змінити пояс можна в «Налаштування» → «Часовий пояс».</i>"
    )
    try:
        await callback.message.edit_text(
            text=cal_text,
            parse_mode="HTML",
            reply_markup=get_schedule_calendar_keyboard(
                user_id=owner_uid,
                back_callback_data="mirror_schedule_cancel",
            ),
        )
    except TelegramBadRequest:
        m = await callback.message.answer(
            text=cal_text,
            parse_mode="HTML",
            reply_markup=get_schedule_calendar_keyboard(
                user_id=owner_uid,
                back_callback_data="mirror_schedule_cancel",
            ),
        )
        await state.update_data(schedule_prompt_message_id=int(m.message_id))
    await callback.answer()


async def mirror_finalize_schedule_save(
    event: Union[types.CallbackQuery, types.Message], state: FSMContext
) -> None:
    is_cb = isinstance(event, types.CallbackQuery)
    actor_uid = event.from_user.id if event.from_user else 0
    reply_msg = event.message if is_cb else event

    data = await state.get_data()
    pk = data.get("mirror_schedule_pk")
    owner_uid = data.get("mirror_schedule_owner_uid")
    schedule_datetime_str = data.get("schedule_datetime")

    if not pk or not owner_uid or not schedule_datetime_str:
        if is_cb:
            await event.answer("❌ Помилка планування", show_alert=True)
        else:
            await reply_msg.answer("❌ Помилка планування.")
        return

    row = get_copy_mirror_pending_publish(int(pk))
    if not row or str(row[8]) != "pending":
        await state.clear()
        await reply_msg.answer("❌ Запис копії вже недійсний.")
        return

    dest_group_id = int(row[7])
    chat_id = reply_msg.chat.id if reply_msg.chat else 0
    if int(chat_id) != dest_group_id:
        if is_cb:
            await event.answer("❌ Неправильний чат", show_alert=True)
        else:
            await reply_msg.answer("❌ Планування можна завершити лише в групі отримувача.")
        return

    if not await group_admin_guard_user(actor_uid, dest_group_id):
        if is_cb:
            await event.answer("❌ Потрібні права адміністратора", show_alert=True)
        else:
            await reply_msg.answer("❌ Потрібні права адміністратора.")
        return

    tl = await get_telethon_client()
    if not tl:
        await reply_msg.answer("Telethon недоступний.")
        return

    mids = sorted(int(x) for x in json.loads(row[6] or "[]"))
    msgs = await load_tl_messages(int(row[4]), mids)
    if not msgs:
        await reply_msg.answer("Не вдалося прочитати оригінал.")
        return

    extras = get_copy_mirror_pending_extras(int(pk))
    targets = merge_mirror_targets(int(row[1]), str(row[2]), int(row[3]), extras)
    if not targets:
        await reply_msg.answer("Немає цільових каналів.")
        return

    strip_media = bool(extras.get("strip_media"))
    replaced_photo_file_id = extras.get("replaced_photo_file_id")
    if replaced_photo_file_id is not None:
        replaced_photo_file_id = str(replaced_photo_file_id)
    schedule_datetime_naive = datetime.strptime(schedule_datetime_str, "%Y-%m-%d %H:%M:%S")
    db_dt = schedule_datetime_naive.strftime("%Y-%m-%d %H:%M:%S")

    scheduled_count = 0
    for channel_id in targets:
        pdata = await mirror_build_schedule_payload(
            tl,
            msgs,
            strip_media=strip_media,
            owner_uid=int(row[1]),
            channel_id=int(channel_id),
            replaced_photo_file_id=replaced_photo_file_id,
        )
        try:
            add_scheduled_post(
                user_id=int(row[1]),
                channel_id=int(channel_id),
                scheduled_time=db_dt,
                post_text=pdata.get("text", ""),
                media_files=pdata.get("media_files") or [],
                url_buttons="",
                settings=pdata.get("settings") or {},
            )
            scheduled_count += 1
        except Exception:
            logger.exception("mirror schedule add channel %s", channel_id)

    tz_note = user_timezone_label(int(owner_uid))
    zi = ZoneInfo(get_user_timezone(int(owner_uid)))
    schedule_local = schedule_datetime_naive.replace(tzinfo=zi)
    now_local = datetime.now(zi)
    time_delta = schedule_local - now_local
    hours_until = int(time_delta.total_seconds() // 3600)
    minutes_until = int((time_delta.total_seconds() % 3600) // 60)
    if hours_until > 0:
        time_until_text = f"через {hours_until} год {minutes_until} хв"
    else:
        time_until_text = f"через {minutes_until} хв"
    time_formatted = schedule_datetime_naive.strftime("%d.%m.%Y о %H:%M")

    done_text = f"""✅ <b>Копію заплановано!</b>

{E.calendar} <b>Дата і час:</b> {time_formatted}
{E.clock} <b>Часовий пояс:</b> {tz_note}
⏱ <b>Публікація:</b> {time_until_text}
📢 <b>Каналів:</b> {scheduled_count}

<i>Пост буде автоматично опубліковано в зазначений місцевий час.</i>"""

    await mirror_delete_group_preview_messages(bot, dest_group_id, extras)

    pmid = data.get("schedule_prompt_message_id")
    if is_cb:
        await reply_msg.edit_text(text=done_text, parse_mode="HTML")
    else:
        if pmid:
            try:
                await bot.edit_message_text(
                    chat_id=int(chat_id),
                    message_id=int(pmid),
                    text=done_text,
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except TelegramBadRequest:
                await reply_msg.answer(done_text, parse_mode="HTML")
            try:
                await bot.delete_message(int(chat_id), reply_msg.message_id)
            except TelegramBadRequest:
                pass
        else:
            await reply_msg.answer(done_text, parse_mode="HTML")

    set_copy_mirror_pending_publish_status(int(pk), "scheduled")
    await state.clear()
    if is_cb:
        await event.answer("✅ Заплановано!")


async def mirror_open_editor_from_pending_start(
    message: types.Message, state: FSMContext, pk: int
) -> bool:
    """Після /start cpyed_<pk> — чернетка як у «Створити пост». True = не показувати стандартне /start."""
    user_id = message.from_user.id if message.from_user else 0
    row = get_copy_mirror_pending_publish(int(pk))
    if not row or str(row[8]) != "pending":
        await message.answer(
            "❌ Цей запис уже не в очікуванні (опубліковано, відхилено або застарів).",
            parse_mode="HTML",
        )
        return True
    if int(row[1]) != user_id:
        await message.answer(
            "❌ Редагувати може лише <b>власник</b> налаштування копії.",
            parse_mode="HTML",
        )
        return True

    tl = await get_telethon_client()
    if not tl:
        await message.answer("❌ Сервіс копій тимчасово недоступний (Telethon).")
        return True

    mids = sorted(int(x) for x in json.loads(row[6] or "[]"))
    msgs = await load_tl_messages(int(row[4]), mids)
    if not msgs:
        await message.answer("❌ Не вдалося завантажити оригінал з каналу-донора.")
        return True

    extras = get_copy_mirror_pending_extras(int(pk))
    targets = merge_mirror_targets(int(row[1]), str(row[2]), int(row[3]), extras)
    if not targets:
        await message.answer("❌ Немає цільових каналів для публікації.")
        return True

    strip_media = bool(extras.get("strip_media"))
    replaced_photo_file_id = extras.get("replaced_photo_file_id")
    if replaced_photo_file_id is not None:
        replaced_photo_file_id = str(replaced_photo_file_id)
    first_ch = int(targets[0])
    pdata = await mirror_build_schedule_payload(
        tl,
        msgs,
        strip_media=strip_media,
        owner_uid=int(row[1]),
        channel_id=first_ch,
        replaced_photo_file_id=replaced_photo_file_id,
    )

    post_data: dict = {
        "text": pdata.get("text") or "",
        "media_files": list(pdata.get("media_files") or []),
        "url_buttons": [],
        "url_buttons_raw_text": "",
        "url_buttons_entities": [],
        "settings": {
            "notification": True,
            "pin_message": False,
            "disable_comments": False,
        },
    }

    await state.clear()
    preview_ids: list[int] = []
    chat_id = message.chat.id
    try:
        await send_post_preview(
            bot, chat_id, post_data, preview_message_ids=preview_ids
        )
    except Exception:
        logger.exception("mirror_open_editor preview pk=%s", pk)
        await message.answer("❌ Не вдалося зібрати превʼю поста.")
        return True

    await state.update_data(
        selected_channels=list(targets),
        post_data=post_data,
        **{_POST_PREVIEW_IDS_KEY: preview_ids},
    )
    await state.set_state(PostCreation.editing_post)

    await message.answer(
        f"{E.sign} <b>Редагування поста з копії</b>\n\n"
        "Нижче — контент як у групі підтвердження. Після змін — «Далі» → публікація або планування.",
        parse_mode="HTML",
        reply_markup=get_post_editing_keyboard(post_data),
    )
    return True
