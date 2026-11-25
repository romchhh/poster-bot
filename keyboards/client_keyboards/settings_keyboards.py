from utils.ui_emoji import Icon
from texts import Btn, Folder, Settings
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, SwitchInlineQueryChosenChat

from database_functions.client_db import (
    TIMEZONE_META_UK,
    get_timezone_info,
    get_user_confirm_publish_status,
    get_user_notifications_status,
    get_user_timezone,
)


def channel_hub_callback_data(channel_id: int, *, from_copy_branch: bool) -> str:
    """Hub після налаштувань: звичні «Налаштування» або гілка «Копіювання»."""
    if from_copy_branch:
        return f"cpy_stg:c:{channel_id}:cpy"
    return f"channel_settings_{channel_id}"


def get_settings_main_keyboard(user_id: int | None = None) -> InlineKeyboardMarkup:
    notifications_enabled = True
    confirm_publish_enabled = True
    if user_id:
        notifications_enabled = get_user_notifications_status(user_id)
        confirm_publish_enabled = get_user_confirm_publish_status(user_id)

    tz_info = get_timezone_info()
    user_tz = get_user_timezone(user_id) if user_id else "Europe/Kyiv"
    tz_meta = tz_info.get(user_tz, {})
    tz_title = tz_meta.get("name_uk", user_tz)
    tz_time = tz_meta.get("current_time", "")
    timezone_line = f"🕐 {tz_title} · {tz_time}" if tz_time else f"🕐 {tz_title}"

    notification_emoji = "🔔" if notifications_enabled else "🔕"
    confirm_emoji = "✅" if confirm_publish_enabled else "❌"

    rows = [
        [
            InlineKeyboardButton(
                text=Settings.channels_groups,
                icon_custom_emoji_id=Icon.channel,
                callback_data="settings_channels",
            )
        ],
        [
            InlineKeyboardButton(
                text=Settings.autolinks,
                icon_custom_emoji_id=Icon.link,
                callback_data="settings_autolinks",
            )
        ],
        [
            InlineKeyboardButton(
                text=Settings.my_folders,
                icon_custom_emoji_id=Icon.folder,
                callback_data="settings_folders_manage",
            )
        ],
        [
            InlineKeyboardButton(
                text=Settings.profile,
                icon_custom_emoji_id=Icon.user,
                callback_data="settings_profile",
            )
        ],
        [
            InlineKeyboardButton(
                text=Settings.subscription,
                icon_custom_emoji_id=Icon.calendar,
                callback_data="settings_subscription",
            )
        ],
        [
            InlineKeyboardButton(
                text=Settings.add_channel_or_group,
                icon_custom_emoji_id=Icon.channel,
                callback_data="addsettings_channel",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{confirm_emoji} {Settings.confirm_publish}",
                icon_custom_emoji_id=Icon.settings,
                callback_data="settings_confirm_publish",
            )
        ],
        [
            InlineKeyboardButton(
                text=timezone_line,
                icon_custom_emoji_id=Icon.calendar,
                callback_data="settings_timezone",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{notification_emoji} {Settings.notifications}",
                icon_custom_emoji_id=Icon.support,
                callback_data="settings_notifications",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_back_to_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=Settings.to_settings,
                    icon_custom_emoji_id=Icon.settings,
                    callback_data="back_to_settings",
                )
            ]
        ]
    )


def get_profile_keyboard(referral_link: str) -> InlineKeyboardMarkup:
    from utils.referral_share import REFERRAL_SHARE_QUERY

    _ = referral_link
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=Settings.share,
                    switch_inline_query_chosen_chat=SwitchInlineQueryChosenChat(
                        query=REFERRAL_SHARE_QUERY,
                        allow_user_chats=True,
                        allow_bot_chats=False,
                        allow_group_chats=True,
                        allow_channel_chats=False,
                    ),
                    icon_custom_emoji_id=Icon.send,
                )
            ],
            [
                InlineKeyboardButton(
                    text=Settings.to_settings,
                    icon_custom_emoji_id=Icon.settings,
                    callback_data="back_to_settings",
                )
            ],
        ]
    )


