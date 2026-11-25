"""Inline keyboards for create / edit / schedule post (markup only)."""

from __future__ import annotations

import calendar
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database_functions.channels_db import get_channels_by_folder
from database_functions.client_db import get_user_timezone
from texts import Btn, Calendar, Post, post_autodel_button_label, post_flag_label
from utils.ui_emoji import Icon, Plus


def _folder_row_prefix(folder_id: int, selected_ids: Optional[list]) -> str:
    """Prefix: full / partial selection of folder channels."""
    selected_ids = selected_ids or []
    ids = [r[1] for r in get_channels_by_folder(folder_id)]
    if not ids:
        return ""
    n_sel = sum(1 for i in ids if i in selected_ids)
    if n_sel == len(ids):
        return "✓ "
    if n_sel > 0:
        return f"{n_sel}/{len(ids)} "
    return ""


def _split_channels_and_groups(channel_rows: list) -> tuple[list, list]:
    channels, groups = [], []
    for row in channel_rows:
        chat_type = row[5] if len(row) > 5 and row[5] else "channel"
        (channels if chat_type == "channel" else groups).append(row)
    return channels, groups


def _append_two_column_channel_group_rows(
    keyboard: list,
    channels_list: list,
    groups_list: list,
    *,
    selected_ids: Optional[list] = None,
    max_title_len: int = 15,
    toggle_callback_fmt: str = "toggle_channel_{cid}",
) -> None:
    selected_ids = selected_ids or []
    empty = InlineKeyboardButton(text=Btn.spacer, callback_data="ignore")

    if channels_list and groups_list:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=Btn.channels, callback_data="ignore", icon_custom_emoji_id=Icon.channel
                ),
                InlineKeyboardButton(
                    text=Btn.groups, callback_data="ignore", icon_custom_emoji_id=Icon.users
                ),
            ]
        )
    elif channels_list:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=Btn.channels, callback_data="ignore", icon_custom_emoji_id=Icon.channel
                ),
                empty,
            ]
        )
    elif groups_list:
        keyboard.append(
            [
                empty,
                InlineKeyboardButton(
                    text=Btn.groups, callback_data="ignore", icon_custom_emoji_id=Icon.users
                ),
            ]
        )

    for i in range(max(len(channels_list), len(groups_list))):
        row: list[InlineKeyboardButton] = []
        if i < len(channels_list):
            cid, title = channels_list[i][1], channels_list[i][2]
            short = title[:max_title_len] + "…" if len(title) > max_title_len else title
            row.append(
                InlineKeyboardButton(
                    text=short,
                    callback_data=toggle_callback_fmt.format(cid=cid),
                    icon_custom_emoji_id=Icon.ok if cid in selected_ids else Icon.channel,
                )
            )
        else:
            row.append(empty)

        if i < len(groups_list):
            gid, gtitle = groups_list[i][1], groups_list[i][2]
            short = gtitle[:max_title_len] + "…" if len(gtitle) > max_title_len else gtitle
            row.append(
                InlineKeyboardButton(
                    text=short,
                    callback_data=toggle_callback_fmt.format(cid=gid),
                    icon_custom_emoji_id=Icon.ok if gid in selected_ids else Icon.users,
                )
            )
        else:
            row.append(empty)
        keyboard.append(row)


