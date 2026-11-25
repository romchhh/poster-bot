"""Події в каналах: пости без бота (контент-план), зміни прав бота в чаті (my_chat_member)."""

from utils.ui_emoji import E
import html
from datetime import datetime

from aiogram import Router, types
from aiogram.exceptions import TelegramBadRequest

from database_functions.channels_db import (
    add_channel,
    auto_detect_discussion_group,
    get_channel_by_id,
    get_channel_members,
    remove_channel,
)
from database_functions.folders_db import get_user_folders
from database_functions.posts_db import add_external_channel_post
from keyboards.client_keyboards.folder_keyboards import get_folder_move_keyboard
from app.runtime import bot
from utils.channel_post_utils import channel_post_media_type, channel_post_text
from utils.client_functions import check_bot_permissions, get_chat_link

router = Router()


@router.channel_post()
async def track_external_channel_post(message: types.Message):
    """Записує пости, опубліковані в каналі не через бота (для контент-плану)."""
    if message.chat.type != "channel":
        return

    ch = get_channel_by_id(message.chat.id)
    if not ch:
        return
    if len(ch) > 8 and ch[8] == 0:
        return
    if (ch[5] or "channel") != "channel":
        return

    if message.from_user and message.from_user.id == message.bot.id:
        return

    body = channel_post_text(message)
    media_t = channel_post_media_type(message)
    if not body.strip() and not media_t:
        return

    owner_user_id = ch[6]
    if message.date:
        published_date = message.date.strftime("%Y-%m-%d %H:%M:%S")
    else:
        published_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    add_external_channel_post(
        user_id=owner_user_id,
        channel_id=message.chat.id,
        message_id=message.message_id,
        post_text=body,
        media_type=media_t,
        published_date=published_date,
    )


@router.my_chat_member()
async def bot_chat_member_updated(update: types.ChatMemberUpdated):
    if update.chat.type not in ["channel", "supergroup", "group"]:
        return

    old_status = update.old_chat_member.status if update.old_chat_member else "left"
    new_status = update.new_chat_member.status

    # Бот вилучений з чату
    if new_status in ("left", "kicked"):
        if old_status in ("administrator", "member", "creator"):
            await handle_bot_removed(update)
        return

    # Бот зʼявився в чаті (запрошений / знято обмеження / тощо)
    if old_status in ("left", "kicked", "restricted") and new_status in (
        "administrator",
        "member",
    ):
        await handle_bot_added(update)
        return

    # Канал: бота зняли з адмінів — лишився підписником
    if (
        update.chat.type == "channel"
        and old_status == "administrator"
        and new_status == "member"
    ):
        await handle_bot_removed(update)
        return

    # Зміна прав або member → administrator у групі / супергрупі
    if old_status in ("administrator", "member") and new_status in (
        "administrator",
        "member",
    ):
        await handle_bot_permissions_changed(update)


