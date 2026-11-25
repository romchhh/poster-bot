from utils.ui_emoji import E
from texts import AddChannel, Main
from texts.messages import add_channel as add_channel_msg
from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from app.runtime import bot
from utils.client_functions import (
    check_bot_permissions, 
    get_permission_check_message, 
    get_chat_link
)
from database_functions.client_db import update_user_activity
from keyboards.client_keyboards.client_keyboards import get_start_keyboard
from keyboards.client_keyboards.add_channel_keyboards import get_add_channel_keyboard
from keyboards.client_keyboards.folder_keyboards import get_folder_selection_keyboard, get_cancel_keyboard
from database_functions.channels_db import (
    get_channel_by_id,
    add_channel,
    auto_detect_discussion_group,
)
from database_functions.folders_db import (
    get_user_folders,
    add_folder,
    check_folder_exists,
    update_channels_count
)
from states.client_states import AddChannelStates

router = Router()


@router.message(F.text == Main.add_channel)
async def add_channel_menu(message: types.Message):
    user_id = message.from_user.id
    update_user_activity(user_id)
    await message.answer(
        text=add_channel_msg.MENU,
        parse_mode="HTML",
        reply_markup=get_add_channel_keyboard(),
    )


@router.message(F.text == AddChannel.back)
async def back_to_main_menu(message: types.Message):
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    from texts.messages.main import START

    await message.answer(
        START,
        parse_mode="HTML",
        reply_markup=get_start_keyboard(user_id),
    )