def get_post_all_channels_select_keyboard(
    channel_rows: list, selected_channels: Optional[list] = None
) -> InlineKeyboardMarkup:
    selected_channels = selected_channels or []
    keyboard: list = []
    ch_list, gr_list = _split_channels_and_groups(channel_rows)
    _append_two_column_channel_group_rows(
        keyboard,
        ch_list,
        gr_list,
        selected_ids=selected_channels,
        toggle_callback_fmt="post_all_toggle_{cid}",
    )
    keyboard.append(
        [
            InlineKeyboardButton(
                text=Post.confirm_selection,
                callback_data="confirm_channel_selection",
                icon_custom_emoji_id=Icon.ok_alt,
            )
        ]
    )
    keyboard.append(
        [
            InlineKeyboardButton(
                text=Post.back_to_selection,
                callback_data="post_view_all_channels_back",
                icon_custom_emoji_id=Icon.back,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_channels_main_menu_keyboard(
    folders, channels_without_folder, selected_channels=None
) -> InlineKeyboardMarkup:
    selected_channels = selected_channels or []
    keyboard: list = [
        [
            InlineKeyboardButton(
                text=Post.select_all_channels,
                icon_custom_emoji_id=Icon.ok_alt,
                callback_data="select_all_channels",
            )
        ],
        [
            InlineKeyboardButton(
                text=Post.all_folders,
                icon_custom_emoji_id=Icon.folder,
                callback_data="select_all_folders",
            )
        ],
        [
            InlineKeyboardButton(
                text=Post.view_all_channels,
                callback_data="post_view_all_channels",
                icon_custom_emoji_id=Icon.search,
            )
        ],
    ]

    for folder in folders or []:
        folder_id, folder_name, channels_count = folder[0], folder[1], folder[5]
        display = folder_name[:40] + "..." if len(folder_name) > 40 else folder_name
        prefix = _folder_row_prefix(folder_id, selected_channels)
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix}{display} ({channels_count})",
                    icon_custom_emoji_id=Icon.folder,
                    callback_data=f"select_post_folder_{folder_id}",
                )
            ]
        )

    if channels_without_folder:
        ch_list, gr_list = _split_channels_and_groups(channels_without_folder)
        _append_two_column_channel_group_rows(
            keyboard, ch_list, gr_list, selected_ids=selected_channels
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                text=Post.confirm_selection,
                icon_custom_emoji_id=Icon.ok_alt,
                callback_data="confirm_channel_selection",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_folder_channels_keyboard(
    folder_id, channels, selected_channels=None
) -> InlineKeyboardMarkup:
    selected_channels = selected_channels or []
    keyboard: list = [
        [
            InlineKeyboardButton(
                text=Post.select_whole_folder,
                icon_custom_emoji_id=Icon.ok_alt,
                callback_data=f"select_whole_folder_{folder_id}",
            )
        ]
    ]
    ch_list, gr_list = _split_channels_and_groups(channels)
    _append_two_column_channel_group_rows(
        keyboard, ch_list, gr_list, selected_ids=selected_channels
    )
    keyboard.append(
        [
            InlineKeyboardButton(
                text=Post.back_to_folders,
                icon_custom_emoji_id=Icon.back,
                callback_data="back_to_folders_menu",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_no_folder_channels_keyboard(
    channels, selected_channels=None
) -> InlineKeyboardMarkup:
    selected_channels = selected_channels or []
    keyboard: list = [
        [
            InlineKeyboardButton(
                text=Post.select_all,
                icon_custom_emoji_id=Icon.ok_alt,
                callback_data="select_all_no_folder",
            )
        ]
    ]
    ch_list, gr_list = _split_channels_and_groups(channels)
    _append_two_column_channel_group_rows(
        keyboard, ch_list, gr_list, selected_ids=selected_channels
    )
    keyboard.append(
        [
            InlineKeyboardButton(
                text=Post.back_to_folders,
                icon_custom_emoji_id=Icon.back,
                callback_data="back_to_folders_menu",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def _switch(on: bool) -> str:
    return Plus.switch_on if on else Plus.switch_off


def get_post_editing_keyboard(post_data=None) -> InlineKeyboardMarkup:
    post_data = post_data or {}
    settings = post_data.get("settings") or {}
    sound_on = bool(settings.get("notification", True))
    comments_on = not settings.get("disable_comments", False)
    album = len(post_data.get("media_files") or []) > 1
    rows: list = [
            [
                InlineKeyboardButton(
                    text=Post.text_btn,
                    callback_data="edit_text",
                    icon_custom_emoji_id=Plus.text,
                ),
                InlineKeyboardButton(
                    text=Post.media_btn,
                    callback_data="edit_media",
                    icon_custom_emoji_id=Icon.photo,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=Post.generate_image,
                    callback_data="post_generate_image",
                    icon_custom_emoji_id=Icon.spark,
                )
            ],
            [
                InlineKeyboardButton(
                    text=Post.ai,
                    callback_data="post_ai_menu",
                    icon_custom_emoji_id=Icon.notes,
                )
            ],
    ]
    if not album:
        rows.append(
            [
                InlineKeyboardButton(
                    text=Post.add_buttons,
                    callback_data="edit_url_buttons",
                    icon_custom_emoji_id=Plus.plus,
                )
            ]
        )
    rows.extend([
            [
                InlineKeyboardButton(
                    text=Post.replace_links,
                    callback_data="post_replace_links",
                    icon_custom_emoji_id=Plus.refresh,
                )
            ],
            [
                InlineKeyboardButton(
                    text=Post.autosign,
                    callback_data="toggle_autosign",
                    icon_custom_emoji_id=_switch(bool(settings.get("autosign"))),
                ),
                InlineKeyboardButton(
                    text=Post.comments,
                    callback_data="toggle_comments",
                    icon_custom_emoji_id=_switch(comments_on),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=Post.pin,
                    callback_data="toggle_pin",
                    icon_custom_emoji_id=_switch(bool(settings.get("pin_message"))),
                ),
                InlineKeyboardButton(
                    text=Post.with_sound,
                    callback_data="toggle_notification",
                    icon_custom_emoji_id=Plus.bell if sound_on else Plus.bell_off,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=Post.content_protect,
                    callback_data="toggle_protect",
                    icon_custom_emoji_id=_switch(bool(settings.get("content_protection"))),
                ),
                InlineKeyboardButton(
                    text=Post.review,
                    callback_data="toggle_review",
                    icon_custom_emoji_id=_switch(bool(settings.get("review"))),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=post_flag_label(
                        Post.no_format, bool(settings.get("skip_channel_format"))
                    ),
                    callback_data="toggle_plain",
                    icon_custom_emoji_id=_switch(bool(settings.get("skip_channel_format"))),
                )
            ],
            [
                InlineKeyboardButton(
                    text=Btn.back, callback_data="post_back", icon_custom_emoji_id=Icon.back
                ),
                InlineKeyboardButton(
                    text=Btn.next, callback_data="post_next", icon_custom_emoji_id=Icon.next
                ),
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_publishing_menu_keyboard(post_data=None) -> InlineKeyboardMarkup:
    settings = (post_data or {}).get("settings") or {}
    mode = settings.get("publish_mode") or "copy"
    reply_set = bool(settings.get("reply_to"))
    reply_label = Post.reply_post + (" ✓" if reply_set else "")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=post_autodel_button_label(post_data),
                    callback_data="set_auto_delete",
                    icon_custom_emoji_id=Plus.clock,
                )
            ],
            [
                InlineKeyboardButton(
                    text=post_flag_label(Post.ad_top, bool(settings.get("ad_top"))),
                    callback_data="pub_toggle_ad",
                    icon_custom_emoji_id=Icon.copy,
                )
            ],
            [
                InlineKeyboardButton(
                    text=post_flag_label(Post.autorepeat, bool(settings.get("autorepeat"))),
                    callback_data="pub_toggle_repeat",
                    icon_custom_emoji_id=Plus.refresh,
                )
            ],
            [
                InlineKeyboardButton(
                    text=reply_label,
                    callback_data="pub_reply",
                    icon_custom_emoji_id=Icon.back,
                )
            ],
            [
                InlineKeyboardButton(
                    text=Post.copy_publish,
                    callback_data="pub_mode_copy",
                    icon_custom_emoji_id=Plus.ok if mode == "copy" else Icon.doc,
                ),
                InlineKeyboardButton(
                    text=Post.forward_publish,
                    callback_data="pub_mode_forward",
                    icon_custom_emoji_id=Plus.ok if mode == "forward" else Icon.link,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=Post.postpone,
                    callback_data="schedule_post",
                    icon_custom_emoji_id=Plus.calendar,
                ),
                InlineKeyboardButton(
                    text=Post.publish,
                    callback_data="post_publish_now",
                    icon_custom_emoji_id=Icon.send,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=Btn.back,
                    callback_data="back_to_editing",
                    icon_custom_emoji_id=Icon.back,
                )
            ],
        ]
    )


def get_auto_delete_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=Post.autodel_15m, callback_data="autodel_15", icon_custom_emoji_id=Icon.clock
                ),
                InlineKeyboardButton(
                    text=Post.autodel_30m, callback_data="autodel_30", icon_custom_emoji_id=Icon.clock
                ),
                InlineKeyboardButton(
                    text=Post.autodel_1h, callback_data="autodel_60", icon_custom_emoji_id=Icon.clock
                ),
            ],
            [
                InlineKeyboardButton(
                    text=Post.autodel_3h, callback_data="autodel_180", icon_custom_emoji_id=Icon.clock
                ),
                InlineKeyboardButton(
                    text=Post.autodel_6h, callback_data="autodel_360", icon_custom_emoji_id=Icon.clock
                ),
            ],
            [
                InlineKeyboardButton(
                    text=Post.autodel_12h, callback_data="autodel_720", icon_custom_emoji_id=Icon.clock
                ),
                InlineKeyboardButton(
                    text=Post.autodel_24h, callback_data="autodel_1440", icon_custom_emoji_id=Icon.clock
                ),
                InlineKeyboardButton(
                    text=Post.autodel_48h, callback_data="autodel_2880", icon_custom_emoji_id=Icon.clock
                ),
            ],
            [
                InlineKeyboardButton(
                    text=Post.no_autodel,
                    callback_data="autodel_disable",
                    icon_custom_emoji_id=Icon.cancel,
                )
            ],
            [
                InlineKeyboardButton(
                    text=Btn.back,
                    callback_data="back_to_publishing",
                    icon_custom_emoji_id=Icon.back,
                )
            ],
        ]
    )


def get_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=Btn.yes, callback_data="confirm_yes", icon_custom_emoji_id=Icon.ok_alt
                ),
                InlineKeyboardButton(
                    text=Btn.no, callback_data="confirm_no", icon_custom_emoji_id=Icon.cancel
                ),
            ]
        ]
    )


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return get_step_cancel_keyboard("cancel_action")


