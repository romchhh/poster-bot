"""Autolink setup: pick a channel, then phrase → URL sets."""

from __future__ import annotations

import html

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from database_functions.channels_db import get_all_channels, get_channel_by_id
from database_functions.client_db import update_user_activity
from keyboards.client_keyboards.autolink_keyboards import (
    channel_sets_keyboard,
    channels_keyboard,
    confirm_delete_keyboard,
    set_keyboard,
)
from modules.autolink.apply import apply_autolinks, normalize_url, split_phrases
from modules.autolink.db import (
    add_phrases,
    add_set,
    delete_phrase,
    delete_set,
    get_phrase,
    get_set,
    list_phrases,
    list_sets,
    toggle_set,
)
from states.client_states import AutolinkSetup
from texts.messages import autolink as msg

router = Router()


def _channel_title(channel_id: int) -> str:
    row = get_channel_by_id(int(channel_id))
    return (row[2] if row and len(row) > 2 else "") or "Канал"


async def _show_channels(target: types.Message, user_id: int, *, edit: bool) -> None:
    channels = get_all_channels(user_id=user_id, only_active=True)
    if not channels:
        text, markup = msg.EMPTY_CHANNELS, None
    else:
        text, markup = msg.INTRO, channels_keyboard(channels)
    if edit:
        await target.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=markup)


async def _show_channel(target: types.Message, channel_id: int) -> None:
    sets = list_sets(channel_id)
    await target.edit_text(
        msg.channel_screen(_channel_title(channel_id), len(sets)),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=channel_sets_keyboard(channel_id, sets),
    )


async def _show_set(target: types.Message, set_id: int) -> None:
    row = get_set(set_id)
    if not row:
        await target.answer("Набір не знайдено.")
        return
    phrases = list_phrases(set_id)
    await target.edit_text(
        msg.set_screen(row[3], row[4], bool(row[5]), [item[1] for item in phrases]),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=set_keyboard(set_id, row[2], bool(row[5]), phrases),
    )


@router.callback_query(F.data == "settings_autolinks")
async def open_autolinks(callback: types.CallbackQuery, state: FSMContext):
    update_user_activity(callback.from_user.id)
    from database_functions.billing_db import denial

    reason = denial(callback.from_user.id, "posting")
    if reason:
        await callback.answer(reason, show_alert=True)
        return
    await state.clear()
    await _show_channels(callback.message, callback.from_user.id, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("al_ch_"))
async def open_channel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await _show_channel(callback.message, int(callback.data.removeprefix("al_ch_")))
    await callback.answer()


@router.callback_query(F.data.startswith("al_add_"))
async def start_set(callback: types.CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.removeprefix("al_add_"))
    await state.set_state(AutolinkSetup.waiting_name)
    await state.update_data(channel_id=channel_id)
    await callback.message.answer(msg.ask_name(), parse_mode="HTML")
    await callback.answer()


