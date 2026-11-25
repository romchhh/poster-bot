"""Autolink keyboards — markup only."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from texts import Btn, Settings
from utils.ui_emoji import Icon


def channels_keyboard(channels: list) -> InlineKeyboardMarkup:
    rows = []
    for row in channels:
        channel_id, title = row[1], row[2] or "Чат"
        label = title if len(title) <= 40 else title[:39] + "…"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"al_ch_{channel_id}",
                    icon_custom_emoji_id=Icon.channel,
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=Settings.to_settings,
                callback_data="back_to_settings",
                icon_custom_emoji_id=Icon.settings,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def channel_sets_keyboard(channel_id: int, sets: list) -> InlineKeyboardMarkup:
    rows = []
    for item in sets:
        set_id, _user, _channel, name, _url, enabled = item
        mark = "✓ " if enabled else "○ "
        label = f"{mark}{name}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label[:60],
                    callback_data=f"al_set_{set_id}",
                    icon_custom_emoji_id=Icon.link if enabled else Icon.cancel,
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="Додати набір",
                callback_data=f"al_add_{channel_id}",
                icon_custom_emoji_id=Icon.add,
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="Перевірити на тексті",
                callback_data=f"al_try_{channel_id}",
                icon_custom_emoji_id=Icon.search,
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=Btn.back,
                callback_data="settings_autolinks",
                icon_custom_emoji_id=Icon.back,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def set_keyboard(set_id: int, channel_id: int, enabled: bool, phrases: list[tuple]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="Вимкнути" if enabled else "Увімкнути",
                callback_data=f"al_tog_{set_id}",
                icon_custom_emoji_id=Icon.ok if enabled else Icon.cancel,
            )
        ],
        [
            InlineKeyboardButton(
                text="Додати фрази",
                callback_data=f"al_ph_{set_id}",
                icon_custom_emoji_id=Icon.add,
            )
        ],
    ]
    for phrase_id, phrase in phrases:
        label = phrase if len(phrase) <= 32 else phrase[:31] + "…"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"al_delph_{phrase_id}",
                    icon_custom_emoji_id=Icon.trash,
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=Btn.delete,
                callback_data=f"al_del_{set_id}",
                icon_custom_emoji_id=Icon.trash,
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=Btn.back,
                callback_data=f"al_ch_{channel_id}",
                icon_custom_emoji_id=Icon.back,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete_keyboard(set_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Так, видалити",
                    callback_data=f"al_delok_{set_id}",
                    icon_custom_emoji_id=Icon.trash,
                ),
                InlineKeyboardButton(
                    text=Btn.cancel,
                    callback_data=f"al_set_{set_id}",
                    icon_custom_emoji_id=Icon.back,
                ),
            ]
        ]
    )
