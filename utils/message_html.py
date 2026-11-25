"""Normalize Telegram message text/caption into Bot API HTML."""

from __future__ import annotations

import html as html_module
import re

from aiogram import types

from utils.entity_parser import convert_entities_to_html


def message_to_html(message: types.Message) -> str:
    """Prefer aiogram html helpers; fall back to entity conversion."""
    if message.text is not None:
        html = getattr(message, "html_text", None)
        if html is not None:
            return html
        return convert_entities_to_html(message.text, message.entities)

    if message.caption is not None:
        html = getattr(message, "caption_html", None)
        if html is not None:
            return html
        return convert_entities_to_html(message.caption, message.caption_entities)

    return ""


def safe_truncate_html(text: str, max_plain_len: int = 400) -> str:
    """Preview HTML/text without cutting mid-tag; long content becomes escaped plain."""
    if not text:
        return ""
    plain = re.sub(r"<[^>]+>", "", text)
    if len(plain) <= max_plain_len:
        return text
    cut = max_plain_len - 1
    return html_module.escape(plain[:cut]) + "…"
