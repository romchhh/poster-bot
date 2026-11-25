from __future__ import annotations

import copy
import html as html_lib
import logging
import re
from io import BytesIO

from aiogram import Bot
from aiogram.types import BufferedInputFile, InputMediaPhoto, Message

from database_functions.auto_signatures_db import get_auto_signature
from database_functions.channel_start_emoji_db import get_channel_start_emoji
from database_functions.watermark_db import get_any_watermark_for_channel, get_watermark
from utils.watermark_utils import apply_watermark_to_image

from .copy_mirror_bot_delivery import (
    TELEGRAM_CAPTION_HTML_MAX,
    TELEGRAM_MESSAGE_HTML_MAX,
    caption_html,
    donor_markup_only,
    download_bytes,
    fit_telegram_html,
)

logger = logging.getLogger(__name__)


TAG_RE = re.compile(r"<[^>]+>")


def mirror_plain_text_from_caption_html(caption_html: str) -> str:
    if not caption_html:
        return ""
    t = TAG_RE.sub(" ", caption_html)
    t = html_lib.unescape(t)
    return " ".join(t.split()).strip()


def mirror_format_caption_html(base_caption_html: str, channel_id: int) -> str:
    """Префікс tg-emoji каналу та автопідпис (як у створенні поста)."""
    cid = int(channel_id)
    text = base_caption_html or ""
    ei, et = get_channel_start_emoji(str(cid))
    sig_row = get_auto_signature(str(cid))
    manual_sig = (sig_row[3] if sig_row else "") or ""

    if ei and et:
        prefix = f'<tg-emoji emoji-id="{ei}">{et}</tg-emoji> '
        if not (text.startswith("<tg-emoji") and f'emoji-id="{ei}"' in text[:120]):
            text = prefix + (text or "").lstrip()
    if manual_sig.strip():
        sig_html = manual_sig.strip()
        if sig_html not in text:
            sep = "\n\n" if text else ""
            text = (text or "") + sep + manual_sig
    from modules.autolink.apply import apply_autolinks

    return apply_autolinks(text, cid)


def post_data_with_channel_signature(post_data: dict, channel_id: int) -> dict:
    """Копія чернетки з емодзі/автопідписом цільового каналу перед відправкою (як «Формат каналу»)."""
    settings = post_data.get("settings") or {}
    if post_data.get("channel_format_active") or settings.get("skip_channel_format"):
        return copy.deepcopy(post_data)
    out = copy.deepcopy(post_data)
    media_files = list(out.get("media_files") or [])
    out["media_files"] = media_files
    base = out.get("text")
    base = "" if base is None else str(base)
    if not base.strip() and media_files:
        cap = media_files[0].get("caption")
        if cap:
            base = str(cap)
    formatted = mirror_format_caption_html(base, channel_id)
    if formatted != base:
        out["text"] = formatted
        if media_files:
            media_files[0] = {**media_files[0], "caption": formatted}
            out["media_files"] = media_files
    return out


def _message_log_caption_html(msg: Message) -> str:
    cap = getattr(msg, "caption_html", None) or getattr(msg, "html_text", None)
    if cap:
        return cap
    if getattr(msg, "caption", None):
        return msg.caption or ""
    return getattr(msg, "text", None) or ""


def _message_media_type(msg: Message) -> str | None:
    if getattr(msg, "photo", None):
        return "photo"
    if getattr(msg, "video", None):
        return "video"
    if getattr(msg, "document", None):
        return "document"
    if getattr(msg, "animation", None):
        return "animation"
    return None


def _log_copy_mirror_published(
    owner_user_id: int,
    channel_id: int,
    primary: Message,
    *,
    post_text_fallback: str = "",
    media_type_fallback: str | None = None,
) -> None:
    from database_functions.posts_db import add_published_post

    post_text = _message_log_caption_html(primary) or post_text_fallback or ""
    mt = _message_media_type(primary) or media_type_fallback
    try:
        add_published_post(
            user_id=owner_user_id,
            channel_id=int(channel_id),
            message_id=int(primary.message_id),
            post_text=post_text,
            media_type=mt,
            url_buttons="",
            settings={},
            published_source="bot",
        )
    except Exception:
        logger.exception(
            "copy mirror add_published_post ch=%s mid=%s", channel_id, primary.message_id
        )


def _pick_primary_mirror_message(sent: list[Message]) -> Message | None:
    if not sent:
        return None
    for m in sent:
        if m.photo or m.video or m.document or m.animation or m.audio or m.voice:
            return m
        tx = (m.text or m.caption or "").strip()
        if tx and tx not in ("🔗 Кнопки:", "Дії для поста вище:", "⚙️ Додаткові опції:"):
            return m
    return sent[0]


