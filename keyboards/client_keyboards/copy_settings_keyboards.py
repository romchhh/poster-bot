"""Copy / channel-scope settings keyboards (markup only)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from texts import Btn, Copy
from utils.ui_emoji import Icon


def _back_btn(st: str, sid: str, back: str) -> list[InlineKeyboardButton]:
    if back == "chs":
        return [
            InlineKeyboardButton(
                text=Copy.back_to_channel_summary,
                callback_data=f"channel_settings_{sid}",
                icon_custom_emoji_id=Icon.back,
            )
        ]
    return [
        InlineKeyboardButton(
            text=Copy.back_to_copy,
            callback_data=f"cpy_mg:{st}:{sid}",
            icon_custom_emoji_id=Icon.back,
        )
    ]


def get_channel_scope_settings_keyboard(
    st: str,
    sid: str,
    back: str,
    settings: dict,
    *,
    user_id: int | None,
    show_pause_row: bool,
    emoji_configured: bool,
    autopodpis_configured: bool,
    watermark_configured: bool,
) -> InlineKeyboardMarkup:
    bell = settings.get("bell", True)
    paused = settings.get("paused", False)
    ai = settings.get("ai_rewrite", False)

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=Copy.sound_on if bell else Copy.sound_off,
                callback_data=f"cpy_stbell:{st}:{sid}:{back}",
                icon_custom_emoji_id=Icon.spark if bell else Icon.bell_off,
            )
        ]
    ]

    if show_pause_row:
        rows.append(
            [
                InlineKeyboardButton(
                    text=Copy.start_copy if paused else Copy.pause_copy,
                    callback_data=f"cpy_stpause:{st}:{sid}:{back}",
                    icon_custom_emoji_id=Icon.ok if paused else Icon.cancel,
                )
            ]
        )

    if st == "c":
        cid = sid
        cpy_sfx = "|cpy" if back == "cpy" else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=Copy.emoji_prefix_ok if emoji_configured else Copy.emoji_prefix,
                    callback_data=f"cse|m|{cid}{cpy_sfx}",
                    icon_custom_emoji_id=Icon.art,
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=Copy.autosign_ok if autopodpis_configured else Copy.autosign,
                    callback_data=f"auto_signature_settings_{cid}{cpy_sfx}",
                    icon_custom_emoji_id=Icon.sign,
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=f"{Copy.ai_rewrite}{' ✓' if ai else ''}",
                callback_data=f"cpy_stai:{st}:{sid}:{back}",
                icon_custom_emoji_id=Icon.spark if ai else Icon.cancel,
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=Copy.blacklist,
                callback_data=f"cpy_stbl:{st}:{sid}:{back}",
                icon_custom_emoji_id=Icon.lock,
            )
        ]
    )

    if st == "c" and user_id is not None:
        cid = sid
        wm_nav = 2 if back == "chs" else 0
        rows.append(
            [
                InlineKeyboardButton(
                    text=Copy.watermark_ok if watermark_configured else Copy.watermark,
                    callback_data=f"ch_wm|{cid}|{wm_nav}",
                    icon_custom_emoji_id=Icon.photo,
                )
            ]
        )

    rows.append(_back_btn(st, sid, back))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_copy_blacklist_keyboard(
    st: str, sid: str, back: str, words: list[tuple[int, str]]
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=wtxt,
                callback_data=f"cpy_stblrm:{wid}:{st}:{sid}:{back}",
                icon_custom_emoji_id=Icon.cancel,
            )
        ]
        for wid, wtxt in words
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=Copy.add_word,
                callback_data=f"cpy_stbladd:{st}:{sid}:{back}",
                icon_custom_emoji_id=Icon.add,
            )
        ]
    )
    if words:
        rows.append(
            [
                InlineKeyboardButton(
                    text=Copy.clear_list,
                    callback_data=f"cpy_stblclr:{st}:{sid}:{back}",
                    icon_custom_emoji_id=Icon.trash,
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=Copy.back_to_channel_settings,
                callback_data=f"cpy_stg:{st}:{sid}:{back}",
                icon_custom_emoji_id=Icon.back,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_copy_blacklist_add_keyboard(st: str, sid: str, back: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=Btn.cancel,
                    callback_data=f"cpy_stbl:{st}:{sid}:{back}",
                    icon_custom_emoji_id=Icon.cancel,
                )
            ]
        ]
    )
