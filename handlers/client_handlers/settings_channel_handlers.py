"""Settings: folders, channels, editors, watermark, start emoji."""

from utils.ui_emoji import E, Icon
from aiogram import Router, F, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from app.runtime import bot
import html
import re
from keyboards.client_keyboards.settings_keyboards import (
    get_back_to_settings_keyboard,
    get_channel_settings_keyboard,
    get_channel_start_emoji_keyboard,
    get_settings_channels_grid_keyboard,
    get_settings_channels_intro_keyboard,
    get_settings_folder_panel_keyboard,
    get_settings_folders_manage_keyboard,
)
from database_functions.client_db import (
    get_user_language,
    resolve_registered_user_id_from_input,
)
from database_functions.channels_db import (
    add_channel_editor,
    get_all_channels,
    get_channel_by_id,
    get_channel_members,
    get_channels_by_folder,
    get_channels_without_folder,
    remove_channel_admin,
    get_user_channel_role,
    set_channel_folder,
)
from database_functions.auto_signatures_db import get_auto_signature
from database_functions.channel_start_emoji_db import (
    get_channel_start_emoji,
    remove_channel_start_emoji,
    save_channel_start_emoji,
)
from database_functions.folders_db import (
    add_folder,
    check_folder_exists,
    delete_folder,
    get_folder_by_id,
    get_user_folders,
    update_channels_count,
    update_folder_name,
)
from keyboards.client_keyboards.folder_keyboards import (
    get_channel_settings_folder_move_keyboard,
)
from states.client_states import (
    AddChannelStates,
    ChannelEditorsSettings,
    ChannelStartEmojiSettings,
    SettingsFolders,
)
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from handlers.client_handlers.clone_settings_handlers import (
    navigate_copy_unified_for_channel,
)

router = Router()