def get_url_buttons_prompt_keyboard(
    style: str | None = None, cancel_callback: str = "post_step_cancel"
) -> InlineKeyboardMarkup:
    def mark(name: str, active: bool) -> str:
        return f"{name} ✓" if active else name

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=mark("Червона", style == "danger"),
                    callback_data="post_url_style_danger",
                ),
                InlineKeyboardButton(
                    text=mark("Зелена", style == "success"),
                    callback_data="post_url_style_success",
                ),
                InlineKeyboardButton(
                    text=mark("Синя", style == "primary"),
                    callback_data="post_url_style_primary",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Без кольору" if style else "Колір не вибрано",
                    callback_data="post_url_style_off",
                )
            ],
            [
                InlineKeyboardButton(
                    text=Btn.cancel,
                    callback_data=cancel_callback,
                    icon_custom_emoji_id=Icon.cancel,
                )
            ],
        ]
    )


def get_post_ai_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=Post.ai_improve, callback_data="post_ai_improve"),
                InlineKeyboardButton(text=Post.ai_rewrite, callback_data="post_ai_rewrite"),
            ],
            [InlineKeyboardButton(text=Post.ai_heads, callback_data="post_ai_heads")],
            [
                InlineKeyboardButton(text=Post.ai_uk, callback_data="post_ai_uk"),
                InlineKeyboardButton(text=Post.ai_en, callback_data="post_ai_en"),
            ],
            [
                InlineKeyboardButton(text=Post.ai_ideas, callback_data="post_ai_ideas"),
                InlineKeyboardButton(text=Post.ai_proof, callback_data="post_ai_proof"),
            ],
            [
                InlineKeyboardButton(
                    text=Btn.cancel,
                    callback_data="post_step_cancel",
                    icon_custom_emoji_id=Icon.cancel,
                )
            ],
        ]
    )


