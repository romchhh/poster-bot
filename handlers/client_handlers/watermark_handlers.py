from utils.ui_emoji import E
from aiogram import Router, types, F
from app.runtime import bot
from aiogram.fsm.context import FSMContext
from keyboards.client_keyboards.watermark_keyboards import (
    get_watermark_confirm_delete_keyboard,
    get_watermark_management_keyboard,
    get_watermark_settings_keyboard,
    get_watermark_upload_cancel_keyboard,
)
from states.client_states import WatermarkStates
from database_functions.watermark_db import (
    has_watermark,
    get_watermark,
    save_temp_watermark,
    update_watermark_settings,
    delete_watermark,
    commit_temp_watermark,
    clear_temp_watermark,
)
from utils.watermark_utils import image_to_base64, create_preview_image
from PIL import Image
from io import BytesIO
import asyncio

router = Router()


def _parse_wm(data: str) -> list[str] | None:
    if not data.startswith("wm|"):
        return None
    return data.split("|")


def watermark_nav_back(channel_id: str, folder_id: int) -> str | None:
    """Куди повернутись із меню водяного знаку: 1 — підсумок каналу, 2 — блок налаштувань каналу, 0 — копіювання."""
    cid = channel_id
    if folder_id == 1:
        return f"channel_settings_{cid}"
    if folder_id == 2:
        return f"cpy_stg:c:{cid}:chs"
    if folder_id == 0:
        return f"cpy_stg:c:{cid}:cpy"
    return None


@router.callback_query(F.data.startswith("wm|m|"))
async def watermark_manage_callback(callback: types.CallbackQuery, state: FSMContext):
    try:
        p = _parse_wm(callback.data)
        if not p or len(p) < 5:
            await callback.answer("❌ Помилка формату")
            return
        channel_id, donor_id, folder_id = p[2], p[3], int(p[4])
        user_id = callback.from_user.id
        await state.clear()
        back_cb = watermark_nav_back(channel_id, folder_id)

        watermark_exists = has_watermark(user_id, channel_id, donor_id)
        keyboard = get_watermark_management_keyboard(
            channel_id, donor_id, folder_id, watermark_exists, back_callback=back_cb
        )

        if watermark_exists:
            text = f"{E.water} <b>Управління водяним знаком</b>\n\n✅ Водяний знак активний\n\nОберіть дію:"
        else:
            text = f"{E.water} <b>Управління водяним знаком</b>\n\n❌ Водяний знак не встановлено\n\nОберіть дію:"

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        print(f"Error in watermark_manage_callback: {e}")
        await callback.answer("❌ Помилка")


@router.callback_query(F.data.startswith("wm|a|"))
async def watermark_add_callback(callback: types.CallbackQuery, state: FSMContext):
    try:
        p = _parse_wm(callback.data)
        if not p or len(p) < 5:
            await callback.answer("❌ Помилка формату")
            return
        channel_id, donor_id, folder_id = p[2], p[3], int(p[4])
        await state.update_data(
            watermark_channel_id=channel_id,
            watermark_donor_id=donor_id,
            watermark_folder_id=folder_id,
        )
        await state.set_state(WatermarkStates.waiting_for_watermark_image)
        text = (
            f"{E.water} <b>Додавання водяного знаку</b>\n\n"
            "📎 Надішліть зображення для водяного знаку.\n\n"
            "💡 <b>Рекомендації:</b>\n"
            "• Для прозорого фону надсилайте PNG як <b>файл</b> (📎), а не як фото\n"
            "• Підтримуються формати: PNG, JPEG, WEBP\n"
            "• Оптимальний розмір: 200-500px\n"
            "• Максимальний розмір файлу: 5MB"
        )
        keyboard = get_watermark_upload_cancel_keyboard(channel_id, donor_id, folder_id)
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()
    except Exception as e:
        print(f"Error in watermark_add_callback: {e}")
        await callback.answer("❌ Помилка")


