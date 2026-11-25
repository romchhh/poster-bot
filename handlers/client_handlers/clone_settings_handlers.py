"""Єдині «Налаштування каналу» для scope копіювання (канал / папка) та екранів з налаштувань."""
from __future__ import annotations

from utils.ui_emoji import E, Icon
import html

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from database_functions.auto_signatures_db import get_auto_signature
from database_functions.channels_db import get_all_channels, get_channel_by_id, get_user_channel_role, telegram_tme_chat_url
from database_functions.channel_start_emoji_db import get_channel_start_emoji
from database_functions.clone_db import (
    add_copy_blacklist_word,
    clear_copy_blacklist,
    get_copy_blacklist,
    get_copy_blacklist_word_by_id,
    get_copy_scope_settings,
    remove_copy_blacklist_word,
    toggle_copy_ai,
    toggle_copy_bell,
    toggle_copy_pause,
)
from database_functions.copy_mirror_db import SCOPE_CHANNEL, SCOPE_FOLDER, list_copy_donors, scope_has_copy_mirror_config
from database_functions.folders_db import get_folder_by_id, get_user_folders
from database_functions.watermark_db import has_watermark
from keyboards.client_keyboards.copy_mirror_keyboards import get_copy_manage_keyboard
from keyboards.client_keyboards.copy_settings_keyboards import (
    get_channel_scope_settings_keyboard,
    get_copy_blacklist_add_keyboard,
    get_copy_blacklist_keyboard,
)
from states.client_states import CopyChannelSettings
from utils.copy_utils.copy_mirror_format import format_manage_html
from utils.copy_utils.mirror_flow import folder_id_cell

router = Router()


def _channel_folder_id_from_row(channel_info: tuple) -> int | None:
    if not channel_info or len(channel_info) < 12:
        return None
    fid = channel_info[11]
    return int(fid) if fid is not None else None


def _parse_st_sid_back(data: str, prefix: str) -> tuple[str, str, str] | None:
    rest = data.removeprefix(prefix)
    parts = rest.split(":", 2)
    if len(parts) < 3:
        return None
    return parts[0], parts[1], parts[2]


def _scope_type_from_st(st: str) -> str:
    return SCOPE_FOLDER if st == "f" else SCOPE_CHANNEL


def _user_owns_scope(user_id: int, st: str, sid: str) -> bool:
    scope_id = int(sid)
    if st == "f":
        return any(f[0] == scope_id for f in get_user_folders(user_id))
    return any(c[1] == scope_id for c in get_all_channels(user_id=user_id, only_active=True))


