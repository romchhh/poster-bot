"""Парсинг посилань та приєднання до каналу-донора через Telethon (без згадки службового акаунта)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Union

from telethon import utils
from telethon.errors import UserAlreadyParticipantError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.types import Channel

logger = logging.getLogger(__name__)


def _is_chat_invite_already(resp) -> bool:
    """У різних версіях Telethon клас може бути в іншому модулі — порівнюємо по імені TL-типу."""
    return type(resp).__name__ == "ChatInviteAlready"


class JoinDonorKind(Enum):
    JOINED = "joined"
    PENDING_INVITE = "pending_invite"
    ERROR = "error"


@dataclass
class JoinDonorOutcome:
    kind: JoinDonorKind
    channel_id: int | None = None
    title: str | None = None
    fingerprint: str | None = None
    invite_hash: str | None = None
    preview_title: str | None = None
    error_uk: str | None = None


def _invite_fingerprint(h: str) -> str:
    return "i:" + h.strip()


def _username_fingerprint(un: str) -> str:
    return "u:" + un.strip().lower()


@dataclass
class _InviteRef:
    hash: str


@dataclass
class _UsernameRef:
    username: str


ParsedRef = Union[_InviteRef, _UsernameRef]


def parse_donor_channel_ref(text: str) -> ParsedRef | None:
    raw = (text or "").strip()
    if not raw:
        return None
    block = (
        "joinchat",
        "addstickers",
        "addemoji",
        "share",
        "iv",
        "proxy",
        "socks",
    )
    m = re.search(
        r"(?:https?://)?(?:t(?:elegram)?\.me|telegram\.dog)/\+([\w-]+)", raw, re.I
    )
    if m:
        return _InviteRef(m.group(1))
    m = re.search(r"(?:https?://)?(?:t(?:elegram)?\.me)/joinchat/([\w-]+)", raw, re.I)
    if m:
        return _InviteRef(m.group(1))
    m = re.search(
        r"(?:https?://)?(?:t(?:elegram)?\.me|telegram\.dog)/s/([a-z][\w\d_]{3,31})",
        raw,
        re.I,
    )
    if m:
        u = m.group(1).lower()
        if u not in block:
            return _UsernameRef(u)
    m = re.search(
        r"(?:https?://)?(?:t(?:elegram)?\.me|telegram\.dog)/([a-z][\w\d_]{3,31})(?:[/\s?].*)?$",
        raw,
        re.I,
    )
    if m:
        u = m.group(1).lower()
        if u not in block and not u.isdigit():
            return _UsernameRef(u)
    if raw.startswith("@"):
        u = raw[1:].split()[0]
        if re.match(r"^[a-zA-Z][\w\d_]{3,31}$", u):
            return _UsernameRef(u.lower())
    if re.match(r"^[a-zA-Z][\w\d_]{3,31}$", raw):
        return _UsernameRef(raw.lower())
    return None


def _channel_from_updates(upd) -> tuple[int | None, str | None]:
    chats = getattr(upd, "chats", None) or ()
    picked = None
    for ch in chats:
        if isinstance(ch, Channel):
            if getattr(ch, "megagroup", False):
                continue
            picked = ch
    if picked is None:
        return None, None
    return utils.get_peer_id(picked), getattr(picked, "title", None)


async def _peek_invite_title(client, invite_hash: str) -> str | None:
    try:
        r = await client(CheckChatInviteRequest(invite_hash))
        return getattr(r, "title", None)
    except Exception:
        return None


async def invite_join_outcome(client, invite_hash: str) -> JoinDonorOutcome:
    fp = _invite_fingerprint(invite_hash)
    peek = await _peek_invite_title(client, invite_hash)
    try:
        from telethon.errors import InviteHashExpiredError, InviteHashInvalidError
    except ImportError:
        InviteHashExpiredError = type(None)
        InviteHashInvalidError = type(None)
    try:
        from telethon.errors import InviteRequestSentError
    except ImportError:
        InviteRequestSentError = None  # noqa: N816 — прапор відсутності класу помилки

    try:
        upd = await client(ImportChatInviteRequest(invite_hash))
        cid, title = _channel_from_updates(upd)
        if cid is None:
            return JoinDonorOutcome(
                kind=JoinDonorKind.ERROR,
                fingerprint=fp,
                invite_hash=invite_hash,
                preview_title=peek,
                error_uk="Не вдалося визначити канал із відповіді Telegram. Перевірте посилання та спробуйте ще раз.",
            )
        return JoinDonorOutcome(
            kind=JoinDonorKind.JOINED,
            channel_id=cid,
            title=title or peek,
            fingerprint=fp,
            invite_hash=invite_hash,
            preview_title=peek or title,
        )
    except UserAlreadyParticipantError:
        cid, title = await _participant_via_check_invite(client, invite_hash)
        if cid is None:
            return JoinDonorOutcome(
                kind=JoinDonorKind.ERROR,
                fingerprint=fp,
                invite_hash=invite_hash,
                error_uk="Посилання вказує на канал, але не вдалося отримати технічні дані каналу.",
            )
        ent = await client.get_entity(cid)
        ttl = getattr(ent, "title", None) or title
        return JoinDonorOutcome(
            kind=JoinDonorKind.JOINED,
            channel_id=cid,
            title=ttl,
            fingerprint=fp,
            invite_hash=invite_hash,
        )
    except Exception as ex:
        if InviteRequestSentError is not None and isinstance(
            ex, InviteRequestSentError
        ):
            return JoinDonorOutcome(
                kind=JoinDonorKind.PENDING_INVITE,
                fingerprint=fp,
                invite_hash=invite_hash,
                preview_title=peek,
            )
        if InviteHashExpiredError and isinstance(ex, InviteHashExpiredError):
            return JoinDonorOutcome(
                kind=JoinDonorKind.ERROR,
                fingerprint=fp,
                error_uk="Термін дії інвайт-посилання вичерпано. Попросіть нове запрошення.",
            )
        if InviteHashInvalidError and isinstance(ex, InviteHashInvalidError):
            return JoinDonorOutcome(
                kind=JoinDonorKind.ERROR,
                fingerprint=fp,
                error_uk="Некоректне або недійсне посилання запрошення.",
            )
        logger.exception("ImportChatInvite")
        return JoinDonorOutcome(
            kind=JoinDonorKind.ERROR,
            fingerprint=fp,
            invite_hash=invite_hash,
            error_uk=f"Не вдалося підключити канал: {type(ex).__name__}",
        )


async def _participant_via_check_invite(
    client, invite_hash: str
) -> tuple[int | None, str | None]:
    try:
        r = await client(CheckChatInviteRequest(invite_hash))
        if _is_chat_invite_already(r):
            chat = getattr(r, "chat", None)
            if chat is None:
                return None, None
            return utils.get_peer_id(chat), getattr(chat, "title", None)
    except Exception:
        logger.exception("CheckChatInvite after already participant")
    return None, None


async def check_invite_already_member(client, invite_hash: str) -> JoinDonorOutcome | None:
    """Повертає JOINED або None якщо ще не учасник / не визначено."""
    try:
        r = await client(CheckChatInviteRequest(invite_hash))
        if _is_chat_invite_already(r):
            chat = getattr(r, "chat", None)
            if chat is None:
                return None
            cid = utils.get_peer_id(chat)
            title = getattr(chat, "title", None)
            return JoinDonorOutcome(
                kind=JoinDonorKind.JOINED,
                channel_id=cid,
                title=title,
                fingerprint=_invite_fingerprint(invite_hash),
                invite_hash=invite_hash,
            )
    except UserAlreadyParticipantError:
        cid, title = await _participant_via_check_invite(client, invite_hash)
        if cid:
            ent = await client.get_entity(cid)
            ttl = getattr(ent, "title", None) or title
            return JoinDonorOutcome(
                kind=JoinDonorKind.JOINED,
                channel_id=cid,
                title=ttl,
                fingerprint=_invite_fingerprint(invite_hash),
                invite_hash=invite_hash,
            )
    except Exception:
        pass
    return None


async def username_join_outcome(client, username: str) -> JoinDonorOutcome:
    fp = _username_fingerprint(username)
    try:
        from telethon.errors import ChannelPrivateError, UsernameInvalidError, UsernameNotOccupiedError
    except ImportError:
        ChannelPrivateError = UsernameInvalidError = UsernameNotOccupiedError = type(None)
    try:
        ent = await client.get_entity(username)
    except Exception as ex:
        if UsernameInvalidError and isinstance(
            ex, (UsernameInvalidError, UsernameNotOccupiedError)
        ):
            return JoinDonorOutcome(
                kind=JoinDonorKind.ERROR,
                fingerprint=fp,
                error_uk="Канал з таким @username не знайдено. Перевірте написання.",
            )
        logger.exception("get_entity username")
        return JoinDonorOutcome(
            kind=JoinDonorKind.ERROR,
            fingerprint=fp,
            error_uk="Не вдалося відкрити канал за посиланням або @.",
        )

    if not isinstance(ent, Channel):
        return JoinDonorOutcome(
            kind=JoinDonorKind.ERROR,
            fingerprint=fp,
            error_uk="Потрібен саме <b>канал</b> для клонування постів.",
        )
    if getattr(ent, "megagroup", False):
        return JoinDonorOutcome(
            kind=JoinDonorKind.ERROR,
            fingerprint=fp,
            error_uk="Це група-обговорення, не канал. Вкажіть саме канал або інвайт-посилання.",
        )

    try:
        await client(JoinChannelRequest(ent))
    except UserAlreadyParticipantError:
        pass
    except Exception as ex:
        if ChannelPrivateError and isinstance(ex, ChannelPrivateError):
            return JoinDonorOutcome(
                kind=JoinDonorKind.ERROR,
                fingerprint=fp,
                error_uk="Цей канал закритий. Надішліть дійсне <b>посилання-запрошення</b> (t.me/+…).",
            )
        logger.exception("JoinChannel")
        return JoinDonorOutcome(
            kind=JoinDonorKind.ERROR,
            fingerprint=fp,
            error_uk="Не вдалося відкрити доступ до каналу. Спробуйте інвайт-посилання.",
        )

    cid = utils.get_peer_id(ent)
    ttl = getattr(ent, "title", None)
    return JoinDonorOutcome(
        kind=JoinDonorKind.JOINED,
        channel_id=cid,
        title=ttl,
        fingerprint=fp,
    )


async def join_donor_from_parsed(client, parsed: ParsedRef) -> JoinDonorOutcome:
    if isinstance(parsed, _InviteRef):
        return await invite_join_outcome(client, parsed.hash)
    return await username_join_outcome(client, parsed.username)