def mirror_try_watermark_photo_bytes(
    user_id: int, channel_id: int, image_bytes: bytes
) -> bytes | None:
    cid = str(channel_id)
    wm = get_watermark(user_id, cid, "manual")
    if not wm:
        wm = get_any_watermark_for_channel(user_id, cid)
    if not wm or not image_bytes or len(image_bytes) < 100:
        return None
    out = apply_watermark_to_image(
        image_bytes,
        wm["watermark_data"],
        wm["position"],
        wm["size_percent"],
        wm["opacity"],
    )
    return out


async def mirror_file_id_for_photo_bytes(
    bot: Bot, upload_chat_id: int, image_bytes: bytes, filename: str = "wm.jpg"
) -> str | None:
    try:
        msg = await bot.send_photo(
            chat_id=upload_chat_id,
            photo=BufferedInputFile(image_bytes, filename=filename),
        )
        fid = msg.photo[-1].file_id
        await bot.delete_message(chat_id=upload_chat_id, message_id=msg.message_id)
        return fid
    except Exception:
        logger.exception("mirror_file_id_for_photo_bytes")
        return None


async def _download_bot_file_bytes(bot: Bot, file_id: str) -> bytes | None:
    try:
        tg_file = await bot.get_file(file_id)
        buf = await bot.download_file(tg_file.file_path)
        if buf is None:
            return None
        if hasattr(buf, "read"):
            return buf.read()
        if isinstance(buf, (bytes, bytearray)):
            return bytes(buf)
        return None
    except Exception:
        logger.exception("download bot file_id failed")
        return None


