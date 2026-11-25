from utils.ui_emoji import Icon
from texts import Btn, Calendar, ContentPlan, Settings
import calendar
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database_functions.client_db import get_user_timezone


def get_content_plan_channel_menu_keyboard(folders, channels_without_folder):
    keyboard = []
    for folder in folders:
        folder_id = folder[0]
        folder_name = folder[1]
        channels_count = folder[5] if len(folder) > 5 else 0
        display_name = folder_name[:40] + "…" if len(folder_name) > 40 else folder_name
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{display_name} ({channels_count})",
                    icon_custom_emoji_id=Icon.folder,
                    callback_data=f"cp_select_folder:{folder_id}",
                )
            ]
        )
    for channel in channels_without_folder:
        channel_id = channel[1]
        channel_title = channel[2]
        display_title = channel_title[:35] + "…" if len(channel_title) > 35 else channel_title
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{display_title}",
                    icon_custom_emoji_id=Icon.channel,
                    callback_data=f"cp_select_channel:{channel_id}",
                )
            ]
        )
    keyboard.append(
        [
            InlineKeyboardButton(
                text=Settings.all_channels_list,
                icon_custom_emoji_id=Icon.channel,
                callback_data="cp_cp_show_all_channels",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_content_plan_channel_selection_keyboard(channels, folder_mode: bool = False):
    channels_list = []
    chats_list = []
    for channel_info in channels:
        chat_type = (
            channel_info[5] if len(channel_info) > 5 and channel_info[5] else "channel"
        )
        if chat_type == "channel":
            channels_list.append(channel_info)
        else:
            chats_list.append(channel_info)

    keyboard = []
    if channels_list and chats_list:
        keyboard.append(
            [
                InlineKeyboardButton(text=ContentPlan.channels, callback_data="header_channels", icon_custom_emoji_id=Icon.channel),
                InlineKeyboardButton(text=ContentPlan.groups, callback_data="header_chats", icon_custom_emoji_id=Icon.users),
            ]
        )
    elif channels_list:
        keyboard.append(
            [
                InlineKeyboardButton(text=ContentPlan.channels, callback_data="header_channels", icon_custom_emoji_id=Icon.channel),
                InlineKeyboardButton(text=" ", callback_data="empty_header"),
            ]
        )
    elif chats_list:
        keyboard.append(
            [
                InlineKeyboardButton(text=" ", callback_data="empty_header"),
                InlineKeyboardButton(text=ContentPlan.groups, callback_data="header_chats", icon_custom_emoji_id=Icon.users),
            ]
        )

    max_rows = max(len(channels_list), len(chats_list))
    for i in range(max_rows):
        row = []
        if i < len(channels_list):
            channel = channels_list[i]
            channel_id = channel[1]
            channel_title = channel[2]
            display_title = (
                channel_title[:15] + "…" if len(channel_title) > 15 else channel_title
            )
            row.append(
                InlineKeyboardButton(
                    text=f"{display_title}",
                    callback_data=f"cp_select_channel:{channel_id}",
                icon_custom_emoji_id=Icon.channel,
            )
            )
        else:
            row.append(InlineKeyboardButton(text=" ", callback_data="empty_button"))

        if i < len(chats_list):
            chat = chats_list[i]
            chat_id = chat[1]
            chat_title = chat[2]
            display_title = chat_title[:15] + "…" if len(chat_title) > 15 else chat_title
            row.append(
                InlineKeyboardButton(
                    text=f"{display_title}",
                    callback_data=f"cp_select_channel:{chat_id}",
                icon_custom_emoji_id=Icon.channel,
            )
            )
        else:
            row.append(InlineKeyboardButton(text=" ", callback_data="empty_button"))

        keyboard.append(row)

    nav = []
    if folder_mode:
        nav.append(
            InlineKeyboardButton(
                text=ContentPlan.to_channel_menu,
                callback_data="cp_back_to_folders",
                icon_custom_emoji_id=Icon.back,
            )
        )
    nav.append(
        InlineKeyboardButton(text=ContentPlan.to_channel_menu, callback_data="cp_back_to_mode", icon_custom_emoji_id=Icon.back)
    )
    keyboard.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_content_plan_calendar_keyboard(
    year,
    month,
    channel_id,
    scheduled_dates,
    language=None,
    tz_name: str | None = None,
):
    tz = tz_name or "Europe/Kyiv"
    now_local = datetime.now(ZoneInfo(tz))
    today_day = (
        now_local.day
        if (year == now_local.year and month == now_local.month)
        else None
    )

    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year

    if month == 12:
        next_month, next_year = 1, year + 1
    else:
        next_month, next_year = month + 1, year

    keyboard = []
    month_name = Calendar.months[month - 1]
    keyboard.append(
        [
            InlineKeyboardButton(
                text=Btn.back,
                callback_data=f"cp_cal_prev:{channel_id}:{year}-{prev_month:02d}",
            icon_custom_emoji_id=Icon.back,
        ),
            InlineKeyboardButton(text=f"{month_name} {year}", callback_data="ignore", icon_custom_emoji_id=Icon.calendar),
            InlineKeyboardButton(
                text=Btn.next,
                callback_data=f"cp_cal_next:{channel_id}:{year}-{next_month:02d}",
            icon_custom_emoji_id=Icon.next,
        ),
        ]
    )
    keyboard.append(
        [
            InlineKeyboardButton(text=day, callback_data="ignore")
            for day in Calendar.weekdays
        ]
    )

    for week in calendar.monthcalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                d_str = f"{year}-{month:02d}-{day:02d}"
                markers = "•" if d_str in scheduled_dates else ""
                if day == today_day:
                    label = f"{markers}{day}" if markers else f"◇{day}"
                else:
                    label = f"{markers}{day}" if markers else str(day)
                row.append(
                    InlineKeyboardButton(
                        text=label,
                        callback_data=f"cp_date:{channel_id}:{d_str}",
                    )
                )
        keyboard.append(row)

    keyboard.append(
        [
            InlineKeyboardButton(
                text=ContentPlan.clear_plan,
                icon_custom_emoji_id=Icon.trash,
                callback_data=f"cp_clear_plan_confirm:{channel_id}",
            )
        ]
    )
    keyboard.append(
        [
            InlineKeyboardButton(
                text=ContentPlan.to_channels_list, callback_data="cp_back_to_channels", icon_custom_emoji_id=Icon.back
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_content_plan_folder_calendar_keyboard(
    year, month, folder_id, scheduled_dates, language=None, tz_name: str | None = None
):
    tz = tz_name or "Europe/Kyiv"
    now_local = datetime.now(ZoneInfo(tz))
    today_day = (
        now_local.day
        if (year == now_local.year and month == now_local.month)
        else None
    )

    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year

    if month == 12:
        next_month, next_year = 1, year + 1
    else:
        next_month, next_year = month + 1, year

    keyboard = []
    month_name = Calendar.months[month - 1]
    keyboard.append(
        [
            InlineKeyboardButton(
                text=Btn.back,
                callback_data=f"cp_fcal_prev:{folder_id}:{year}-{prev_month:02d}",
            icon_custom_emoji_id=Icon.back,
        ),
            InlineKeyboardButton(text=f"{month_name} {year}", callback_data="ignore", icon_custom_emoji_id=Icon.calendar),
            InlineKeyboardButton(
                text=Btn.next,
                callback_data=f"cp_fcal_next:{folder_id}:{year}-{next_month:02d}",
            icon_custom_emoji_id=Icon.next,
        ),
        ]
    )
    keyboard.append(
        [
            InlineKeyboardButton(text=day, callback_data="ignore")
            for day in Calendar.weekdays
        ]
    )

    for week in calendar.monthcalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                d_str = f"{year}-{month:02d}-{day:02d}"
                markers = "•" if d_str in scheduled_dates else ""
                if day == today_day:
                    label = f"{markers}{day}" if markers else f"◇{day}"
                else:
                    label = f"{markers}{day}" if markers else str(day)
                row.append(
                    InlineKeyboardButton(
                        text=label,
                        callback_data=f"cp_fdate:{folder_id}:{d_str}",
                    )
                )
        keyboard.append(row)

    keyboard.append(
        [
            InlineKeyboardButton(
                text=ContentPlan.to_channels_list, callback_data="cp_back_to_channels", icon_custom_emoji_id=Icon.back
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_content_plan_day_keyboard(
    scope: str,
    date_str: str,
    post_button_rows: list,
    *,
    channel_id: int | None = None,
    folder_id: int | None = None,
    page: int = 0,
    total_pages: int = 1,
):
    rows = []
    if scope == "channel":
        rows.append(
            [
                InlineKeyboardButton(
                    text=ContentPlan.to_calendar,
                    icon_custom_emoji_id=Icon.back,
                    callback_data=f"cp_back_to_calendar:{channel_id}",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=ContentPlan.clear_plan,
                    icon_custom_emoji_id=Icon.trash,
                    callback_data=f"cp_clear_plan_confirm:{channel_id}",
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text=ContentPlan.to_calendar,
                    icon_custom_emoji_id=Icon.back,
                    callback_data=f"cp_folder_cal:{folder_id}",
                )
            ]
        )
    rows.extend(post_button_rows)
    if total_pages > 1:
        nav = []
        if page > 0:
            prev_cb = (
                f"cp_dpage:{channel_id}:{date_str}:{page - 1}"
                if scope == "channel"
                else f"cp_dfpage:{folder_id}:{date_str}:{page - 1}"
            )
            nav.append(InlineKeyboardButton(text=Btn.back, callback_data=prev_cb, icon_custom_emoji_id=Icon.back))
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}", callback_data="ignore",
            icon_custom_emoji_id=Icon.doc,
        )
        )
        if page < total_pages - 1:
            next_cb = (
                f"cp_dpage:{channel_id}:{date_str}:{page + 1}"
                if scope == "channel"
                else f"cp_dfpage:{folder_id}:{date_str}:{page + 1}"
            )
            nav.append(InlineKeyboardButton(text=Btn.next, callback_data=next_cb, icon_custom_emoji_id=Icon.next))
        rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(
                text=ContentPlan.to_channels_list, callback_data="cp_back_to_channels", icon_custom_emoji_id=Icon.back
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)




def get_content_plan_post_actions_keyboard(post_type, post_id, language=None):
    keyboard = [
        [
            InlineKeyboardButton(
                text=Settings.datetime_btn,
                icon_custom_emoji_id=Icon.calendar,
                callback_data=f"cp_edit_time:{post_type}:{post_id}",
            ),
            InlineKeyboardButton(
                text=ContentPlan.publish_now,
                icon_custom_emoji_id=Icon.send,
                callback_data=f"cp_publish_now:{post_type}:{post_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=ContentPlan.edit_now,
                icon_custom_emoji_id=Icon.sign,
                callback_data=f"cp_edit_post_draft:{post_id}",
            ),
            InlineKeyboardButton(
                text=ContentPlan.from_plan,
                icon_custom_emoji_id=Icon.cancel,
                callback_data=f"cp_delete_confirm:{post_type}:{post_id}",
            ),
        ],
        [InlineKeyboardButton(text=ContentPlan.to_day, callback_data="cp_back_to_date", icon_custom_emoji_id=Icon.back)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_content_plan_post_details_keyboard(post_type, post_id, language=None):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=Btn.delete, callback_data=f"cp_delete_confirm:{post_type}:{post_id}", icon_custom_emoji_id=Icon.cancel)],
            [InlineKeyboardButton(text=ContentPlan.to_day, callback_data="cp_back_to_date", icon_custom_emoji_id=Icon.back)],
        ]
    )


def get_content_plan_delete_confirmation_keyboard(post_type, post_id, language=None):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=ContentPlan.yes_delete, callback_data=f"cp_delete_yes:{post_type}:{post_id}", icon_custom_emoji_id=Icon.ok_alt),
                InlineKeyboardButton(text=Btn.no, callback_data=f"cp_view_post:{post_type}:{post_id}", icon_custom_emoji_id=Icon.cancel),
            ]
        ]
    )


