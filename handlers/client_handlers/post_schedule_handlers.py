"""Post scheduling calendar / time / confirm (shared with mirror schedule)."""

from __future__ import annotations

from utils.ui_emoji import E, Icon
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.runtime import bot
from database_functions.channels_db import get_channel_by_id
from database_functions.client_db import (
    get_user_confirm_publish_status,
    get_user_timezone,
    user_timezone_label,
)
from keyboards.client_keyboards.post_keyboards import (
    get_publishing_menu_keyboard,
    get_schedule_calendar_keyboard,
)
from texts.messages import post as post_msg
from states.client_states import PostCreation
from utils.copy_utils.mirror_flow import (
    mirror_finalize_schedule_save,
    mirror_restore_group_confirmation,
    mirror_try_handle_schedule_time_message,
)
from utils.post_schedule_utils import finalize_schedule_save
from utils.post_utils import parse_time_input

router = Router()


@router.callback_query(F.data == "schedule_post")
async def schedule_post_callback(callback: types.CallbackQuery, state: FSMContext):
    """Меню вибору дати для планування"""
    uid = callback.from_user.id
    from database_functions.billing_db import denial

    reason = denial(uid, "posting")
    if reason:
        await callback.answer(reason, show_alert=True)
        return
    tz_hint = user_timezone_label(uid)
    await callback.message.edit_text(
        text=f"""{E.calendar} <b>Планування публікації</b>

Оберіть дату публікації.

{E.clock} <b>Час у календарі та для поста</b> — за вашим поясом: {tz_hint}
<i>Змінити пояс можна в «Налаштування» → «Часовий пояс».</i>""",
        parse_mode="HTML",
        reply_markup=get_schedule_calendar_keyboard(user_id=uid),
    )

    await callback.answer()


@router.callback_query(F.data.startswith("schedule_date_"))
async def process_schedule_date(callback: types.CallbackQuery, state: FSMContext):
    """Обробка вибору дати"""
    date_str = callback.data.split("_")[2]  # schedule_date_YYYY-MM-DD
    
    # Зберігаємо дату та id повідомлення з календарем / підказкою часу (для edit замість нових повідомлень)
    await state.update_data(
        scheduled_date=date_str,
        schedule_prompt_message_id=callback.message.message_id,
    )
    
    # Конвертуємо дату для відображення
    from datetime import datetime
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    date_formatted = date_obj.strftime('%d.%m.%Y')
    
    day_names = {
        0: 'Понеділок', 1: 'Вівторок', 2: 'Середа', 
        3: 'Четвер', 4: 'П\'ятниця', 5: 'Субота', 6: 'Неділя'
    }
    day_name = day_names[date_obj.weekday()]
    data_pref = await state.get_data()
    tz_uid = callback.from_user.id
    if data_pref.get("mirror_schedule_pk") and data_pref.get("mirror_schedule_owner_uid"):
        tz_uid = int(data_pref["mirror_schedule_owner_uid"])
    tz_line = user_timezone_label(tz_uid)

    await callback.message.edit_text(
        text=f"""{E.clock} <b>Планування публікації</b>

<b>Обрана дата:</b> {date_formatted} ({day_name})

🕐 Час нижче — у <b>{tz_line}</b> (як у вашому профілі).

Введіть час публікації у зручному форматі:

<b>Приклади:</b>
• <code>14:30</code> - 14 годин 30 хвилин
• <code>1430</code> - те саме
• <code>9</code> - 9:00
• <code>09:00</code> - 9:00 ранку
• <code>21</code> - 21:00 (9 вечора)
• <code>1645</code> - 16:45

💡 <i>Просто введіть час в будь-якому зручному форматі!</i>""",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Скасувати",
                        callback_data="cancel_schedule",
                    icon_custom_emoji_id=Icon.cancel,
                )
                ]
            ]
        ),
    )

    await state.set_state(PostCreation.waiting_for_schedule_time)
    await callback.answer()


