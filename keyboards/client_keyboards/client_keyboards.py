"""Main reply keyboard + support links (markup only)."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from database_functions.admin_db import get_all_administrators
from texts import Main, Support
from utils.ui_emoji import Icon


def get_start_keyboard(user_id: int, language: str = "uk") -> ReplyKeyboardMarkup:
    del language  # reserved for future locales
    rows = [
        [
            KeyboardButton(text=Main.create_post, icon_custom_emoji_id=Icon.sign),
            KeyboardButton(text=Main.edit_post, icon_custom_emoji_id=Icon.sign),
        ],
        [
            KeyboardButton(text=Main.add_channel, icon_custom_emoji_id=Icon.channel),
            KeyboardButton(text=Main.content_plan, icon_custom_emoji_id=Icon.calendar),
        ],
        [
            KeyboardButton(text=Main.copy, icon_custom_emoji_id=Icon.copy),
            KeyboardButton(text=Main.search_posts, icon_custom_emoji_id=Icon.search),
        ],
        [
            KeyboardButton(text=Main.my_profile, icon_custom_emoji_id=Icon.user),
            KeyboardButton(text=Main.settings, icon_custom_emoji_id=Icon.settings),
        ],
        [KeyboardButton(text=Main.support, icon_custom_emoji_id=Icon.support)],
    ]
    if user_id in get_all_administrators():
        rows.append(
            [KeyboardButton(text=Main.admin_panel, icon_custom_emoji_id=Icon.brand)]
        )
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def get_support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=Support.support,
                    icon_custom_emoji_id=Icon.support,
                    url="https://t.me/SkyPostHelp",
                )
            ],
            [
                InlineKeyboardButton(
                    text=Support.news,
                    icon_custom_emoji_id=Icon.news,
                    url="https://t.me/SkyPost_News",
                )
            ],
            [
                InlineKeyboardButton(
                    text=Support.manager,
                    icon_custom_emoji_id=Icon.user,
                    url="https://t.me/SkyPostHelp",
                )
            ],
        ]
    )