def get_edit_time_calendar_keyboard(
    year, month, post_type, post_id, language=None, user_id: int | None = None
):
    tz_name = get_user_timezone(user_id) if user_id is not None else "Europe/Kyiv"
    now = datetime.now(ZoneInfo(tz_name))
    today_day = now.day if (year == now.year and month == now.month) else None

    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year

    if month == 12:
        next_month, next_year = 1, year + 1
    else:
        next_month, next_year = month + 1, year

    keyboard = []
    month_name = Calendar.months[month - 1]
    keyboard.append(
        [
            InlineKeyboardButton(
                text=Btn.back,
                callback_data=f"cp_edit_cal_prev:{post_type}:{post_id}:{prev_year}-{prev_month:02d}",
            icon_custom_emoji_id=Icon.back,
        ),
            InlineKeyboardButton(text=f"{month_name} {year}", callback_data="ignore", icon_custom_emoji_id=Icon.calendar),
            InlineKeyboardButton(
                text=Btn.next,
                callback_data=f"cp_edit_cal_next:{post_type}:{post_id}:{next_year}-{next_month:02d}",
            icon_custom_emoji_id=Icon.next,
        ),
        ]
    )
    keyboard.append(
        [InlineKeyboardButton(text=day, callback_data="ignore") for day in Calendar.weekdays]
    )

    for week in calendar.monthcalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                current_date = datetime(year, month, day, tzinfo=now.tzinfo)
                if current_date.date() >= now.date():
                    day_text = f"📌{day}" if day == today_day else f"{day}"
                    callback_data = f"cp_edit_date_{post_type}_{post_id}_{year}-{month:02d}-{day:02d}"
                else:
                    day_text = "·"
                    callback_data = "ignore"
                row.append(
                    InlineKeyboardButton(text=day_text, callback_data=callback_data)
                )
        keyboard.append(row)

    keyboard.append(
        [InlineKeyboardButton(text=Btn.back, callback_data="cp_back_to_date", icon_custom_emoji_id=Icon.back)]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_edit_time_confirmation_keyboard(post_type, post_id, new_datetime, language=None):
    compact = new_datetime.strftime("%Y%m%d%H%M")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=Btn.confirm,
                    icon_custom_emoji_id=Icon.ok_alt,
                    callback_data=f"cp_edit_time_confirm:{post_type}:{post_id}:{compact}",
                ),
                InlineKeyboardButton(text=Btn.cancel, callback_data="cp_back_to_date", icon_custom_emoji_id=Icon.cancel),
            ]
        ]
    )


def get_clear_content_plan_first_confirmation_keyboard(channel_id, language=None):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=ContentPlan.clear_yes, callback_data=f"cp_clear_plan_second:{channel_id}", icon_custom_emoji_id=Icon.ok_alt),
                InlineKeyboardButton(text=Btn.cancel, callback_data="cp_back_to_date", icon_custom_emoji_id=Icon.cancel),
            ]
        ]
    )


def get_clear_content_plan_second_confirmation_keyboard(channel_id, language=None):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=ContentPlan.clear_exact, callback_data=f"cp_clear_plan_execute:{channel_id}", icon_custom_emoji_id=Icon.ok_alt),
                InlineKeyboardButton(text=Btn.cancel, callback_data="cp_back_to_date", icon_custom_emoji_id=Icon.cancel),
            ]
        ]
    )
