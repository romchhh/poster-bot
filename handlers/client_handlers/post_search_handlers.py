"""Search published posts by text, keywords, or id, with channel/folder/date filters."""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta

from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database_functions.channels_db import get_all_channels
from database_functions.folders_db import get_user_folders
from database_functions.posts_db import search_published_posts
from services.posts.delivery import post_link_for_channel
from states.client_states import PostCreation, PostSearch
from texts import Main
from utils.datetime_ui import format_user_datetime
from utils.ui_emoji import E, Icon

router = Router()


def _plain(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _since(period: str) -> str | None:
    now = datetime.now()
    if period == "1":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7":
        start = now - timedelta(days=7)
    elif period == "30":
        start = now - timedelta(days=30)
    else:
        return None
    return start.strftime("%Y-%m-%d %H:%M:%S")


def _filters_keyboard(data: dict) -> InlineKeyboardMarkup:
    channel_id = data.get("search_channel_id")
    folder_id = data.get("search_folder_id")
    period = data.get("search_period") or "all"
    channel_label = "Канал: усі" if not channel_id else "Канал: обрано"
    folder_label = "Папка: усі" if not folder_id else "Папка: обрано"
    date_labels = {"all": "Увесь час", "1": "Сьогодні", "7": "7 днів", "30": "30 днів"}
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=channel_label, callback_data="ps_channels"),
                InlineKeyboardButton(text=folder_label, callback_data="ps_folders"),
            ],
            [
                InlineKeyboardButton(
                    text=f"Дата: {date_labels.get(period, 'Увесь час')}",
                    callback_data="ps_dates",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Новий пошук",
                    callback_data="ps_new",
                    icon_custom_emoji_id=Icon.search,
                )
            ],
        ]
    )


def _results_text(query: str, rows: list[dict]) -> str:
    title = html.escape(query or "усі пости")
    if not rows:
        return (
            f"{E.search} <b>Пошук постів</b>\n\n"
            f"Запит: <code>{title}</code>\n\n"
            "Нічого не знайдено. Змініть запит або фільтр."
        )
    lines = [
        f"{E.search} <b>Пошук постів</b>",
        f"Запит: <code>{title}</code>",
        "",
    ]
    for row in rows:
        snippet = html.escape(_plain(row["post_text"])[:80] or "без тексту")
        deleted = " · вже видалено" if row["is_deleted"] else ""
        _name, link = post_link_for_channel(row["channel_id"], row["message_id"])
        link_html = f' · <a href="{link}">відкрити</a>' if link else ""
        lines.append(
            f"• <b>{html.escape(row['channel_title'])}</b> · ID {row['id']}"
            f" · msg {row['message_id']}\n"
            f"  {format_user_datetime(row['published_date'])}{deleted}{link_html}\n"
            f"  {snippet}"
        )
    return "\n".join(lines)


async def _show_results(target: types.Message, state: FSMContext, *, edit: bool) -> None:
    data = await state.get_data()
    rows = search_published_posts(
        target.chat.id,
        data.get("search_query") or "",
        channel_id=data.get("search_channel_id"),
        folder_id=data.get("search_folder_id"),
        since=_since(data.get("search_period") or "all"),
    )
    text = _results_text(data.get("search_query") or "", rows)
    markup = _filters_keyboard(data)
    if edit:
        await target.edit_text(
            text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True
        )
    else:
        await target.answer(
            text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True
        )


async def search_start(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(PostSearch.waiting_query)
    await message.answer(
        f"{E.search} <b>Пошук постів</b>\n\n"
        "Надішліть текст, ключові слова або ID поста чи повідомлення.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Скасувати",
                        callback_data="ps_cancel",
                        icon_custom_emoji_id=Icon.cancel,
                    )
                ]
            ]
        ),
    )


@router.message(F.text == Main.search_posts, ~StateFilter(PostCreation, PostSearch))
async def search_posts_entry(message: types.Message, state: FSMContext) -> None:
    await search_start(message, state)


@router.callback_query(F.data == "ps_cancel")
async def search_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Пошук скасовано.")
    await callback.answer()


@router.callback_query(F.data == "ps_new")
async def search_new(callback: types.CallbackQuery, state: FSMContext) -> None:
    await search_start(callback.message, state)
    await callback.answer()


@router.message(PostSearch.waiting_query, F.text)
async def search_query(message: types.Message, state: FSMContext) -> None:
    query = (message.text or "").strip()
    if not query:
        await message.answer("Надішліть текст або ID.")
        return
    await state.update_data(
        search_query=query,
        search_channel_id=None,
        search_folder_id=None,
        search_period="all",
    )
    await state.set_state(None)
    await _show_results(message, state, edit=False)


@router.callback_query(F.data == "ps_channels")
async def search_channels(callback: types.CallbackQuery, state: FSMContext) -> None:
    rows = [
        [
            InlineKeyboardButton(
                text="Усі канали",
                callback_data="ps_setch_0",
            )
        ]
    ]
    for channel in get_all_channels(callback.from_user.id)[:24]:
        title = (channel[2] or "Канал")[:32]
        rows.append(
            [
                InlineKeyboardButton(
                    text=title,
                    callback_data=f"ps_setch_{channel[1]}",
                )
            ]
        )
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(F.data.startswith("ps_setch_"))
async def search_set_channel(callback: types.CallbackQuery, state: FSMContext) -> None:
    raw = int(callback.data.removeprefix("ps_setch_"))
    await state.update_data(search_channel_id=raw or None)
    await _show_results(callback.message, state, edit=True)
    await callback.answer()


@router.callback_query(F.data == "ps_folders")
async def search_folders(callback: types.CallbackQuery, state: FSMContext) -> None:
    rows = [[InlineKeyboardButton(text="Усі папки", callback_data="ps_setfd_0")]]
    for folder in get_user_folders(callback.from_user.id):
        rows.append(
            [
                InlineKeyboardButton(
                    text=(folder[1] or "Папка")[:32],
                    callback_data=f"ps_setfd_{folder[0]}",
                )
            ]
        )
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(F.data.startswith("ps_setfd_"))
async def search_set_folder(callback: types.CallbackQuery, state: FSMContext) -> None:
    raw = int(callback.data.removeprefix("ps_setfd_"))
    await state.update_data(search_folder_id=raw or None)
    await _show_results(callback.message, state, edit=True)
    await callback.answer()


@router.callback_query(F.data == "ps_dates")
async def search_dates(callback: types.CallbackQuery) -> None:
    await callback.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Увесь час", callback_data="ps_setdt_all"),
                    InlineKeyboardButton(text="Сьогодні", callback_data="ps_setdt_1"),
                ],
                [
                    InlineKeyboardButton(text="7 днів", callback_data="ps_setdt_7"),
                    InlineKeyboardButton(text="30 днів", callback_data="ps_setdt_30"),
                ],
            ]
        )
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ps_setdt_"))
async def search_set_date(callback: types.CallbackQuery, state: FSMContext) -> None:
    await state.update_data(search_period=callback.data.removeprefix("ps_setdt_"))
    await _show_results(callback.message, state, edit=True)
    await callback.answer()