@router.message(F.chat_shared)
async def process_chat_shared(message: types.Message, state: FSMContext):
    from states.client_states import CopySetup

    if await state.get_state() == CopySetup.waiting_for_destination_group.state:
        from handlers.client_handlers.copy_handlers import process_copy_destination_shared

        await process_copy_destination_shared(message, state)
        return

    chat_id = message.chat_shared.chat_id
    user_id = message.from_user.id
    update_user_activity(user_id)
    
    try:
        chat = await bot.get_chat(chat_id)
        chat_link = get_chat_link(chat)
        chat_type_ukr = "Канал" if chat.type == "channel" else "Група"
        
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            if member.status not in ['administrator', 'creator']:
                await message.answer(
                    text=f"""❌ <b>Ви не є адміністратором!</b>

{E.channel} {chat_type_ukr}: <a href="{chat_link}">{chat.title}</a>

⚠️ Недостатньо прав: щоб додати {chat_type_ukr.lower()} до бота, ви повинні бути адміністратором.""",
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                return
            user_role = "owner" if member.status == "creator" else "admin"
        except TelegramBadRequest as e:
            if "member list is inaccessible" in str(e):
                await message.answer(
                    text=f"""❌ <b>Недостатньо прав користувача</b>

{E.channel} {chat_type_ukr}: <a href="{chat_link}">{chat.title}</a>

⚠️ Не вдалося перевірити вашу роль у {chat_type_ukr.lower()}.
Переконайтеся, що ви є адміністратором цього чату та спробуйте ще раз.""",
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                return
            else:
                print(f"❌ Помилка перевірки прав користувача: {e}")
                await message.answer(
                    text=f"""❌ <b>Помилка при додаванні</b>

{E.channel} {chat_type_ukr}: <a href="{chat_link}">{chat.title}</a>

⚠️ Не вдалося перевірити ваші права. Переконайтеся, що:
• Ви є адміністратором каналу/групи
• Бот доданий як адміністратор з необхідними правами
• Канал/група не має обмежень доступу

Спробуйте ще раз або зверніться в підтримку.""",
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                return
        except Exception as e:
            print(f"❌ Помилка перевірки прав користувача: {e}")
            await message.answer(
                text="❌ <b>Помилка при додаванні</b>\n\nСталася помилка при додаванні каналу/групи. Спробуйте ще раз або зверніться в підтримку.",
                parse_mode="HTML"
            )
            return
        
        permission_result = await check_bot_permissions(bot, chat_id)
        
        if not permission_result['has_all_permissions']:
            error_type = permission_result.get('error_type', None)
            
            if error_type == 'member_list_inaccessible':
                await message.answer(
                    text=f"""❌ <b>Бот не доданий як адміністратор!</b>

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

<i>⚠️ Після додавання бота адміністратором, спробуйте додати канал ще раз через кнопку "Додати канал" в меню.</i>""",
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                return
            
            if not permission_result['is_admin']:
                await message.answer(
                    text=f"""❌ <b>Бот не є адміністратором!</b>

{E.channel} {chat_type_ukr}: <a href="{chat_link}">{chat.title}</a>

⚠️ Спочатку додайте бота як адміністратора з наступними правами:
• Публікувати повідомлення
• Редагувати повідомлення інших користувачів
• Видаляти повідомлення інших користувачів

Після цього спробуйте знову.""",
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            else:
                missing_perms = '\n'.join([f"• {perm}" for perm in permission_result['missing_permissions']])
                await message.answer(
                    text=f"""{E.warn} <b>Недостатньо прав бота!</b>

{E.channel} {chat_type_ukr}: <a href="{chat_link}">{chat.title}</a>

❌ Боту потрібні наступні права адміністратора:
{missing_perms}

Надайте боту ці права та спробуйте знову.""",
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            return
        
        await state.update_data(
            channel_id=chat_id,
            channel_title=chat.title,
            channel_username=chat.username or "",
            channel_link=chat_link,
            chat_type=chat.type,
            user_channel_role=user_role
        )
        
        if chat.type == 'channel':
            await auto_detect_discussion_group(bot, chat_id)
        
        folders = get_user_folders(user_id)
        
        if folders:
            text = f"""✅ <b>Канал перевірено!</b>

{E.channel} {chat_type_ukr}: <a href="{chat_link}">{chat.title}</a>

{E.folder} <b>Виберіть папку для каналу:</b>"""
        else:
            text = f"""✅ <b>Канал перевірено!</b>

{E.channel} {chat_type_ukr}: <a href="{chat_link}">{chat.title}</a>

{E.folder} <b>У вас поки немає папок.</b>
Ви можете створити нову папку або додати канал без папки."""
        
        await message.answer(
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=get_folder_selection_keyboard(user_id)
        )
        
        await state.set_state(AddChannelStates.waiting_for_folder_choice)
        
    except TelegramBadRequest as e:
        print(f"❌ Помилка в add_channel_handlers: {e}")
        if "chat not found" in str(e).lower():
            await message.answer(
                text=(
                    "❌ <b>Канал/групу не знайдено</b>\n\n"
                    "Спочатку додайте бота в канал/групу та призначте його <b>адміністратором</b>, "
                    "після цього повторіть додавання."
                ),
                parse_mode="HTML"
            )
            return
        await message.answer(
            text="❌ <b>Помилка при додаванні</b>\n\nСталася помилка при додаванні каналу/групи. Спробуйте ще раз або зверніться в підтримку.",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"❌ Помилка в add_channel_handlers: {e}")
        await message.answer(
            text="❌ <b>Помилка при додаванні</b>\n\nСталася помилка при додаванні каналу/групи. Спробуйте ще раз або зверніться в підтримку.",
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("select_folder_"))
async def select_folder_callback(callback: types.CallbackQuery, state: FSMContext):
    folder_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    data = await state.get_data()
    channel_id = data.get('channel_id')
    
    if not channel_id:
        await callback.answer("⚠️ Дані каналу не знайдено. Спробуйте ще раз.")
        return
    
    channel_title = data.get('channel_title')
    channel_username = data.get('channel_username')
    channel_link = data.get('channel_link')
    chat_type = data.get('chat_type')
    
    from database_functions.billing_db import ChannelLimitError

    try:
        is_new = add_channel(
            channel_id=channel_id,
            channel_title=channel_title,
            channel_username=channel_username,
            channel_link=channel_link,
            added_by_user_id=user_id,
            chat_type=chat_type,
            folder_id=folder_id,
            user_role=data.get('user_channel_role', 'admin')
        )
    except ChannelLimitError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    
    from database_functions.folders_db import get_folder_by_id
    folder_info = get_folder_by_id(folder_id)
    folder_name = folder_info[1] if folder_info else "Папка"
    
    chat_type_ukr = "Канал" if chat_type == "channel" else "Група"
    
    if chat_type == 'channel':
        text = f"""✅ <b>Канал успішно додано!</b>

{E.channel} Канал: <a href="{channel_link}">{channel_title}</a>
{E.folder} Папка: <b>{folder_name}</b>
🆔 ID: <code>{channel_id}</code>

Тепер ви можете публікувати пости в цей канал через бота."""
    else:
        text = f"""✅ <b>Група успішно додана!</b>

💬 Група: <a href="{channel_link}">{channel_title}</a>
{E.folder} Папка: <b>{folder_name}</b>
🆔 ID: <code>{channel_id}</code>

Тепер ви можете керувати цією групою через бота."""
    
    await callback.message.edit_text(
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    
    await state.clear()
    await callback.answer("✅ Канал додано!")


@router.callback_query(F.data == "create_new_folder")
async def create_new_folder_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обробка створення нової папки"""
    await callback.message.edit_text(
        text=f"{E.folder} <b>Створення нової папки</b>\n\nВведіть назву нової папки (до 50 символів):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    
    await state.set_state(AddChannelStates.waiting_for_new_folder_name)
    await callback.answer()


@router.message(AddChannelStates.waiting_for_new_folder_name)
async def process_new_folder_name(message: types.Message, state: FSMContext):
    """Обробка назви нової папки"""
    user_id = message.from_user.id
    folder_name = message.text.strip()
    
    # Перевіряємо довжину назви
    if len(folder_name) > 50:
        await message.answer(
            text="❌ <b>Помилка!</b>\n\nНазва папки занадто довга. Максимум 50 символів.",
            parse_mode="HTML"
        )
        return
    
    if len(folder_name) < 1:
        await message.answer(
            text="❌ <b>Помилка!</b>\n\nНазва папки не може бути порожньою.",
            parse_mode="HTML"
        )
        return
    
    # Перевіряємо чи папка вже існує
    if check_folder_exists(folder_name, user_id):
        await message.answer(
            text=f"❌ <b>Помилка!</b>\n\nПапка з назвою <b>{folder_name}</b> вже існує.",
            parse_mode="HTML"
        )
        return
    
    # Створюємо папку
    folder_id = add_folder(folder_name, user_id)
    
    if not folder_id:
        await message.answer(
            text="❌ <b>Помилка при створенні папки!</b>\n\nСпробуйте ще раз.",
            parse_mode="HTML"
        )
        return
    
    # Отримуємо дані зі state
    data = await state.get_data()
    channel_id = data.get('channel_id')
    move_channel_id = data.get('move_channel_id')  # Для вже доданих каналів
    
    # Якщо це для вже доданого каналу (подія my_chat_member обробляється в channel_track_handlers)
    if move_channel_id:
        from database_functions.channels_db import set_channel_folder
        set_channel_folder(move_channel_id, folder_id)
        
        channel_info = get_channel_by_id(move_channel_id)
        if channel_info:
            channel_title = channel_info[2]
            channel_link = channel_info[4]
            
            text = f"""✅ <b>Папка створена і канал переміщено!</b>

{E.channel} Канал: <a href="{channel_link}">{channel_title}</a>
{E.folder} Папка: <b>{folder_name}</b> (нова)

Канал успішно додано до нової папки."""
    
    # Якщо це звичайне додавання каналу
    elif channel_id:
        channel_title = data.get('channel_title')
        channel_username = data.get('channel_username')
        channel_link = data.get('channel_link')
        chat_type = data.get('chat_type')
        
        # Додаємо канал з новою папкою
        from database_functions.billing_db import ChannelLimitError

        try:
            is_new = add_channel(
                channel_id=channel_id,
                channel_title=channel_title,
                channel_username=channel_username,
                channel_link=channel_link,
                added_by_user_id=user_id,
                chat_type=chat_type,
                folder_id=folder_id,
                user_role=data.get('user_channel_role', 'admin')
            )
        except ChannelLimitError as exc:
            await message.answer(str(exc))
            return
        
        chat_type_ukr = "Канал" if chat_type == "channel" else "Група"
        
        if chat_type == 'channel':
            text = f"""✅ <b>Канал успішно додано!</b>

{E.channel} Канал: <a href="{channel_link}">{channel_title}</a>
{E.folder} Папка: <b>{folder_name}</b> (нова)
🆔 ID: <code>{channel_id}</code>

Тепер ви можете публікувати пости в цей канал через бота."""
        else:
            text = f"""✅ <b>Група успішно додана!</b>

💬 Група: <a href="{channel_link}">{channel_title}</a>
{E.folder} Папка: <b>{folder_name}</b> (нова)
🆔 ID: <code>{channel_id}</code>

Тепер ви можете керувати цією групою через бота."""
    else:
        text = "✅ Папку створено!"
    
    await message.answer(
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    
    await state.clear()


@router.callback_query(F.data == "add_without_folder")
async def add_without_folder_callback(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    data = await state.get_data()
    channel_id = data.get('channel_id')
    channel_title = data.get('channel_title')
    channel_username = data.get('channel_username')
    channel_link = data.get('channel_link')
    chat_type = data.get('chat_type')
    
    from database_functions.billing_db import ChannelLimitError

    try:
        is_new = add_channel(
            channel_id=channel_id,
            channel_title=channel_title,
            channel_username=channel_username,
            channel_link=channel_link,
            added_by_user_id=user_id,
            chat_type=chat_type,
            folder_id=None,
            user_role=data.get('user_channel_role', 'admin')
        )
    except ChannelLimitError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    
    chat_type_ukr = "Канал" if chat_type == "channel" else "Група"
    
    if chat_type == 'channel':
        text = f"""✅ <b>Канал успішно додано!</b>

{E.channel} Канал: <a href="{channel_link}">{channel_title}</a>
{E.folder} Папка: <i>без папки</i>
🆔 ID: <code>{channel_id}</code>

Тепер ви можете публікувати пости в цей канал через бота."""
    else:
        text = f"""✅ <b>Група успішно додана!</b>

💬 Група: <a href="{channel_link}">{channel_title}</a>
{E.folder} Папка: <i>без папки</i>
🆔 ID: <code>{channel_id}</code>

Тепер ви можете керувати цією групою через бота."""
    
    await callback.message.edit_text(
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    
    await state.clear()
    await callback.answer("✅ Канал додано!")


@router.callback_query(F.data == "cancel_folder_creation")
async def cancel_folder_creation_callback(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    await callback.message.edit_text(
        text="❌ Створення папки скасовано.\n\nВиберіть дію:",
        parse_mode="HTML",
        reply_markup=get_folder_selection_keyboard(user_id)
    )
    
    await state.set_state(AddChannelStates.waiting_for_folder_choice)
    await callback.answer()


@router.callback_query(F.data.startswith("move_to_folder_"))
async def move_to_folder_callback(callback: types.CallbackQuery):
    """Переміщення каналу в папку"""
    parts = callback.data.split("_")
    folder_id = int(parts[3])
    channel_id = int(parts[4])
    
    from database_functions.channels_db import set_channel_folder
    set_channel_folder(channel_id, folder_id)
    
    from database_functions.folders_db import get_folder_by_id
    folder_info = get_folder_by_id(folder_id)
    folder_name = folder_info[1] if folder_info else "Папка"
    
    channel_info = get_channel_by_id(channel_id)
    if channel_info:
        channel_title = channel_info[2]
        channel_link = channel_info[4]
        
        await callback.message.edit_text(
            text=f"""✅ <b>Канал переміщено в папку!</b>

{E.channel} Канал: <a href="{channel_link}">{channel_title}</a>
{E.folder} Папка: <b>{folder_name}</b>

Канал успішно додано до папки.""",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    
    await callback.answer("✅ Переміщено!")


@router.callback_query(F.data.startswith("create_folder_for_"))
async def create_folder_for_channel_callback(callback: types.CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split("_")[3])
    
    await state.update_data(move_channel_id=channel_id)
    
    await callback.message.edit_text(
        text=f"{E.folder} <b>Створення нової папки</b>\n\nВведіть назву нової папки (до 50 символів):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    
    await state.set_state(AddChannelStates.waiting_for_new_folder_name)
    await callback.answer()


@router.callback_query(F.data.startswith("skip_folder_"))
async def skip_folder_callback(callback: types.CallbackQuery):
    channel_id = int(callback.data.split("_")[2])
    
    channel_info = get_channel_by_id(channel_id)
    if channel_info:
        channel_title = channel_info[2]
        channel_link = channel_info[4]
        
        await callback.message.edit_text(
            text=f"""✅ <b>Канал додано!</b>

{E.channel} Канал: <a href="{channel_link}">{channel_title}</a>
{E.folder} Папка: <i>без папки</i>

Ви завжди можете перемістити канал в папку пізніше.""",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    
    await callback.answer("✅")
