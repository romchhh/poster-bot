"""Telethon monitor: donor channel posts → preview group via Bot API."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from telethon import events, utils

from database_functions.copy_mirror_db import (
    insert_copy_mirror_pending_publish,
    merge_copy_mirror_pending_extras,
    mirror_routes_for_donor_channel,
    release_mirror_route_claim,
    set_copy_mirror_pending_publish_status,
    try_claim_mirror_route,
)
from keyboards.client_keyboards.copy_mirror_keyboards import get_mirror_pending_ui_keyboard

from .copy_mirror_bot_delivery import MirrorBotDelivery
from .mirror_flow import mirror_confirmation_html
from .mirror_owner_notify import (
    is_mirror_dest_unreachable,
    notify_mirror_destination_unreachable,
)
from .telethon_copy_client import get_telethon_client

logger = logging.getLogger(__name__)


class CopyMirrorMonitor:
    """Registers Telethon event handlers once per process lifetime."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._started = False

    @staticmethod
    def _has_any_media(tl_msgs: list) -> bool:
        for m in tl_msgs:
            if getattr(m, "photo", None) or getattr(m, "video", None):
                return True
            if getattr(m, "document", None) or getattr(m, "animation", None):
                return True
            if getattr(m, "audio", None) or getattr(m, "voice", None):
                return True
        return False

    @staticmethod
    def _first_sent_photo_message_id(sent: list) -> int | None:
        for sm in sent:
            if getattr(sm, "photo", None):
                return int(sm.message_id)
        return None

    async def start(self, bot: Bot) -> None:
        async with self._lock:
            if self._started:
                return
            client = await get_telethon_client()
            if not client:
                logger.warning(
                    "Copy mirror monitor: Telethon не активний — моніторинг вимкнено."
                )
                return

            async def on_album(ev: events.Album.Event):
                try:
                    await self._handle_incoming(bot, client, list(ev.messages))
                except Exception:
                    logger.exception("copy mirror album handler")

            async def on_new(ev: events.NewMessage.Event):
                try:
                    msg = ev.message
                    if getattr(msg, "grouped_id", None):
                        return
                    if not getattr(msg, "post", False):
                        return
                    if getattr(msg, "action", None) is not None:
                        return
                    await self._handle_incoming(bot, client, [msg])
                except Exception:
                    logger.exception("copy mirror newmessage handler")

            client.add_event_handler(on_album, events.Album(chats=None))
            client.add_event_handler(on_new, events.NewMessage(chats=None))
            self._started = True
            logger.info("Copy mirror monitor: обробники подій увімкнено.")

    async def stop(self) -> None:
        async with self._lock:
            self._started = False
            logger.info("Copy mirror monitor: stopped.")

    async def _handle_incoming(self, bot: Bot, client, messages: list) -> None:
        if not messages:
            return
        msg0 = messages[0]
        if not getattr(msg0, "post", False):
            return
        if getattr(msg0, "action", None) is not None:
            return

        donor_chat_id = utils.get_peer_id(msg0.peer_id)
        mids = sorted(int(m.id) for m in messages)
        first_mid = min(mids)

        routes = mirror_routes_for_donor_channel(int(donor_chat_id))
        if not routes:
            return

        tl_msgs = await client.get_messages(donor_chat_id, ids=mids)
        if tl_msgs is None:
            return
        if not isinstance(tl_msgs, list):
            tl_msgs = [tl_msgs]
        tl_msgs = sorted([m for m in tl_msgs if m is not None], key=lambda x: x.id)
        if len(tl_msgs) != len(mids):
            logger.warning(
                "copy mirror: кількість завантажених повідомлень не збігається %s vs %s",
                len(tl_msgs),
                len(mids),
            )
            return

        for owner_uid, sc_type, sc_id, dest_gid, donor_title in routes:
            if not try_claim_mirror_route(
                int(donor_chat_id), first_mid, owner_uid, sc_type, sc_id
            ):
                continue

            pk = insert_copy_mirror_pending_publish(
                owner_user_id=owner_uid,
                scope_type=sc_type,
                scope_id=sc_id,
                donor_channel_id=donor_chat_id,
                donor_title=donor_title,
                message_ids=mids,
                destination_group_id=dest_gid,
            )
            try:
                sent = await MirrorBotDelivery(bot, client).deliver(
                    dest_chat_id=dest_gid,
                    messages=tl_msgs,
                    extra_markup=None,
                    attach_markup_to_media=False,
                )
            except Exception as exc:
                logger.exception("deliver mirror preview pending_id=%s", pk)
                if is_mirror_dest_unreachable(exc):
                    await notify_mirror_destination_unreachable(
                        bot,
                        owner_user_id=owner_uid,
                        destination_group_id=int(dest_gid),
                        donor_title=donor_title,
                        scope_type=sc_type,
                        scope_id=int(sc_id),
                    )
                set_copy_mirror_pending_publish_status(pk, "failed")
                release_mirror_route_claim(
                    int(donor_chat_id), first_mid, owner_uid, sc_type, sc_id
                )
                continue

            is_album = len(tl_msgs) > 1
            has_any = self._has_any_media(tl_msgs)
            has_photo_single = len(tl_msgs) == 1 and bool(
                getattr(tl_msgs[0], "photo", None)
            )
            photo_mid = (
                self._first_sent_photo_message_id(sent) if has_photo_single else None
            )
            me = await bot.get_me()
            bot_uname = (me.username or "").strip().lstrip("@") or None
            kb = get_mirror_pending_ui_keyboard(
                pk,
                has_any_media=has_any,
                has_photo_single=has_photo_single,
                photo_message_id=photo_mid,
                is_media_group=is_album,
                bot_username=bot_uname,
            )
            try:
                preview_ids = [
                    int(getattr(m, "message_id"))
                    for m in sent
                    if getattr(m, "message_id", None) is not None
                ]
                ui = await bot.send_message(
                    chat_id=int(dest_gid),
                    text=mirror_confirmation_html(
                        owner_uid=owner_uid,
                        donor_title=donor_title,
                        donor_chat_id=int(donor_chat_id),
                        posted_at=msg0.date,
                        scope_type=sc_type,
                        scope_id=sc_id,
                    ),
                    parse_mode="HTML",
                    reply_markup=kb,
                )
                merge_copy_mirror_pending_extras(
                    pk,
                    {
                        "confirmation_message_id": int(ui.message_id),
                        "preview_photo_message_id": photo_mid,
                        "is_media_group_preview": is_album,
                        "preview_message_ids": preview_ids,
                    },
                )
            except Exception as exc:
                logger.exception("mirror UI message pending_id=%s", pk)
                if is_mirror_dest_unreachable(exc):
                    await notify_mirror_destination_unreachable(
                        bot,
                        owner_user_id=owner_uid,
                        destination_group_id=int(dest_gid),
                        donor_title=donor_title,
                        scope_type=sc_type,
                        scope_id=int(sc_id),
                    )
                set_copy_mirror_pending_publish_status(pk, "failed")
                continue


copy_mirror_monitor = CopyMirrorMonitor()


async def start_copy_mirror_monitor(bot: Bot) -> None:
    await copy_mirror_monitor.start(bot)


async def stop_copy_mirror_monitor() -> None:
    await copy_mirror_monitor.stop()