async def publish_mirror_messages_to_targets(
    bot: Bot,
    tl,
    *,
    owner_user_id: int,
    msgs: list,
    target_channel_ids: list[int],
    strip_media: bool,
    upload_chat_id: int,
    replaced_photo_file_id: str | None = None,
) -> list[int]:
    """
    Для кожного цільового каналу: підпис через емодзі/автопідпис, для одиночного фото —
    спроба вотермарки. Альбом лише підпис першого фрейму (водяний знак не покадрово).

    replaced_photo_file_id — якщо користувач замінив медіа в approve (AI / своє фото).

    Повертає channel_id де не вдалося надіслати.
    """
    from database_functions.billing_db import denial

    if denial(int(owner_user_id), "posting"):
        return list(target_channel_ids)

    failed: list[int] = []
    tl_msgs = sorted([m for m in msgs if m is not None], key=lambda z: getattr(z, "id", 0))
    markup_pub = donor_markup_only(tl_msgs[-1]) if tl_msgs else None

    base_first_caption_html = caption_html(tl_msgs[0]) if tl_msgs else ""
    donor_extra = "".join(
        caption_html(x)
        for x in tl_msgs[1:]
        if (getattr(x, "message", "") or getattr(x, "raw_text", ""))
    )
    donor_extra_plain = mirror_plain_text_from_caption_html(donor_extra)

    all_photo = (
        tl_msgs and len(tl_msgs) > 1 and all(getattr(x, "photo", None) for x in tl_msgs)
    )

    replaced_raw: bytes | None = None
    if replaced_photo_file_id and not strip_media:
        replaced_raw = await _download_bot_file_bytes(bot, str(replaced_photo_file_id))

    for channel_id in target_channel_ids:
        try:
            cap0 = mirror_format_caption_html(base_first_caption_html, channel_id)
            if strip_media:
                body = cap0
                if donor_extra_plain:
                    body = body + "\n\n" + html_lib.escape(donor_extra_plain)
                body_fit = (
                    fit_telegram_html(body.strip(), TELEGRAM_MESSAGE_HTML_MAX)
                    if body and body.strip()
                    else ""
                )
                msg_out = await bot.send_message(
                    int(channel_id),
                    body_fit,
                    parse_mode="HTML",
                    reply_markup=markup_pub,
                )
                _log_copy_mirror_published(
                    owner_user_id,
                    int(channel_id),
                    msg_out,
                    post_text_fallback=body_fit,
                    media_type_fallback=None,
                )
                continue

            if replaced_raw is not None:
                wm_bytes = mirror_try_watermark_photo_bytes(
                    owner_user_id, channel_id, replaced_raw
                )
                out_bytes = wm_bytes or replaced_raw
                cap_photo = (
                    fit_telegram_html(cap0, TELEGRAM_CAPTION_HTML_MAX) if cap0 else ""
                )
                msg_out = await bot.send_photo(
                    int(channel_id),
                    photo=BufferedInputFile(out_bytes, filename="photo.jpg"),
                    caption=cap_photo if cap_photo else None,
                    parse_mode="HTML" if cap_photo else None,
                    reply_markup=markup_pub,
                )
                _log_copy_mirror_published(
                    owner_user_id,
                    int(channel_id),
                    msg_out,
                    post_text_fallback=cap_photo,
                    media_type_fallback="photo",
                )
                continue

            if len(tl_msgs) == 1:
                m = tl_msgs[0]
                if getattr(m, "photo", None):
                    raw, _ = await download_bytes(tl, m)
                    wm_bytes = mirror_try_watermark_photo_bytes(
                        owner_user_id, channel_id, raw
                    )
                    out_bytes = wm_bytes or raw
                    cap_photo = (
                        fit_telegram_html(cap0, TELEGRAM_CAPTION_HTML_MAX) if cap0 else ""
                    )
                    msg_out = await bot.send_photo(
                        int(channel_id),
                        photo=BufferedInputFile(out_bytes, filename="photo.jpg"),
                        caption=cap_photo if cap_photo else None,
                        parse_mode="HTML" if cap_photo else None,
                        reply_markup=markup_pub,
                    )
                    _log_copy_mirror_published(
                        owner_user_id,
                        int(channel_id),
                        msg_out,
                        post_text_fallback=cap_photo,
                        media_type_fallback="photo",
                    )
                    continue
                if getattr(m, "video", None):
                    raw, fn = await download_bytes(tl, m)
                    if not str(fn).lower().endswith((".mp4", ".mov", ".mkv", ".webm")):
                        fn = "clip.mp4"
                    cap_photo = (
                        fit_telegram_html(cap0, TELEGRAM_CAPTION_HTML_MAX) if cap0 else ""
                    )
                    msg_out = await bot.send_video(
                        int(channel_id),
                        video=BufferedInputFile(raw, filename=fn[-64:] or "video.mp4"),
                        caption=cap_photo if cap_photo else None,
                        parse_mode="HTML" if cap_photo else None,
                        reply_markup=markup_pub,
                    )
                    _log_copy_mirror_published(
                        owner_user_id,
                        int(channel_id),
                        msg_out,
                        post_text_fallback=cap_photo,
                        media_type_fallback="video",
                    )
                    continue
                if getattr(m, "document", None):
                    raw, fn = await download_bytes(tl, m)
                    cap_photo = (
                        fit_telegram_html(cap0, TELEGRAM_CAPTION_HTML_MAX) if cap0 else ""
                    )
                    msg_out = await bot.send_document(
                        int(channel_id),
                        document=BufferedInputFile(raw, filename=fn[-64:] or "file.bin"),
                        caption=cap_photo if cap_photo else None,
                        parse_mode="HTML" if cap_photo else None,
                        reply_markup=markup_pub,
                    )
                    _log_copy_mirror_published(
                        owner_user_id,
                        int(channel_id),
                        msg_out,
                        post_text_fallback=cap_photo,
                        media_type_fallback="document",
                    )
                    continue

            if all_photo:
                imgs: list[InputMediaPhoto] = []
                cap_first_log = ""
                for i, m in enumerate(tl_msgs):
                    raw, _ = await download_bytes(tl, m)
                    cap = (
                        cap0
                        if i == 0
                        else (
                            caption_html(m)
                            if getattr(m, "message", "") or getattr(m, "raw_text", "")
                            else ""
                        )
                    )
                    inp = BufferedInputFile(raw, filename=f"p{i}.jpg")
                    if i == 0 and cap:
                        cap_fit = fit_telegram_html(cap, TELEGRAM_CAPTION_HTML_MAX)
                        cap_first_log = cap_fit
                        imgs.append(
                            InputMediaPhoto(
                                media=inp,
                                caption=cap_fit,
                                parse_mode="HTML",
                            )
                        )
                    else:
                        imgs.append(InputMediaPhoto(media=inp))
                grp = await bot.send_media_group(int(channel_id), media=imgs)
                if grp:
                    _log_copy_mirror_published(
                        owner_user_id,
                        int(channel_id),
                        grp[0],
                        post_text_fallback=cap_first_log,
                        media_type_fallback="photo",
                    )
                if markup_pub:
                    await bot.send_message(
                        int(channel_id),
                        "🔗 Кнопки:",
                        reply_markup=markup_pub,
                    )
                continue

            from .copy_mirror_bot_delivery import MirrorBotDelivery

            sent_list = await MirrorBotDelivery(bot, tl).deliver(
                dest_chat_id=int(channel_id),
                messages=tl_msgs,
                extra_markup=markup_pub,
                attach_markup_to_media=True,
            )
            primary = _pick_primary_mirror_message(sent_list)
            if primary:
                cap_log = (
                    fit_telegram_html(cap0, TELEGRAM_CAPTION_HTML_MAX) if cap0 else ""
                )
                _log_copy_mirror_published(
                    owner_user_id,
                    int(channel_id),
                    primary,
                    post_text_fallback=cap_log,
                )
        except Exception:
            logger.exception("publish_mirror to channel %s", channel_id)
            failed.append(int(channel_id))
    return failed