@router.message(AutolinkSetup.waiting_name, F.text)
async def take_name(message: types.Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name or len(name) > 80:
        await message.answer("Назва має бути від 1 до 80 символів.")
        return
    await state.update_data(name=name)
    await state.set_state(AutolinkSetup.waiting_url)
    await message.answer(msg.ask_url(name), parse_mode="HTML")


@router.message(AutolinkSetup.waiting_url, F.text)
async def take_url(message: types.Message, state: FSMContext):
    url = normalize_url(message.text or "")
    if not url:
        await message.answer(msg.BAD_URL)
        return
    data = await state.get_data()
    await state.update_data(url=url)
    await state.set_state(AutolinkSetup.waiting_phrases)
    await message.answer(msg.ask_phrases(data.get("name", ""), url), parse_mode="HTML")


@router.message(AutolinkSetup.waiting_phrases, F.text)
async def take_phrases(message: types.Message, state: FSMContext):
    phrases = split_phrases(message.text or "")
    if not phrases:
        await message.answer("Надішліть хоча б одну фразу, кожну з нового рядка.")
        return
    data = await state.get_data()
    set_id = add_set(
        message.from_user.id,
        int(data["channel_id"]),
        data.get("name") or "Набір",
        data["url"],
    )
    add_phrases(set_id, phrases)
    await state.clear()
    channel_id = int(data["channel_id"])
    sets = list_sets(channel_id)
    await message.answer(
        msg.channel_screen(_channel_title(channel_id), len(sets)),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=channel_sets_keyboard(channel_id, sets),
    )


@router.callback_query(F.data.startswith("al_set_"))
async def open_set(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await _show_set(callback.message, int(callback.data.removeprefix("al_set_")))
    await callback.answer()


@router.callback_query(F.data.startswith("al_tog_"))
async def toggle(callback: types.CallbackQuery):
    set_id = int(callback.data.removeprefix("al_tog_"))
    toggle_set(set_id)
    await _show_set(callback.message, set_id)
    await callback.answer("Оновлено")


@router.callback_query(F.data.startswith("al_ph_"))
async def more_phrases(callback: types.CallbackQuery, state: FSMContext):
    set_id = int(callback.data.removeprefix("al_ph_"))
    await state.set_state(AutolinkSetup.waiting_extra_phrase)
    await state.update_data(set_id=set_id)
    await callback.message.answer(
        "Надішліть нові фрази, кожну з нового рядка.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AutolinkSetup.waiting_extra_phrase, F.text)
async def save_extra_phrases(message: types.Message, state: FSMContext):
    phrases = split_phrases(message.text or "")
    if not phrases:
        await message.answer("Порожній список. Надішліть фрази рядками.")
        return
    data = await state.get_data()
    set_id = int(data["set_id"])
    added = add_phrases(set_id, phrases)
    await state.clear()
    await message.answer(f"Додано: <b>{added}</b>", parse_mode="HTML")
    row = get_set(set_id)
    if row:
        phrases_rows = list_phrases(set_id)
        await message.answer(
            msg.set_screen(row[3], row[4], bool(row[5]), [item[1] for item in phrases_rows]),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=set_keyboard(set_id, row[2], bool(row[5]), phrases_rows),
        )


@router.callback_query(F.data.startswith("al_delph_"))
async def remove_phrase(callback: types.CallbackQuery):
    phrase = get_phrase(int(callback.data.removeprefix("al_delph_")))
    if not phrase:
        await callback.answer("Фразу вже видалено", show_alert=True)
        return
    delete_phrase(phrase[0])
    await _show_set(callback.message, phrase[1])
    await callback.answer("Фразу видалено")


@router.callback_query(F.data.startswith("al_del_"))
async def ask_delete(callback: types.CallbackQuery):
    set_id = int(callback.data.removeprefix("al_del_"))
    row = get_set(set_id)
    if not row:
        await callback.answer()
        return
    await callback.message.edit_text(
        f"Видалити набір <b>{html.escape(row[3])}</b> разом із фразами?",
        parse_mode="HTML",
        reply_markup=confirm_delete_keyboard(set_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("al_delok_"))
async def confirm_delete(callback: types.CallbackQuery):
    set_id = int(callback.data.removeprefix("al_delok_"))
    row = get_set(set_id)
    channel_id = row[2] if row else None
    delete_set(set_id)
    if channel_id is None:
        await callback.answer()
        return
    await _show_channel(callback.message, channel_id)
    await callback.answer("Видалено")


@router.callback_query(F.data.startswith("al_try_"))
async def start_preview(callback: types.CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.removeprefix("al_try_"))
    await state.set_state(AutolinkSetup.waiting_preview)
    await state.update_data(channel_id=channel_id)
    await callback.message.answer(msg.ASK_PREVIEW, parse_mode="HTML")
    await callback.answer()


@router.message(AutolinkSetup.waiting_preview, F.text)
async def show_preview(message: types.Message, state: FSMContext):
    data = await state.get_data()
    channel_id = int(data["channel_id"])
    linked = apply_autolinks(html.escape(message.text or ""), channel_id)
    await state.clear()
    await message.answer(linked, parse_mode="HTML", disable_web_page_preview=True)
    await message.answer(
        msg.channel_screen(_channel_title(channel_id), len(list_sets(channel_id))),
        parse_mode="HTML",
        reply_markup=channel_sets_keyboard(channel_id, list_sets(channel_id)),
    )
