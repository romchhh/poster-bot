"""Settings: profile, subscription, notifications, timezone, confirm publish."""

from utils.ui_emoji import E, Icon
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
import asyncio
import html
import re
from datetime import datetime
from keyboards.client_keyboards.settings_keyboards import (
    get_back_to_settings_keyboard,
    get_profile_keyboard,
    get_settings_channels_intro_keyboard,
    get_settings_main_keyboard,
    get_timezone_selection_keyboard,
)
from utils.datetime_ui import format_user_datetime
from database_functions.client_db import (
    get_user_language,
    get_user_timezone,
    get_timezone_info,
    toggle_user_confirm_publish,
    toggle_user_notifications,
    update_user_activity,
    set_user_timezone,
)
from database_functions.channels_db import (
    get_all_channels,
    get_channel_by_id,
    get_channels_without_folder,
    remove_channel,
)
from database_functions.folders_db import get_user_folders
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()


def _profile_counts(user_id: int) -> tuple[int, int]:
    channels = groups = 0
    for row in get_all_channels(user_id=user_id, only_active=True):
        kind = row[5] if len(row) > 5 and row[5] else "channel"
        if kind == "channel":
            channels += 1
        else:
            groups += 1
    return channels, groups


async def profile_payload_for(user: types.User) -> tuple[str, InlineKeyboardMarkup]:
    from app.runtime import bot
    from database_functions.billing_db import snapshot
    from texts.messages.settings import profile_screen

    name = user.full_name or user.username or "Користувач"
    channels, groups = _profile_counts(user.id)
    info = snapshot(user.id, with_referrals=True)
    me = await bot.get_me()
    username = me.username or ""
    link = f"https://t.me/{username}?start=ref_{user.id}" if username else f"ref_{user.id}"
    text = profile_screen(
        name=name,
        user_id=user.id,
        channels=channels,
        groups=groups,
        referrals=info["referrals"],
        plan=info["title"],
        tokens=info["tokens"],
        bonus_days=info["bonus_days"],
        next_goal=info["next_goal"],
        link=link,
        low_tokens=info["tokens"] < 1,
    )
    return text, get_profile_keyboard(link)


async def profile_text_for(user: types.User) -> str:
    text, _ = await profile_payload_for(user)
    return text


@router.callback_query(F.data == "settings_profile")
async def profile_settings(callback: types.CallbackQuery, state: FSMContext):
    update_user_activity(callback.from_user.id)
    text, markup = await profile_payload_for(callback.from_user)
    await callback.message.edit_text(
        text=text,
        parse_mode="HTML",
        reply_markup=markup,
    )
    await callback.answer()


@router.callback_query(F.data == "addsettings_channel")
async def add_channel_settings(callback: types.CallbackQuery, state: FSMContext):
    caption = f"{E.channel} <b>Немає каналів</b>\n\nДодайте канал або групу через меню, щоб користуватися контент-планом."
    await callback.message.answer(
        text=caption, parse_mode="HTML", disable_web_page_preview=True
    )
    await callback.answer()


@router.callback_query(F.data == "settings_subscription")
async def subscription_settings(callback: types.CallbackQuery, state: FSMContext):
    from database_functions.billing_db import snapshot

    info = snapshot(callback.from_user.id)
    limit = "без обмежень" if info["channel_limit"] is None else str(info["channel_limit"])
    ends = "—"
    if info["ends_at"]:
        ends = format_user_datetime(info["ends_at"])
    status = "активний" if info["active"] else "немає"
    message_text = (
        f"{E.gem} <b>Моя підписка</b>\n\n"
        f"Тариф: <b>{info['title']}</b> · {status}\n"
        f"{E.calendar} Діє до: {ends}\n"
        f"Токени: <b>{info['tokens']:g}</b>\n"
        f"{E.channel} Ліміт каналів: {limit}\n\n"
        f"Тариф видає адміністратор."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Назад",
                    callback_data="back_to_settings",
                    icon_custom_emoji_id=Icon.back,
                )
            ],
        ]
    )
    await callback.message.edit_text(
        text=message_text, parse_mode="HTML", reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "settings_notifications")