def get_settings_channels_intro_keyboard(
    folders, channels_without_folder
) -> InlineKeyboardMarkup:
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
                    callback_data=f"settings_folder_channels:{folder_id}",
                icon_custom_emoji_id=Icon.folder,
            )
            ]
        )
    for channel in channels_without_folder:
        cid = channel[1]
        title = channel[2]
        display_title = title[:35] + "…" if len(title) > 35 else title
        prefix = "📺" if (len(channel) > 5 and (channel[5] or "channel") == "channel") else "👥"
        role_mark = "👑" if len(channel) > 11 and channel[11] == "owner" else "🛡"
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{prefix} {display_title} {role_mark}",
                    callback_data=f"channel_settings_{cid}",
                icon_custom_emoji_id=Icon.doc,
            )
            ]
        )
    keyboard.append(
        [
            InlineKeyboardButton(
                text=Settings.all_channels_list,
                callback_data="settings_channels_flat",
            icon_custom_emoji_id=Icon.channel,
        )
        ]
    )
    keyboard.append(
        [
            InlineKeyboardButton(
                text=Settings.to_settings,
                icon_custom_emoji_id=Icon.settings,
                callback_data="back_to_settings",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_settings_channels_grid_keyboard(
    channels, back_callback_data: str
) -> InlineKeyboardMarkup:
    channels_list = []
    groups_list = []
    for channel_info in channels:
        chat_type = (
            channel_info[5] if len(channel_info) > 5 and channel_info[5] else "channel"
        )
        if chat_type == "channel":
            channels_list.append(channel_info)
        else:
            groups_list.append(channel_info)

    keyboard = []
    if channels_list and groups_list:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=ContentPlan.channels, callback_data="header_channels",
                icon_custom_emoji_id=Icon.channel,
            ),
                InlineKeyboardButton(text=ContentPlan.groups, callback_data="header_groups", icon_custom_emoji_id=Icon.users),
            ]
        )
    elif channels_list:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=ContentPlan.channels, callback_data="header_channels",
                icon_custom_emoji_id=Icon.channel,
            ),
                InlineKeyboardButton(text=" ", callback_data="empty_header"),
            ]
        )
    elif groups_list:
        keyboard.append(
            [
                InlineKeyboardButton(text=" ", callback_data="empty_header"),
                InlineKeyboardButton(
                    text=ContentPlan.groups, callback_data="header_groups",
                icon_custom_emoji_id=Icon.users,
            ),
            ]
        )

    max_rows = max(len(channels_list), len(groups_list))
    for i in range(max_rows):
        row = []
        if i < len(channels_list):
            ch = channels_list[i]
            cid = ch[1]
            title = ch[2]
            display_title = title[:15] + "…" if len(title) > 15 else title
            role_mark = "👑" if len(ch) > 11 and ch[11] == "owner" else "🛡"
            row.append(
                InlineKeyboardButton(
                    text=f"{display_title} {role_mark}",
                    callback_data=f"channel_settings_{cid}",
                icon_custom_emoji_id=Icon.doc,
            )
            )
        else:
            row.append(InlineKeyboardButton(text=" ", callback_data="empty_button"))

        if i < len(groups_list):
            g = groups_list[i]
            gid = g[1]
            title = g[2]
            display_title = title[:15] + "…" if len(title) > 15 else title
            role_mark = "👑" if len(g) > 11 and g[11] == "owner" else "🛡"
            row.append(
                InlineKeyboardButton(
                    text=f"{display_title} {role_mark}",
                    callback_data=f"channel_settings_{gid}",
                icon_custom_emoji_id=Icon.doc,
            )
            )
        else:
            row.append(InlineKeyboardButton(text=" ", callback_data="empty_button"))

        keyboard.append(row)

    keyboard.append(
        [
            InlineKeyboardButton(
                text=ContentPlan.to_channel_menu,
                callback_data=back_callback_data,
            icon_custom_emoji_id=Icon.back,
        )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_timezone_selection_keyboard(current_timezone: str) -> InlineKeyboardMarkup:
    rows = []
    info = get_timezone_info()
    for tz_id in TIMEZONE_META_UK.keys():
        meta = info.get(tz_id, {})
        name = meta.get("name_uk", tz_id)
        tim = meta.get("current_time", "")
        label = f"{name} ({tim})" if tim else name
        if len(label) > 64:
            label = label[:61] + "…"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"set_timezone_{tz_id}",
                    icon_custom_emoji_id=Icon.ok if tz_id == current_timezone else Icon.clock,
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=Settings.to_settings,
                icon_custom_emoji_id=Icon.settings,
                callback_data="back_to_settings",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_channel_settings_keyboard(
    channel_id: int,
    is_channel: bool,
    *,
    channel_in_folder: bool = False,
) -> InlineKeyboardMarkup:
    del_text = Settings.delete_channel if is_channel else Settings.delete_group
    if is_channel:
        folder_btn_text = (
            Settings.change_folder_channel
            if channel_in_folder
            else Settings.add_folder_channel
        )
    else:
        folder_btn_text = (
            Settings.change_folder_group
            if channel_in_folder
            else Settings.add_folder_group
        )
    keyboard = [
        [
            InlineKeyboardButton(
                text=Settings.editors,
                icon_custom_emoji_id=Icon.users,
                callback_data=f"channel_admins_list_{channel_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text=Settings.channel_settings,
                icon_custom_emoji_id=Icon.settings,
                callback_data=f"cpy_stg:c:{channel_id}:chs",
            )
        ],
        [
            InlineKeyboardButton(
                text=folder_btn_text,
                icon_custom_emoji_id=Icon.folder,
                callback_data=f"channel_folder_flow:{channel_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text=Settings.delete_last_post,
                callback_data=f"del_last_post:{channel_id}",
                icon_custom_emoji_id=Icon.trash,
            )
        ],
        [
            InlineKeyboardButton(
                text=Settings.deletion_log,
                callback_data=f"del_log:{channel_id}",
                icon_custom_emoji_id=Icon.list,
            )
        ],
        [
            InlineKeyboardButton(
                text=del_text,
                callback_data=f"delete_channel_{channel_id}",
                icon_custom_emoji_id=Icon.trash,
            )
        ],
        [
            InlineKeyboardButton(
                text=ContentPlan.to_channels_list,
                icon_custom_emoji_id=Icon.channel,
                callback_data="settings_channels",
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_channel_admins_list_keyboard(
    channel_id: int,
    channel_members,
    can_manage_admins: bool,
    is_superadmin: bool = False,
) -> InlineKeyboardMarkup:
    rows = []
    if is_superadmin:
        rows.append(
            [
                InlineKeyboardButton(
                    text=Settings.add_editor,
                    callback_data=f"channel_add_editor_{channel_id}",
                icon_custom_emoji_id=Icon.add,
            )
            ]
        )
    for member in channel_members or []:
        user_id = member[0]
        role = member[1]
        username = member[2]
        first_name = member[3] or ""
        last_name = member[4] or ""
        full_name = f"{first_name} {last_name}".strip()
        display = (username or full_name or f"ID: {user_id}")[:40]
        prefix = "👑" if role == "owner" else "👤"
        if role == "admin" and can_manage_admins:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{prefix} {display}",
                        callback_data=f"channel_admin_info_{channel_id}_{user_id}",
                    icon_custom_emoji_id=Icon.doc,
                ),
                    InlineKeyboardButton(
                        text=Btn.delete, icon_custom_emoji_id=Icon.cancel,
                        callback_data=f"channel_admin_remove_{channel_id}_{user_id}",
                    ),
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{prefix} {display}",
                        callback_data=f"channel_admin_info_{channel_id}_{user_id}",
                    icon_custom_emoji_id=Icon.doc,
                )
                ]
            )
    rows.append(
        [
            InlineKeyboardButton(
                text=Folder.to_channel_settings,
                icon_custom_emoji_id=Icon.channel,
                callback_data=f"channel_settings_{channel_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_channel_start_emoji_keyboard(
    channel_id: int, has_emoji: bool, *, from_copy_manage: bool = False
) -> InlineKeyboardMarkup:
    hub_cd = channel_hub_callback_data(channel_id, from_copy_branch=from_copy_manage)
    suf = "|cpy" if from_copy_manage else ""
    rows = []
    if has_emoji:
        rows.append(
            [
                InlineKeyboardButton(
                    text=Settings.replace_emoji,
                    callback_data=f"cse|r|{channel_id}{suf}",
                icon_custom_emoji_id=Icon.refresh,
            ),
                InlineKeyboardButton(
                    text=Btn.delete,
                    callback_data=f"cse|x|{channel_id}{suf}",
                icon_custom_emoji_id=Icon.trash,
            ),
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text=Settings.add_premium_emoji,
                    callback_data=f"cse|a|{channel_id}{suf}",
                icon_custom_emoji_id=Icon.add,
            )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=Settings.to_channel,
                icon_custom_emoji_id=Icon.channel,
                callback_data=hub_cd,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_auto_signature_create_keyboard(
    channel_id: int, *, from_copy_manage: bool = False
) -> InlineKeyboardMarkup:
    hub_cd = channel_hub_callback_data(channel_id, from_copy_branch=from_copy_manage)
    sfx = "|cpy" if from_copy_manage else ""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=Settings.add_autosign,
                    callback_data=f"auto_signature_create_{channel_id}{sfx}",
                icon_custom_emoji_id=Icon.add,
            )
            ],
            [
                InlineKeyboardButton(
                    text=Settings.to_channel,
                    callback_data=hub_cd,
                icon_custom_emoji_id=Icon.back,
            )
            ],
        ]
    )