@router.callback_query(F.data.startswith("schedule_cal_prev:"))
async def schedule_calendar_prev(callback: types.CallbackQuery, state: FSMContext):
    """Перехід до попереднього місяця в календарі"""
    year_month = callback.data.split(":")[1]  # schedule_cal_prev:YYYY-MM
    year, month = map(int, year_month.split("-"))

    data = await state.get_data()
    cal_uid = callback.from_user.id
    back_cd = "back_to_publishing"
    if data.get("mirror_schedule_pk") and data.get("mirror_schedule_owner_uid"):
        cal_uid = int(data["mirror_schedule_owner_uid"])
        back_cd = "mirror_schedule_cancel"

    await callback.message.edit_reply_markup(
        reply_markup=get_schedule_calendar_keyboard(
            year, month, user_id=cal_uid, back_callback_data=back_cd
        )
    )
    await callback.answer()


@router.callback_query(F.data.startswith("schedule_cal_next:"))
async def schedule_calendar_next(callback: types.CallbackQuery, state: FSMContext):
    """Перехід до наступного місяця в календарі"""
    year_month = callback.data.split(":")[1]  # schedule_cal_next:YYYY-MM
    year, month = map(int, year_month.split("-"))

    data = await state.get_data()
    cal_uid = callback.from_user.id
    back_cd = "back_to_publishing"
    if data.get("mirror_schedule_pk") and data.get("mirror_schedule_owner_uid"):
        cal_uid = int(data["mirror_schedule_owner_uid"])
        back_cd = "mirror_schedule_cancel"

    await callback.message.edit_reply_markup(
        reply_markup=get_schedule_calendar_keyboard(
            year, month, user_id=cal_uid, back_callback_data=back_cd
        )
    )
    await callback.answer()


@router.callback_query(F.data == "ignore")
async def ignore_callback(callback: types.CallbackQuery):
    """Ігнорує натискання на неактивні кнопки"""
    await callback.answer()


