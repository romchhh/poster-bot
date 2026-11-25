import logging
import json
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot

from app.config import get_settings
from database_functions.posts_db import (
    get_pending_scheduled_posts,
    update_post_status,
)
from database_functions.client_db import get_user_notifications_status
from database_functions.channels_db import get_channel_by_id
from services.posts.delivery import deliver_post_to_channel
from utils.post_utils import parse_url_buttons

logger = logging.getLogger(__name__)


async def _execute_auto_delete_messages(
    bot: Bot, channel_id: int, message_ids: list[int]
) -> None:
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=channel_id, message_id=mid)
            logger.info("Auto-delete message_id=%s channel=%s", mid, channel_id)
        except Exception:
            logger.exception("Auto-delete failed mid=%s channel=%s", mid, channel_id)


def schedule_post_deletion(bot: Bot, channel_id: int, message_ids, minutes: int) -> None:
    from app.runtime import scheduler

    ids = [message_ids] if isinstance(message_ids, int) else list(message_ids)
    ids = [int(x) for x in ids if x is not None]
    if not ids or not minutes:
        return

    tz_name = get_settings().timezone
    run_date = datetime.now(ZoneInfo(tz_name)) + timedelta(minutes=int(minutes))
    job_id = f"autodel_{channel_id}_{ids[0]}_{uuid.uuid4().hex[:12]}"
    scheduler.add_job(
        _execute_auto_delete_messages,
        "date",
        run_date=run_date,
        args=[bot, channel_id, ids],
        id=job_id,
        replace_existing=False,
    )
    logger.info(
        "Auto-delete scheduled at %s (%s msgs) channel=%s",
        run_date.strftime("%Y-%m-%d %H:%M"),
        len(ids),
        channel_id,
    )


async def check_and_publish_scheduled_posts(bot: Bot):
    try:
        notify_by_user: dict[int, list[str]] = {}
        pending_posts = get_pending_scheduled_posts()

        if pending_posts:
            logger.info("Pending scheduled posts: %s", len(pending_posts))

        for post in pending_posts:
            post_id = post[0]
            try:
                user_id = post[1]
                from database_functions.billing_db import denial

                reason = denial(user_id, "posting")
                if reason:
                    update_post_status(post_id, "failed", error_message=reason)
                    continue
                channel_id = post[2]
                post_text = post[3]
                media_files_json = post[6]
                url_buttons_text = post[7]
                settings_json = post[11]

                media_files = json.loads(media_files_json) if media_files_json else []
                settings = json.loads(settings_json) if settings_json else {}
                url_buttons = (
                    parse_url_buttons(url_buttons_text) if url_buttons_text else []
                )

                post_data = {
                    "text": post_text,
                    "media_files": media_files,
                    "url_buttons": url_buttons,
                    "settings": settings,
                }

                result = await deliver_post_to_channel(
                    bot,
                    user_id=user_id,
                    channel_id=channel_id,
                    post_data=post_data,
                    scheduled_post_id=post_id,
                    url_buttons_log=url_buttons_text or "",
                )

                if result.skipped:
                    update_post_status(post_id, "skipped", error_message=result.error)
                    logger.info(
                        "Skipped scheduled post id=%s channel=%s: %s",
                        post_id,
                        channel_id,
                        result.error,
                    )
                elif result.ok:
                    update_post_status(post_id, "published")
                    logger.info(
                        "Published scheduled post id=%s channel=%s",
                        post_id,
                        channel_id,
                    )
                    if get_user_notifications_status(user_id):
                        ch_row = get_channel_by_id(int(channel_id))
                        title = (
                            result.channel_title
                            or (ch_row[2] if ch_row else str(channel_id))
                        )
                        lst = notify_by_user.setdefault(user_id, [])
                        if title not in lst:
                            lst.append(title)
                else:
                    update_post_status(post_id, "failed", error_message=result.error)
                    logger.warning(
                        "Failed scheduled post id=%s: %s", post_id, result.error
                    )
            except Exception as e:
                logger.exception("Error processing scheduled post id=%s", post_id)
                try:
                    update_post_status(post_id, "failed", error_message=str(e))
                except Exception:
                    pass

        for uid, titles in notify_by_user.items():
            try:
                lines = "\n".join(f"• {t}" for t in titles)
                await bot.send_message(
                    uid,
                    f"🔔 <b>Запланований пост опубліковано</b>\n\n"
                    f"<b>Канали:</b>\n{lines}",
                    parse_mode="HTML",
                )
            except Exception:
                logger.exception("Notify failed for user %s", uid)

    except Exception:
        logger.exception("Scheduler check_and_publish failed")
