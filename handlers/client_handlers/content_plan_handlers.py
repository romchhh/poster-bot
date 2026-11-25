from utils.ui_emoji import E, Icon
from texts import Main
import asyncio
import json
from datetime import datetime, timedelta

from zoneinfo import ZoneInfo

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database_functions.client_db import (
    get_user_timezone,
    get_user_confirm_publish_status,
    user_timezone_label,
)
from database_functions.channels_db import (
    get_all_channels,
    get_channel_by_id,
    get_channels_without_folder,
    get_channels_by_folder,
)
from database_functions.content_plan_db import (
    get_posts_for_date,
    get_posts_for_date_channels,
    get_scheduled_dates_for_channel,
    get_scheduled_dates_for_channels,
    delete_all_scheduled_posts_for_channel,
    get_scheduled_post_by_id_content_plan,
    get_published_post_by_id_content_plan,
    published_post_content_data,
    update_scheduled_post_time,
    get_day_post_stats_for_channel,
    get_day_post_stats_for_channels,
)
from database_functions.posts_db import (
    delete_scheduled_post,
    add_published_post,
    get_scheduled_post_row,
    update_scheduled_post_content,
)
from keyboards.client_keyboards.content_plan_keyboards import (
    get_content_plan_channel_menu_keyboard,
    get_content_plan_channel_selection_keyboard,
    get_content_plan_calendar_keyboard,
    get_content_plan_folder_calendar_keyboard,
    build_content_plan_day_keyboard,
    get_content_plan_post_actions_keyboard,
    get_content_plan_delete_confirmation_keyboard,
    get_edit_time_calendar_keyboard,
    get_edit_time_confirmation_keyboard,
    get_clear_content_plan_first_confirmation_keyboard,
    get_clear_content_plan_second_confirmation_keyboard,
)
from app.runtime import bot
from states.client_states import ContentPlan, PostCreation
from keyboards.client_keyboards.post_keyboards import get_post_editing_keyboard
from utils.content_plan_utils import (
    format_post_preview,
    send_post_preview_to_user,
    send_published_post_preview_to_user,
    parse_time_input_content_plan,
    post_data_from_scheduled_sqlite_row,
)
from utils.post_utils import (
    deserialize_url_buttons,
    parse_url_buttons,
    send_post_preview,
    serialize_url_buttons,
)

router = Router()

CONTENT_PLAN_PAGE_SIZE = 10

# Alias для коду, що очікує старий формат рядка scheduled_posts
get_scheduled_post_by_id = get_scheduled_post_by_id_content_plan


async def show_content_plan_calendar_screen(
    callback_or_message,
    state: FSMContext,
    channel_id: int,
    year: int | None = None,
    month: int | None = None,
    edit_message: bool = True,
):
    data = await state.get_data()
    channel_title = data.get("selected_channel_title", "Невідомий канал")
    channel_link = data.get("selected_channel_link", "#")

    user_id = callback_or_message.from_user.id
    tz_name = get_user_timezone(user_id)
    now = datetime.now(ZoneInfo(tz_name))
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    start_date = f"{year}-{month:02d}-01"
    end_date = (datetime(year, month, 1) + timedelta(days=32)).replace(day=1) - timedelta(
        days=1
    )
    end_date_str = end_date.strftime("%Y-%m-%d")

    scheduled_dates_raw = get_scheduled_dates_for_channel(
        channel_id, start_date, end_date_str
    )
    scheduled_dates = {date[0] for date in scheduled_dates_raw}

    calendar_text = (
        f'{E.calendar} <b>Контент-план</b>\n\n'
        f'Канал: <a href="{channel_link}">{channel_title}</a>\n\n'
        f'{E.notes} Оберіть дату:\n\n'
        "• — дні з запланованими постами\n\n"
        f"<i>Календар за вашим поясом: {user_timezone_label(user_id)}</i>"
    )

    keyboard = get_content_plan_calendar_keyboard(
        year, month, channel_id, scheduled_dates, tz_name=tz_name
    )

    if edit_message:
        await callback_or_message.message.edit_text(
            text=calendar_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=keyboard,
        )
    else:
        if hasattr(callback_or_message, "message"):
            await callback_or_message.message.answer(
                text=calendar_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=keyboard,
            )
        else:
            await callback_or_message.answer(
                text=calendar_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=keyboard,
            )

    await state.set_state(ContentPlan.viewing_calendar)


async def show_folder_calendar_screen(
    callback_or_message,
    state: FSMContext,
    folder_id: int,
    year: int | None = None,
    month: int | None = None,
    edit_message: bool = True,
):
    data = await state.get_data()
    folder_name = data.get("selected_channel_title", "Папка")

    user_id = callback_or_message.from_user.id
    tz_name = get_user_timezone(user_id)
    now = datetime.now(ZoneInfo(tz_name))
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    channel_rows = get_channels_by_folder(folder_id)
    channel_ids = [c[1] for c in channel_rows]

    start_date = f"{year}-{month:02d}-01"
    end_date = (datetime(year, month, 1) + timedelta(days=32)).replace(day=1) - timedelta(
        days=1
    )
    end_date_str = end_date.strftime("%Y-%m-%d")

    scheduled_dates_raw = get_scheduled_dates_for_channels(
        channel_ids, start_date, end_date_str
    )
    scheduled_dates = {d[0] for d in scheduled_dates_raw}

    calendar_text = (
        f'{E.calendar} <b>Контент-план</b>\n\n'
        f"Папка: <b>{folder_name}</b>\n"
        f"{E.channel} Каналів у папці: {len(channel_ids)}\n\n"
        f'{E.notes} Оберіть дату:\n\n'
        "• — дні з запланованими постами\n\n"
        f"<i>Календар за вашим поясом: {user_timezone_label(user_id)}</i>"
    )

    keyboard = get_content_plan_folder_calendar_keyboard(
        year, month, folder_id, scheduled_dates, tz_name=tz_name
    )

    if edit_message:
        await callback_or_message.message.edit_text(
            text=calendar_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=keyboard,
        )
    else:
        if hasattr(callback_or_message, "message"):
            await callback_or_message.message.answer(
                text=calendar_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=keyboard,
            )
        else:
            await callback_or_message.answer(
                text=calendar_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=keyboard,
            )

    await state.set_state(ContentPlan.viewing_calendar)


def _user_chat_id(callback_or_message) -> int:
    if hasattr(callback_or_message, "message") and callback_or_message.message:
        return callback_or_message.message.chat.id
    if hasattr(callback_or_message, "chat") and callback_or_message.chat:
        return callback_or_message.chat.id
    return callback_or_message.from_user.id


async def _show_content_plan_main_menu(target_message, state: FSMContext, user_id: int):
    """Головне меню: папки → канали без папки → усі списком."""
    from database_functions.folders_db import get_user_folders

    await state.update_data(content_scope=None, selected_folder_id=None)
    folders = get_user_folders(user_id)
    channels_no_folder = get_channels_without_folder(user_id)
    await target_message.edit_text(
        text=(
            f"{E.calendar} <b>Контент-план</b>\n\n"
            f"{E.channel} <b>Оберіть канал</b>\n\n"
            "Спочатку натисніть папку — відкриється контент-план усіх каналів у папці.\n"
            "Окремі канали без папки — нижче.\n\n"
            "За потреби натисніть «Усі канали списком», щоб побачити двоколонковий список."
        ),
        parse_mode="HTML",
        reply_markup=get_content_plan_channel_menu_keyboard(
            folders, channels_no_folder
        ),
        disable_web_page_preview=True,
    )
    await state.set_state(ContentPlan.selecting_channel)


