"""Add channel / group request keyboard (markup only)."""

from aiogram.types import KeyboardButton, KeyboardButtonRequestChat, ReplyKeyboardMarkup

from texts import AddChannel
from utils.ui_emoji import Icon


def get_add_channel_keyboard(language: str = "uk") -> ReplyKeyboardMarkup:
    del language
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=AddChannel.add_channel,
                    icon_custom_emoji_id=Icon.channel,
                    request_chat=KeyboardButtonRequestChat(
                        request_id=1,
                        chat_is_channel=True,
                        user_administrator_rights=None,
                        bot_administrator_rights=None,
                    ),
                ),
                KeyboardButton(
                    text=AddChannel.add_group,
                    icon_custom_emoji_id=Icon.users,
                    request_chat=KeyboardButtonRequestChat(
                        request_id=2,
                        chat_is_channel=False,
                        user_administrator_rights=None,
                        bot_administrator_rights=None,
                    ),
                ),
            ],
            [
                KeyboardButton(
                    text=AddChannel.back, icon_custom_emoji_id=Icon.back
                )
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
