from __future__ import annotations

from utils.ui_emoji import E
from typing import Union

from aiogram import types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import MessageEntity
from datetime import datetime
from zoneinfo import ZoneInfo

from database_functions.client_db import get_user_timezone, user_timezone_label
from database_functions.channels_db import get_channel_by_id
from database_functions.folders_db import get_user_folders
from database_functions.posts_db import add_scheduled_post, get_scheduled_post_row, update_scheduled_post_content
from database_functions.content_plan_db import update_scheduled_post_time
from app.runtime import bot
from utils.post_utils import parse_url_buttons_with_entities


async def ensure_post_url_buttons_in_state(state: FSMContext) -> None:
    data = await state.get_data()
    post_data = data.get("post_data", {})
    if not post_data.get("url_buttons_raw_text"):
        return

    entities_data = post_data.get("url_buttons_entities", [])
    entities = []
    for e_data in entities_data:
        entity = MessageEntity(
            type=e_data["type"],
            offset=e_data["offset"],
            length=e_data["length"],
        )
        if e_data.get("custom_emoji_id"):
            entity.custom_emoji_id = e_data["custom_emoji_id"]
        entities.append(entity)
    post_data["url_buttons"] = parse_url_buttons_with_entities(
        post_data["url_buttons_raw_text"],
        entities,
    )
    await state.update_data(post_data=post_data)