async def _edit_channel_admins_screen(
    message: types.Message, channel_id: int, user_id: int
):
    payload = _channel_editors_screen_payload(channel_id, user_id)
    if not payload:
        return False
    text, keyboard = payload
    await message.edit_text(
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    return True


async def _finalize_channel_editor_added(
    channel_id: int,
    target_id: int,
    actor_id: int,
    prompt_chat_id: int,
    prompt_message_id: int,
    *,
    fallback_answer_chat_id: int | None = None,
    delete_user_message: tuple[int, int] | None = None,
    delete_confirm_message: tuple[int, int] | None = None,
) -> None:
    """Повідомлення новому редактору та оновлення екрана «Редактори»."""
    ch = get_channel_by_id(channel_id)
    channel_title_plain = html.escape(ch[2]) if ch else "Канал"
    channel_link = ch[4] if ch and len(ch) > 4 and ch[4] else "#"
    chat_type = ch[5] if ch and len(ch) > 5 and ch[5] else "channel"
    chat_word = "каналу" if chat_type == "channel" else "групи"
    try:
        await bot.send_message(
            target_id,
            f'✅ Вас додано як <b>редактора {chat_word}</b> <a href="{channel_link}">{channel_title_plain}</a> у SkyPost.\n\nВідкрийте «Налаштування» → канали, щоб керувати цим чатом.',
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:
        pass
    if delete_user_message:
        dc, mid = delete_user_message
        try:
            await bot.delete_message(chat_id=dc, message_id=mid)
        except Exception:
            pass
    if delete_confirm_message:
        cc, mm = delete_confirm_message
        try:
            await bot.delete_message(chat_id=cc, message_id=mm)
        except Exception:
            pass
    payload = _channel_editors_screen_payload(channel_id, actor_id)
    if payload:
        text, keyboard = payload
        try:
            await bot.edit_message_text(
                chat_id=prompt_chat_id,
                message_id=prompt_message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        except TelegramBadRequest:
            if fallback_answer_chat_id is not None:
                await bot.send_message(
                    fallback_answer_chat_id,
                    f"✅ Користувача <code>{target_id}</code> додано як редактора.",
                    parse_mode="HTML",
                )
    elif fallback_answer_chat_id is not None:
        await bot.send_message(
            fallback_answer_chat_id, "✅ Редактора додано.", parse_mode="HTML"
        )


@router.callback_query(F.data == "settings_channels")
async def channels_settings(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    folders = get_user_folders(user_id)
    channels_wo = get_channels_without_folder(user_id)
    user_channels = get_all_channels(user_id)
    if not user_channels:
        await callback.message.edit_text(
            text=f'{E.channel} <b>Канали та групи</b>\n\nПоки немає підключених каналів. Додайте канал через головне меню.',
            parse_mode="HTML",
            reply_markup=get_back_to_settings_keyboard(),
        )
        await callback.answer()
        return
    header = f'{E.channel} <b>Канали та групи</b>\n\nПапки → усі чати всередині. Окремі канали без папки — нижче. Внизу — повний список двома колонками (канали · групи).'
    await callback.message.edit_text(
        text=header,
        parse_mode="HTML",
        reply_markup=get_settings_channels_intro_keyboard(folders, channels_wo),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings_folder_channels:"))
async def settings_open_folder_channels(
    callback: types.CallbackQuery, state: FSMContext
):
    folder_id = int(callback.data.split(":")[1])
    channels = get_channels_by_folder(folder_id, only_active=True)
    if not channels:
        await callback.answer("У цій папці ще немає каналів", show_alert=True)
        return
    from database_functions.folders_db import get_folder_by_id

    finfo = get_folder_by_id(folder_id)
    folder_name = html.escape(finfo[1]) if finfo else ""
    header = f'{E.folder} <b>Папка:</b> {folder_name}\n\nОберіть канал або групу:'
    await callback.message.edit_text(
        text=header,
        parse_mode="HTML",
        reply_markup=get_settings_channels_grid_keyboard(channels, "settings_channels"),
    )
    await callback.answer()


@router.callback_query(F.data == "settings_channels_flat")
async def settings_channels_flat(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    channels = get_all_channels(user_id)
    if not channels:
        await callback.answer("Немає каналів", show_alert=True)
        return
    header = f'{E.channel} <b>Усі канали та групи</b>\n\nЗліва канали, справа групи.'
    await callback.message.edit_text(
        text=header,
        parse_mode="HTML",
        reply_markup=get_settings_channels_grid_keyboard(channels, "settings_channels"),
    )
    await callback.answer()


@router.callback_query(F.data == "settings_folders_manage")
async def settings_folders_manage(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    folders = get_user_folders(user_id)
    text = f'{E.folder} <b>Мої папки</b>\n\nСтворюйте папки та групуйте канали для швидкого доступу.'
    await callback.message.edit_text(
        text=text,
        parse_mode="HTML",
        reply_markup=get_settings_folders_manage_keyboard(folders),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings_folder_panel:"))
async def settings_folder_panel(callback: types.CallbackQuery, state: FSMContext):
    folder_id = int(callback.data.split(":")[1])
    from database_functions.folders_db import get_folder_by_id

    finfo = get_folder_by_id(folder_id)
    if not finfo:
        await callback.answer("Папку не знайдено", show_alert=True)
        return
    name = html.escape(finfo[1])
    cnt = finfo[5] if len(finfo) > 5 else 0
    text = f'{E.folder} <b>{name}</b>\n\nКаналів у папці: <b>{cnt}</b>'
    await callback.message.edit_text(
        text=text,
        parse_mode="HTML",
        reply_markup=get_settings_folder_panel_keyboard(folder_id),
    )
    await callback.answer()


@router.callback_query(F.data == "settings_folder_create")
async def settings_folder_create_start(
    callback: types.CallbackQuery, state: FSMContext
):
    await callback.message.edit_text(
        text="Введіть назву нової папки (до 80 символів):",
        reply_markup=get_back_to_settings_keyboard(),
    )
    await state.set_state(SettingsFolders.waiting_new_folder_name)
    await callback.answer()


@router.message(SettingsFolders.waiting_new_folder_name)
async def settings_folder_create_receive(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    name = (message.text or "").strip()
    if not name or len(name) > 80:
        await message.answer("Назва не може бути порожньою або довшою за 80 символів.")
        return
    if check_folder_exists(name, user_id):
        await message.answer("Папка з такою назвою вже є.")
        return
    fid = add_folder(name, user_id)
    if not fid:
        await message.answer("Не вдалося створити папку.")
        return
    await state.clear()
    folders = get_user_folders(user_id)
    await message.answer(
        "✅ Папку створено.", reply_markup=get_settings_folders_manage_keyboard(folders)
    )


@router.callback_query(F.data.startswith("settings_folder_rename:"))
async def settings_folder_rename_start(
    callback: types.CallbackQuery, state: FSMContext
):
    folder_id = int(callback.data.split(":")[1])
    await state.update_data(rename_folder_id=folder_id)
    await callback.message.edit_text(
        text="Введіть нову назву папки:", reply_markup=get_back_to_settings_keyboard()
    )
    await state.set_state(SettingsFolders.waiting_rename_folder)
    await callback.answer()


@router.message(SettingsFolders.waiting_rename_folder)
async def settings_folder_rename_receive(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    folder_id = data.get("rename_folder_id")
    name = (message.text or "").strip()
    if not folder_id or not name or len(name) > 80:
        await message.answer("Некоректні дані. Почніть з меню «Мої папки».")
        await state.clear()
        return
    if check_folder_exists(name, user_id):
        await message.answer("Папка з такою назвою вже існує.")
        return
    update_folder_name(folder_id, name)
    from database_functions.folders_db import update_channels_count

    update_channels_count(folder_id)
    await state.clear()
    folders = get_user_folders(user_id)
    await message.answer(
        "✅ Назву оновлено.", reply_markup=get_settings_folders_manage_keyboard(folders)
    )


@router.callback_query(F.data.startswith("settings_folder_delete:"))
async def settings_folder_delete(callback: types.CallbackQuery, state: FSMContext):
    folder_id = int(callback.data.split(":")[1])
    from database_functions.channels_db import remove_channels_from_folder

    remove_channels_from_folder(folder_id)
    delete_folder(folder_id)
    from database_functions.folders_db import update_channels_count

    update_channels_count(folder_id)
    user_id = callback.from_user.id
    folders = get_user_folders(user_id)
    await callback.message.edit_text(
        text=f'{E.folder} <b>Мої папки</b>\n\nПапку прибрано. Канали залишилися без цієї папки.',
        parse_mode="HTML",
        reply_markup=get_settings_folders_manage_keyboard(folders),
    )
    await callback.answer()


@router.callback_query(
    F.data.in_(
        [
            "header_channels",
            "header_groups",
            "no_channels",
            "empty_header",
            "empty_button",
        ]
    )
)
async def ignore_header_clicks(callback: types.CallbackQuery):
    await callback.answer()


def _parse_trailing_channel_id(callback_data: str, prefix: str) -> int | None:
    if not callback_data.startswith(prefix):
        return None
    tail = callback_data[len(prefix) :]
    try:
        return int(tail)
    except ValueError:
        return None


async def _show_channel_settings_screen(
    message: types.Message, user_id: int, channel_id: int
) -> bool:
    channel_info = get_channel_by_id(channel_id, user_id=user_id)
    if not channel_info:
        return False
    channel_title = channel_info[2]
    channel_link = channel_info[4] if len(channel_info) > 4 and channel_info[4] else "#"
    escaped_channel_title = html.escape(channel_title)
    chat_type = (
        channel_info[5]
        if channel_info and len(channel_info) > 5 and channel_info[5]
        else "channel"
    )
    is_channel = chat_type == "channel"
    role = get_user_channel_role(user_id, channel_id) or "admin"
    role_label = "Власник" if role == "owner" else "Редактор"
    auto_signature = get_auto_signature(channel_id)
    auto_sig_status = "✅ Налаштовано" if auto_signature else "❌ Не налаштовано"
    emoji_id, emoji_text = get_channel_start_emoji(channel_id)
    if emoji_id and emoji_text:
        emoji_disp = f'<tg-emoji emoji-id="{emoji_id}">{emoji_text}</tg-emoji>'
        emoji_status = f"✅ {emoji_disp}"
    else:
        emoji_status = "❌ Не налаштовано"
    settings_text = f"""{E.settings} <b>НАЛАШТУВАННЯ {('КАНАЛУ' if is_channel else 'ГРУПИ')}</b>\n\n{E.channel} {('Канал' if is_channel else 'Група')}: <a href="{channel_link}">{escaped_channel_title}</a>\n\n{E.settings} <b>Оберіть дію в меню нижче</b>\n\n{E.user} <b>Ваша роль:</b> {role_label}\n\n{E.art} <b>Емодзі на початку:</b> {emoji_status}\n\n{E.sign} <b>Автопідпис:</b> {auto_sig_status}"""
    folder_id = _channel_folder_id_from_row(channel_info)
    if folder_id:
        finfo = get_folder_by_id(folder_id)
        fname = html.escape(finfo[1]) if finfo else "—"
        folder_line = f'\n{E.folder} <b>Папка:</b> {fname}'
    else:
        folder_line = f'\n{E.folder} <b>Папка:</b> <i>не в папці</i>'
    settings_text = (
        settings_text
        + folder_line
        + "\n\n<i>⚙️ Налаштування каналу — звук, копії, ШІ, емодзі, автопідпис, список слів, вотермарки.</i>"
    )
    keyboard = get_channel_settings_keyboard(
        channel_id, is_channel, channel_in_folder=bool(folder_id)
    )
    await message.edit_text(
        text=settings_text,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
    return True


@router.callback_query(F.data.startswith("channel_settings_"))
async def channel_settings_menu(callback: types.CallbackQuery, state: FSMContext):
    channel_id = _parse_trailing_channel_id(callback.data, "channel_settings_")
    if channel_id is None:
        await callback.answer("❌ Некоректні дані")
        return
    user_id = callback.from_user.id
    user_language = get_user_language(user_id) or "uk"
    ok = await _show_channel_settings_screen(callback.message, user_id, channel_id)
    if not ok:
        error_texts = {"uk": "❌ Чат не знайдено"}
        await callback.answer(error_texts.get(user_language, error_texts["uk"]))
        return
    await callback.answer()


@router.callback_query(F.data.startswith("channel_folder_flow:"))
async def channel_folder_flow_start(callback: types.CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split(":", 1)[1])
    user_id = callback.from_user.id
    ch = get_channel_by_id(channel_id, user_id=user_id)
    if not ch:
        await callback.answer("❌ Чат не знайдено", show_alert=True)
        return
    is_ch = (ch[5] or "channel") == "channel"
    title = html.escape(ch[2])
    link = ch[4] if len(ch) > 4 and ch[4] else "#"
    chat_word = "канал" if is_ch else "групу"
    await callback.message.edit_text(
        text=f"""{E.folder} <b>Папка для {chat_word}</b>\n\n{('Канал' if is_ch else 'Група')}: <a href="{link}">{title}</a>\n\nОберіть папку, створіть нову або приберіть з поточної папки.""",
        parse_mode="HTML",
        reply_markup=get_channel_settings_folder_move_keyboard(user_id, channel_id),
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("schf_mv:"))
async def channel_settings_move_to_folder(
    callback: types.CallbackQuery, state: FSMContext
):
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("❌ Помилка даних", show_alert=True)
        return
    folder_id = int(parts[1])
    channel_id = int(parts[2])
    user_id = callback.from_user.id
    ch = get_channel_by_id(channel_id, user_id=user_id)
    if not ch:
        await callback.answer("❌ Чат не знайдено", show_alert=True)
        return
    finf = get_folder_by_id(folder_id)
    if not finf or finf[2] != user_id:
        await callback.answer("❌ Папку не знайдено", show_alert=True)
        return
    old_folder = _channel_folder_id_from_row(ch)
    set_channel_folder(channel_id, folder_id)
    if old_folder and old_folder != folder_id:
        update_channels_count(old_folder)
    if folder_id:
        update_channels_count(folder_id)
    await _show_channel_settings_screen(callback.message, user_id, channel_id)
    await callback.answer("✅ Папку оновлено")


@router.callback_query(F.data.startswith("schf_nop:"))
async def channel_settings_clear_folder(
    callback: types.CallbackQuery, state: FSMContext
):
    channel_id = int(callback.data.split(":", 1)[1])
    user_id = callback.from_user.id
    ch = get_channel_by_id(channel_id, user_id=user_id)
    if not ch:
        await callback.answer("❌ Чат не знайдено", show_alert=True)
        return
    old_folder = _channel_folder_id_from_row(ch)
    if old_folder:
        set_channel_folder(channel_id, None)
        update_channels_count(old_folder)
    await _show_channel_settings_screen(callback.message, user_id, channel_id)
    await callback.answer("✅ Папку прибрано")


@router.callback_query(F.data.startswith("schf_new:"))
async def channel_settings_create_folder_start(
    callback: types.CallbackQuery, state: FSMContext
):
    channel_id = int(callback.data.split(":", 1)[1])
    user_id = callback.from_user.id
    if not get_channel_by_id(channel_id, user_id=user_id):
        await callback.answer("❌ Чат не знайдено", show_alert=True)
        return
    await state.update_data(move_channel_id=channel_id)
    await callback.message.edit_text(
        text=f"{E.folder} <b>Створення нової папки</b>\n\nВведіть назву нової папки (до 50 символів):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Скасувати",
                        callback_data=f"schf_cancel_create:{channel_id}",
                    icon_custom_emoji_id=Icon.cancel,
                )
                ]
            ]
        ),
    )
    await state.set_state(AddChannelStates.waiting_for_new_folder_name)
    await callback.answer()


@router.callback_query(F.data.startswith("schf_cancel_create:"))
async def channel_settings_create_folder_cancel(
    callback: types.CallbackQuery, state: FSMContext
):
    channel_id = int(callback.data.split(":", 1)[1])
    user_id = callback.from_user.id
    if not get_channel_by_id(channel_id, user_id=user_id):
        await state.clear()
        await callback.answer("❌ Чат не знайдено", show_alert=True)
        return
    await state.clear()
    ch = get_channel_by_id(channel_id, user_id=user_id)
    is_ch = (ch[5] or "channel") == "channel"
    title = html.escape(ch[2])
    link = ch[4] if len(ch) > 4 and ch[4] else "#"
    chat_word = "канал" if is_ch else "групу"
    await callback.message.edit_text(
        text=f"""{E.folder} <b>Папка для {chat_word}</b>\n\n{('Канал' if is_ch else 'Група')}: <a href="{link}">{title}</a>\n\nОберіть папку, створіть нову або приберіть з поточної папки.""",
        parse_mode="HTML",
        reply_markup=get_channel_settings_folder_move_keyboard(user_id, channel_id),
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("channel_admins_list_"))
async def channel_admins_list_menu(callback: types.CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.removeprefix("channel_admins_list_"))
    user_id = callback.from_user.id
    ok = await _edit_channel_admins_screen(callback.message, channel_id, user_id)
    if not ok:
        await callback.answer("❌ Чат не знайдено")
        return
    await callback.answer()


@router.callback_query(F.data.startswith("ch_wm|"))
async def channel_watermark_open(callback: types.CallbackQuery, state: FSMContext):
    from handlers.client_handlers.watermark_handlers import watermark_nav_back
    from database_functions.watermark_db import has_watermark
    from keyboards.client_keyboards.watermark_keyboards import (
        get_watermark_management_keyboard,
    )

    raw = callback.data or ""
    tail = raw.removeprefix("ch_wm|")
    tid1, sep, tid2 = tail.partition("|")
    try:
        channel_id = int(tid1.strip() if tid1 else "")
    except ValueError:
        await callback.answer("❌ Помилка")
        return
    folder_id = 1
    if sep and tid2.strip() != "":
        try:
            folder_id = int(tid2.strip())
        except ValueError:
            folder_id = 1
    user_id = callback.from_user.id
    if not get_channel_by_id(channel_id, user_id=user_id):
        await callback.answer("❌ Чат не знайдено")
        return
    cid_str = str(channel_id)
    watermark_exists = has_watermark(user_id, cid_str, "manual")
    back_cb = watermark_nav_back(cid_str, folder_id)
    keyboard = get_watermark_management_keyboard(
        cid_str, "manual", folder_id, watermark_exists, back_callback=back_cb
    )
    if watermark_exists:
        text = f"{E.water} <b>Водяний знак каналу</b>\n\n✅ Активний — застосовується до <b>фото</b> у постах каналу і до копій з донорів.\n\nОберіть дію:"
    else:
        text = f"{E.water} <b>Водяний знак каналу</b>\n\n❌ Не встановлено\n\nВін використовується і для ваших постів у каналі, і для зображень у скопійованих постах."
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("cse|"))
async def channel_start_emoji_menu(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("|")
    if len(parts) < 3:
        await callback.answer("❌ Помилка")
        return
    op, channel_id_s = (parts[1], parts[2])
    channel_id = int(channel_id_s)
    from_copy = len(parts) > 3 and parts[3] == "cpy"
    user_id = callback.from_user.id
    if op == "q":
        if from_copy:
            await navigate_copy_unified_for_channel(
                callback.message, user_id, channel_id
            )
        else:
            await state.clear()
            if not await _show_channel_settings_screen(
                callback.message, user_id, channel_id
            ):
                await callback.answer("❌ Чат не знайдено")
                return
        await callback.answer()
        return
    channel_info = get_channel_by_id(channel_id, user_id=user_id)
    if not channel_info:
        await callback.answer("❌ Чат не знайдено")
        return
    channel_title = html.escape(channel_info[2])
    channel_link = channel_info[4] if len(channel_info) > 4 and channel_info[4] else "#"
    emoji_id, emoji_text = get_channel_start_emoji(channel_id)
    if op == "m":
        if emoji_id and emoji_text:
            emoji_display = f"<tg-emoji emoji-id='{emoji_id}'>{emoji_text}</tg-emoji>"
            body = f"{E.art} <b>Емодзі на початку поста</b>\n\n{E.channel} Канал: <a href='{channel_link}'>{channel_title}</a>\n\n🎭 Поточне емодзі: {emoji_display}\n🆔 ID: <code>{emoji_id}</code>"
        else:
            body = f"{E.art} <b>Емодзі на початку поста</b>\n\n{E.channel} Канал: <a href='{channel_link}'>{channel_title}</a>\n\n❌ Не налаштовано\n\n💡 Додайте одне преміум емодзі — воно буде на початку тексту поста."
        await callback.message.edit_text(
            text=body,
            parse_mode="HTML",
            reply_markup=get_channel_start_emoji_keyboard(
                channel_id, bool(emoji_id and emoji_text), from_copy_manage=from_copy
            ),
            disable_web_page_preview=True,
        )
        await callback.answer()
        return
    if op == "a" or op == "r":
        await state.set_state(ChannelStartEmojiSettings.waiting_for_emoji)
        await state.update_data(
            cse_channel_id=channel_id,
            cse_action="add" if op == "a" else "replace",
            cse_from_copy=from_copy,
        )
        verb = "Додавання" if op == "a" else "Заміна"
        q_cb = f"cse|q|{channel_id}|cpy" if from_copy else f"cse|q|{channel_id}"
        await callback.message.edit_text(
            f"🎭 <b>{verb} преміум емодзі</b>\n\n{E.channel} Канал: <a href='{channel_link}'>{channel_title}</a>\n\n📤 Надішліть <b>одне</b> преміум емодзі повідомленням:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Скасувати",
                            icon_custom_emoji_id=Icon.cancel,
                            callback_data=q_cb,
                        )
                    ]
                ]
            ),
        )
        await callback.answer()
        return
    if op == "x":
        remove_channel_start_emoji(channel_id)
        if from_copy:
            await navigate_copy_unified_for_channel(
                callback.message, user_id, channel_id
            )
        else:
            await _show_channel_settings_screen(callback.message, user_id, channel_id)
        await callback.answer("🗑 Емодзі видалено")
        return
    await callback.answer("❌ Невідома дія")


@router.message(StateFilter(ChannelStartEmojiSettings.waiting_for_emoji))
async def channel_start_emoji_receive(message: types.Message, state: FSMContext):
    data = await state.get_data()
    channel_id = data.get("cse_channel_id")
    action = data.get("cse_action", "add")
    from_copy = bool(data.get("cse_from_copy", False))
    if not channel_id:
        await message.answer("❌ Сесія закінчилась. Відкрийте налаштування знову.")
        await state.clear()
        return
    if not message.entities:
        await message.answer("❌ Надішліть повідомлення з преміум емодзі.")
        return
    custom_emoji = None
    emoji_text = None
    for entity in message.entities:
        if entity.type == "custom_emoji":
            custom_emoji = entity.custom_emoji_id
            start = entity.offset
            end = entity.offset + entity.length
            emoji_text = message.text[start:end]
            break
    if not custom_emoji or not emoji_text:
        await message.answer("❌ Не знайдено преміум емодзі.")
        return
    from database_functions.billing_db import can_save_emoji

    emoji_error = can_save_emoji(message.from_user.id, int(channel_id))
    if emoji_error:
        await message.answer(emoji_error)
        return
    save_channel_start_emoji(channel_id, custom_emoji, emoji_text)
    await state.clear()
    emoji_display = f"<tg-emoji emoji-id='{custom_emoji}'>{emoji_text}</tg-emoji>"
    action_text = "додано" if action == "add" else "замінено"
    await message.answer(
        f"✅ <b>Емодзі {action_text}!</b>\n\n🎭 {emoji_display}",
        parse_mode="HTML",
        reply_markup=get_channel_start_emoji_keyboard(
            channel_id, True, from_copy_manage=from_copy
        ),
    )


@router.callback_query(F.data.startswith("channel_admin_info_"))
async def channel_admin_info(callback: types.CallbackQuery):
    import re

    m = re.fullmatch("channel_admin_info_(-?\\d+)_(\\d+)", callback.data)
    if not m:
        await callback.answer("❌ Некоректні дані", show_alert=True)
        return
    channel_id = int(m.group(1))
    member_user_id = int(m.group(2))
    members = get_channel_members(channel_id)
    member = next((m for m in members if m[0] == member_user_id), None)
    if not member:
        await callback.answer("❌ Редактора не знайдено", show_alert=True)
        return
    role_label = "Власник" if member[1] == "owner" else "Редактор"
    username = member[2]
    first_name = member[3] or ""
    last_name = member[4] or ""
    full_name = f"{first_name} {last_name}".strip()
    display = username or full_name or f"ID: {member_user_id}"
    await callback.answer(f"{display}\nРоль: {role_label}", show_alert=True)


@router.callback_query(F.data.startswith("channel_rm_yes_"))
async def channel_admin_remove_confirmed(
    callback: types.CallbackQuery, state: FSMContext
):
    m = re.fullmatch("channel_rm_yes_(-?\\d+)_(\\d+)", callback.data)
    if not m:
        await callback.answer("❌ Некоректні дані", show_alert=True)
        return
    channel_id = int(m.group(1))
    admin_user_id = int(m.group(2))
    user_id = callback.from_user.id
    requester_role = get_user_channel_role(user_id, channel_id)
    if requester_role != "owner":
        await callback.answer(
            "❌ Лише власник каналу може видаляти редакторів", show_alert=True
        )
        return
    admin_role = get_user_channel_role(admin_user_id, channel_id)
    if admin_role != "admin":
        await callback.answer("❌ Можна видалити тільки редактора", show_alert=True)
        return
    removed = remove_channel_admin(channel_id, admin_user_id)
    if not removed:
        await callback.answer("❌ Не вдалося видалити редактора", show_alert=True)
        return
    await callback.answer("✅ Редактора видалено")
    await _edit_channel_admins_screen(callback.message, channel_id, user_id)


@router.callback_query(F.data.startswith("channel_admin_remove_"))
async def channel_admin_remove_ask(callback: types.CallbackQuery, state: FSMContext):
    m = re.fullmatch("channel_admin_remove_(-?\\d+)_(\\d+)", callback.data)
    if not m:
        await callback.answer("❌ Некоректні дані", show_alert=True)
        return
    channel_id = int(m.group(1))
    admin_user_id = int(m.group(2))
    user_id = callback.from_user.id
    requester_role = get_user_channel_role(user_id, channel_id)
    if requester_role != "owner":
        await callback.answer(
            "❌ Лише власник каналу може видаляти редакторів", show_alert=True
        )
        return
    admin_role = get_user_channel_role(admin_user_id, channel_id)
    if admin_role != "admin":
        await callback.answer("❌ Можна видалити тільки редактора", show_alert=True)
        return
    members = get_channel_members(channel_id)
    member = next((mem for mem in members if mem[0] == admin_user_id), None)
    if not member:
        await callback.answer("❌ Редактора не знайдено", show_alert=True)
        return
    username = member[2]
    first_name = member[3] or ""
    last_name = member[4] or ""
    full_name = f"{first_name} {last_name}".strip()
    display = html.escape(username or full_name or f"ID {admin_user_id}")
    ch = get_channel_by_id(channel_id, user_id=user_id)
    if not ch:
        await callback.answer("❌ Чат не знайдено", show_alert=True)
        return
    channel_title = html.escape(ch[2])
    channel_link = ch[4] if len(ch) > 4 and ch[4] else "#"
    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Так, прибрати з редакторів",
                    callback_data=f"channel_rm_yes_{channel_id}_{admin_user_id}",
                icon_custom_emoji_id=Icon.trash,
            )
            ],
            [
                InlineKeyboardButton(
                    text="Ні, залишити",
                    callback_data=f"channel_admins_list_{channel_id}",
                icon_custom_emoji_id=Icon.cancel,
            )
            ],
        ]
    )
    await callback.message.edit_text(
        text=f'{E.editors} <b>Підтвердження</b>\n\nПрибрати <b>{display}</b> з редакторів каналу <a href="{channel_link}">{channel_title}</a>?\n\n<i>Користувач втратить доступ до керування цим чатом у боті (окрім власника).</i>',
        parse_mode="HTML",
        reply_markup=confirm_kb,
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("channel_add_editor_cancel_"))
async def channel_add_editor_cancel(callback: types.CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.removeprefix("channel_add_editor_cancel_"))
    user_id = callback.from_user.id
    if not get_channel_by_id(channel_id, user_id=user_id):
        await callback.answer("❌ Чат не знайдено", show_alert=True)
        await state.clear()
        return
    data = await state.get_data()
    confirm_mid = data.get("editor_confirm_message_id")
    prompt_chat_id = data.get("editor_prompt_chat_id")
    prompt_message_id = data.get("editor_prompt_message_id")
    await state.clear()
    payload = _channel_editors_screen_payload(channel_id, user_id)
    if not payload:
        await callback.answer("❌ Чат не знайдено", show_alert=True)
        return
    text, keyboard = payload
    if (
        confirm_mid is not None
        and prompt_chat_id is not None
        and (prompt_message_id is not None)
    ):
        try:
            await bot.edit_message_text(
                chat_id=prompt_chat_id,
                message_id=prompt_message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        except TelegramBadRequest:
            pass
        if callback.message.message_id != prompt_message_id:
            try:
                await bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                )
            except TelegramBadRequest:
                pass
        await callback.answer("Скасовано")
        return
    if await _edit_channel_admins_screen(callback.message, channel_id, user_id):
        await callback.answer("Скасовано")
    else:
        await callback.answer("❌ Чат не знайдено", show_alert=True)