async def handle_bot_added(update: types.ChatMemberUpdated):
    chat = update.chat
    user_who_added = update.from_user
    if user_who_added is None:
        print(
            "⚠️ my_chat_member: немає from_user — канал не привʼязано до акаунта в SkyPost"
        )
        return
    chat_link = get_chat_link(chat)
    chat_type_ukr = "Канал" if chat.type == "channel" else "Група"

    try:
        member = await bot.get_chat_member(chat.id, user_who_added.id)
        if member.status not in ["administrator", "creator"]:
            return
        user_role = "owner" if member.status == "creator" else "admin"
    except TelegramBadRequest as e:
        if "member list is inaccessible" in str(e):
            user_role = "admin"
        else:
            print(f"❌ Помилка перевірки прав: {e}")
            return
    except Exception as e:
        print(f"❌ Помилка перевірки прав: {e}")
        return

    permission_result = await check_bot_permissions(bot, chat.id)

    try:
        if permission_result["has_all_permissions"]:
            if chat.type == "channel":
                await auto_detect_discussion_group(bot, chat.id)

            from database_functions.billing_db import ChannelLimitError

            try:
                add_channel(
                    channel_id=chat.id,
                    channel_title=chat.title,
                    channel_username=chat.username or "",
                    channel_link=chat_link,
                    added_by_user_id=user_who_added.id,
                    chat_type=chat.type,
                    folder_id=None,
                    user_role=user_role,
                )
            except ChannelLimitError as exc:
                await bot.send_message(user_who_added.id, str(exc))
                return

            folders = get_user_folders(user_who_added.id)

            if folders:
                text = f"""✅ <b>Канал успішно додано!</b>

{E.channel} {chat_type_ukr}: <a href="{chat_link}">{chat.title}</a>
🆔 ID: <code>{chat.id}</code>

{E.folder} <b>Бажаєте перемістити канал в папку?</b>

Оберіть папку зі списку, створіть нову або пропустіть цей крок."""
            else:
                text = f"""✅ <b>Канал успішно додано!</b>

{E.channel} {chat_type_ukr}: <a href="{chat_link}">{chat.title}</a>
🆔 ID: <code>{chat.id}</code>

{E.folder} <b>Бажаєте додати канал в папку?</b>

Ви можете створити нову папку для організації каналів або додати канал без папки."""

            await bot.send_message(
                chat_id=user_who_added.id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=get_folder_move_keyboard(user_who_added.id, chat.id),
            )

        else:
            error_type = permission_result.get("error_type", None)

            if error_type == "member_list_inaccessible":
                message_text = f"""❌ <b>Бот не доданий як адміністратор!</b>

{E.channel} {chat_type_ukr}: <a href="{chat_link}">{chat.title}</a>

<b>{E.list} Інструкція:</b>

<b>1.</b> Відкрийте налаштування каналу/групи
<b>2.</b> Перейдіть в розділ "Адміністратори"
<b>3.</b> Натисніть "Додати адміністратора"
<b>4.</b> Знайдіть та оберіть бота <b>@{(await bot.get_me()).username}</b>
<b>5.</b> Надайте боту наступні права:
   • ✅ Публікувати повідомлення
   • ✅ Редагувати повідомлення інших користувачів
   • ✅ Видаляти повідомлення інших користувачів
<b>6.</b> Збережіть зміни

<i>⚠️ Після додавання бота адміністратором, канал автоматично з'явиться в вашому списку.</i>"""
            elif not permission_result["is_admin"]:
                message_text = f"""❌ <b>Бот не є адміністратором!</b>

{E.channel} {chat_type_ukr}: <a href="{chat_link}">{chat.title}</a>

⚠️ Спочатку додайте бота як адміністратора з наступними правами:
• Публікувати повідомлення
• Редагувати повідомлення інших користувачів
• Видаляти повідомлення інших користувачів

Після цього спробуйте знову."""
            else:
                missing_perms = "\n".join(
                    [f"• {perm}" for perm in permission_result["missing_permissions"]]
                )
                message_text = f"""{E.warn} <b>Недостатньо прав бота!</b>

{E.channel} {chat_type_ukr}: <a href="{chat_link}">{chat.title}</a>

❌ Боту потрібні наступні права адміністратора:
{missing_perms}

Надайте боту ці права та спробуйте знову."""

            await bot.send_message(
                chat_id=user_who_added.id,
                text=message_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
    except Exception as e:
        print(f"❌ Не вдалося відправити повідомлення користувачу {user_who_added.id}: {e}")


async def handle_bot_permissions_changed(update: types.ChatMemberUpdated):
    chat = update.chat
    user_who_changed = update.from_user
    chat_link = get_chat_link(chat)

    try:
        member = await bot.get_chat_member(chat.id, user_who_changed.id)
        if member.status not in ["administrator", "creator"]:
            return
        user_role = "owner" if member.status == "creator" else "admin"
    except Exception as e:
        print(f"❌ Помилка перевірки прав: {e}")
        return

    permission_result = await check_bot_permissions(bot, chat.id)

    try:
        if permission_result["has_all_permissions"]:
            from database_functions.billing_db import ChannelLimitError

            try:
                is_new = add_channel(
                    channel_id=chat.id,
                    channel_title=chat.title,
                    channel_username=chat.username or "",
                    channel_link=chat_link,
                    added_by_user_id=user_who_changed.id,
                    chat_type=chat.type,
                    user_role=user_role,
                )
            except ChannelLimitError as exc:
                await bot.send_message(user_who_changed.id, str(exc))
                return

            if chat.type == "channel":
                await auto_detect_discussion_group(bot, chat.id)

            if is_new:
                if chat.type == "channel":
                    text = f"""✅ <b>Канал успішно додано!</b>

{E.channel} Канал: <a href="{chat_link}">{chat.title}</a>
🆔 ID: <code>{chat.id}</code>

Тепер ви можете публікувати пости в цей канал через бота."""
                else:
                    text = f"""✅ <b>Група успішно додана!</b>

💬 Група: <a href="{chat_link}">{chat.title}</a>
🆔 ID: <code>{chat.id}</code>

Тепер ви можете керувати цією групою через бота."""

                await bot.send_message(
                    chat_id=user_who_changed.id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
    except Exception as e:
        print(f"❌ Не вдалося відправити повідомлення користувачу {user_who_changed.id}: {e}")


async def handle_bot_removed(update: types.ChatMemberUpdated):
    chat = update.chat
    chat_link = get_chat_link(chat)
    title = html.escape(chat.title or "Канал")

    channel_info = get_channel_by_id(chat.id)
    if not channel_info:
        return

    members = get_channel_members(chat.id)
    user_ids = [m[0] for m in members] if members else []
    if not user_ids and len(channel_info) > 6:
        user_ids = [channel_info[6]]

    success = remove_channel(chat.id)
    if not success or not user_ids:
        return

    notify_text = f"""🚫 <b>Канал видалено з SkyPost</b>

{E.channel} Канал: <a href="{chat_link}">{title}</a>

Канал прибрано зі списку, бо у бота більше немає потрібних прав адміністратора (бот вилучений з адмінів або втратив статус адміна).

Щоб знову керувати каналом через бота, додайте його заново й надайте всі необхідні права."""

    for uid in user_ids:
        try:
            await bot.send_message(
                chat_id=uid,
                text=notify_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as e:
            print(f"❌ Не вдалося повідомити user {uid} про видалення каналу: {e}")