def get_back_to_auto_signature_keyboard(
    channel_id: int, *, from_copy_manage: bool = False
) -> InlineKeyboardMarkup:
    sfx = "|cpy" if from_copy_manage else ""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=Btn.back,
                    callback_data=f"auto_signature_settings_{channel_id}{sfx}",
                icon_custom_emoji_id=Icon.back,
            )
            ]
        ]
    )


def get_auto_signature_manage_keyboard(
    signature_id: int, channel_id: int, *, from_copy_manage: bool = False
) -> InlineKeyboardMarkup:
    hub_cd = channel_hub_callback_data(channel_id, from_copy_branch=from_copy_manage)
    sfx = "|cpy" if from_copy_manage else ""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=Settings.edit_text,
                    callback_data=f"auto_signature_edit_{signature_id}_{channel_id}{sfx}",
                icon_custom_emoji_id=Icon.sign,
            )
            ],
            [
                InlineKeyboardButton(
                    text=Btn.delete,
                    callback_data=f"auto_signature_delete_{signature_id}{sfx}",
                icon_custom_emoji_id=Icon.trash,
            )
            ],
            [
                InlineKeyboardButton(
                    text=Settings.to_channel,
                    callback_data=hub_cd,
                icon_custom_emoji_id=Icon.back,
            )
            ],
        ]
    )