async def notifications_settings(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    new_status = toggle_user_notifications(user_id)
    status_text = "увімкнені" if new_status else "вимкнені"
    intro = f"{E.settings} <b>Налаштування SkyPost</b>\n\nОберіть розділ нижче."
    await callback.message.edit_text(
        text=intro, parse_mode="HTML", reply_markup=get_settings_main_keyboard(user_id)
    )
    await callback.answer(
        f"🔔 Сповіщення {status_text}.\n\nЯкщо вимкнути — бот не надсилатиме нагадування про публікацію чи видалення.",
        show_alert=True,
    )


@router.callback_query(F.data == "settings_timezone")
async def timezone_settings(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    update_user_activity(user_id)
    current_timezone = get_user_timezone(user_id)
    body = f"{E.clock} <b>Часовий пояс</b>\n\nПоточне значення: <code>{current_timezone}</code>\n\nОберіть місто / регіон — заплановані пости будуть з’являтися «до часу» саме за цим часом."
    await callback.message.edit_text(
        text=body,
        parse_mode="HTML",
        reply_markup=get_timezone_selection_keyboard(current_timezone),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_timezone_"))
async def set_timezone(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    update_user_activity(user_id)
    timezone_name = callback.data.replace("set_timezone_", "")
    set_user_timezone(user_id, timezone_name)
    timezones = get_timezone_info()
    selected_tz_info = timezones.get(timezone_name, {})
    display_name = selected_tz_info.get("name_uk", timezone_name)
    current_time = selected_tz_info.get("current_time", "00:00")
    body = f"{E.clock} <b>Часовий пояс</b>\n\nПоточне значення: <code>{timezone_name}</code>\n\nОберіть інше місто, якщо потрібно:"
    await callback.message.edit_text(
        text=body,
        parse_mode="HTML",
        reply_markup=get_timezone_selection_keyboard(timezone_name),
    )
    await callback.answer(
        f"✅ Часовий пояс: {display_name} · зараз {current_time}", show_alert=True
    )


@router.callback_query(
    F.data.startswith("delete_channel_") & ~F.data.startswith("delete_channel_confirm_")
)
async def delete_channel_confirm(callback: types.CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.removeprefix("delete_channel_"))
    user_id = callback.from_user.id
    user_language = get_user_language(user_id) or "uk"
    channel_info = get_channel_by_id(channel_id)
    if not channel_info:
        await callback.answer("❌ Канал не знайдено")
        return
    channel_title = channel_info[2]
    channel_link = channel_info[4] if len(channel_info) > 4 and channel_info[4] else "#"
    escaped_channel_title = html.escape(channel_title)
    confirm_texts = {
        "uk": f'❓ <b>ВИДАЛЕННЯ КАНАЛУ</b>\n\n⚠️ Ви дійсно хочете видалити канал <a href="{channel_link}">{escaped_channel_title}</a>?\n\nЦя дія видалить усі заплановані пости та налаштування каналу.\nЦю дію неможливо скасувати.'
    }
    keyboard = get_channel_delete_confirmation_keyboard(channel_id, user_language)
    await callback.message.edit_text(
        text=confirm_texts.get(user_language, confirm_texts["uk"]),
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    await callback.answer()


def get_channel_delete_confirmation_keyboard(channel_id: int, language: str = "uk"):
    texts = {"uk": {"yes": "Так, видалити", "no": "Скасувати"}}
    text = texts.get(language, texts["uk"])
    keyboard = [
        [
            InlineKeyboardButton(
                text=text["yes"],
                callback_data=f"delete_channel_confirm_{channel_id}",
                icon_custom_emoji_id=Icon.trash,
            ),
            InlineKeyboardButton(
                text=text["no"],
                callback_data=f"channel_settings_{channel_id}",
                icon_custom_emoji_id=Icon.cancel,
            ),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


@router.callback_query(F.data.startswith("delete_channel_confirm_"))
async def delete_channel_execute(callback: types.CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.removeprefix("delete_channel_confirm_"))
    user_id = callback.from_user.id
    user_language = get_user_language(user_id) or "uk"
    channel_info = get_channel_by_id(channel_id)
    if not channel_info:
        error_texts = {"uk": "❌ Чат не знайдено"}
        await callback.answer(error_texts.get(user_language, error_texts["uk"]))
        return
    chat_type = (
        channel_info[5]
        if channel_info and len(channel_info) > 5 and channel_info[5]
        else "channel"
    )
    is_channel = chat_type == "channel"
    success = remove_channel(channel_id, user_id=user_id)
    if success:
        success_texts = {
            "uk": f"✅ <b>{('Канал' if is_channel else 'Групу')} успішно видалено!</b>"
        }
        await callback.message.edit_text(
            text=success_texts.get(user_language, success_texts["uk"]),
            parse_mode="HTML",
        )
        await asyncio.sleep(2)
        user_id = callback.from_user.id
        user_language = get_user_language(user_id) or "uk"
        user_channels = get_all_channels(user_id)
        if not user_channels:
            no_channels_texts = {
                "uk": f"{E.channel} <b>КАНАЛИ</b>\n\n❌ У вас немає доданих каналів!\n\nСпочатку додайте канал через головне меню."
            }
            await callback.message.edit_text(
                text=no_channels_texts.get(user_language, no_channels_texts["uk"]),
                parse_mode="HTML",
                reply_markup=get_back_to_settings_keyboard(),
            )
            await callback.answer()
            return
        channels_text = f"{E.channel} <b>Канали та групи</b>\n\nОберіть канал або групу для налаштування."
        folders = get_user_folders(user_id)
        channels_wo = get_channels_without_folder(user_id)
        keyboard = get_settings_channels_intro_keyboard(folders, channels_wo)
        await callback.message.edit_text(
            text=channels_text, parse_mode="HTML", reply_markup=keyboard
        )
        await callback.answer()
    else:
        error_texts = {
            "uk": f"❌ Помилка при видаленні {('каналу' if is_channel else 'групи')}"
        }
        await callback.answer(error_texts.get(user_language, error_texts["uk"]))


@router.callback_query(F.data == "settings_confirm_publish")
async def settings_confirm_publish(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_language = get_user_language(user_id) or "uk"
    new_status = toggle_user_confirm_publish(user_id)
    await callback.message.edit_reply_markup(
        reply_markup=get_settings_main_keyboard(user_id)
    )
    status_texts = {
        "uk": {
            "enabled": "✅ Підтвердження публікації увімкнено",
            "disabled": "❌ Підтвердження публікації вимкнено",
        }
    }
    text = status_texts.get(user_language, status_texts["uk"])
    status_text = text["enabled"] if new_status else text["disabled"]
    await callback.answer(status_text, show_alert=True)


def generate_signature_name_from_text(text: str) -> str:
    """Generate signature name from text by taking first meaningful words"""
    clean_text = re.sub("<[^>]*>", "", text)
    clean_text = re.sub("\\s+", " ", clean_text).strip()
    words = clean_text.split()
    if not words:
        return "Автопідпис"
    name_parts = []
    current_length = 0
    for word in words[:4]:
        if current_length + len(word) + 1 > 30:
            break
        name_parts.append(word)
        current_length += len(word) + 1
    if not name_parts:
        return words[0][:25] + "..." if len(words[0]) > 25 else words[0]
    return " ".join(name_parts)