def _editor_add_block(user_id: int, channel_id: int) -> str | None:
    from database_functions.billing_db import denial

    if get_user_channel_role(user_id, channel_id) != "owner":
        return "Додавати редакторів може власник каналу з тарифом ULTRA."
    return denial(user_id, "editors")


@router.callback_query(
    F.data.startswith("channel_add_editor_"),
    ~F.data.startswith("channel_add_editor_cancel_"),
    ~F.data.startswith("channel_add_editor_yes_"),
)
async def channel_add_editor_start(callback: types.CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.removeprefix("channel_add_editor_"))
    user_id = callback.from_user.id
    blocked = _editor_add_block(user_id, channel_id)
    if blocked:
        await callback.answer(blocked, show_alert=True)
        return
    if not get_channel_by_id(channel_id, user_id=user_id):
        await callback.answer("❌ Чат не знайдено", show_alert=True)
        return
    channel_info = get_channel_by_id(channel_id, user_id=user_id)
    channel_title = html.escape(channel_info[2])
    channel_link = channel_info[4] if len(channel_info) > 4 and channel_info[4] else "#"
    await state.set_state(ChannelEditorsSettings.waiting_for_editor_identifier)
    await state.update_data(
        editor_add_channel_id=channel_id,
        editor_prompt_chat_id=callback.message.chat.id,
        editor_prompt_message_id=callback.message.message_id,
    )
    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Скасувати",
                    callback_data=f"channel_add_editor_cancel_{channel_id}",
                icon_custom_emoji_id=Icon.cancel,
            )
            ]
        ]
    )
    await callback.message.edit_text(
        text=f'{E.add} <b>Додати редактора</b>\n\n{E.channel} Канал: <a href="{channel_link}">{channel_title}</a>\n\nНадішліть <b>@username</b> або <b>числовий Telegram ID</b> користувача.\nКористувач має бути зареєстрований у бота (хоча б один раз натиснув /start).',
        parse_mode="HTML",
        reply_markup=cancel_kb,
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.message(StateFilter(ChannelEditorsSettings.waiting_for_editor_identifier))
async def channel_add_editor_receive(message: types.Message, state: FSMContext):
    data = await state.get_data()
    channel_id = data.get("editor_add_channel_id")
    prompt_chat_id = data.get("editor_prompt_chat_id")
    prompt_message_id = data.get("editor_prompt_message_id")
    actor_id = message.from_user.id
    if not channel_id or prompt_chat_id is None or prompt_message_id is None:
        await state.clear()
        await message.answer("❌ Сесія закінчилась. Відкрийте список редакторів знову.")
        return
    if not get_channel_by_id(channel_id, user_id=actor_id):
        await state.clear()
        await message.answer("❌ У вас немає доступу до цього чату.")
        return
    blocked = _editor_add_block(actor_id, int(channel_id))
    if blocked:
        await state.clear()
        await message.answer(blocked)
        return
    raw = (message.text or "").strip()
    if raw.lower() in ("/cancel", "скасувати"):
        await state.clear()
        payload = _channel_editors_screen_payload(channel_id, actor_id)
        if payload:
            text, keyboard = payload
            try:
                await bot.edit_message_text(
                    chat_id=prompt_chat_id,
                    message_id=prompt_message_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    disable_web_page_preview=True,
                )
            except TelegramBadRequest:
                pass
        await message.answer("Скасовано.")
        return
    target_id = resolve_registered_user_id_from_input(raw)
    if not target_id:
        await message.answer(
            "❌ Користувача не знайдено в базі бота. Він має натиснути /start у боті."
        )
        return
    if target_id == actor_id:
        await message.answer(
            "❌ Не можна додати себе таким чином (ви вже маєте доступ)."
        )
        return
    if not get_channel_by_id(channel_id):
        await state.clear()
        await message.answer("❌ Канал не знайдено.")
        return
    role_chk = get_user_channel_role(target_id, channel_id)
    if role_chk == "owner":
        await message.answer(
            "ℹ️ Цей користувач уже є <b>власником</b> каналу в боті.", parse_mode="HTML"
        )
        return
    if role_chk == "admin":
        await message.answer(
            "ℹ️ Цей користувач уже є <b>редактором</b> цього каналу.", parse_mode="HTML"
        )
        return
    ch_info = get_channel_by_id(channel_id, user_id=actor_id)
    if not ch_info:
        await state.clear()
        await message.answer("❌ Канал не знайдено.")
        return
    channel_title = html.escape(ch_info[2])
    channel_link = ch_info[4] if len(ch_info) > 4 and ch_info[4] else "#"
    display_user = html.escape(raw)
    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Так, додати редактора",
                    callback_data=f"channel_add_editor_yes_{channel_id}",
                icon_custom_emoji_id=Icon.ok,
            )
            ],
            [
                InlineKeyboardButton(
                    text="Скасувати",
                    callback_data=f"channel_add_editor_cancel_{channel_id}",
                icon_custom_emoji_id=Icon.cancel,
            )
            ],
        ]
    )
    await state.set_state(ChannelEditorsSettings.waiting_for_editor_add_confirm)
    confirm_msg = await message.answer(
        text=f'{E.add} <b>Підтвердження</b>\n\nДодати користувача <b>{display_user}</b> (<code>{target_id}</code>) як <b>редактора</b> каналу <a href="{channel_link}">{channel_title}</a>?\n\n<i>Редактор зможе керувати цим чатом у SkyPost (у списку каналів і налаштуваннях).</i>',
        parse_mode="HTML",
        reply_markup=confirm_kb,
        disable_web_page_preview=True,
    )
    await state.update_data(
        editor_add_channel_id=channel_id,
        editor_prompt_chat_id=prompt_chat_id,
        editor_prompt_message_id=prompt_message_id,
        editor_pending_target_id=target_id,
        editor_pending_display=display_user,
        editor_user_reply_message_id=message.message_id,
        editor_user_reply_chat_id=message.chat.id,
        editor_confirm_message_id=confirm_msg.message_id,
    )


