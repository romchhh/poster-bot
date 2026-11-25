"""Watermark inline keyboards (markup only). Callbacks use pipe (wm|...) for negative ids."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from texts import Btn, Watermark
from utils.ui_emoji import Icon

WM_POSITIONS = [
    ("↖", "top-left"),
    ("↑", "top-center"),
    ("↗", "top-right"),
    ("←", "center-left"),
    ("◎", "center"),
    ("→", "center-right"),
    ("↙", "bottom-left"),
    ("↓", "bottom-center"),
    ("↘", "bottom-right"),
]


def _cid(channel_id) -> str:
    return str(channel_id)


def get_watermark_management_keyboard(
    channel_id,
    donor_id: str,
    folder_id: int,
    has_watermark: bool,
    back_callback: str | None = None,
) -> InlineKeyboardMarkup:
    cid, did, fid = _cid(channel_id), donor_id, folder_id
    rows: list[list[InlineKeyboardButton]] = []
    if has_watermark:
        rows.append(
            [
                InlineKeyboardButton(
                    text=Watermark.settings,
                    callback_data=f"wm|e|{cid}|{did}|{fid}",
                    icon_custom_emoji_id=Icon.settings,
                ),
                InlineKeyboardButton(
                    text=Watermark.change_image,
                    callback_data=f"wm|img|{cid}|{did}|{fid}",
                    icon_custom_emoji_id=Icon.refresh,
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=Watermark.delete,
                    callback_data=f"wm|d|{cid}|{did}|{fid}",
                    icon_custom_emoji_id=Icon.trash,
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text=Watermark.add,
                    callback_data=f"wm|a|{cid}|{did}|{fid}",
                    icon_custom_emoji_id=Icon.add,
                )
            ]
        )
    if back_callback:
        rows.append(
            [
                InlineKeyboardButton(
                    text=Watermark.to_channel,
                    callback_data=back_callback,
                    icon_custom_emoji_id=Icon.back,
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_watermark_upload_cancel_keyboard(
    channel_id, donor_id: str, folder_id: int
) -> InlineKeyboardMarkup:
    cid, did, fid = _cid(channel_id), donor_id, folder_id
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=Btn.cancel,
                    icon_custom_emoji_id=Icon.cancel,
                    callback_data=f"wm|m|{cid}|{did}|{fid}",
                )
            ]
        ]
    )


def get_watermark_confirm_delete_keyboard(
    channel_id, donor_id: str, folder_id: int
) -> InlineKeyboardMarkup:
    cid, did, fid = _cid(channel_id), donor_id, folder_id
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=Watermark.yes_delete,
                    callback_data=f"wm|dc|{cid}|{did}|{fid}",
                    icon_custom_emoji_id=Icon.trash,
                ),
                InlineKeyboardButton(
                    text=Watermark.no,
                    callback_data=f"wm|m|{cid}|{did}|{fid}",
                    icon_custom_emoji_id=Icon.cancel,
                ),
            ]
        ]
    )


def get_watermark_settings_keyboard(
    channel_id,
    donor_id: str,
    folder_id: int,
    position: str = "bottom-right",
    size_percent: int = 50,
    opacity: int = 100,
    indent: int = 0,
) -> InlineKeyboardMarkup:
    cid, did, fid = _cid(channel_id), donor_id, folder_id
    pos_rows: list[list[InlineKeyboardButton]] = []
    buf: list[InlineKeyboardButton] = []
    for label, pos in WM_POSITIONS:
        mark = "·" if pos == position else ""
        buf.append(
            InlineKeyboardButton(
                text=f"{mark}{label}",
                callback_data=f"wm|p|{cid}|{did}|{fid}|{pos}",
                icon_custom_emoji_id=Icon.ok if pos == position else Icon.pin,
            )
        )
        if len(buf) == 3:
            pos_rows.append(buf)
            buf = []
    if buf:
        pos_rows.append(buf)

    size_row = [
        InlineKeyboardButton(
            text=f"{'✓' if s == size_percent else ''}{s}%",
            callback_data=f"wm|sz|{cid}|{did}|{fid}|{s}",
            icon_custom_emoji_id=Icon.ok if s == size_percent else Icon.doc,
        )
        for s in (25, 40, 50, 60, 75)
    ]
    op_row = [
        InlineKeyboardButton(
            text=f"{'✓' if o == opacity else ''}{o}%",
            callback_data=f"wm|op|{cid}|{did}|{fid}|{o}",
            icon_custom_emoji_id=Icon.ok if o == opacity else Icon.doc,
        )
        for o in (30, 50, 70, 100)
    ]
    ind_row = [
        InlineKeyboardButton(
            text=f"{'✓' if i == indent else ''}{i}px",
            callback_data=f"wm|in|{cid}|{did}|{fid}|{i}",
            icon_custom_emoji_id=Icon.ok if i == indent else Icon.doc,
        )
        for i in (0, 10, 20, 30)
    ]

    return InlineKeyboardMarkup(
        inline_keyboard=[
            *pos_rows,
            size_row,
            op_row,
            ind_row,
            [
                InlineKeyboardButton(
                    text=Watermark.save,
                    callback_data=f"wm|sv|{cid}|{did}|{fid}",
                    icon_custom_emoji_id=Icon.ok,
                ),
                InlineKeyboardButton(
                    text=Btn.back,
                    callback_data=f"wm|m|{cid}|{did}|{fid}",
                    icon_custom_emoji_id=Icon.back,
                ),
            ],
        ]
    )
