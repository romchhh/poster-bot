from __future__ import annotations

import html as html_lib
import logging
import re

from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, InputMediaPhoto

from database_functions.channels_db import get_all_channels
from database_functions.copy_mirror_db import (
    get_copy_mirror_pending_extras,
    get_copy_mirror_pending_publish,
    merge_copy_mirror_pending_extras,
    set_copy_mirror_pending_publish_status,
)
from database_functions.folders_db import get_user_folders
from keyboards.client_keyboards.copy_mirror_keyboards import (
    get_mirror_replace_media_keyboard,
    mirror_cross_folder_keyboard,
    mirror_cross_main_keyboard,
)
from app.runtime import bot
from states.client_states import CopyMirrorCrosspost, CopyMirrorReplaceMedia
from utils.copy_utils.ai import Ai
from utils.copy_utils.mirror_flow import (
    folder_id_cell,
    channels_pairs_in_folder,
    group_admin_guard_user,
    mirror_ai_news_context,
    mirror_ai_store_generated,
    mirror_begin_schedule_calendar,
    mirror_delete_group_preview_messages,
    mirror_do_publish,
    mirror_merge_cross_pick_into_extras,
    mirror_refresh_ui_kb,
    mirror_restore_group_confirmation,
)

logger = logging.getLogger(__name__)

router = Router()

_RE_CROSS_TOG = re.compile(r"^cpxtog_(\d+)_(\d+)_(-?\d+)$")


def _safe_int(v) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _cross_pick_keys(extras: dict) -> set[str]:
    v = extras.get("cross_pick_keys")
    if not isinstance(v, list) or not v:
        return set()
    return {str(x) for x in v}


@router.callback_query(F.data.startswith("cpyma_"))
async def mirror_cb_approve(callback: types.CallbackQuery):
    pk = int(callback.data.removeprefix("cpyma_"))
    await mirror_do_publish(callback, pk)