def get_ai_variants_keyboard(variants: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for index, variant in enumerate(variants[:3]):
        label = " ".join(variant.split())
        if len(label) > 60:
            label = label[:57] + "…"
        rows.append(
            [InlineKeyboardButton(text=label or f"{index + 1}", callback_data=f"post_ai_pick_{index}")]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=Btn.cancel,
                callback_data="post_step_cancel",
                icon_custom_emoji_id=Icon.cancel,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_step_cancel_keyboard(callback_data: str = "post_step_cancel") -> InlineKeyboardMarkup:
    """One «Скасувати» button for any prompt that waits for the next message."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=Btn.cancel,
                    callback_data=callback_data,
                    icon_custom_emoji_id=Icon.cancel,
                )
            ]
        ]
    )


def get_schedule_calendar_keyboard(
    year=None,
    month=None,
    user_id: int | None = None,
    *,
    callback_prefix: str = "schedule",
    back_callback_data: str = "back_to_publishing",
) -> InlineKeyboardMarkup:
    tz_name = get_user_timezone(user_id) if user_id is not None else "Europe/Kyiv"
    now = datetime.now(ZoneInfo(tz_name))
    year = year or now.year
    month = month or now.month
    today_day = now.day if (year == now.year and month == now.month) else None

    prev_month, prev_year = (12, year - 1) if month == 1 else (month - 1, year)
    next_month, next_year = (1, year + 1) if month == 12 else (month + 1, year)

    keyboard: list = [
        [
            InlineKeyboardButton(
                text=Btn.back,
                callback_data=f"{callback_prefix}_cal_prev:{prev_year}-{prev_month:02d}",
                icon_custom_emoji_id=Icon.back,
            ),
            InlineKeyboardButton(
                text=Calendar.month_title(month, year),
                callback_data="ignore",
                icon_custom_emoji_id=Icon.calendar,
            ),
            InlineKeyboardButton(
                text=Btn.next,
                callback_data=f"{callback_prefix}_cal_next:{next_year}-{next_month:02d}",
                icon_custom_emoji_id=Icon.next,
            ),
        ],
        [
            InlineKeyboardButton(text=day, callback_data="ignore")
            for day in Calendar.weekdays
        ],
    ]

    for week in calendar.monthcalendar(year, month):
        row: list[InlineKeyboardButton] = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=Btn.spacer, callback_data="ignore"))
                continue
            current = datetime(year, month, day, tzinfo=now.tzinfo)
            if current.date() >= now.date():
                kwargs = {
                    "text": str(day),
                    "callback_data": f"{callback_prefix}_date_{year}-{month:02d}-{day:02d}",
                    "icon_custom_emoji_id": (
                        Icon.calendar if day == today_day else Icon.clock
                    ),
                }
            else:
                kwargs = {"text": Btn.past_day, "callback_data": "ignore"}
            row.append(InlineKeyboardButton(**kwargs))
        keyboard.append(row)

    keyboard.append(
        [
            InlineKeyboardButton(
                text=Btn.back,
                callback_data=back_callback_data,
                icon_custom_emoji_id=Icon.back,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