@router.message(PostCreation.waiting_for_schedule_time)
async def process_schedule_time(message: types.Message, state: FSMContext):
    """Обробка введення часу для планування"""
    time_result = parse_time_input(message.text)
    
    if not time_result:
        await message.answer(
            "❌ <b>Неправильний формат часу!</b>\n\n"
            "Спробуйте ще раз. Приклади:\n"
            "<code>14:30</code>, <code>1430</code>, <code>9</code>, <code>21:00</code>",
            parse_mode="HTML"
        )
        return
    
    hours, minutes = time_result
    
    data = await state.get_data()
    date_str = data.get("scheduled_date")

    if not date_str:
        await message.answer("❌ Помилка: дата не обрана")
        return

    if await mirror_try_handle_schedule_time_message(
        message, state, hours=hours, minutes=minutes, date_str=date_str
    ):
        return

    post_data = data.get('post_data', {})
    selected_channels = data.get('selected_channels', [])
    
    # Створюємо datetime об'єкт у часовому поясі користувача (зберігаємо як локальний «настінний» час)
    user_id = message.from_user.id
    tz_name = get_user_timezone(user_id)
    zi = ZoneInfo(tz_name)
    schedule_local = datetime.strptime(
        f"{date_str} {hours:02d}:{minutes:02d}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=zi)
    now_local = datetime.now(zi)
    if schedule_local <= now_local:
        await message.answer(
            "❌ <b>Помилка!</b>\n\n"
            f"Час публікації має бути в майбутньому (за вашим поясом: {user_timezone_label(user_id)}).\n"
            "Введіть інший час:",
            parse_mode="HTML"
        )
        return
    
    schedule_datetime_naive = schedule_local.replace(tzinfo=None)
    await state.update_data(
        schedule_datetime=schedule_datetime_naive.strftime("%Y-%m-%d %H:%M:%S")
    )
    
    # Відновлюємо кнопки якщо вони були
    if post_data.get('url_buttons_raw_text'):
        from utils.post_utils import parse_url_buttons_with_entities
        entities_data = post_data.get('url_buttons_entities', [])
        
        from aiogram.types import MessageEntity
        entities = []
        for e_data in entities_data:
            entity = MessageEntity(
                type=e_data['type'],
                offset=e_data['offset'],
                length=e_data['length']
            )
            if e_data.get('custom_emoji_id'):
                entity.custom_emoji_id = e_data['custom_emoji_id']
            entities.append(entity)
        
        post_data['url_buttons'] = parse_url_buttons_with_entities(
            post_data['url_buttons_raw_text'],
            entities
        )
        await state.update_data(post_data=post_data)
    
    # Показуємо превʼю поста
    from handlers.client_handlers.post_handlers_simple import _replace_editing_post_preview
    await _replace_editing_post_preview(bot, message.chat.id, post_data, state)

    # Отримуємо назви каналів
    channel_names = []
    for channel_id in selected_channels:
        channel = get_channel_by_id(channel_id)
        if channel:
            channel_names.append(channel[2])  # channel_title
    
    channels_text = "\n".join([f"• {name}" for name in channel_names[:5]])
    if len(channel_names) > 5:
        channels_text += f"\n• ... і ще {len(channel_names) - 5}"
    
    # Форматуємо час для відображення
    time_formatted = schedule_datetime_naive.strftime("%d.%m.%Y о %H:%M")
    tz_note = user_timezone_label(user_id)
    
    # Рахуємо через скільки
    time_delta = schedule_local - now_local
    hours_until = int(time_delta.total_seconds() // 3600)
    minutes_until = int((time_delta.total_seconds() % 3600) // 60)
    
    if hours_until > 0:
        time_until_text = f"через {hours_until} год {minutes_until} хв"
    else:
        time_until_text = f"через {minutes_until} хв"
    
    confirmation_text = f"""{E.calendar} <b>Підтвердження планування</b>

<b>Дата і час публікації:</b>
{time_formatted} ({time_until_text})
{E.clock} <b>Часовий пояс:</b> {tz_note}

<b>Канали для публікації ({len(selected_channels)}):</b>
{channels_text}

<b>Справді запланувати публікацію цього поста?</b>"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Так, запланувати", callback_data="confirm_schedule",
                icon_custom_emoji_id=Icon.ok,
            ),
                InlineKeyboardButton(text="Скасувати", callback_data="cancel_schedule", icon_custom_emoji_id=Icon.cancel),
            ]
        ]
    )

    if get_user_confirm_publish_status(user_id):
        pmid = data.get("schedule_prompt_message_id")
        if pmid:
            try:
                await bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=int(pmid),
                    text=confirmation_text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            except TelegramBadRequest:
                await message.answer(
                    text=confirmation_text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
        else:
            await message.answer(
                text=confirmation_text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        try:
            await bot.delete_message(message.chat.id, message.message_id)
        except TelegramBadRequest:
            pass
    else:
        await finalize_schedule_save(message, state)


@router.callback_query(F.data == "confirm_schedule")
async def confirm_schedule_callback(callback: types.CallbackQuery, state: FSMContext):
    """Підтверджує планування та зберігає в БД"""
    data = await state.get_data()
    if data.get("mirror_schedule_pk"):
        await mirror_finalize_schedule_save(callback, state)
        return

    await finalize_schedule_save(callback, state)


@router.callback_query(F.data == "cancel_schedule")
async def cancel_schedule_callback(callback: types.CallbackQuery, state: FSMContext):
    """Скасовує планування і повертає до меню публікації"""
    data = await state.get_data()
    if data.get("mirror_schedule_pk"):
        pk = data.get("mirror_schedule_pk")
        await state.update_data(
            mirror_schedule_pk=None,
            mirror_schedule_owner_uid=None,
            scheduled_date=None,
            schedule_datetime=None,
            schedule_prompt_message_id=None,
        )
        await state.set_state(None)
        if pk:
            await mirror_restore_group_confirmation(bot, int(pk))
        await callback.answer("❌ Планування скасовано")
        return

    post_data = data.get("post_data", {})
    await state.set_state(PostCreation.editing_post)
    await callback.message.edit_text(
        text=post_msg.PUBLISH_SETTINGS,
        parse_mode="HTML",
        reply_markup=get_publishing_menu_keyboard(post_data),
    )
    await callback.answer("❌ Планування скасовано")