@router.callback_query(F.data.startswith("cmpp:"))
async def mirror_cb_legacy_cmpp(callback: types.CallbackQuery):
    try:
        pk = int((callback.data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer()
        return
    await mirror_do_publish(callback, pk)


@router.callback_query(F.data.startswith("cpymr_"))
async def mirror_cb_reject(callback: types.CallbackQuery):
    pk = int(callback.data.removeprefix("cpymr_"))
    row = get_copy_mirror_pending_publish(pk)
    if not row or str(row[8]) != "pending":
        await callback.answer("Вже оброблено.", show_alert=True)
        return
    if int(callback.message.chat.id) != int(row[7]):
        await callback.answer()
        return
    if not await group_admin_guard_user(callback.from_user.id or 0, int(row[7])):
        await callback.answer("Немає прав.", show_alert=True)
        return
    set_copy_mirror_pending_publish_status(pk, "rejected")
    extras = get_copy_mirror_pending_extras(pk)
    dest_gid = int(row[7])
    await mirror_delete_group_preview_messages(bot, dest_gid, extras)
    cmid = extras.get("confirmation_message_id")
    if cmid:
        try:
            await bot.edit_message_text(
                chat_id=dest_gid,
                message_id=int(cmid),
                text="❌ <b>Копію відхилено</b>",
                parse_mode="HTML",
                reply_markup=None,
            )
        except TelegramBadRequest:
            pass
    aux = callback.message
    if aux and cmid and int(aux.message_id) != int(cmid):
        try:
            await bot.delete_message(dest_gid, aux.message_id)
        except TelegramBadRequest:
            pass
    await callback.answer("Відхилено.")


@router.callback_query(F.data.startswith("cpymz_"))
async def mirror_cb_no_media(callback: types.CallbackQuery):
    pk = int(callback.data.removeprefix("cpymz_"))
    row = get_copy_mirror_pending_publish(pk)
    if not row or str(row[8]) != "pending":
        await callback.answer("Недійсно.", show_alert=True)
        return
    if int(callback.message.chat.id) != int(row[7]):
        await callback.answer()
        return
    if not await group_admin_guard_user(callback.from_user.id or 0, int(row[7])):
        await callback.answer("Немає прав.", show_alert=True)
        return

    merge_copy_mirror_pending_extras(pk, {"strip_media": True})
    await mirror_refresh_ui_kb(int(row[7]), pk=pk, extras=None)

    await callback.answer("Наступна публікація буде лише текстом звідси.")


@router.callback_query(F.data.startswith("cpymt_"))
async def mirror_schedule_begin(callback: types.CallbackQuery, state: FSMContext):
    pk = int(callback.data.removeprefix("cpymt_"))
    await mirror_begin_schedule_calendar(callback, state, pk=pk)


@router.callback_query(F.data == "mirror_schedule_cancel")
async def mirror_schedule_cancel_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    pk = data.get("mirror_schedule_pk")
    if not pk:
        await callback.answer()
        return
    await state.update_data(
        mirror_schedule_pk=None,
        mirror_schedule_owner_uid=None,
        scheduled_date=None,
        schedule_datetime=None,
        schedule_prompt_message_id=None,
    )
    await state.set_state(None)
    await mirror_restore_group_confirmation(bot, int(pk))
    await callback.answer("Скасовано.")


@router.callback_query(F.data.startswith("cpxst_"))
async def mirror_cross_start(callback: types.CallbackQuery, state: FSMContext):
    pk = int(callback.data.removeprefix("cpxst_"))
    row = get_copy_mirror_pending_publish(pk)
    if not row or str(row[8]) != "pending":
        await callback.answer("Недійсно.", show_alert=True)
        return
    if int(callback.message.chat.id) != int(row[7]):
        await callback.answer()
        return
    if not await group_admin_guard_user(callback.from_user.id or 0, int(row[7])):
        await callback.answer("Немає прав.", show_alert=True)
        return
    uid = callback.from_user.id
    extras = get_copy_mirror_pending_extras(pk)
    if not extras.get("cross_pick_keys"):
        merge_copy_mirror_pending_extras(pk, {"cross_pick_keys": []})

    folders = get_user_folders(uid)
    await state.set_state(CopyMirrorCrosspost.picking_channels)
    await state.update_data(mirror_cross_pk=pk)
    kb = mirror_cross_main_keyboard(pk, folders)
    await callback.message.answer(
        "📤 Оберіть додаткові канали SkyPost (підсумок додається до області копіювання).",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(StateFilter(CopyMirrorCrosspost.picking_channels), F.data.startswith("cpxcan_"))
async def mirror_cross_cancel(callback: types.CallbackQuery, state: FSMContext):
    pk = int(callback.data.removeprefix("cpxcan_"))
    await state.clear()
    merge_copy_mirror_pending_extras(pk, {"cross_pick_keys": []})
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await callback.answer("Скасовано.")


@router.callback_query(StateFilter(CopyMirrorCrosspost.picking_channels), F.data.startswith("cpxmall_"))
async def mirror_cross_all(callback: types.CallbackQuery, state: FSMContext):
    pk = int(callback.data.removeprefix("cpxmall_"))
    row = get_copy_mirror_pending_publish(pk)
    if not row:
        await callback.answer()
        return
    uid = int(row[1])
    keys = []
    for r in get_all_channels(user_id=uid, only_active=True):
        ch_id = int(r[1])
        fid = folder_id_cell(r)
        keys.append(f"{fid}_{ch_id}" if fid is not None else f"0_{ch_id}")
    merge_copy_mirror_pending_extras(pk, {"cross_pick_keys": keys})
    await callback.answer("Усі канали позначено в списку — відкрийте папку для підтвердження.")


@router.callback_query(StateFilter(CopyMirrorCrosspost.picking_channels), F.data.startswith("cpxfld_"))
async def mirror_cross_folder(callback: types.CallbackQuery, state: FSMContext):
    rest = callback.data.removeprefix("cpxfld_")
    pk_str, fid_str = rest.rsplit("_", 1)
    pk, fid = int(pk_str), int(fid_str)
    row = get_copy_mirror_pending_publish(pk)
    if not row:
        await callback.answer()
        return
    uid = int(row[1])
    chans = channels_pairs_in_folder(uid, fid)
    extras = get_copy_mirror_pending_extras(pk)
    sel = _cross_pick_keys(extras)
    kb = mirror_cross_folder_keyboard(pk, fid, chans, sel)
    try:
        await callback.message.edit_text(
            text=f"Папка {fid}: відмітьте канали", reply_markup=kb
        )
    except TelegramBadRequest:
        await callback.message.answer("Канали папки:", reply_markup=kb)
    await callback.answer()


@router.callback_query(StateFilter(CopyMirrorCrosspost.picking_channels), F.data.startswith("cpxtog_"))
async def mirror_cross_toggle(callback: types.CallbackQuery, state: FSMContext):
    m = _RE_CROSS_TOG.match(callback.data or "")
    if not m:
        await callback.answer()
        return
    pk, fid, chid = int(m.group(1)), int(m.group(2)), int(m.group(3))
    key = f"{fid}_{chid}"
    extras = get_copy_mirror_pending_extras(pk)
    sel = _cross_pick_keys(extras)
    if key in sel:
        sel.discard(key)
    else:
        sel.add(key)
    merge_copy_mirror_pending_extras(pk, {"cross_pick_keys": list(sel)})
    row = get_copy_mirror_pending_publish(pk)
    uid = int(row[1])
    chans = channels_pairs_in_folder(uid, fid)
    kb = mirror_cross_folder_keyboard(pk, fid, chans, sel)
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(StateFilter(CopyMirrorCrosspost.picking_channels), F.data.startswith("cpxtbk_"))
async def mirror_cross_back(callback: types.CallbackQuery, state: FSMContext):
    pk = int(callback.data.removeprefix("cpxtbk_"))
    folders = get_user_folders(callback.from_user.id)
    kb = mirror_cross_main_keyboard(pk, folders)
    try:
        await callback.message.edit_text(
            text="📤 Оберіть канали або підтвердьте публікацію.",
            reply_markup=kb,
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(StateFilter(CopyMirrorCrosspost.picking_channels), F.data.startswith("cpxtok_"))
async def mirror_cross_ok(callback: types.CallbackQuery, state: FSMContext):
    pk = int(callback.data.removeprefix("cpxtok_"))
    if not await mirror_merge_cross_pick_into_extras(callback, pk):
        return
    await state.clear()
    await mirror_do_publish(callback, pk)


@router.callback_query(StateFilter(CopyMirrorCrosspost.picking_channels), F.data.startswith("cpxtsc_"))
async def mirror_cross_schedule(callback: types.CallbackQuery, state: FSMContext):
    pk = int(callback.data.removeprefix("cpxtsc_"))
    if not await mirror_merge_cross_pick_into_extras(callback, pk):
        return
    await mirror_begin_schedule_calendar(callback, state, pk=pk)


async def _apply_mirror_replaced_photo(
    *,
    pk: int,
    chat_id: int,
    img_bytes: bytes,
    owner_uid: int,
    news: str,
    source: str,
    photo_mid: int | None,
) -> int | None:
    """Оновлює превʼю в групі і зберігає file_id для публікації. Повертає message_id фото."""
    extras = get_copy_mirror_pending_extras(pk)
    target_mid = photo_mid or extras.get("preview_photo_message_id")
    new_mid: int | None = None
    file_id: str | None = None

    if target_mid:
        try:
            edited = await bot.edit_message_media(
                chat_id=chat_id,
                message_id=int(target_mid),
                media=InputMediaPhoto(
                    media=BufferedInputFile(img_bytes, filename="ai.png")
                ),
            )
            new_mid = int(target_mid)
            if getattr(edited, "photo", None):
                file_id = edited.photo[-1].file_id
        except TelegramBadRequest:
            target_mid = None

    if new_mid is None:
        cmid = extras.get("confirmation_message_id")
        sent = await bot.send_photo(
            chat_id=chat_id,
            photo=BufferedInputFile(img_bytes, filename="ai.png"),
            reply_to_message_id=int(cmid) if cmid else None,
        )
        new_mid = int(sent.message_id)
        if sent.photo:
            file_id = sent.photo[-1].file_id
        prev = extras.get("preview_message_ids")
        prev_list = list(prev) if isinstance(prev, list) else []
        prev_list.append(new_mid)
        merge_copy_mirror_pending_extras(pk, {"preview_message_ids": prev_list})

    if not file_id:
        # Fallback: upload privately to get file_id
        try:
            tmp = await bot.send_photo(
                owner_uid,
                photo=BufferedInputFile(img_bytes, filename="ai.png"),
            )
            file_id = tmp.photo[-1].file_id if tmp.photo else None
            await bot.delete_message(owner_uid, tmp.message_id)
        except Exception:
            logger.exception("mirror replace: private upload for file_id")

    patch = {
        "preview_photo_message_id": new_mid,
        "strip_media": False,
    }
    if file_id:
        patch["replaced_photo_file_id"] = file_id
    merge_copy_mirror_pending_extras(pk, patch)
    await mirror_ai_store_generated(
        owner_uid=owner_uid,
        pk=pk,
        img_bytes=img_bytes,
        caption_plain=news,
        source=source,
    )
    await mirror_refresh_ui_kb(chat_id, pk=pk, extras=None)
    return new_mid


@router.callback_query(F.data.startswith("cpymrep_"))
async def mirror_replace_media_menu(callback: types.CallbackQuery):
    pk = int(callback.data.removeprefix("cpymrep_"))
    row = get_copy_mirror_pending_publish(pk)
    if not row or str(row[8]) != "pending":
        await callback.answer("Недійсно.", show_alert=True)
        return
    chat_id = int(row[7])
    if int(callback.message.chat.id) != chat_id:
        await callback.answer()
        return
    if not await group_admin_guard_user(callback.from_user.id or 0, chat_id):
        await callback.answer("Немає прав.", show_alert=True)
        return

    extras = get_copy_mirror_pending_extras(pk)
    photo_mid = extras.get("preview_photo_message_id")
    try:
        photo_mid = int(photo_mid) if photo_mid is not None else None
    except (TypeError, ValueError):
        photo_mid = None

    text = (
        "🔄 <b>Замінити медіа</b>\n\n"
        "Оберіть спосіб:\n"
        "• <b>Згенерувати нове (AI)</b> — через OpenAI\n"
        "• <b>Надіслати своє фото</b> — завантажити файл у цю групу"
    )
    kb = get_mirror_replace_media_keyboard(pk, photo_message_id=photo_mid)
    try:
        await callback.message.edit_text(text=text, parse_mode="HTML", reply_markup=kb)
    except TelegramBadRequest:
        await callback.message.answer(text=text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("cpymrb_"))
async def mirror_replace_media_back(callback: types.CallbackQuery, state: FSMContext):
    pk = int(callback.data.removeprefix("cpymrb_"))
    await state.clear()
    row = get_copy_mirror_pending_publish(pk)
    if not row or str(row[8]) != "pending":
        await callback.answer()
        return
    await mirror_restore_group_confirmation(bot, pk)
    await callback.answer()


@router.callback_query(F.data.startswith("cpymup_"))
async def mirror_replace_upload_start(callback: types.CallbackQuery, state: FSMContext):
    pk = int(callback.data.removeprefix("cpymup_"))
    row = get_copy_mirror_pending_publish(pk)
    if not row or str(row[8]) != "pending":
        await callback.answer("Недійсно.", show_alert=True)
        return
    chat_id = int(row[7])
    if int(callback.message.chat.id) != chat_id:
        await callback.answer()
        return
    if not await group_admin_guard_user(callback.from_user.id or 0, chat_id):
        await callback.answer("Немає прав.", show_alert=True)
        return

    await state.set_state(CopyMirrorReplaceMedia.waiting_for_photo)
    await state.update_data(mirror_replace_pk=pk)
    try:
        await callback.message.edit_text(
            text=(
                "📎 <b>Надішліть фото</b> у цю групу — воно замінить медіа для публікації.\n\n"
                "Скасувати: кнопка нижче."
            ),
            parse_mode="HTML",
            reply_markup=get_mirror_replace_media_keyboard(
                pk,
                photo_message_id=_safe_int(
                    (get_copy_mirror_pending_extras(pk) or {}).get(
                        "preview_photo_message_id"
                    )
                ),
            ),
        )
    except TelegramBadRequest:
        pass
    await callback.answer("Чекаю на фото…")


@router.message(StateFilter(CopyMirrorReplaceMedia.waiting_for_photo), F.photo)
async def mirror_replace_upload_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pk = data.get("mirror_replace_pk")
    if not pk:
        await state.clear()
        return
    row = get_copy_mirror_pending_publish(int(pk))
    if not row or str(row[8]) != "pending":
        await state.clear()
        await message.answer("❌ Запис уже недійсний.")
        return
    chat_id = int(row[7])
    if int(message.chat.id) != chat_id:
        await message.answer("❌ Надішліть фото в групу-отримувач копії.")
        return
    if not await group_admin_guard_user(message.from_user.id if message.from_user else 0, chat_id):
        await message.answer("❌ Потрібні права адміністратора.")
        return

    photo = message.photo[-1]
    file_id = photo.file_id
    try:
        tg_file = await bot.get_file(file_id)
        buf = await bot.download_file(tg_file.file_path)
        img_bytes = buf.read() if hasattr(buf, "read") else bytes(buf or b"")
    except Exception:
        logger.exception("mirror replace upload download")
        await message.answer("❌ Не вдалося завантажити фото.")
        return
    if not img_bytes:
        await message.answer("❌ Порожній файл.")
        return

    extras = get_copy_mirror_pending_extras(int(pk))
    photo_mid = extras.get("preview_photo_message_id")
    try:
        photo_mid = int(photo_mid) if photo_mid is not None else None
    except (TypeError, ValueError):
        photo_mid = None

    news = await mirror_ai_news_context(row)
    await _apply_mirror_replaced_photo(
        pk=int(pk),
        chat_id=chat_id,
        img_bytes=img_bytes,
        owner_uid=int(row[1]),
        news=news or "",
        source="user_upload",
        photo_mid=photo_mid,
    )
    # Persist exact uploaded file_id (more reliable than re-upload)
    merge_copy_mirror_pending_extras(
        int(pk),
        {"replaced_photo_file_id": file_id, "strip_media": False},
    )
    await state.clear()
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    await mirror_restore_group_confirmation(bot, int(pk))
    await message.answer("✅ Медіа замінено. Можна публікувати.")


@router.callback_query(F.data.startswith("cpyair_"))
async def mirror_ai_regenerate(callback: types.CallbackQuery, state: FSMContext):
    rest = (callback.data or "").removeprefix("cpyair_")
    try:
        pk_str, photo_mid_str = rest.rsplit("_", 1)
        pk, photo_mid = int(pk_str), int(photo_mid_str)
    except ValueError:
        await callback.answer()
        return
    row = get_copy_mirror_pending_publish(pk)
    if not row or str(row[8]) != "pending":
        await callback.answer("Недійсно.", show_alert=True)
        return
    chat_id = int(row[7])
    if int(callback.message.chat.id) != chat_id:
        await callback.answer()
        return
    if not await group_admin_guard_user(callback.from_user.id or 0, chat_id):
        await callback.answer()
        return

    news = await mirror_ai_news_context(row)
    if not news:
        await callback.answer("Немає тексту для зображення.", show_alert=True)
        return

    from database_functions.billing_db import refund_tokens, spend_tokens

    owner_id = int(row[1])
    token_error = spend_tokens(owner_id, "image")
    if token_error:
        await callback.answer(token_error, show_alert=True)
        return
    await callback.answer("⏳ OpenAI…")
    try:
        img_bytes = await Ai().generate_image_from_news(news)
    except Exception as e:
        refund_tokens(owner_id, "image")
        logger.exception("mirror AI regen")
        err = html_lib.escape(str(e))[:180]
        await callback.message.answer(f"❌ Помилка генерації зображення OpenAI.\n<code>{err}</code>", parse_mode="HTML")
        return

    await _apply_mirror_replaced_photo(
        pk=pk,
        chat_id=chat_id,
        img_bytes=img_bytes,
        owner_uid=int(row[1]),
        news=news,
        source="ai_regenerate",
        photo_mid=photo_mid,
    )
    await state.clear()
    await mirror_restore_group_confirmation(bot, pk)


@router.callback_query(F.data.startswith("cpyaig_"))
async def mirror_ai_generate(callback: types.CallbackQuery, state: FSMContext):
    pk = int((callback.data or "").removeprefix("cpyaig_"))
    row = get_copy_mirror_pending_publish(pk)
    if not row or str(row[8]) != "pending":
        await callback.answer("Недійсно.", show_alert=True)
        return
    chat_id = int(row[7])
    if int(callback.message.chat.id) != chat_id:
        await callback.answer()
        return
    if not await group_admin_guard_user(callback.from_user.id or 0, chat_id):
        await callback.answer()
        return

    news = await mirror_ai_news_context(row)
    if not news:
        await callback.answer("Немає тексту для генерації.", show_alert=True)
        return

    from database_functions.billing_db import refund_tokens, spend_tokens

    owner_id = int(row[1])
    token_error = spend_tokens(owner_id, "image")
    if token_error:
        await callback.answer(token_error, show_alert=True)
        return
    await callback.answer("⏳ OpenAI…")
    try:
        img_bytes = await Ai().generate_image_from_news(news)
    except Exception as e:
        refund_tokens(owner_id, "image")
        logger.exception("mirror AI gen")
        err = html_lib.escape(str(e))[:180]
        await callback.message.answer(f"❌ Помилка генерації зображення OpenAI.\n<code>{err}</code>", parse_mode="HTML")
        return

    await _apply_mirror_replaced_photo(
        pk=pk,
        chat_id=chat_id,
        img_bytes=img_bytes,
        owner_uid=int(row[1]),
        news=news,
        source="ai_generate",
        photo_mid=None,
    )
    await state.clear()
    await mirror_restore_group_confirmation(bot, pk)