@router.callback_query(
    F.data.startswith("channel_add_editor_yes_"),
    StateFilter(ChannelEditorsSettings.waiting_for_editor_add_confirm),
)
async def channel_add_editor_confirmed(
    callback: types.CallbackQuery, state: FSMContext
):
    channel_id = int(callback.data.removeprefix("channel_add_editor_yes_"))
    data = await state.get_data()
    if data.get("editor_add_channel_id") != channel_id:
        await callback.answer("❌ Сесія не збігається", show_alert=True)
        return
    target_id = data.get("editor_pending_target_id")
    prompt_chat_id = data.get("editor_prompt_chat_id")
    prompt_message_id = data.get("editor_prompt_message_id")
    reply_mid = data.get("editor_user_reply_message_id")
    reply_cid = data.get("editor_user_reply_chat_id")
    actor_id = callback.from_user.id
    if target_id is None or prompt_chat_id is None or prompt_message_id is None:
        await state.clear()
        await callback.answer("❌ Дані втрачено", show_alert=True)
        return
    if not get_channel_by_id(channel_id, user_id=actor_id):
        await state.clear()
        await callback.answer("❌ Немає доступу", show_alert=True)
        return
    editor_error = _editor_add_block(actor_id, channel_id)
    if editor_error:
        await callback.answer(editor_error, show_alert=True)
        return
    await state.clear()
    result = add_channel_editor(channel_id, target_id)
    if result != "ok":
        payload = _channel_editors_screen_payload(channel_id, actor_id)
        if payload:
            text, keyboard = payload
            try:
                await bot.edit_message_text(
                    chat_id=prompt_chat_id,
                    message_id=prompt_message_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    disable_web_page_preview=True,
                )
            except TelegramBadRequest:
                pass
        try:
            await bot.delete_message(
                chat_id=callback.message.chat.id, message_id=callback.message.message_id
            )
        except TelegramBadRequest:
            pass
        if result == "already_owner":
            await callback.answer(
                "ℹ️ Цей користувач уже є власником каналу в боті.", show_alert=True
            )
        elif result == "already_editor":
            await callback.answer(
                "ℹ️ Цей користувач уже є редактором цього каналу.", show_alert=True
            )
        else:
            await callback.answer("❌ Канал не знайдено", show_alert=True)
        return
    del_tuple = None
    if reply_cid is not None and reply_mid is not None:
        del_tuple = (reply_cid, reply_mid)
    confirm_del = (callback.message.chat.id, callback.message.message_id)
    await _finalize_channel_editor_added(
        channel_id,
        target_id,
        actor_id,
        prompt_chat_id,
        prompt_message_id,
        fallback_answer_chat_id=callback.message.chat.id,
        delete_user_message=del_tuple,
        delete_confirm_message=confirm_del,
    )
    await callback.answer("✅ Редактора додано")
