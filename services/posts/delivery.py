"""Shared Bot API publish pipeline for create-post / scheduler / content-plan."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from database_functions.channels_db import get_channel_by_id
from database_functions.posts_db import add_published_post
from utils.copy_utils.mirror_publish_delivery import post_data_with_channel_signature
from utils.post_utils import send_post_preview

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PublishResult:
    ok: bool
    channel_id: int
    message_id: int | None = None
    message_ids: list[int] | None = None
    channel_title: str | None = None
    post_link: str | None = None
    error: str | None = None
    url_error: bool = False
    skipped: bool = False


@dataclass(slots=True)
class PostDraft:
    """Normalized post payload used by the publisher."""

    text: str = ""
    media_files: list[dict[str, Any]] = field(default_factory=list)
    url_buttons: list = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)
    url_buttons_raw_text: str = ""
    channel_format_active: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PostDraft:
        data = data or {}
        return cls(
            text=data.get("text") or "",
            media_files=list(data.get("media_files") or []),
            url_buttons=data.get("url_buttons") or [],
            settings=dict(data.get("settings") or {}),
            url_buttons_raw_text=data.get("url_buttons_raw_text") or "",
            channel_format_active=bool(data.get("channel_format_active")),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "text": self.text,
            "media_files": self.media_files,
            "url_buttons": self.url_buttons,
            "settings": self.settings,
            "url_buttons_raw_text": self.url_buttons_raw_text,
        }
        if self.channel_format_active:
            out["channel_format_active"] = True
        return out


class PostPublisher:
    """Publish a draft into one or many channels via Bot API."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @staticmethod
    def post_link_for_channel(
        channel_id: int, message_id: int
    ) -> tuple[str | None, str | None]:
        channel = get_channel_by_id(channel_id)
        if not channel:
            return None, None

        channel_title = channel[2]
        channel_username = channel[3]
        if channel_username:
            return channel_title, f"https://t.me/{channel_username}/{message_id}"

        chat_id_str = str(channel_id)
        if chat_id_str.startswith("-100"):
            chat_id_for_link = chat_id_str[4:]
        else:
            chat_id_for_link = str(abs(channel_id))
        return channel_title, f"https://t.me/c/{chat_id_for_link}/{message_id}"

    async def deliver_to_channel(
        self,
        *,
        user_id: int,
        channel_id: int,
        post_data: dict[str, Any] | PostDraft,
        scheduled_post_id: int | None = None,
        url_buttons_log: str | None = None,
    ) -> PublishResult:
        draft = (
            post_data
            if isinstance(post_data, PostDraft)
            else PostDraft.from_dict(post_data)
        )
        payload = draft.to_dict()
        blocked = _blacklist_word(user_id, channel_id, payload.get("text") or "")
        if blocked:
            channel = get_channel_by_id(channel_id)
            return PublishResult(
                ok=False,
                channel_id=channel_id,
                channel_title=channel[2] if channel else None,
                skipped=True,
                error=f"blacklist:{blocked}",
            )

        try:
            to_send = post_data_with_channel_signature(payload, channel_id)
            from modules.autolink.apply import apply_autolinks_to_post

            to_send = apply_autolinks_to_post(to_send, channel_id)
            sent_message_ids: list[int] = []
            sent_message = await send_post_preview(
                self.bot, channel_id, to_send, preview_message_ids=sent_message_ids
            )
            if not sent_message:
                return PublishResult(
                    ok=False,
                    channel_id=channel_id,
                    error="send_post_preview returned empty",
                )

            settings = dict(payload.get("settings") or {})
            if sent_message_ids:
                settings["message_ids"] = list(sent_message_ids)
            media_files = payload.get("media_files") or []
            log_text = (
                getattr(sent_message, "html_text", None)
                or getattr(sent_message, "caption_html", None)
                or sent_message.caption
                or to_send.get("text")
                or payload.get("text", "")
                or ""
            )
            buttons_log = (
                url_buttons_log
                if url_buttons_log is not None
                else payload.get("url_buttons_raw_text", "") or ""
            )

            add_published_post(
                user_id=user_id,
                channel_id=channel_id,
                message_id=sent_message.message_id,
                post_text=log_text,
                media_type=media_files[0].get("type") if media_files else None,
                url_buttons=buttons_log,
                settings=settings,
                scheduled_post_id=scheduled_post_id,
                media_files=media_files if media_files else None,
            )

            auto_delete_minutes = settings.get("auto_delete_minutes")
            if auto_delete_minutes:
                from utils.scheduler import schedule_post_deletion

                to_delete = sent_message_ids or [sent_message.message_id]
                schedule_post_deletion(
                    self.bot, channel_id, to_delete, auto_delete_minutes
                )

            title, link = self.post_link_for_channel(
                channel_id, sent_message.message_id
            )
            return PublishResult(
                ok=True,
                channel_id=channel_id,
                message_id=sent_message.message_id,
                message_ids=sent_message_ids or [sent_message.message_id],
                channel_title=title,
                post_link=link,
            )
        except TelegramBadRequest as e:
            err = str(e)
            logger.warning("Publish failed channel=%s: %s", channel_id, err)
            return PublishResult(
                ok=False,
                channel_id=channel_id,
                error=err,
                url_error=("URL" in err or "invalid" in err.lower()),
            )
        except Exception as e:
            logger.exception("Publish failed channel=%s", channel_id)
            return PublishResult(ok=False, channel_id=channel_id, error=str(e))

    async def deliver_to_channels(
        self,
        *,
        user_id: int,
        channel_ids: list[int],
        post_data: dict[str, Any] | PostDraft,
    ) -> list[PublishResult]:
        results: list[PublishResult] = []
        for channel_id in channel_ids:
            results.append(
                await self.deliver_to_channel(
                    user_id=user_id,
                    channel_id=channel_id,
                    post_data=post_data,
                )
            )
        return results


def _blacklist_word(user_id: int, channel_id: int, text: str) -> str | None:
    import re

    from database_functions.clone_db import get_copy_blacklist
    from database_functions.copy_mirror_db import SCOPE_CHANNEL, SCOPE_FOLDER

    channel = get_channel_by_id(channel_id)
    if not channel:
        return None
    words = list(get_copy_blacklist(user_id, SCOPE_CHANNEL, channel_id))
    folder_id = channel[11] if len(channel) > 11 else None
    if folder_id:
        words.extend(get_copy_blacklist(user_id, SCOPE_FOLDER, folder_id))
    plain = re.sub(r"<[^>]+>", " ", text or "")
    folded = plain.casefold()
    for _word_id, word in words:
        token = (word or "").strip().casefold()
        if token and token in folded:
            return word
    return None


def post_link_for_channel(channel_id: int, message_id: int) -> tuple[str | None, str | None]:
    return PostPublisher.post_link_for_channel(channel_id, message_id)


async def deliver_post_to_channel(
    bot: Bot,
    *,
    user_id: int,
    channel_id: int,
    post_data: dict[str, Any],
    scheduled_post_id: int | None = None,
    url_buttons_log: str | None = None,
) -> PublishResult:
    return await PostPublisher(bot).deliver_to_channel(
        user_id=user_id,
        channel_id=channel_id,
        post_data=post_data,
        scheduled_post_id=scheduled_post_id,
        url_buttons_log=url_buttons_log,
    )
