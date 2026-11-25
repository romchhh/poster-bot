"""Folder selection / move keyboards (markup only)."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database_functions.folders_db import get_user_folders
from texts import Btn, Folder
from utils.ui_emoji import Icon


def get_folder_selection_keyboard(
    user_id: int, show_create_new: bool = True
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for folder in get_user_folders(user_id):
        folder_id, folder_name, channels_count = folder[0], folder[1], folder[5]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{folder_name} ({channels_count})",
                    callback_data=f"select_folder_{folder_id}",
                    icon_custom_emoji_id=Icon.folder,
                )
            ]
        )
    if show_create_new:
        rows.append(
            [
                InlineKeyboardButton(
                    text=Folder.create_new,
                    callback_data="create_new_folder",
                    icon_custom_emoji_id=Icon.add,
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=Folder.add_without,
                callback_data="add_without_folder",
                icon_custom_emoji_id=Icon.folder_open,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=Btn.cancel,
                    callback_data="cancel_folder_creation",
                    icon_custom_emoji_id=Icon.cancel,
                )
            ]
        ]
    )


def get_folder_move_keyboard(user_id: int, channel_id: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for folder in get_user_folders(user_id):
        folder_id, folder_name, channels_count = folder[0], folder[1], folder[5]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{folder_name} ({channels_count})",
                    callback_data=f"move_to_folder_{folder_id}_{channel_id}",
                    icon_custom_emoji_id=Icon.folder,
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=Folder.create_new,
                callback_data=f"create_folder_for_{channel_id}",
                icon_custom_emoji_id=Icon.add,
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=Folder.leave_without,
                callback_data=f"skip_folder_{channel_id}",
                icon_custom_emoji_id=Icon.ok,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_channel_settings_folder_move_keyboard(
    user_id: int, channel_id: int
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for folder in get_user_folders(user_id):
        folder_id, folder_name, channels_count = folder[0], folder[1], folder[5]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{folder_name} ({channels_count})",
                    callback_data=f"schf_mv:{folder_id}:{channel_id}",
                    icon_custom_emoji_id=Icon.folder,
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=Folder.create_new,
                    callback_data=f"schf_new:{channel_id}",
                    icon_custom_emoji_id=Icon.add,
                )
            ],
            [
                InlineKeyboardButton(
                    text=Folder.remove_from,
                    callback_data=f"schf_nop:{channel_id}",
                    icon_custom_emoji_id=Icon.folder_open,
                )
            ],
            [
                InlineKeyboardButton(
                    text=Folder.to_channel_settings,
                    callback_data=f"channel_settings_{channel_id}",
                    icon_custom_emoji_id=Icon.back,
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