async def finalize_schedule_save(
    event: Union[types.CallbackQuery, types.Message], state: FSMContext
) -> None:
    """Зберігає запланований пост (новий або з контент-плану) без додаткового кроку підтвердження."""
    is_cb = isinstance(event, types.CallbackQuery)
    user_id = event.from_user.id
    reply_msg = event.message if is_cb else event

    data = await state.get_data()
    post_data = data.get("post_data", {})
    selected_channels = data.get("selected_channels", [])
    schedule_datetime_str = data.get("schedule_datetime")

    editing_id = data.get("editing_scheduled_post_id")
    if editing_id:
        if len(selected_channels) != 1:
            if is_cb:
                await event.answer("❌ Помилка каналу", show_alert=True)
            else:
                await reply_msg.answer("❌ Помилка каналу")
            return
        if not schedule_datetime_str:
            if is_cb:
                await event.answer("❌ Помилка: час не обрано", show_alert=True)
            else:
                await reply_msg.answer("❌ Помилка: час не обрано")
            return

        row = get_scheduled_post_row(editing_id)
        if not row or row[1] != user_id or row[2] != selected_channels[0]:
            if is_cb:
                await event.answer("❌ Помилка доступу", show_alert=True)
            else:
                await reply_msg.answer("❌ Помилка доступу")
            return
        update_scheduled_post_content(
            editing_id,
            post_data.get("text", ""),
            post_data.get("media_files", []),
            post_data.get("url_buttons_raw_text", ""),
            post_data.get("settings", {}),
        )
        update_scheduled_post_time(editing_id, schedule_datetime_str)

        schedule_datetime = datetime.strptime(
            schedule_datetime_str, "%Y-%m-%d %H:%M:%S"
        )
        time_formatted = schedule_datetime.strftime("%d.%m.%Y о %H:%M")
        tz_note = user_timezone_label(user_id)
        success_text = (
            f"✅ <b>Контент-план оновлено</b>\n\n"
            f"Новий час: {time_formatted}\n🕐 {tz_note}"
        )
        if is_cb:
            await reply_msg.edit_text(text=success_text, parse_mode="HTML")
        else:
            await reply_msg.answer(success_text, parse_mode="HTML")

        scope = data.get("cp_r_scope", "channel")
        date_str = data.get("cp_r_date")
        page = data.get("cp_r_page", 0)
        anchor = data.get("cp_r_anchor")
        ch_id = data.get("cp_r_channel_id")
        fold_id = data.get("cp_r_folder_id")

        await state.clear()
        await state.update_data(
            content_plan_scope=scope,
            selected_channel_id=ch_id,
            content_plan_folder_id=fold_id,
            selected_date=date_str,
            content_plan_date_page=page,
            content_plan_anchor_message_id=anchor,
        )
        if scope == "channel" and ch_id:
            ch = get_channel_by_id(ch_id)
            if ch:
                await state.update_data(
                    selected_channel_title=ch[2],
                    selected_channel_link=(ch[4] if len(ch) > 4 and ch[4] else "#"),
                )
        elif scope == "folder" and fold_id:
            folders = get_user_folders(user_id)
            fname = next((f[1] for f in folders if f[0] == fold_id), "Папка")
            await state.update_data(
                selected_channel_title=fname,
                selected_channel_link="#",
            )

        from handlers.client_handlers.content_plan_handlers import show_date_content

        if date_str:
            if scope == "folder" and fold_id:
                await show_date_content(
                    event,
                    state,
                    date_str,
                    edit_message=True,
                    folder_id=fold_id,
                    page=page,
                    edit_target_message_id=anchor,
                )
            elif scope == "channel" and ch_id:
                await show_date_content(
                    event,
                    state,
                    date_str,
                    edit_message=True,
                    channel_id=ch_id,
                    page=page,
                    edit_target_message_id=anchor,
                )
        if is_cb:
            await event.answer("✅ Збережено")
        return

    if not schedule_datetime_str:
        if is_cb:
            await event.answer("❌ Помилка: час не обрано", show_alert=True)
        else:
            await reply_msg.answer("❌ Помилка: час не обрано")
        return

    schedule_datetime = datetime.strptime(schedule_datetime_str, "%Y-%m-%d %H:%M:%S")
    tz_name = get_user_timezone(user_id)
    zi = ZoneInfo(tz_name)
    schedule_local = schedule_datetime.replace(tzinfo=zi)
    now_local = datetime.now(zi)

    scheduled_count = 0
    for channel_id in selected_channels:
        try:
            post_id = add_scheduled_post(
                user_id=user_id,
                channel_id=channel_id,
                scheduled_time=schedule_datetime_str,
                post_text=post_data.get("text", ""),
                media_files=post_data.get("media_files", []),
                url_buttons=post_data.get("url_buttons_raw_text", ""),
                settings=post_data.get("settings", {}),
            )
            print(f"✅ Scheduled post ID: {post_id} for channel {channel_id}")
            scheduled_count += 1
        except Exception as e:
            print(f"❌ Помилка збереження запланованого поста: {e}")
            import traceback

            traceback.print_exc()

    time_formatted = schedule_datetime.strftime("%d.%m.%Y о %H:%M")
    tz_note = user_timezone_label(user_id)
    time_delta = schedule_local - now_local
    hours_until = int(time_delta.total_seconds() // 3600)
    minutes_until = int((time_delta.total_seconds() % 3600) // 60)
    if hours_until > 0:
        time_until_text = f"через {hours_until} год {minutes_until} хв"
    else:
        time_until_text = f"через {minutes_until} хв"

    done_text = f"""✅ <b>Пост заплановано!</b>

{E.calendar} <b>Дата і час:</b> {time_formatted}
{E.clock} <b>Часовий пояс:</b> {tz_note}
⏱ <b>Публікація:</b> {time_until_text}
📢 <b>Каналів:</b> {scheduled_count}

<i>Пост буде автоматично опубліковано в зазначений місцевий час.</i>"""
    if is_cb:
        await reply_msg.edit_text(text=done_text, parse_mode="HTML")
    else:
        pmid = data.get("schedule_prompt_message_id")
        chat_id = reply_msg.chat.id
        if pmid:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=int(pmid),
                    text=done_text,
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except TelegramBadRequest:
                await reply_msg.answer(done_text, parse_mode="HTML")
            try:
                await bot.delete_message(chat_id, reply_msg.message_id)
            except TelegramBadRequest:
                pass
        else:
            await reply_msg.answer(done_text, parse_mode="HTML")

    await state.clear()
    if is_cb:
        await event.answer("✅ Заплановано!")