def get_auto_signature_save_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=Btn.save, callback_data="auto_signature_save", icon_custom_emoji_id=Icon.ok),
                InlineKeyboardButton(text=Btn.cancel, callback_data="auto_signature_cancel", icon_custom_emoji_id=Icon.cancel),
            ]
        ]
    )


def get_settings_folders_manage_keyboard(folders) -> InlineKeyboardMarkup:
    rows = []
    for folder in folders:
        fid = folder[0]
        name = folder[1]
        cnt = folder[5] if len(folder) > 5 else 0
        display = name[:28] + "…" if len(name) > 28 else name
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{display} ({cnt})",
                    callback_data=f"settings_folder_panel:{fid}",
                icon_custom_emoji_id=Icon.doc,
            )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=Settings.create_folder,
                icon_custom_emoji_id=Icon.folder,
                callback_data="settings_folder_create",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=Settings.to_settings_short,
                icon_custom_emoji_id=Icon.settings,
                callback_data="back_to_settings",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_settings_folder_panel_keyboard(folder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=Settings.rename,
                    callback_data=f"settings_folder_rename:{folder_id}",
                    icon_custom_emoji_id=Icon.settings,
                ),
                InlineKeyboardButton(
                    text=Btn.delete,
                    callback_data=f"settings_folder_delete:{folder_id}",
                    icon_custom_emoji_id=Icon.cancel,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=Settings.delete_last_folder,
                    callback_data=f"del_last_folder:{folder_id}",
                    icon_custom_emoji_id=Icon.trash,
                )
            ],
            [
                InlineKeyboardButton(
                    text=Settings.to_folders,
                    callback_data="settings_folders_manage",
                    icon_custom_emoji_id=Icon.folder,
                )
            ],
        ]
    )