@router.message(F.text.in_([Main.content_plan, "Контент план", f"📋 {Main.content_plan}", "📋 Контент план"]))
async def content_plan_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    from database_functions.billing_db import denial

    reason = denial(user_id, "posting")
    if reason:
        await message.answer(reason)
        return
    await state.clear()

    user_channels = get_all_channels(user_id)

    # bot_info = await bot.get_me()
    # bot_username = bot_info.username
        
    # add_channel_url = f"https://t.me/{bot_username}?startchannel=&admin=post_messages+edit_messages+delete_messages"
    # add_group_url = f"https://t.me/{bot_username}?startgroup=&admin=post_messages+edit_messages+delete_messages"

        
    # add_channel_button = InlineKeyboardButton(text=texts2['add_channel'], url=add_channel_url)
    # add_group_button = InlineKeyboardButton(text=texts2['add_group'], url=add_group_url)
    # keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_channel_button, add_group_button]])
    
    if not user_channels:
        await message.answer(
            text=(
                f"{E.channel} <b>Немає каналів</b>\n\n"
                "Додайте канал або групу через меню, щоб користуватися контент-планом."
            ),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return

    from database_functions.folders_db import get_user_folders

    user_folders = get_user_folders(user_id)
    channels_no_folder = get_channels_without_folder(user_id)

    await message.answer(
        text=(
            f"{E.calendar} <b>Контент-план</b>\n\n"
            f"{E.channel} <b>Оберіть канал</b>\n\n"
            "Спочатку натисніть папку — відкриється контент-план усіх каналів у папці.\n"
            "Окремі канали без папки — нижче.\n\n"
            "За потреби натисніть «Усі канали списком», щоб побачити двоколонковий список."
        ),
        parse_mode="HTML",
        reply_markup=get_content_plan_channel_menu_keyboard(
            user_folders, channels_no_folder
        ),
        disable_web_page_preview=True,
    )
    await state.update_data(content_scope=None, selected_folder_id=None)
    await state.set_state(ContentPlan.selecting_channel)


@router.callback_query(F.data == "cp_back_to_mode")
async def content_plan_back_to_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await _show_content_plan_main_menu(callback.message, state, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data == "cp_back_to_folders")
async def content_plan_back_to_folders(callback: types.CallbackQuery, state: FSMContext):
    await _show_content_plan_main_menu(callback.message, state, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data == "cp_cp_show_all_channels")
async def content_plan_show_all_channels_flat(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    channels = get_all_channels(user_id)
    if not channels:
        await callback.answer("Немає каналів", show_alert=True)
        return
    await state.update_data(content_scope="all", selected_folder_id=None)
    await callback.message.edit_text(
        text=(
            f"{E.channel} <b>Оберіть канал або групу</b>\n\n"
            "Натисніть на назву, щоб відкрити календар і пости."
        ),
        parse_mode="HTML",
        reply_markup=get_content_plan_channel_selection_keyboard(
            channels, folder_mode=False
        ),
        disable_web_page_preview=True,
    )
    await state.set_state(ContentPlan.selecting_channel)
    await callback.answer()


@router.callback_query(F.data.startswith("cp_select_folder:"))
async def content_plan_folder_picked(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    folder_id = int(callback.data.split(":")[1])
    from database_functions.folders_db import get_user_folders

    channels = get_channels_by_folder(folder_id)
    if not channels:
        await callback.answer("У папці немає каналів", show_alert=True)
        return
    folders = get_user_folders(user_id)
    folder_name = next((f[1] for f in folders if f[0] == folder_id), "Папка")
    await state.update_data(
        content_scope="folder",
        selected_folder_id=folder_id,
        content_plan_scope="folder",
        content_plan_folder_id=folder_id,
        selected_channel_id=None,
        selected_channel_title=folder_name,
        selected_channel_link="#",
    )
    await show_folder_calendar_screen(callback, state, folder_id, edit_message=True)
    await callback.answer()


@router.callback_query(F.data.startswith("cp_select_channel:"))
async def channel_selected(callback: types.CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    channel_info = get_channel_by_id(channel_id)
    if not channel_info:
        await callback.answer("❌ Канал не знайдено")
        return
    
    channel_title = channel_info[2]
    channel_link = channel_info[4] if len(channel_info) > 4 and channel_info[4] else '#'
    
    await state.update_data(
        content_plan_scope="channel",
        content_plan_folder_id=None,
        selected_channel_id=channel_id,
        selected_channel_title=channel_title,
        selected_channel_link=channel_link,
    )
    
    await show_content_plan_calendar_screen(callback, state, channel_id, edit_message=True)
    
    await callback.answer()

async def show_date_content(
    callback_or_message,
    state: FSMContext,
    date_str: str,
    edit_message: bool = False,
    *,
    channel_id: int | None = None,
    folder_id: int | None = None,
    page: int = 0,
    edit_target_message_id: int | None = None,
):
    data = await state.get_data()
    scope = data.get("content_plan_scope", "channel")

    if channel_id is None and folder_id is None:
        if scope == "folder":
            folder_id = data.get("content_plan_folder_id")
        else:
            channel_id = data.get("selected_channel_id")

    channel_title = data.get("selected_channel_title", "Невідомий канал")
    channel_link = data.get("selected_channel_link", "#")
    folder_name = data.get("selected_channel_title", "Папка")

    if scope == "folder" and folder_id is not None:
        ch_rows = get_channels_by_folder(folder_id)
        channel_ids = [c[1] for c in ch_rows]
        posts = get_posts_for_date_channels(channel_ids, date_str)
        stats = get_day_post_stats_for_channels(channel_ids, date_str)
    else:
        posts = (
            get_posts_for_date(channel_id, date_str) if channel_id is not None else []
        )
        stats = (
            get_day_post_stats_for_channel(channel_id, date_str)
            if channel_id is not None
            else {"scheduled": 0, "published_bot": 0, "published_external": 0}
        )

    stats_html = (
        f'{E.stats} <b>Статистика за день:</b>\n'
        f'✅ Опубліковано через бота: <b>{stats["published_bot"]}</b>\n'
        f'⏳ Очікують публікації: <b>{stats["scheduled"]}</b>\n'
        f'📤 Опубліковано в каналі (не через бота): <b>{stats["published_external"]}</b>'
    )

    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        formatted_date = date_obj.strftime("%d.%m")
    except Exception:
        formatted_date = date_str

    total = len(posts)
    total_pages = max(1, (total + CONTENT_PLAN_PAGE_SIZE - 1) // CONTENT_PLAN_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start_i = page * CONTENT_PLAN_PAGE_SIZE
    posts_slice = posts[start_i : start_i + CONTENT_PLAN_PAGE_SIZE]

    if not posts:
        posts_list = (
            f"{E.notes} На цю дату постів немає.\n"
            "Оберіть іншу дату в календарі або заплануйте пост через «Створити пост»."
        )
        post_buttons = []
    else:
        posts_list = f"{E.list} Сторінка <b>{{page}}</b> з <b>{{total_pages}}</b> · Усього постів: <b>{{total}}</b>".format(
            page=page + 1, total_pages=total_pages, total=total
        )
        post_buttons = []

        for i, post in enumerate(posts_slice, start=start_i + 1):
            if post["status"] == "scheduled":
                status_icon = Icon.clock
            elif post.get("published_source") == "external":
                status_icon = Icon.send
            elif post["status"] == "published":
                status_icon = Icon.ok
            else:
                status_icon = Icon.clock

            try:
                if post["type"] == "scheduled":
                    post_data = (
                        json.loads(post["data"][4])
                        if isinstance(post["data"][4], str)
                        else post["data"][4]
                    )
                    if "file_id" in post_data and "media_file_id" not in post_data:
                        post_data["media_file_id"] = post_data["file_id"]
                elif post["type"] == "multi_scheduled":
                    post_data = (
                        json.loads(post["data"][4])
                        if isinstance(post["data"][4], str)
                        else post["data"][4]
                    )
                    if "file_id" in post_data and "media_file_id" not in post_data:
                        post_data["media_file_id"] = post_data["file_id"]
                else:
                    post_data = {}

                is_ad_post = False
                if isinstance(post_data, dict):
                    settings = post_data.get("settings", {})
                    is_ad_post = settings.get("ad_post", False)

                if is_ad_post:
                    status_emoji = "💰"
                    status_icon = Icon.gem

                text = post_data.get("text", "").strip()
                if text:
                    post_title = text[:10]
                    if len(text) > 10:
                        post_title += "..."
                elif post_data.get("has_media"):
                    media_files = post_data.get("media_files", [])

                    if media_files and len(media_files) > 1:
                        media_count = len(media_files)
                        post_title = f"[{media_count} медіа]"
                    else:
                        media_type = post_data.get("media_type", "медіа")
                        media_titles = {
                            "photo": "Фото",
                            "video": "Відео",
                            "document": "Файл",
                            "animation": "GIF",
                        }
                        post_title = media_titles.get(media_type, str(media_type))
                else:
                    post_title = f"Пост #{i}"

                if post["type"] == "multi_scheduled":
                    total_ch = post.get("total_channels", 1)
                    if total_ch > 1:
                        post_title = f"×{total_ch} {post_title}"

            except Exception as e:
                print(f"Error getting post title: {e}")
                post_title = f"Пост #{i}"
                status_icon = Icon.clock

            src = post.get("source_channel_title")
            if src:
                short = src[:18] + "…" if len(src) > 18 else src
                label = f"[{short}] {post_title}"
            else:
                label = post_title

            post_buttons.append(
                [
                    InlineKeyboardButton(
                        text=label[:64],
                        callback_data=f"cp_view_post:{post['type']}:{post['id']}",
                        icon_custom_emoji_id=status_icon,
                    )
                ]
            )

    if scope == "folder" and folder_id is not None:
        keyboard = build_content_plan_day_keyboard(
            "folder",
            date_str,
            post_buttons,
            folder_id=folder_id,
            page=page,
            total_pages=total_pages,
        )
        message_text = (
            f"{E.calendar} <b>{{date}}</b>\n"
            "Папка: <b>{folder_name}</b>\n\n"
            f"{E.notes} Всього постів: {{total_posts}}\n\n"
            "{stats_html}\n\n"
            "{legend}\n\n{posts_list}"
        ).format(
            date=formatted_date,
            folder_name=folder_name,
            total_posts=total,
            stats_html=stats_html,
            legend=f"{E.info} <b>Позначки:</b> • є заплановані пости · ◇ сьогодні · 📤 пост у каналі без бота",
            posts_list=posts_list,
        )
    else:
        keyboard = build_content_plan_day_keyboard(
            "channel",
            date_str,
            post_buttons,
            channel_id=channel_id,
            page=page,
            total_pages=total_pages,
        )
        message_text = (
            f"{E.calendar} <b>{{date}}</b>\n"
            "Канал: <a href=\"{channel_link}\">{channel_title}</a>\n\n"
            f"{E.notes} Всього постів: {{total_posts}}\n\n"
            "{stats_html}\n\n"
            "{legend}\n\n{posts_list}"
        ).format(
            date=formatted_date,
            channel_title=channel_title,
            channel_link=channel_link,
            total_posts=total,
            stats_html=stats_html,
            legend=f"{E.info} <b>Позначки:</b> • є заплановані пости · ◇ сьогодні · 📤 пост у каналі без бота",
            posts_list=posts_list,
        )

    await state.update_data(selected_date=date_str, content_plan_date_page=page)

    chat_id = _user_chat_id(callback_or_message)
    target_mid = edit_target_message_id
    if edit_message and target_mid is None and hasattr(callback_or_message, "message"):
        if callback_or_message.message:
            target_mid = callback_or_message.message.message_id

    if edit_message and target_mid:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=target_mid,
                text=message_text,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        except Exception as e:
            print(f"edit_message day view: {e}")
            await bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
    elif edit_message:
        await callback_or_message.message.edit_text(
            text=message_text,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    else:
        if hasattr(callback_or_message, "message"):
            await callback_or_message.message.answer(
                text=message_text,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        else:
            await callback_or_message.answer(
                text=message_text,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )

    await state.set_state(ContentPlan.viewing_date)

@router.callback_query(F.data.startswith("cp_date:"))
async def date_selected(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    channel_id = int(data_parts[1])
    date_str = data_parts[2]
    await state.update_data(selected_channel_id=channel_id, content_plan_scope="channel")
    await show_date_content(
        callback,
        state,
        date_str,
        edit_message=True,
        channel_id=channel_id,
        page=0,
    )
    await callback.answer()

@router.callback_query(F.data.startswith("cp_back_to_calendar:"))
async def show_calendar(callback: types.CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split(":")[1])
    await show_content_plan_calendar_screen(callback, state, channel_id)
    await callback.answer()

@router.callback_query(F.data.startswith("cp_cal_prev:"))
async def calendar_prev_month(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    channel_id = int(data_parts[1])
    year, month = map(int, data_parts[2].split("-"))
    
    
    start_date = f"{year}-{month:02d}-01"
    end_date = (datetime(year, month, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    end_date_str = end_date.strftime("%Y-%m-%d")
    
    scheduled_dates_raw = get_scheduled_dates_for_channel(channel_id, start_date, end_date_str)
    scheduled_dates = set([date[0] for date in scheduled_dates_raw])  # Витягуємо тільки дати
    
    tz_name = get_user_timezone(callback.from_user.id)
    await callback.message.edit_reply_markup(
        reply_markup=get_content_plan_calendar_keyboard(
            year,
            month,
            channel_id,
            scheduled_dates,
            tz_name=tz_name,
        )
    )
    await callback.answer()

@router.callback_query(F.data.startswith("cp_cal_next:"))
async def calendar_next_month(callback: types.CallbackQuery, state: FSMContext):        
    data_parts = callback.data.split(":")
    channel_id = int(data_parts[1])
    year, month = map(int, data_parts[2].split("-"))
    
    
    start_date = f"{year}-{month:02d}-01"
    end_date = (datetime(year, month, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    end_date_str = end_date.strftime("%Y-%m-%d")
    
    scheduled_dates_raw = get_scheduled_dates_for_channel(channel_id, start_date, end_date_str)
    scheduled_dates = set([date[0] for date in scheduled_dates_raw])  # Витягуємо тільки дати
    
    tz_name = get_user_timezone(callback.from_user.id)
    await callback.message.edit_reply_markup(
        reply_markup=get_content_plan_calendar_keyboard(
            year,
            month,
            channel_id,
            scheduled_dates,
            tz_name=tz_name,
        )
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cp_folder_cal:"))
async def folder_calendar_back(callback: types.CallbackQuery, state: FSMContext):
    folder_id = int(callback.data.split(":")[1])
    await show_folder_calendar_screen(callback, state, folder_id)
    await callback.answer()


@router.callback_query(F.data.startswith("cp_fcal_prev:"))
async def folder_calendar_prev_month(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    folder_id = int(data_parts[1])
    year, month = map(int, data_parts[2].split("-"))

    channel_ids = [c[1] for c in get_channels_by_folder(folder_id)]
    start_date = f"{year}-{month:02d}-01"
    end_date = (datetime(year, month, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    end_date_str = end_date.strftime("%Y-%m-%d")
    scheduled_dates_raw = get_scheduled_dates_for_channels(
        channel_ids, start_date, end_date_str
    )
    scheduled_dates = {d[0] for d in scheduled_dates_raw}

    tz_name = get_user_timezone(callback.from_user.id)
    await callback.message.edit_reply_markup(
        reply_markup=get_content_plan_folder_calendar_keyboard(
            year, month, folder_id, scheduled_dates, tz_name=tz_name
        )
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cp_fcal_next:"))
async def folder_calendar_next_month(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    folder_id = int(data_parts[1])
    year, month = map(int, data_parts[2].split("-"))

    channel_ids = [c[1] for c in get_channels_by_folder(folder_id)]
    start_date = f"{year}-{month:02d}-01"
    end_date = (datetime(year, month, 1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    end_date_str = end_date.strftime("%Y-%m-%d")
    scheduled_dates_raw = get_scheduled_dates_for_channels(
        channel_ids, start_date, end_date_str
    )
    scheduled_dates = {d[0] for d in scheduled_dates_raw}

    tz_name = get_user_timezone(callback.from_user.id)
    await callback.message.edit_reply_markup(
        reply_markup=get_content_plan_folder_calendar_keyboard(
            year, month, folder_id, scheduled_dates, tz_name=tz_name
        )
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cp_fdate:"))
async def folder_date_selected(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    folder_id = int(data_parts[1])
    date_str = data_parts[2]
    data = await state.get_data()
    if data.get("content_plan_folder_id") != folder_id:
        await state.update_data(content_plan_folder_id=folder_id)
    await state.update_data(content_plan_scope="folder")
    await show_date_content(
        callback,
        state,
        date_str,
        edit_message=True,
        folder_id=folder_id,
        page=0,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cp_dpage:"))
async def date_posts_page_channel(callback: types.CallbackQuery, state: FSMContext):
    _, channel_id_s, date_str, page_s = callback.data.split(":", 3)
    channel_id = int(channel_id_s)
    page = int(page_s)
    await show_date_content(
        callback,
        state,
        date_str,
        edit_message=True,
        channel_id=channel_id,
        page=page,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cp_dfpage:"))
async def date_posts_page_folder(callback: types.CallbackQuery, state: FSMContext):
    _, folder_id_s, date_str, page_s = callback.data.split(":", 3)
    folder_id = int(folder_id_s)
    page = int(page_s)
    await show_date_content(
        callback,
        state,
        date_str,
        edit_message=True,
        folder_id=folder_id,
        page=page,
    )
    await callback.answer()

@router.callback_query(F.data.startswith("cp_view_post:"))
async def view_post_actions(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    post_type = data_parts[1]
    post_id = int(data_parts[2])

    await state.update_data(content_plan_anchor_message_id=callback.message.message_id)
    if post_type == 'scheduled':
        post_data = get_scheduled_post_by_id(post_id)
        if not post_data:
            await callback.answer("❌ Пост не знайдено")
            return
        content_data = json.loads(post_data[4])
        if 'file_id' in content_data and 'media_file_id' not in content_data:
            content_data['media_file_id'] = content_data['file_id']
        
    elif post_type == 'multi_scheduled':
        # Для мультипостів використовуємо ту ж схему що й для звичайних постів
        post_data = get_scheduled_post_by_id(post_id)
        if not post_data:
            await callback.answer("❌ Мультипост не знайдено")
            return
        content_data = json.loads(post_data[4])  # post_data зберігається в колонці 4
        if 'file_id' in content_data and 'media_file_id' not in content_data:
            content_data['media_file_id'] = content_data['file_id']
    elif post_type == "published_log":
        row = get_published_post_by_id_content_plan(post_id)
        if not row:
            await callback.answer("❌ Опублікований пост не знайдено")
            return

        channel_id = row[2]
        message_id = row[3]
        url_buttons_raw = row[6] or ""
        ch = get_channel_by_id(channel_id)
        channel_title = ch[2] if ch else "Канал"

        post_link = None
        if ch and len(ch) > 3 and ch[3]:
            post_link = f"https://t.me/{ch[3]}/{message_id}"
        else:
            chat_id_str = str(channel_id)
            chat_id_for_link = chat_id_str[4:] if chat_id_str.startswith("-100") else str(abs(channel_id))
            post_link = f"https://t.me/c/{chat_id_for_link}/{message_id}"

        try:
            bot = callback.bot
            content_data = published_post_content_data(row)
            sent_post = await send_published_post_preview_to_user(
                bot,
                callback.from_user.id,
                channel_id=int(channel_id),
                message_id=int(message_id),
                content_data=content_data,
            )

            actions_message = await bot.send_message(
                chat_id=callback.from_user.id,
                text=(
                    f"{E.settings} "
                    "Цей пост уже опублікований."
                ),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="Відкрити пост", url=post_link, icon_custom_emoji_id=Icon.link)],
                        [InlineKeyboardButton(text="До дня", callback_data="cp_back_to_date", icon_custom_emoji_id=Icon.back)],
                    ]
                ),
                disable_web_page_preview=True,
            )
            await state.update_data(
                sent_post_message_id=sent_post.message_id if sent_post else None,
                actions_message_id=actions_message.message_id,
            )
            await state.update_data(viewing_post_type=post_type, viewing_post_id=post_id)
            await state.set_state(ContentPlan.viewing_post)
            await callback.answer()
            return
        except Exception as e:
            print(f"Error sending published post: {e}")
            await callback.answer("❌ Не вдалося надіслати опублікований пост", show_alert=True)
            return
    
    else:
        await callback.answer("Непідтримуваний тип поста", show_alert=True)
        return
    
    try:
        bot = callback.bot
        
        # Спочатку відправляємо сам пост
        sent_post = await send_post_preview_to_user(bot, callback.from_user.id, content_data)
        
        actions_message = await bot.send_message(
            chat_id=callback.from_user.id,
            text=f"{E.settings} Що зробити з цим постом?",
            parse_mode="HTML",
            reply_markup=get_content_plan_post_actions_keyboard(post_type, post_id),
            disable_web_page_preview=True
        )
        
        await state.update_data(
            sent_post_message_id=sent_post.message_id if sent_post else None,
            actions_message_id=actions_message.message_id
        )
        
    except Exception as e:
        print(f"Error sending post preview: {e}")
        
        # Якщо не вдалось відправити пост, просто покажемо кнопки
        await callback.message.edit_text(
            text=f"{E.settings} Що зробити з цим постом?",
            parse_mode="HTML",
            reply_markup=get_content_plan_post_actions_keyboard(post_type, post_id)
        )
    
    await state.update_data(viewing_post_type=post_type, viewing_post_id=post_id)
    await state.set_state(ContentPlan.viewing_post)
    await callback.answer()


@router.callback_query(F.data.startswith("cp_edit_post_draft:"))
async def edit_post_draft_from_content_plan(
    callback: types.CallbackQuery, state: FSMContext
):
    post_id = int(callback.data.split(":")[1])
    row = get_scheduled_post_row(post_id)
    if not row or row[1] != callback.from_user.id:
        await callback.answer("❌ Пост не знайдено", show_alert=True)
        return
    channel_id = row[2]
    post_data = post_data_from_scheduled_sqlite_row(row)
    data = await state.get_data()
    await state.update_data(
        selected_channels=[channel_id],
        post_data=post_data,
        editing_scheduled_post_id=post_id,
        cp_r_scope=data.get("content_plan_scope", "channel"),
        cp_r_channel_id=data.get("selected_channel_id"),
        cp_r_folder_id=data.get("content_plan_folder_id"),
        cp_r_date=data.get("selected_date"),
        cp_r_page=data.get("content_plan_date_page", 0),
        cp_r_anchor=data.get("content_plan_anchor_message_id"),
    )
    try:
        await send_post_preview(callback.bot, callback.message.chat.id, post_data)
    except Exception as e:
        print(f"preview edit from plan: {e}")
    await callback.bot.send_message(
        chat_id=callback.message.chat.id,
        text=(
            f"{E.tools} <b>Редагування поста</b>\n\n"
            "Натисніть «Далі» → «Запланувати», оберіть дату й час — "
            "зміни збережуться для цього запису в контент-плані."
        ),
        parse_mode="HTML",
        reply_markup=get_post_editing_keyboard(post_data),
    )
    await state.set_state(PostCreation.editing_post)
    await callback.answer()


@router.callback_query(F.data.startswith("cp_delete_confirm:"))
async def delete_post_confirm(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    post_type = data_parts[1]
    post_id = int(data_parts[2])
    
    if post_type == 'scheduled':
        post_data = get_scheduled_post_by_id(post_id)
        if post_data:
            content_data = json.loads(post_data[4])
            if 'file_id' in content_data and 'media_file_id' not in content_data:
                content_data['media_file_id'] = content_data['file_id']
            preview = format_post_preview(content_data)
        else:
            preview = "Пост не знайдено"
    elif post_type == 'multi_scheduled':
        post_data = get_scheduled_post_by_id(post_id)
        if post_data:
            content_data = json.loads(post_data[4])
            if 'file_id' in content_data and 'media_file_id' not in content_data:
                content_data['media_file_id'] = content_data['file_id']
            preview = format_post_preview(content_data)
        else:
            preview = "Мультипост не знайдено"
    else:
        preview = "Пост не знайдено"
    
    await callback.message.edit_text(
        text=("Видалити цей пост?\n\n{preview}").format(preview=preview),
        parse_mode="HTML",
        reply_markup=get_content_plan_delete_confirmation_keyboard(post_type, post_id),
        disable_web_page_preview=True
    )
    
    await callback.answer()

@router.callback_query(F.data.startswith("cp_delete_yes:"))
async def delete_post_confirmed(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    post_type = data_parts[1]
    post_id = int(data_parts[2])
    
    try:
        if post_type == 'scheduled':
            success = delete_scheduled_post(post_id)
        elif post_type == 'multi_scheduled':
            success = delete_scheduled_post(post_id)
        else:
            success = False
        
        if success:
            # Отримуємо інформацію про канал для посилання
            data = await state.get_data()
            channel_title = data.get('selected_channel_title', 'Невідомий канал')
            channel_link = data.get('selected_channel_link', '#')
            
            # Форматуємо текст з посиланням на канал
            channel_link_formatted = f"<a href='{channel_link}'>{channel_title}</a>"
            
            await callback.message.edit_text(
                text=("Пост видалено з контент-плану ({channel_link}).").format(channel_link=channel_link_formatted),
                parse_mode="HTML"
            )
            
            await asyncio.sleep(1.5)
            
            data = await state.get_data()
            selected_date = data.get('selected_date')
            scope = data.get('content_plan_scope', 'channel')
            page = data.get('content_plan_date_page', 0)
            if selected_date:
                if scope == 'folder':
                    folder_id = data.get('content_plan_folder_id')
                    if folder_id:
                        await show_date_content(
                            callback,
                            state,
                            selected_date,
                            edit_message=True,
                            folder_id=folder_id,
                            page=page,
                        )
                else:
                    channel_id = data.get('selected_channel_id')
                    if channel_id:
                        await show_date_content(
                            callback,
                            state,
                            selected_date,
                            edit_message=True,
                            channel_id=channel_id,
                            page=page,
                        )
        else:
            await callback.message.edit_text(
                text=f"{E.warn} Не вдалося видалити пост.",
                parse_mode="HTML"
            )
            await callback.answer("❌")
            
    except Exception as e:
        print(f"Error deleting post: {e}")
        await callback.message.edit_text(
            text=f"{E.warn} Не вдалося видалити пост.",
            parse_mode="HTML"
        )
        await callback.answer("❌")

@router.callback_query(F.data == "cp_back_to_channels")
async def back_to_channels(callback: types.CallbackQuery, state: FSMContext):
    await _show_content_plan_main_menu(callback.message, state, callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "cp_back_to_date")
async def back_to_date(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_date = data.get('selected_date')
    scope = data.get('content_plan_scope', 'channel')
    sent_post_message_id = data.get('sent_post_message_id')
    actions_message_id = data.get('actions_message_id')
    anchor = data.get('content_plan_anchor_message_id')
    page = data.get('content_plan_date_page', 0)
    
    if sent_post_message_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.from_user.id,
                message_id=sent_post_message_id
            )
        except Exception as e:
            print(f"Error deleting sent post: {e}")
    
    if actions_message_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.from_user.id,
                message_id=actions_message_id
            )
        except Exception as e:
            print(f"Error deleting actions message: {e}")
        
    await state.update_data(
        sent_post_message_id=None,
        actions_message_id=None
    )
    
    if not selected_date:
        await callback.answer()
        return

    try:
        if scope == 'folder':
            folder_id = data.get('content_plan_folder_id')
            if folder_id:
                await show_date_content(
                    callback,
                    state,
                    selected_date,
                    edit_message=True,
                    folder_id=folder_id,
                    page=page,
                    edit_target_message_id=anchor,
                )
        else:
            channel_id = data.get('selected_channel_id')
            if channel_id:
                await show_date_content(
                    callback,
                    state,
                    selected_date,
                    edit_message=True,
                    channel_id=channel_id,
                    page=page,
                    edit_target_message_id=anchor,
                )
    except Exception as e:
        print(f"Error editing message, sending new one: {e}")
        try:
            if scope == 'folder':
                folder_id = data.get('content_plan_folder_id')
                if folder_id:
                    await show_date_content(
                        callback,
                        state,
                        selected_date,
                        edit_message=False,
                        folder_id=folder_id,
                        page=page,
                    )
            else:
                channel_id = data.get('selected_channel_id')
                if channel_id:
                    await show_date_content(
                        callback,
                        state,
                        selected_date,
                        edit_message=False,
                        channel_id=channel_id,
                        page=page,
                    )
        except Exception as e2:
            print(f"Error sending new message: {e2}")
            await callback.bot.send_message(
                chat_id=callback.from_user.id,
                text=f"<b>{E.list} Контент-план завантажується...</b>",
                parse_mode="HTML",
            )
    await callback.answer()

@router.callback_query(F.data.startswith("cp_clear_plan_confirm:"))
async def clear_content_plan_first_confirmation(callback: types.CallbackQuery, state: FSMContext):
    """Перше підтвердження очищення контент-плану"""
    channel_id = int(callback.data.split(":")[1])
    
    data = await state.get_data()
    channel_title = data.get('selected_channel_title', 'Невідомий канал')
    channel_link = data.get('selected_channel_link', '#')
    
    await callback.message.edit_text(
        text=(
            "Ви хочете очистити <b>усі заплановані</b> пости для каналу "
            "<a href=\"{channel_link}\">{channel_title}</a>?"
        ).format(
            channel_title=channel_title,
            channel_link=channel_link
        ),
        parse_mode="HTML",
        reply_markup=get_clear_content_plan_first_confirmation_keyboard(channel_id),
        disable_web_page_preview=True
    )
    
    await callback.answer()

@router.callback_query(F.data.startswith("cp_clear_plan_second:"))
async def clear_content_plan_second_confirmation(callback: types.CallbackQuery, state: FSMContext):
    """Друге підтвердження очищення контент-плану"""
    channel_id = int(callback.data.split(":")[1])
    
    data = await state.get_data()
    channel_title = data.get('selected_channel_title', 'Невідомий канал')
    channel_link = data.get('selected_channel_link', '#')
    
    await callback.message.edit_text(
        text=(
            f"{E.warn} Це остаточно. "
            "Усі очікувані (pending) заплановані пости для цього каналу будуть видалені."
        ).format(
            channel_title=channel_title,
            channel_link=channel_link
        ),
        parse_mode="HTML",
        reply_markup=get_clear_content_plan_second_confirmation_keyboard(channel_id),
        disable_web_page_preview=True
    )
    
    await callback.answer()

@router.callback_query(F.data.startswith("cp_clear_plan_execute:"))
async def clear_content_plan_execute(callback: types.CallbackQuery, state: FSMContext):
    """Виконання очищення контент-плану"""
    channel_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    data = await state.get_data()
    channel_title = data.get('selected_channel_title', 'Невідомий канал')
    channel_link = data.get('selected_channel_link', '#')
    
    try:
        # Видаляємо всі заплановані пости
        scheduled_deleted = delete_all_scheduled_posts_for_channel(user_id, channel_id)
        
        if scheduled_deleted > 0:
            await callback.message.edit_text(
                text=("Контент-план очищено для <a href=\"{channel_link}\">{channel_title}</a>.").format(
                    channel_title=channel_title,
                    channel_link=channel_link
                ),
                parse_mode="HTML"
            )
            
            await asyncio.sleep(2)

            await show_content_plan_calendar_screen(
                callback, state, channel_id, edit_message=True
            )
        else:
            await callback.message.edit_text(
                text="Не вдалося очистити контент-план.",
                parse_mode="HTML"
            )
            
    except Exception as e:
        print(f"Error clearing content plan: {e}")
        await callback.message.edit_text(
            text="Не вдалося очистити контент-план.",
            parse_mode="HTML"
        )
    
    await callback.answer()

@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: types.CallbackQuery):
    await callback.answer()

@router.callback_query(F.data.in_(["empty_button", "empty_header", "header_channels", "header_chats"]))
async def ignore_empty_buttons(callback: types.CallbackQuery):
    await callback.answer()

@router.callback_query(F.data.startswith("cp_edit_cal_prev:"))
async def edit_time_calendar_prev_month(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    post_type = data_parts[1]
    post_id = int(data_parts[2])
    year, month = map(int, data_parts[3].split("-"))
    
    
    await callback.message.edit_reply_markup(
        reply_markup=get_edit_time_calendar_keyboard(
            year, month, post_type, post_id, user_id=callback.from_user.id
        ),
        disable_web_page_preview=True
    )
    await callback.answer()

@router.callback_query(F.data.startswith("cp_edit_cal_next:"))
async def edit_time_calendar_next_month(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    post_type = data_parts[1]
    post_id = int(data_parts[2])
    year, month = map(int, data_parts[3].split("-"))
    
    
    await callback.message.edit_reply_markup(
        reply_markup=get_edit_time_calendar_keyboard(
            year, month, post_type, post_id, user_id=callback.from_user.id
        )
    )
    await callback.answer()

@router.callback_query(F.data.startswith("cp_edit_date_"))
async def edit_time_date_selected(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split("_")
    post_type = data_parts[3]
    post_id = int(data_parts[4])
    selected_date = data_parts[5]
    
    
    await state.update_data(selected_edit_date=selected_date)
    
    data = await state.get_data()
    channel_title = data.get('channel_title', 'Невідомий канал')
    channel_link = data.get('selected_channel_link', '#')
    current_time_str = data.get('current_post_time')
    current_time = datetime.fromisoformat(current_time_str)
    
    date_obj = datetime.strptime(selected_date, "%Y-%m-%d")
    formatted_date = date_obj.strftime("%d.%m.%Y")
    tz_note = user_timezone_label(callback.from_user.id)

    hour_texts = {
        'uk': f'''{E.clock} <b>Вибір години</b>

Канал: <a href='{channel_link}'>{channel_title}</a>
Поточний час: {current_time.strftime("%d.%m.%Y %H:%M")}
Вибрана дата: {formatted_date}

{E.clock} Час нижче — у <b>{tz_note}</b>

{E.clock} Введіть годину публікації у форматі <code>ГГ:ХХ</code>

Приклад: <code>15:30</code> або <code>09:15</code>''',
        'ru': f'''{E.clock} <b>Выбор часа</b>

Канал: <a href='{channel_link}'>{channel_title}</a>
Текущее время: {current_time.strftime("%d.%m.%Y %H:%M")}
Выбранная дата: {formatted_date}

{E.clock} Время — в <b>{tz_note}</b>

{E.clock} Введите час публикации в формате <code>ЧЧ:ММ</code>

Пример: <code>15:30</code> или <code>09:15</code>''',
        'en': f'''{E.clock} <b>Time selection</b>

Channel: <a href='{channel_link}'>{channel_title}</a>
Current time: {current_time.strftime("%d.%m.%Y %H:%M")}
Selected date: {formatted_date}

{E.clock} Time is in <b>{tz_note}</b>

{E.clock} Enter publication time in format <code>HH:MM</code>

Example: <code>15:30</code> or <code>09:15</code>'''
    }
    
    await callback.message.edit_text(
        text=hour_texts['uk'],
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад до календаря", callback_data=f"cp_edit_back_to_cal:{post_type}:{post_id}", icon_custom_emoji_id=Icon.back)]
        ]),
        disable_web_page_preview=True
    )
    
    await state.set_state(ContentPlan.editing_post_time_hour)
    await callback.answer()

@router.callback_query(F.data.startswith("cp_edit_back_to_cal:"))
async def edit_time_back_to_calendar(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    post_type = data_parts[1]
    post_id = int(data_parts[2])
    
    
    data = await state.get_data()
    channel_title = data.get('channel_title', 'Невідомий канал')
    channel_link = data.get('selected_channel_link', '#')
    current_time_str = data.get('current_post_time')
    current_time = datetime.fromisoformat(current_time_str)

    uid = callback.from_user.id
    now = datetime.now(ZoneInfo(get_user_timezone(uid)))
    tz_note = user_timezone_label(uid)

    calendar_texts = {
        'uk': f'''{E.calendar} <b>Вибір дати для редагування</b>

Канал: <a href='{channel_link}'>{channel_title}</a>
Поточний час: {current_time.strftime("%d.%m.%Y %H:%M")}

{E.clock} <b>Пояс:</b> {tz_note}

📋 Оберіть нову дату публікації:''',
        'ru': f'''{E.calendar} <b>Выбор даты для редактирования</b>

Канал: <a href='{channel_link}'>{channel_title}</a>
Текущее время: {current_time.strftime("%d.%m.%Y %H:%M")}

{E.clock} <b>Пояс:</b> {tz_note}

📋 Выберите новую дату публикации:''',
        'en': f'''{E.calendar} <b>Date selection for editing</b>

Channel: <a href='{channel_link}'>{channel_title}</a>
Current time: {current_time.strftime("%d.%m.%Y %H:%M")}

{E.clock} <b>Timezone:</b> {tz_note}

📋 Select new publication date:'''
    }
    
    await callback.message.edit_text(
        text=calendar_texts['uk'],
        parse_mode="HTML",
        reply_markup=get_edit_time_calendar_keyboard(
            now.year, now.month, post_type, post_id, user_id=uid
        ),
        disable_web_page_preview=True
    )
    
    await state.set_state(ContentPlan.editing_post_time_date)
    await callback.answer()



@router.callback_query(F.data.startswith("cp_edit_time_confirm:"))
async def edit_time_confirmed(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    post_type = data_parts[1]
    post_id = int(data_parts[2])
    compact = data_parts[3]

    try:
        new_datetime = datetime.strptime(compact, "%Y%m%d%H%M")
        db_str = new_datetime.strftime("%Y-%m-%d %H:%M:%S")
        update_scheduled_post_time(post_id, db_str)

        data = await state.get_data()
        channel_title = data.get('channel_title', 'Невідомий канал')
        channel_link = data.get('selected_channel_link', '#')
        
        tz_note = user_timezone_label(callback.from_user.id)
        success_texts = {
            'uk': f"{E.ok} <b>Час оновлено!</b>\n\nНовий час для поста на каналі <a href='{channel_link}'>{channel_title}</a>: {new_datetime.strftime('%d.%m.%Y %H:%M')}\n{E.clock} {tz_note}",
            'ru': f"{E.ok} <b>Время обновлено!</b>\n\nНовое время для поста на канале <a href='{channel_link}'>{channel_title}</a>: {new_datetime.strftime('%d.%m.%Y %H:%M')}\n{E.clock} {tz_note}",
            'en': f"{E.ok} <b>Time updated!</b>\n\nNew time for post on channel <a href='{channel_link}'>{channel_title}</a>: {new_datetime.strftime('%d.%m.%Y %H:%M')}\n{E.clock} {tz_note}"
        }
        
        await callback.message.edit_text(
            text=success_texts['uk'],
            parse_mode="HTML"
        )
        
        await asyncio.sleep(2)
        
        data = await state.get_data()
        selected_date = data.get('selected_date')
        scope = data.get('content_plan_scope', 'channel')
        page = data.get('content_plan_date_page', 0)
        anchor = data.get('content_plan_anchor_message_id')
        
        if selected_date:
            if scope == 'folder':
                folder_id = data.get('content_plan_folder_id')
                if folder_id:
                    await show_date_content(
                        callback,
                        state,
                        selected_date,
                        edit_message=True,
                        folder_id=folder_id,
                        page=page,
                        edit_target_message_id=anchor,
                    )
            else:
                channel_id = data.get('selected_channel_id')
                if channel_id:
                    await show_date_content(
                        callback,
                        state,
                        selected_date,
                        edit_message=True,
                        channel_id=channel_id,
                        page=page,
                        edit_target_message_id=anchor,
                    )
        await callback.answer()
    except Exception as e:
        print(f"Error updating post time: {e}")
        error_texts = {
            'uk': "❌ Помилка при оновленні часу",
            'ru': "❌ Ошибка при обновлении времени", 
            'en': "❌ Error updating time"
        }
        await callback.message.edit_text(text=error_texts['uk'])
        await callback.answer("❌ Помилка")

@router.message(ContentPlan.editing_post_time_hour)
async def new_time_received(message: types.Message, state: FSMContext):

    # Використовуємо нову функцію парсингу часу
    time_result = parse_time_input_content_plan(message.text)
    
    if not time_result:
        error_texts = {
            'uk': '''❌ <b>Неправильний формат часу!</b>

📝 <b>Підтримувані формати:</b>
• <code>15:30</code> - Вийде в 15:30
• <code>15 30</code> - Вийде в 15:30  
• <code>1530</code> - Вийде в 15:30
• <code>15</code> - Вийде в 15:00

⏰ Спробуйте ще раз:''',
            'ru': '''❌ <b>Неправильный формат времени!</b>

📝 <b>Поддерживаемые форматы:</b>
• <code>15:30</code> - Выйдет в 15:30
• <code>15 30</code> - Выйдет в 15:30
• <code>1530</code> - Выйдет в 15:30
• <code>15</code> - Выйдет в 15:00

⏰ Попробуйте еще раз:''',
            'en': '''❌ <b>Wrong time format!</b>

📝 <b>Supported formats:</b>
• <code>15:30</code> - Will post at 15:30
• <code>15 30</code> - Will post at 15:30
• <code>1530</code> - Will post at 15:30
• <code>15</code> - Will post at 15:00

⏰ Try again:'''
        }
        await message.answer(error_texts['uk'], parse_mode="HTML")
        return
    
    try:
        hour, minute = time_result

        data = await state.get_data()
        selected_date = data.get('selected_edit_date')
        channel_title = data.get('channel_title', 'Невідомий канал')
        channel_link = data.get('selected_channel_link', '#')
        current_time_str = data.get('current_post_time')
        current_time = datetime.fromisoformat(current_time_str)

        tz_name = get_user_timezone(message.from_user.id)
        zi = ZoneInfo(tz_name)
        date_obj = datetime.strptime(selected_date, "%Y-%m-%d")
        new_datetime = datetime(
            date_obj.year, date_obj.month, date_obj.day, hour, minute, tzinfo=zi
        )

        now_local = datetime.now(zi)
        if new_datetime <= now_local:
            past_time_texts = {
                'uk': "❌ Не можна встановлювати час в минулому!",
                'ru': "❌ Нельзя устанавливать время в прошлом!",
                'en': "❌ Cannot set time in the past!"
            }
            await message.answer(past_time_texts['uk'])
            return
        
        tz_note = user_timezone_label(message.from_user.id)
        confirmation_texts = {
            'uk': f'''{E.ok} <b>Підтвердження зміни часу</b>

Канал: <a href='{channel_link}'>{channel_title}</a>

{E.calendar} Поточний час: {current_time.strftime("%d.%m.%Y %H:%M")}
{E.clock} Новий час: {new_datetime.strftime("%d.%m.%Y %H:%M")} ({tz_note})

❓ Підтвердити зміну часу публікації?''',
            'ru': f'''{E.ok} <b>Подтверждение изменения времени</b>

Канал: <a href='{channel_link}'>{channel_title}</a>

{E.calendar} Текущее время: {current_time.strftime("%d.%m.%Y %H:%M")}
{E.clock} Новое время: {new_datetime.strftime("%d.%m.%Y %H:%M")} ({tz_note})

❓ Подтвердить изменение времени публикации?''',
            'en': f'''{E.ok} <b>Confirm time change</b>

Channel: <a href='{channel_link}'>{channel_title}</a>

{E.calendar} Current time: {current_time.strftime("%d.%m.%Y %H:%M")}
{E.clock} New time: {new_datetime.strftime("%d.%m.%Y %H:%M")} ({tz_note})

❓ Confirm publication time change?'''
        }
        
        post_type = data.get('editing_post_type')
        post_id = data.get('editing_post_id')
        
        await message.answer(
            text=confirmation_texts['uk'],
            parse_mode="HTML",
            reply_markup=get_edit_time_confirmation_keyboard(post_type, post_id, new_datetime),
            disable_web_page_preview=True
        )   
        
    except ValueError:
        error_texts = {
            'uk': "❌ Неправильний формат часу! Перевірте введені дані.",
            'ru': "❌ Неправильный формат времени! Проверьте введенные данные.",
            'en': "❌ Invalid time format! Check entered data."
        }
        await message.answer(error_texts['uk'])
    except Exception as e:
        print(f"Error processing time input: {e}")
        error_texts = {
            'uk': "❌ Помилка при обробці часу",
            'ru': "❌ Ошибка при обработке времени",
            'en': "❌ Error processing time"
        }
        await message.answer(error_texts['uk'])

@router.callback_query(F.data.startswith("cp_edit_time:"))
async def edit_post_time_show_calendar(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    post_type = data_parts[1]
    post_id = int(data_parts[2])
    
    if post_type not in ("scheduled", "multi_scheduled"):
        await callback.answer("❌ Можна редагувати час тільки для запланованих постів")
        return
    
    
    post_data = get_scheduled_post_by_id(post_id)
    if not post_data:
        await callback.answer("❌ Пост не знайдено")
        return
    
    channel_title = post_data[3]
    current_time = datetime.fromisoformat(post_data[5])
    
    await state.update_data(
        editing_post_id=post_id,
        editing_post_type=post_type,
        channel_title=channel_title,
        current_post_time=current_time.isoformat()
    )
    
    data = await state.get_data()
    channel_link = data.get('selected_channel_link', '#')
    
    uid = callback.from_user.id
    now = datetime.now(ZoneInfo(get_user_timezone(uid)))
    tz_note = user_timezone_label(uid)

    calendar_texts = {
        'uk': f'''{E.calendar} <b>Вибір дати для редагування</b>

Канал: <a href='{channel_link}'>{channel_title}</a>
Поточний час: {current_time.strftime("%d.%m.%Y %H:%M")}

{E.clock} <b>Пояс:</b> {tz_note}

📋 Оберіть нову дату публікації:''',
        'ru': f'''{E.calendar} <b>Выбор даты для редактирования</b>

Канал: <a href='{channel_link}'>{channel_title}</a>
Текущее время: {current_time.strftime("%d.%m.%Y %H:%M")}

{E.clock} <b>Пояс:</b> {tz_note}

📋 Выберите новую дату публикации:''',
        'en': f'''{E.calendar} <b>Date selection for editing</b>

Channel: <a href='{channel_link}'>{channel_title}</a>
Current time: {current_time.strftime("%d.%m.%Y %H:%M")}

{E.clock} <b>Timezone:</b> {tz_note}

📋 Select new publication date:'''
    }
    
    await callback.message.edit_text(
        text=calendar_texts['uk'],
        parse_mode="HTML",
        reply_markup=get_edit_time_calendar_keyboard(
            now.year, now.month, post_type, post_id, user_id=uid
        ),
        disable_web_page_preview=True
    )
    
    await state.set_state(ContentPlan.editing_post_time_date)
    await callback.answer()

async def execute_cp_publish_now(
    callback: types.CallbackQuery, state: FSMContext, post_type: str, post_id: int
) -> None:
    import logging

    from services.posts.delivery import deliver_post_to_channel

    log = logging.getLogger(__name__)
    try:
        from database_functions.billing_db import denial

        reason = denial(callback.from_user.id, "posting")
        if reason:
            await callback.answer(reason, show_alert=True)
            return

        post_row = get_scheduled_post_by_id(post_id)
        if not post_row:
            await callback.answer("❌ Пост не знайдено")
            return

        channel_id = post_row[2]
        channel_title = post_row[3]
        content_data = json.loads(post_row[4])
        if "file_id" in content_data and "media_file_id" not in content_data:
            content_data["media_file_id"] = content_data["file_id"]

        media_files = list(content_data.get("media_files") or [])
        if (
            content_data.get("has_media")
            and not media_files
            and (content_data.get("media_file_id") or content_data.get("media_id"))
        ):
            media_files = [
                {
                    "type": content_data.get("media_type") or "photo",
                    "file_id": content_data.get("media_file_id")
                    or content_data.get("media_id"),
                }
            ]

        url_buttons = None
        if content_data.get("url_buttons"):
            url_buttons = deserialize_url_buttons(content_data["url_buttons"])

        post_payload = {
            "text": content_data.get("text", ""),
            "media_files": media_files,
            "url_buttons": url_buttons or [],
            "settings": content_data.get("settings") or {},
        }
        stored_buttons = ""
        if content_data.get("url_buttons"):
            try:
                stored_buttons = json.dumps(
                    content_data.get("url_buttons", []), ensure_ascii=False
                )
            except Exception:
                stored_buttons = ""

        uid = post_row[1]
        result = await deliver_post_to_channel(
            bot,
            user_id=uid,
            channel_id=channel_id,
            post_data=post_payload,
            scheduled_post_id=post_id,
            url_buttons_log=stored_buttons,
        )

        if not result.ok:
            await callback.message.edit_text(
                "❌ <b>Не вдалося опублікувати пост у канал.</b>",
                parse_mode="HTML",
            )
            await callback.answer("❌ Помилка")
            return

        settings = post_payload["settings"]
        if not settings.get("comments", True) and result.message_id:
            from database_functions.channels_db import auto_detect_discussion_group

            ch_row = get_channel_by_id(int(channel_id))
            discussion_group_id = ch_row[9] if ch_row and len(ch_row) > 9 else None
            if not discussion_group_id:
                discussion_group_id = await auto_detect_discussion_group(
                    bot, int(channel_id)
                )
            if discussion_group_id:
                from utils.client_functions import delete_discussion_message_with_delay

                asyncio.create_task(
                    delete_discussion_message_with_delay(bot, discussion_group_id, 6)
                )

        delete_scheduled_post(post_id)

        ch_row = get_channel_by_id(int(channel_id))
        channel_link = ch_row[4] if ch_row and len(ch_row) > 4 and ch_row[4] else "#"
        post_link = result.post_link or "#"

        await callback.message.edit_text(
            text=(
                f"{E.brand} <b>Пост опублікований!</b>\n\n"
                f"✅ Успішно опубліковано зараз на каналі "
                f"<a href='{channel_link}'>{channel_title}</a>\n"
                f"⚠️ Пост видалено з контент-плану"
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Відкрити пост", url=post_link, icon_custom_emoji_id=Icon.link)]
                ]
            ),
        )
        await callback.answer("✅ Пост опублікований!")
        await asyncio.sleep(2)

        data = await state.get_data()
        selected_date = data.get("selected_date")
        scope = data.get("content_plan_scope", "channel")
        page = data.get("content_plan_date_page", 0)
        anchor = data.get("content_plan_anchor_message_id")

        if selected_date:
            if scope == "folder":
                folder_id = data.get("content_plan_folder_id")
                if folder_id:
                    await show_date_content(
                        callback,
                        state,
                        selected_date,
                        edit_message=True,
                        folder_id=folder_id,
                        page=page,
                        edit_target_message_id=anchor,
                    )
            else:
                cid = data.get("selected_channel_id")
                if cid:
                    await show_date_content(
                        callback,
                        state,
                        selected_date,
                        edit_message=True,
                        channel_id=cid,
                        page=page,
                        edit_target_message_id=anchor,
                    )

    except Exception:
        log.exception("Error publishing post now")
        await callback.message.edit_text(
            text="❌ <b>Помилка при публікації поста</b>",
            parse_mode="HTML",
        )
        await callback.answer("❌ Помилка")


@router.callback_query(F.data.startswith("cp_publish_now:"))
async def publish_post_now_confirm(callback: types.CallbackQuery, state: FSMContext):   
    data_parts = callback.data.split(":")
    post_type = data_parts[1]
    post_id = int(data_parts[2])
    
    if post_type not in ("scheduled", "multi_scheduled"):
        await callback.answer("❌ Можна опублікувати тільки заплановані пости")
        return
    
    
    post_data = get_scheduled_post_by_id(post_id)
    if not post_data:
        await callback.answer("❌ Пост не знайдено")
        return

    if not get_user_confirm_publish_status(callback.from_user.id):
        await execute_cp_publish_now(callback, state, post_type, post_id)
        return
    
    channel_title = post_data[3]
    scheduled_time = datetime.fromisoformat(post_data[5])
    owner_uid = post_data[1]
    tz_note = user_timezone_label(owner_uid)
    
    data = await state.get_data()
    channel_link = data.get('selected_channel_link', '#')
    
    confirm_texts = {
        'uk': f'''{E.brand} <b>Підтвердження публікації</b>

Канал: <a href='{channel_link}'>{channel_title}</a>
Запланований час: {scheduled_time.strftime("%d.%m.%Y %H:%M")} ({tz_note})

❓ Ви дійсно хочете опублікувати цей пост зараз?
⚠️ Пост буде видалений з контент-плану''',
        'ru': f'''{E.brand} <b>Подтверждение публикации</b>

Канал: <a href='{channel_link}'>{channel_title}</a>
Запланированное время: {scheduled_time.strftime("%d.%m.%Y %H:%M")} ({tz_note})

❓ Вы действительно хотите опубликовать этот пост сейчас?
⚠️ Пост будет удален из контент-плана''',
        'en': f'''{E.brand} <b>Confirm publication</b>

Channel: <a href='{channel_link}'>{channel_title}</a>
Scheduled time: {scheduled_time.strftime("%d.%m.%Y %H:%M")} ({tz_note})

❓ Do you really want to publish this post now?
⚠️ Post will be removed from content plan'''
    }
    
    confirm_publish_buttons = {
        'uk': ["Так, опублікувати", "Ні"],
        'ru': ["Да, опубликовать", "Нет"],
        'en': ["Yes, publish", "No"]
    }
    
    buttons = confirm_publish_buttons['uk']
    
    confirm_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=buttons[0],
                callback_data=f"cp_publish_now_yes:{post_type}:{post_id}",
                icon_custom_emoji_id=Icon.ok,
            ),
            InlineKeyboardButton(
                text=buttons[1],
                callback_data="cp_back_to_date",
                icon_custom_emoji_id=Icon.cancel,
            ),
        ]
    ])
    
    await callback.message.edit_text(
        text=confirm_texts['uk'],
        parse_mode="HTML",
        reply_markup=confirm_keyboard,
        disable_web_page_preview=True
    )
    
    await callback.answer()

@router.callback_query(F.data.startswith("cp_publish_now_yes:"))
async def publish_post_now(callback: types.CallbackQuery, state: FSMContext):
    data_parts = callback.data.split(":")
    post_type = data_parts[1]
    post_id = int(data_parts[2])
    await execute_cp_publish_now(callback, state, post_type, post_id)


