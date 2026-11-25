"""Витягування тексту та типу медіа з повідомлень у каналі."""

from aiogram import types

from utils.message_html import message_to_html


def channel_post_text(message: types.Message) -> str:
    return message_to_html(message)


def channel_post_media_type(message: types.Message) -> str | None:
    if message.photo:
        return "photo"
    if message.video:
        return "video"
    if message.document:
        return "document"
    if message.animation:
        return "animation"
    if message.audio:
        return "audio"
    if message.voice:
        return "voice"
    if message.video_note:
        return "video_note"
    return None
