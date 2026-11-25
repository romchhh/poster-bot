"""Дублікат постів із Telethon до чатів через Bot API з HTML із сутностями Telegram."""

from __future__ import annotations

import html as html_lib
import logging
from html.parser import HTMLParser
from io import BytesIO

from aiogram import Bot
from aiogram.types import (
    BufferedInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)

from telethon.extensions import html as tl_html
from telethon.tl.types import (
    ReplyInlineMarkup,
    DocumentAttributeFilename,
)

# Telethon <1.45: KeyboardButtonUrl; >=1.45: KeyboardInlineButton + InlineButtonTypeUrl
try:
    from telethon.tl.types import KeyboardButtonUrl as _KeyboardButtonUrl
except ImportError:  # pragma: no cover
    _KeyboardButtonUrl = None
try:
    from telethon.tl.types import InlineButtonTypeUrl as _InlineButtonTypeUrl
except ImportError:  # pragma: no cover
    _InlineButtonTypeUrl = None

logger = logging.getLogger(__name__)

TELEGRAM_CAPTION_HTML_MAX = 1024
TELEGRAM_MESSAGE_HTML_MAX = 3900


class _TelegramOpenTagStack(HTMLParser):
    """Тільки парні теги Bot API HTML, які може експортувати telethon.extensions.html.unparse."""

    _PAIRED = frozenset(
        {
            "b",
            "strong",
            "em",
            "i",
            "u",
            "ins",
            "s",
            "strike",
            "del",
            "code",
            "pre",
            "a",
            "tg-emoji",
            "blockquote",
            "span",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag not in self._PAIRED:
            return
        if tag == "span":
            d = dict(attrs)
            cls = d.get("class", "")
            if isinstance(cls, list):
                cls = " ".join(cls)
            if "tg-spoiler" not in str(cls):
                return
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag not in self._PAIRED:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i] == tag:
                self.stack = self.stack[:i]
                return


def _suffix_close_stack(stack: list[str]) -> str:
    parts: list[str] = []
    for t in reversed(stack):
        parts.append(f"</{t}>")
    return "".join(parts)


def _strip_incomplete_trailing_markup(s: str) -> str:
    """Прибирає фрагмент з останнього «<», у якому ще немає «>» (обрив усередині тега)."""
    while True:
        last_lt = s.rfind("<")
        if last_lt < 0:
            return s
        tail = s[last_lt:]
        if ">" not in tail:
            s = s[:last_lt].rstrip()
            continue
        return s


def _stack_after_feed(fragment: str) -> list[str] | None:
    p = _TelegramOpenTagStack()
    try:
        p.feed(fragment)
        p.close()
    except Exception:
        logger.debug(
            "telegram html stack parse failed, fragment truncated or malformed"
        )
        return None
    return p.stack


def fit_telegram_html(html: str, limit: int) -> str:
    """Підганяє HTML під ліміт Bot API без обрізання посередині тегів (typical caption 1024)."""
    if not html or not html.strip():
        return ""
    html = html.strip()

    fast_stack = _stack_after_feed(html)
    if fast_stack is not None and len(html + _suffix_close_stack(fast_stack)) <= limit:
        return html + _suffix_close_stack(fast_stack)

    best_plain = ""
    lo, hi = 0, len(html)
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = _strip_incomplete_trailing_markup(html[:mid])
        stack = _stack_after_feed(cand)
        if stack is None:
            hi = mid - 1
            continue
        fixed = cand + _suffix_close_stack(stack)
        if len(fixed) <= limit:
            best_plain = fixed
            lo = mid + 1
        else:
            hi = mid - 1

    if best_plain:
        return best_plain

    take = html[: max(0, min(len(html), limit))]
    take = html_lib.escape(take)
    if len(take) > limit:
        take = take[:limit]
    return take


def caption_html(message) -> str:
    raw = getattr(message, "message", None) or getattr(message, "raw_text", None) or ""
    if not raw or not raw.strip():
        return ""
    ents = getattr(message, "entities", None)
    if not ents:
        return html_lib.escape(raw)
    try:
        return tl_html.unparse(raw, ents)
    except Exception:
        logger.exception("caption_html tl_html.unparse")
        return html_lib.escape(raw)


def _telethon_button_url(button) -> str | None:
    """URL з кнопки донора (сумісно з Telethon 1.43 і 1.45+)."""
    if _KeyboardButtonUrl is not None and isinstance(button, _KeyboardButtonUrl):
        return getattr(button, "url", None) or None
    btype = getattr(button, "type", None)
    if _InlineButtonTypeUrl is not None and isinstance(btype, _InlineButtonTypeUrl):
        return getattr(btype, "url", None) or None
    # duck-typing fallback
    url = getattr(button, "url", None)
    if url:
        return url
    return getattr(btype, "url", None) or None


def donor_inline_rows(message) -> list[list[InlineKeyboardButton]] | None:
    rm = getattr(message, "reply_markup", None)
    if not rm or not isinstance(rm, ReplyInlineMarkup):
        return None
    rows: list[list[InlineKeyboardButton]] = []
    for row in rm.rows:
        lst: list[InlineKeyboardButton] = []
        for b in row.buttons:
            url = _telethon_button_url(b)
            if not url:
                continue
            lst.append(
                InlineKeyboardButton(
                    text=(getattr(b, "text", None) or "Посилання")[:64],
                    url=url,
                )
            )
        if lst:
            rows.append(lst)
    return rows or None


async def download_bytes(client, message) -> tuple[bytes, str]:
    buf = BytesIO()
    media = getattr(message, "media", None)
    if media is None:
        return b"", "empty"
    await client.download_media(media, file=buf)
    name = "media.bin"
    if getattr(message, "document", None) and getattr(
        message.document, "attributes", None
    ):
        for a in message.document.attributes:
            if isinstance(a, DocumentAttributeFilename) and getattr(
                a, "file_name", None
            ):
                name = str(a.file_name)
                break
    return buf.getvalue(), name


class MirrorBotDelivery:
    """Telethon message → Bot API re-upload into a destination chat."""

    def __init__(self, bot: Bot, client) -> None:
        self.bot = bot
        self.client = client

    async def deliver(
        self,
        *,
        dest_chat_id: int,
        messages: list,
        extra_markup: InlineKeyboardMarkup | None = None,
        attach_markup_to_media: bool = True,
    ) -> list[Message]:
        """Дублює telethon-пости в чат. Повертає надіслані повідомлення Bot API.

        Для медіагрупи inline-кнопки завжди окремим повідомленням після групи.
        Для одного медіа: за attach_markup_to_media=False кнопки лише в окремому повідомленні.
        """
        msgs = sorted(messages, key=lambda x: getattr(x, "id", 0))
        sent: list[Message] = []

        inline_on_media = (
            extra_markup
            if (extra_markup is not None and attach_markup_to_media and len(msgs) == 1)
            else None
        )
        trailing_markup = (
            extra_markup
            if extra_markup is not None
            and (not attach_markup_to_media or len(msgs) > 1)
            else None
        )

        all_photo = msgs and all(getattr(x, "photo", None) for x in msgs)
        all_video = msgs and all(getattr(x, "video", None) for x in msgs)

        async def _send_actions_bar() -> None:
            if trailing_markup:
                bar = await self.bot.send_message(
                    chat_id=dest_chat_id,
                    text="Дії для поста вище:",
                    reply_markup=extra_markup,
                )
                sent.append(bar)

        if len(msgs) > 1 and all_photo:
            imgs: list[InputMediaPhoto] = []
            for i, m in enumerate(msgs):
                raw, _ = await download_bytes(self.client, m)
                fn = f"photo{i}.jpg"
                cap = (
                    caption_html(m)
                    if getattr(m, "message", "") or getattr(m, "raw_text", "")
                    else ""
                )
                if i == 0:
                    cap = (cap or "").strip()
                else:
                    cap = cap or ""
                inp = BufferedInputFile(raw, filename=fn)
                if i == 0 and cap:
                    imgs.append(
                        InputMediaPhoto(
                            media=inp,
                            caption=fit_telegram_html(cap, TELEGRAM_CAPTION_HTML_MAX),
                            parse_mode="HTML",
                        )
                    )
                else:
                    imgs.append(InputMediaPhoto(media=inp))
            grp = await self.bot.send_media_group(chat_id=dest_chat_id, media=imgs)
            sent.extend(grp if isinstance(grp, list) else [grp])
            await _send_actions_bar()
            return sent

        if len(msgs) > 1 and all_video:
            imgs: list[InputMediaVideo] = []
            for i, m in enumerate(msgs):
                raw, fn = await download_bytes(self.client, m)
                if not fn.lower().endswith((".mp4", ".mov", ".mkv", ".webm")):
                    fn = "clip.mp4"
                cap = (
                    caption_html(m)
                    if getattr(m, "message", "") or getattr(m, "raw_text", "")
                    else ""
                )
                if i == 0:
                    cap = (cap or "").strip()
                else:
                    cap = cap or ""
                inp = BufferedInputFile(raw, filename=fn)
                if i == 0 and cap:
                    imgs.append(
                        InputMediaVideo(
                            media=inp,
                            caption=fit_telegram_html(cap, TELEGRAM_CAPTION_HTML_MAX),
                            parse_mode="HTML",
                        )
                    )
                else:
                    imgs.append(InputMediaVideo(media=inp))
            grp = await self.bot.send_media_group(chat_id=dest_chat_id, media=imgs)
            sent.extend(grp if isinstance(grp, list) else [grp])
            await _send_actions_bar()
            return sent

        if len(msgs) > 1:
            for i, m in enumerate(msgs):
                tail = i == len(msgs) - 1
                sub = await self.deliver(
                    dest_chat_id=dest_chat_id,
                    messages=[m],
                    extra_markup=extra_markup if tail else None,
                    attach_markup_to_media=attach_markup_to_media if tail else True,
                )
                sent.extend(sub)
            return sent

        m = msgs[0]
        cap = caption_html(m).strip()
        cap_photo = fit_telegram_html(cap, TELEGRAM_CAPTION_HTML_MAX) if cap else ""
        cap_text = fit_telegram_html(cap, TELEGRAM_MESSAGE_HTML_MAX) if cap else ""

        msg_out: Message | None = None

        if getattr(m, "photo", None):
            raw, _ = await download_bytes(self.client, m)
            msg_out = await self.bot.send_photo(
                chat_id=dest_chat_id,
                photo=BufferedInputFile(raw, filename="photo.jpg"),
                caption=cap_photo if cap_photo else None,
                parse_mode="HTML" if cap_photo else None,
                reply_markup=inline_on_media if len(msgs) == 1 else None,
            )
            sent.append(msg_out)
            await _send_actions_bar()
            return sent

        if getattr(m, "video", None):
            raw, fn = await download_bytes(self.client, m)
            if not fn.lower().endswith((".mp4", ".mov", ".mkv", ".webm")):
                fn = "video.mp4"
            msg_out = await self.bot.send_video(
                chat_id=dest_chat_id,
                video=BufferedInputFile(raw, filename=fn),
                caption=cap_photo if cap_photo else None,
                parse_mode="HTML" if cap_photo else None,
                reply_markup=inline_on_media,
            )
            sent.append(msg_out)
            await _send_actions_bar()
            return sent

        if getattr(m, "document", None):
            raw, fn = await download_bytes(self.client, m)
            msg_out = await self.bot.send_document(
                chat_id=dest_chat_id,
                document=BufferedInputFile(raw, filename=fn[-64:] or "file.bin"),
                caption=cap_photo if cap_photo else None,
                parse_mode="HTML" if cap_photo else None,
                reply_markup=inline_on_media,
            )
            sent.append(msg_out)
            await _send_actions_bar()
            return sent

        if getattr(m, "animation", None):
            raw, fn = await download_bytes(self.client, m)
            msg_out = await self.bot.send_animation(
                chat_id=dest_chat_id,
                animation=BufferedInputFile(raw, filename=fn[-64:] or "anim.mp4"),
                caption=cap_photo if cap_photo else None,
                parse_mode="HTML" if cap_photo else None,
                reply_markup=inline_on_media,
            )
            sent.append(msg_out)
            await _send_actions_bar()
            return sent

        if getattr(m, "audio", None):
            raw, fn = await download_bytes(self.client, m)
            msg_out = await self.bot.send_audio(
                chat_id=dest_chat_id,
                audio=BufferedInputFile(raw, filename=fn[-64:] or "audio.mp3"),
                caption=cap_photo if cap_photo else None,
                parse_mode="HTML" if cap_photo else None,
                reply_markup=inline_on_media,
            )
            sent.append(msg_out)
            await _send_actions_bar()
            return sent

        if getattr(m, "voice", None):
            raw, fn = await download_bytes(self.client, m)
            msg_out = await self.bot.send_voice(
                chat_id=dest_chat_id,
                voice=BufferedInputFile(raw, filename="voice.ogg"),
                caption=cap_photo if cap_photo else None,
                parse_mode="HTML" if cap_photo else None,
                reply_markup=inline_on_media,
            )
            sent.append(msg_out)
            await _send_actions_bar()
            return sent

        if getattr(m, "video_note", None):
            raw, fn = await download_bytes(self.client, m)
            msg_out = await self.bot.send_video_note(
                chat_id=dest_chat_id,
                video_note=BufferedInputFile(raw, filename="videonote.mp4"),
                reply_markup=inline_on_media,
            )
            sent.append(msg_out)
            if cap_text:
                txt = await self.bot.send_message(
                    chat_id=dest_chat_id,
                    text=cap_text,
                    parse_mode="HTML",
                )
                sent.append(txt)
            await _send_actions_bar()
            return sent

        if getattr(m, "sticker", None):
            raw, fn = await download_bytes(self.client, m)
            ext = ".webp"
            try:
                msg_out = await self.bot.send_sticker(
                    chat_id=dest_chat_id,
                    sticker=BufferedInputFile(raw, filename=f"sticker{ext}"),
                    reply_markup=inline_on_media,
                )
            except Exception:
                msg_out = await self.bot.send_document(
                    chat_id=dest_chat_id,
                    document=BufferedInputFile(raw, filename=f"sticker{ext}"),
                    reply_markup=inline_on_media,
                )
            sent.append(msg_out)
            await _send_actions_bar()
            return sent

        if cap_text:
            msg_out = await self.bot.send_message(
                chat_id=dest_chat_id,
                text=cap_text,
                parse_mode="HTML",
                reply_markup=inline_on_media,
            )
            sent.append(msg_out)
            await _send_actions_bar()
            return sent

        return sent


async def deliver_messages_to_chat(
    bot: Bot,
    client,
    *,
    dest_chat_id: int,
    messages: list,
    extra_markup: InlineKeyboardMarkup | None = None,
    attach_markup_to_media: bool = True,
) -> list[Message]:
    return await MirrorBotDelivery(bot, client).deliver(
        dest_chat_id=dest_chat_id,
        messages=messages,
        extra_markup=extra_markup,
        attach_markup_to_media=attach_markup_to_media,
    )


def donor_markup_only(message) -> InlineKeyboardMarkup | None:
    rows = donor_inline_rows(message)
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)