def _summary_html(user_id: int, st: str, sid: str) -> str:
    settings = get_copy_scope_settings(_scope_type_from_st(st), sid)
    bell = settings.get("bell", True)
    paused = settings.get("paused", False)
    ai = settings.get("ai_rewrite", False)

    bell_line = f"🔔 Звук: {'увімкнений' if bell else 'вимкнений'}"

    if st == "c":
        ch_id = int(sid)
        channel_info = get_channel_by_id(ch_id, user_id=user_id)
        if not channel_info:
            return "⚠️ Канал не знайдено."
        channel_title = channel_info[2]
        channel_link = channel_info[4] if len(channel_info) > 4 and channel_info[4] else "#"
        chat_type = (
            channel_info[5]
            if channel_info and len(channel_info) > 5 and channel_info[5]
            else "channel"
        )
        is_channel = chat_type == "channel"
        role = get_user_channel_role(user_id, ch_id) or "admin"
        role_label = "Власник" if role == "owner" else "Редактор"
        auto_signature = get_auto_signature(ch_id)
        auto_sig_status = "✅ Налаштовано" if auto_signature else "❌ Не налаштовано"
        emoji_id, emoji_text = get_channel_start_emoji(ch_id)
        if emoji_id and emoji_text:
            emoji_disp = f"<tg-emoji emoji-id=\"{emoji_id}\">{emoji_text}</tg-emoji>"
            emoji_status = f"✅ {emoji_disp}"
        else:
            emoji_status = "❌ Не налаштовано"
        head = f'{E.settings} <b>НАЛАШТУВАННЯ КАНАЛУ</b>'
        subtitle = f'{E.settings} <b>Стан опцій нижче</b>'
        block = (
            f"{head}\n\n"
            f'{E.channel} {"Канал" if is_channel else "Група"}:'
            f' <a href="{channel_link}">{html.escape(channel_title)}</a>\n\n'
            f"{subtitle}\n\n"
            f"{E.user} <b>Ваша роль:</b> {role_label}\n\n"
            f"{E.art} <b>Емодзі на початку:</b> {emoji_status}\n\n"
            f"{E.sign} <b>Автопідпис:</b> {auto_sig_status}\n\n"
            f"{bell_line}\n"
            f"{'⏸' if not paused else '▶️'} <b>Копіювання:</b> {'активне' if not paused else 'призупинено'}\n\n"
            f"{'✅' if ai else '❌'} <b>ШІ переробка тексту</b>"
        )
        folder_id = _channel_folder_id_from_row(channel_info)
        if folder_id:
            finfo = get_folder_by_id(folder_id)
            fname = html.escape(finfo[1]) if finfo else "—"
            block += (
                f'\n{E.folder} <b>Папка:</b> {fname}'
            )
        else:
            block += (
                f'\n{E.folder} <b>Папка:</b> <i>не в папці</i>'
            )
        return block

    # Папка
    folder_name = None
    for f in get_user_folders(user_id):
        if f[0] == int(sid):
            folder_name = f[1] or str(sid)
            break
    fn = html.escape(folder_name or str(sid))
    return (
        f'{E.settings} <b>НАЛАШТУВАННЯ КАНАЛУ</b>'
        f" (папка)\n\n"
        f"{E.folder} Папка: <b>{fn}</b>\n\n"
        f"{bell_line}\n"
        f"{'⏸' if not paused else '▶️'} <b>Копіювання:</b> {'активне' if not paused else 'призупинено'}\n\n"
        f"{'✅' if ai else '❌'} <b>ШІ переробка тексту</b>\n\n"
        "<i>Емодзі, автопідпис і вотермарки — у меню каналу в налаштуваннях SkyPost.</i>"
    )


async def _show_settings(message: types.Message, user_id: int, st: str, sid: str, back: str) -> None:
    scope_t = _scope_type_from_st(st)
    sid_i = int(sid)
    settings = get_copy_scope_settings(scope_t, sid)

    show_pause = scope_has_copy_mirror_config(user_id, scope_t, sid_i)

    emoji_ok = autop_ok = False
    watermark_ok = False
    if st == "c":
        emoji_ok = bool(get_channel_start_emoji(int(sid))[0])
        autop_ok = bool(get_auto_signature(int(sid)))
        watermark_ok = has_watermark(user_id, sid, "manual")

    text = _summary_html(user_id, st, sid)
    kb = get_channel_scope_settings_keyboard(
        st,
        sid,
        back,
        settings,
        user_id=user_id if st == "c" else None,
        show_pause_row=show_pause,
        emoji_configured=emoji_ok,
        autopodpis_configured=autop_ok,
        watermark_configured=watermark_ok,
    )
    try:
        await message.edit_text(
            text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True
        )
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("cpy_stg:"))
async def show_channel_scope_settings_cb(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    parsed = _parse_st_sid_back(callback.data, "cpy_stg:")
    if not parsed:
        await callback.answer()
        return
    st, sid, back = parsed
    user_id = callback.from_user.id
    if not _user_owns_scope(user_id, st, sid):
        await callback.answer("❌ Немає доступу", show_alert=True)
        return
    await state.update_data(cpy_stg_st=st, cpy_stg_sid=sid, cpy_stg_back=back)
    await _show_settings(callback.message, user_id, st, sid, back)
    await callback.answer()


@router.callback_query(F.data.startswith("cpy_stbell:"))
async def toggle_bell_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    parsed = _parse_st_sid_back(callback.data, "cpy_stbell:")
    if not parsed:
        await callback.answer()
        return
    st, sid, back = parsed
    user_id = callback.from_user.id
    if not _user_owns_scope(user_id, st, sid):
        await callback.answer("❌ Немає доступу", show_alert=True)
        return
    toggle_copy_bell(_scope_type_from_st(st), sid)
    await _show_settings(callback.message, user_id, st, sid, back)
    await callback.answer()


@router.callback_query(F.data.startswith("cpy_stpause:"))
async def toggle_pause_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    parsed = _parse_st_sid_back(callback.data, "cpy_stpause:")
    if not parsed:
        await callback.answer()
        return
    st, sid, back = parsed
    user_id = callback.from_user.id
    if not _user_owns_scope(user_id, st, sid):
        await callback.answer("❌ Немає доступу", show_alert=True)
        return
    if not scope_has_copy_mirror_config(user_id, _scope_type_from_st(st), int(sid)):
        await callback.answer("⚠️ Копіювання ще не налаштовано", show_alert=True)
        return
    toggle_copy_pause(_scope_type_from_st(st), sid)
    await _show_settings(callback.message, user_id, st, sid, back)
    await callback.answer()


@router.callback_query(F.data.startswith("cpy_stai:"))
async def toggle_ai_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    parsed = _parse_st_sid_back(callback.data, "cpy_stai:")
    if not parsed:
        await callback.answer()
        return
    st, sid, back = parsed
    user_id = callback.from_user.id
    if not _user_owns_scope(user_id, st, sid):
        await callback.answer("❌ Немає доступу", show_alert=True)
        return
    toggle_copy_ai(_scope_type_from_st(st), sid)
    await _show_settings(callback.message, user_id, st, sid, back)
    await callback.answer()


async def _show_blacklist(
    message: types.Message, user_id: int, st: str, sid: str, back: str
) -> None:
    words = get_copy_blacklist(user_id, _scope_type_from_st(st), sid)
    kb = get_copy_blacklist_keyboard(st, sid, back, words)
    text = (
        "🚫 <b>Чорний список слів/фраз</b>\n\n"
        "Слова та фрази, які видаляються з текстів скопійованих постів.\n\n"
        f"Зараз у списку: <b>{len(words)}</b>"
    )
    try:
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("cpy_stbl:"))
async def open_blacklist_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    parsed = _parse_st_sid_back(callback.data, "cpy_stbl:")
    if not parsed:
        await callback.answer()
        return
    st, sid, back = parsed
    await _show_blacklist(callback.message, callback.from_user.id, st, sid, back)
    await callback.answer()