@router.callback_query(F.data.startswith("wm|e|"))
async def watermark_edit_callback(callback: types.CallbackQuery, state: FSMContext):
    try:
        p = _parse_wm(callback.data)
        if not p or len(p) < 5:
            await callback.answer("❌ Помилка формату")
            return
        channel_id, donor_id, folder_id = p[2], p[3], int(p[4])
        user_id = callback.from_user.id
        watermark_data = get_watermark(user_id, channel_id, donor_id)
        if not watermark_data:
            await callback.answer("❌ Водяний знак не знайдено")
            return
        preview_data = create_preview_image(
            watermark_data["watermark_data"],
            watermark_data["position"],
            watermark_data["size_percent"],
            watermark_data["opacity"],
        )
        if preview_data:
            chat_id = callback.message.chat.id
            try:
                await callback.message.delete()
            except Exception:
                pass
            preview_message = await bot.send_photo(
                chat_id=chat_id,
                photo=types.BufferedInputFile(preview_data, filename="watermark_preview.jpg"),
                caption=f"{E.water} <b>Налаштування водяного знаку</b>\n\n{E.list} Поточні налаштування показані на превʼю вище",
                parse_mode="HTML",
            )
            await state.update_data(
                watermark_channel_id=channel_id,
                watermark_donor_id=donor_id,
                watermark_folder_id=folder_id,
                preview_message_id=preview_message.message_id,
            )
            keyboard = get_watermark_settings_keyboard(
                channel_id,
                donor_id,
                folder_id,
                watermark_data["position"],
                watermark_data["size_percent"],
                watermark_data["opacity"],
                watermark_data.get("indent") or 0,
            )
            await bot.send_message(
                chat_id=chat_id,
                text=f"{E.tools} <b>Налаштування</b>",
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        else:
            await callback.answer("❌ Помилка створення превʼю")
        await callback.answer()
    except Exception as e:
        print(f"Error in watermark_edit_callback: {e}")
        await callback.answer("❌ Помилка")


@router.callback_query(F.data.startswith("wm|d|"))
async def watermark_delete_callback(callback: types.CallbackQuery, state: FSMContext):
    try:
        p = _parse_wm(callback.data)
        if not p or len(p) < 5:
            await callback.answer("❌ Помилка формату")
            return
        channel_id, donor_id, folder_id = p[2], p[3], int(p[4])
        keyboard = get_watermark_confirm_delete_keyboard(channel_id, donor_id, folder_id)
        text = (
            "🗑️ <b>Видалення водяного знаку</b>\n\n"
            "⚠️ Ви впевнені, що хочете видалити водяний знак?\n\n"
            "Цю дію неможливо скасувати."
        )
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        print(f"Error in watermark_delete_callback: {e}")
        await callback.answer("❌ Помилка")


@router.callback_query(F.data.startswith("wm|dc|"))
async def watermark_confirm_delete_callback(callback: types.CallbackQuery, state: FSMContext):
    try:
        p = _parse_wm(callback.data)
        if not p or len(p) < 5:
            await callback.answer("❌ Помилка формату")
            return
        channel_id, donor_id, folder_id = p[2], p[3], int(p[4])
        user_id = callback.from_user.id
        clear_temp_watermark(user_id, channel_id, donor_id)
        success = delete_watermark(user_id, channel_id, donor_id)
        if success:
            await callback.message.edit_text("✅ <b>Водяний знак видалено</b>", parse_mode="HTML")
            await asyncio.sleep(1)
            back_cb = watermark_nav_back(channel_id, folder_id)
            keyboard = get_watermark_management_keyboard(
                channel_id, donor_id, folder_id, False, back_callback=back_cb
            )
            text = f"{E.water} <b>Управління водяним знаком</b>\n\n❌ Водяний знак не встановлено\n\nОберіть дію:"
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await callback.answer("❌ Не вдалося видалити")
        await callback.answer()
    except Exception as e:
        print(f"Error in watermark_confirm_delete_callback: {e}")
        await callback.answer("❌ Помилка")


async def _refresh_wm_settings_keyboard(
    callback: types.CallbackQuery, state: FSMContext, channel_id, donor_id, folder_id
):
    user_id = callback.from_user.id
    watermark_data = get_watermark(user_id, channel_id, donor_id)
    if not watermark_data:
        return
    preview_data = create_preview_image(
        watermark_data["watermark_data"],
        watermark_data["position"],
        watermark_data["size_percent"],
        watermark_data["opacity"],
    )
    if preview_data:
        state_data = await state.get_data()
        preview_message_id = state_data.get("preview_message_id")
        if preview_message_id:
            try:
                await bot.edit_message_media(
                    chat_id=callback.message.chat.id,
                    message_id=preview_message_id,
                    media=types.InputMediaPhoto(
                        media=types.BufferedInputFile(preview_data, filename="watermark_preview.jpg"),
                        caption=f"{E.water} <b>Налаштування водяного знаку</b>\n\n{E.list} Поточні налаштування показані на превʼю вище",
                        parse_mode="HTML",
                    ),
                )
            except Exception as e:
                print(f"Error updating preview: {e}")
    keyboard = get_watermark_settings_keyboard(
        channel_id,
        donor_id,
        folder_id,
        watermark_data["position"],
        watermark_data["size_percent"],
        watermark_data["opacity"],
        watermark_data.get("indent") or 0,
    )
    await callback.message.edit_reply_markup(reply_markup=keyboard)


@router.callback_query(F.data.startswith("wm|p|"))
async def watermark_position_callback(callback: types.CallbackQuery, state: FSMContext):
    try:
        p = _parse_wm(callback.data)
        if not p or len(p) < 6:
            await callback.answer("❌ Помилка формату")
            return
        channel_id, donor_id, folder_id, position = p[2], p[3], int(p[4]), p[5]
        user_id = callback.from_user.id
        if update_watermark_settings(user_id, channel_id, donor_id, position=position):
            await _refresh_wm_settings_keyboard(callback, state, channel_id, donor_id, folder_id)
        await callback.answer()
    except Exception as e:
        print(f"Error in watermark_position_callback: {e}")
        await callback.answer("❌ Помилка")


@router.callback_query(F.data.startswith("wm|sz|"))
async def watermark_size_callback(callback: types.CallbackQuery, state: FSMContext):
    try:
        p = _parse_wm(callback.data)
        if not p or len(p) < 6:
            await callback.answer("❌ Помилка формату")
            return
        channel_id, donor_id, folder_id, size = p[2], p[3], int(p[4]), int(p[5])
        user_id = callback.from_user.id
        if update_watermark_settings(user_id, channel_id, donor_id, size_percent=size):
            await _refresh_wm_settings_keyboard(callback, state, channel_id, donor_id, folder_id)
        await callback.answer()
    except Exception as e:
        print(f"Error in watermark_size_callback: {e}")
        await callback.answer("❌ Помилка")


@router.callback_query(F.data.startswith("wm|op|"))
async def watermark_opacity_callback(callback: types.CallbackQuery, state: FSMContext):
    try:
        p = _parse_wm(callback.data)
        if not p or len(p) < 6:
            await callback.answer("❌ Помилка формату")
            return
        channel_id, donor_id, folder_id, opacity = p[2], p[3], int(p[4]), int(p[5])
        user_id = callback.from_user.id
        if update_watermark_settings(user_id, channel_id, donor_id, opacity=opacity):
            await _refresh_wm_settings_keyboard(callback, state, channel_id, donor_id, folder_id)
        await callback.answer()
    except Exception as e:
        print(f"Error in watermark_opacity_callback: {e}")
        await callback.answer("❌ Помилка")


@router.callback_query(F.data.startswith("wm|in|"))
async def watermark_indent_callback(callback: types.CallbackQuery, state: FSMContext):
    try:
        p = _parse_wm(callback.data)
        if not p or len(p) < 6:
            await callback.answer("❌ Помилка формату")
            return
        channel_id, donor_id, folder_id, indent = p[2], p[3], int(p[4]), int(p[5])
        user_id = callback.from_user.id
        if update_watermark_settings(user_id, channel_id, donor_id, indent=indent):
            await _refresh_wm_settings_keyboard(callback, state, channel_id, donor_id, folder_id)
        await callback.answer()
    except Exception as e:
        print(f"Error in watermark_indent_callback: {e}")
        await callback.answer("❌ Помилка")


@router.callback_query(F.data.startswith("wm|sv|"))
async def watermark_save_callback(callback: types.CallbackQuery, state: FSMContext):
    try:
        p = _parse_wm(callback.data)
        if not p or len(p) < 5:
            await callback.answer("❌ Помилка формату")
            return
        channel_id, donor_id, folder_id = p[2], p[3], int(p[4])
        user_id = callback.from_user.id
        success = commit_temp_watermark(user_id, channel_id, donor_id)
        has_wm = has_watermark(user_id, channel_id, donor_id)
        if success:
            text = "✅ <b>Налаштування збережено</b>\n\nВодяний знак збережено."
        elif has_wm:
            text = "✅ <b>Готово</b>\n\nПозицію, розмір і прозорість збережено автоматично."
        else:
            text = "⚠️ Спочатку надішліть зображення водяного знаку."
        await callback.message.edit_text(text, parse_mode="HTML")
        await asyncio.sleep(1)
        back_cb = watermark_nav_back(channel_id, folder_id)
        has_wm_after = has_watermark(user_id, channel_id, donor_id)
        keyboard = get_watermark_management_keyboard(
            channel_id, donor_id, folder_id, has_watermark=has_wm_after, back_callback=back_cb
        )
        text2 = (
            f"{E.water} <b>Управління водяним знаком</b>\n\n✅ Водяний знак активний\n\nОберіть дію:"
            if has_wm_after
            else f"{E.water} <b>Управління водяним знаком</b>\n\n❌ Водяний знак не встановлено\n\nОберіть дію:"
        )
        await callback.message.edit_text(text2, reply_markup=keyboard, parse_mode="HTML")
        await state.clear()
        await callback.answer()
    except Exception as e:
        print(f"Error in watermark_save_callback: {e}")
        await callback.answer("❌ Помилка")


@router.callback_query(F.data.startswith("wm|img|"))
async def watermark_change_image_callback(callback: types.CallbackQuery, state: FSMContext):
    try:
        p = _parse_wm(callback.data)
        if not p or len(p) < 5:
            await callback.answer("❌ Помилка формату")
            return
        channel_id, donor_id, folder_id = p[2], p[3], int(p[4])
        await state.update_data(
            watermark_channel_id=channel_id,
            watermark_donor_id=donor_id,
            watermark_folder_id=folder_id,
        )
        await state.set_state(WatermarkStates.waiting_for_watermark_image)
        text = (
            f"{E.water} <b>Зміна зображення водяного знаку</b>\n\n"
            "📎 Надішліть нове зображення для водяного знаку.\n\n"
            "💡 Для прозорого фону надсилайте PNG як <b>файл</b> (📎)."
        )
        keyboard = get_watermark_upload_cancel_keyboard(channel_id, donor_id, folder_id)
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()
    except Exception as e:
        print(f"Error in watermark_change_image_callback: {e}")
        await callback.answer("❌ Помилка")


@router.message(WatermarkStates.waiting_for_watermark_image, F.photo | F.document)
async def watermark_image_handler(message: types.Message, state: FSMContext):
    try:
        state_data = await state.get_data()
        channel_id = state_data.get("watermark_channel_id")
        donor_id = state_data.get("watermark_donor_id")
        folder_id = state_data.get("watermark_folder_id")
        user_id = message.from_user.id
        if channel_id is None or donor_id is None or folder_id is None:
            await message.answer("❌ Помилка: втрачено дані сесії. Спробуйте ще раз.")
            await state.clear()
            return
        if message.photo:
            file_obj = message.photo[-1]
            file_info = await message.bot.get_file(file_obj.file_id)
        elif message.document:
            file_obj = message.document
            file_info = await message.bot.get_file(file_obj.file_id)
            if not file_obj.mime_type or not file_obj.mime_type.startswith("image/"):
                await message.answer(
                    "❌ <b>Неправильний тип файлу</b>\n\nВодяний знак має бути зображенням (PNG, JPEG, WEBP)",
                    parse_mode="HTML",
                )
                return
            if file_obj.file_name and not file_obj.file_name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                await message.answer(
                    "❌ <b>Непідтримуване розширення</b>\n\nПідтримуються: .png, .jpg, .jpeg, .webp",
                    parse_mode="HTML",
                )
                return
        else:
            await message.answer("❌ Надішліть фото або файл зображення")
            return
        if file_info.file_size > 5 * 1024 * 1024:
            await message.answer("❌ Файл занадто великий. Максимум: 5MB")
            return
        file_data = await message.bot.download_file(file_info.file_path)
        file_bytes = file_data.read()
        try:
            with Image.open(BytesIO(file_bytes)) as img:
                if img.format not in ["PNG", "JPEG", "JPG", "WEBP"]:
                    await message.answer(
                        "❌ <b>Непідтримуваний формат</b>\n\nПідтримуються: PNG, JPEG, WEBP",
                        parse_mode="HTML",
                    )
                    return
        except Exception:
            await message.answer("❌ Не вдалося прочитати зображення.")
            return
        watermark_base64 = image_to_base64(file_bytes)
        if not watermark_base64:
            await message.answer("❌ Помилка обробки зображення")
            return
        save_temp_watermark(user_id, channel_id, donor_id, watermark_base64)
        preview_data = create_preview_image(watermark_base64)
        if preview_data:
            preview_message = await message.answer_photo(
                photo=types.BufferedInputFile(preview_data, filename="watermark_preview.jpg"),
                caption=f"{E.water} <b>Водяний знак додано</b>\n\n{E.list} Превʼю вище. Налаштуйте параметри та натисніть «Зберегти».",
                parse_mode="HTML",
            )
            await state.update_data(preview_message_id=preview_message.message_id)
            keyboard = get_watermark_settings_keyboard(channel_id, donor_id, folder_id)
            await message.answer(f"{E.tools} <b>Налаштування</b>", reply_markup=keyboard, parse_mode="HTML")
        else:
            await message.answer("✅ Водяний знак додано, але превʼю не вдалося створити")
    except Exception as e:
        print(f"Error in watermark_image_handler: {e}")
        await message.answer("❌ Помилка при обробці зображення")


@router.message(WatermarkStates.waiting_for_watermark_image)
async def watermark_wrong_content_handler(message: types.Message, state: FSMContext):
    await message.answer("❌ Надішліть зображення як фото або файл (PNG/JPEG/WEBP).")