@router.callback_query(F.data.startswith("cpy_stbladd:"))
async def blacklist_add_start_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    parsed = _parse_st_sid_back(callback.data, "cpy_stbladd:")
    if not parsed:
        await callback.answer()
        return
    st, sid, back = parsed
    await state.set_state(CopyChannelSettings.waiting_for_blacklist_word)
    await state.update_data(cpy_stg_st=st, cpy_stg_sid=sid, cpy_stg_back=back)
    kb = get_copy_blacklist_add_keyboard(st, sid, back)
    await callback.message.edit_text(
        "➕ <b>Додавання слова/фрази в чорний список</b>\n\n"
        "Введіть слово або фразу:",
        reply_markup=kb,
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(StateFilter(CopyChannelSettings.waiting_for_blacklist_word))
async def blacklist_add_word_msg(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    st = data.get("cpy_stg_st", "c")
    sid = data.get("cpy_stg_sid", "")
    back = data.get("cpy_stg_back", "cpy")
    word = (message.text or "").strip()
    user_id = message.from_user.id
    await state.clear()
    if not word:
        await message.answer("❌ Слово не може бути порожнім.")
        return
    ok = add_copy_blacklist_word(user_id, _scope_type_from_st(st), sid, word)
    if ok:
        await message.answer(
            f"✅ Слово <b>{html.escape(word)}</b> додано.", parse_mode="HTML"
        )
    else:
        await message.answer("ℹ️ Це слово вже є у списку.")
    words = get_copy_blacklist(user_id, _scope_type_from_st(st), sid)
    kb = get_copy_blacklist_keyboard(st, sid, back, words)
    await message.answer(
        f"🚫 <b>Чорний список слів/фраз</b>\n\nЗараз у списку: <b>{len(words)}</b>",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("cpy_stblrm:"))
async def blacklist_remove_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.removeprefix("cpy_stblrm:").split(":", 3)
    if len(parts) < 4:
        await callback.answer()
        return
    word_id, st, sid, back = int(parts[0]), parts[1], parts[2], parts[3]
    word = get_copy_blacklist_word_by_id(word_id)
    remove_copy_blacklist_word(word_id)
    if word:
        await callback.answer(f"✅ «{word}» видалено")
    await _show_blacklist(callback.message, callback.from_user.id, st, sid, back)


@router.callback_query(F.data.startswith("cpy_stblclr:"))
async def blacklist_clear_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    parsed = _parse_st_sid_back(callback.data, "cpy_stblclr:")
    if not parsed:
        await callback.answer()
        return
    st, sid, back = parsed
    clear_copy_blacklist(callback.from_user.id, _scope_type_from_st(st), sid)
    await callback.answer("✅ Список очищено")
    await _show_blacklist(callback.message, callback.from_user.id, st, sid, back)


def _parse_copy_donor_callback(data: str) -> tuple[str, int, int] | None:
    if data.startswith("cpy_df:"):
        rest, scope_type = data.removeprefix("cpy_df:"), SCOPE_FOLDER
    elif data.startswith("cpy_dc:"):
        rest, scope_type = data.removeprefix("cpy_dc:"), SCOPE_CHANNEL
    else:
        return None
    try:
        sid_s, did_s = rest.rsplit(":", 1)
        return scope_type, int(sid_s), int(did_s)
    except ValueError:
        return None


@router.callback_query((F.data.startswith("cpy_df:")) | (F.data.startswith("cpy_dc:")))
async def copy_donor_click_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    parsed = _parse_copy_donor_callback(callback.data or "")
    if not parsed:
        await callback.answer()
        return
    scope_type, scope_id, donor_channel_id = parsed
    user_id = callback.from_user.id
    st = "f" if scope_type == SCOPE_FOLDER else "c"
    sid = str(scope_id)

    if st == "f":
        owns = any(f[0] == scope_id for f in get_user_folders(user_id))
    else:
        owns = any(c[1] == scope_id for c in get_all_channels(user_id=user_id, only_active=True))
    if not owns:
        await callback.answer("❌ Немає доступу", show_alert=True)
        return

    donors = list_copy_donors(user_id, scope_type, scope_id)
    row_d = next((d for d in donors if int(d[0]) == int(donor_channel_id)), None)
    if not row_d:
        await callback.answer("Донор не знайдено", show_alert=True)
        return

    donor_title = html.escape((row_d[1] or str(donor_channel_id)).strip())
    donor_url = telegram_tme_chat_url(donor_channel_id)

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="Відкрити в Telegram", url=donor_url, icon_custom_emoji_id=Icon.link)],
    ]
    if st == "c":
        rows.append(
            [
                InlineKeyboardButton(
                    text="Налаштування каналу",
                    callback_data=f"cpy_stg:{st}:{sid}:cpy",
                icon_custom_emoji_id=Icon.settings,
            )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="Назад", callback_data=f"cpy_mg:{st}:{scope_id}", icon_custom_emoji_id=Icon.back)]
    )
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await callback.message.edit_text(
        f"{E.channel} <b>Донор:</b> <a href=\"{html.escape(donor_url, quote=True)}\">{donor_title}</a>\n"
        f"<code>id {donor_channel_id}</code>",
        reply_markup=kb,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cpy_mg:"))
async def copy_manage_back_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    raw = (callback.data or "").removeprefix("cpy_mg:")
    try:
        st, sid_s = raw.split(":", 1)
        scope_id = int(sid_s)
    except ValueError:
        await callback.answer()
        return
    scope_type = SCOPE_FOLDER if st == "f" else SCOPE_CHANNEL
    user_id = callback.from_user.id
    if st == "f":
        owns = any(f[0] == scope_id for f in get_user_folders(user_id))
    else:
        owns = any(c[1] == scope_id for c in get_all_channels(user_id=user_id, only_active=True))
    if not owns:
        await callback.answer("❌ Немає доступу", show_alert=True)
        return
    txt = format_manage_html(user_id, scope_type, scope_id)
    try:
        await callback.message.edit_text(
            text=txt,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=get_copy_manage_keyboard(
                scope_type, scope_id, user_id=user_id
            ),
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


async def navigate_copy_unified_for_channel(
    message: types.Message, user_id: int, channel_id: int
) -> None:
    """Із підменю (емодзі, автопідпис…) повернути єдиний екран налаштувань, відкритий із «Копіювання»."""
    cid = str(channel_id)
    owns = any(
        c[1] == channel_id for c in get_all_channels(user_id=user_id, only_active=True)
    )
    if not owns:
        return
    await _show_settings(message, user_id, "c", cid, "cpy")

