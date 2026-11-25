from utils.ui_emoji import E, Icon
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest
from app.runtime import bot
from utils.safe_telegram import safe_edit_text
from database_functions.client_db import (
    get_user_confirm_publish_status,
    update_user_activity,
)
from database_functions.channels_db import (
    get_all_channels,
    get_channel_by_id,
    get_channels_by_folder,
    get_channels_without_folder,
    add_channel,
    auto_detect_discussion_group,
)
from database_functions.folders_db import get_user_folders
from database_functions.auto_signatures_db import get_auto_signature
from database_functions.channel_start_emoji_db import get_channel_start_emoji
from keyboards.client_keyboards.post_keyboards import (
    get_ai_variants_keyboard,
    get_post_ai_keyboard,
    get_post_editing_keyboard,
    get_publishing_menu_keyboard,
    get_auto_delete_keyboard,
    get_confirmation_keyboard,
    get_channels_main_menu_keyboard,
    get_folder_channels_keyboard,
    get_post_all_channels_select_keyboard,
    get_step_cancel_keyboard,
    get_url_buttons_prompt_keyboard,
)
from texts.messages import post as post_msg
from utils.album import album_to_post_parts, clear_url_buttons, take_album
from utils.post_utils import (
    apply_palette_style,
    parse_url_buttons_with_entities,
    send_post_preview,
    url_button_count,
    validate_post_data,
    MAX_URL_BUTTONS,
)
from utils.post_schedule_utils import ensure_post_url_buttons_in_state
from utils.watermark_utils import apply_watermark_to_telegram_photo
from utils.client_functions import check_bot_permissions, get_chat_link, get_permission_check_message
from states.client_states import PostCreation, PostEditing


router = Router()

# Тексти reply-клавіатури й команди: під час створення поста переходимо в інший сценарій
_POST_CREATION_EXIT_TEXTS = frozenset(
    {
        "Створити пост",
        "Додати канал",
        "Добавить канал",
        "Контент-план",
        "Контент план",
        "📋 Контент-план",
        "📋 Контент план",
        "Редагувати пост",
        "Редактировать пост",
        "Edit Post",
        "/edit_post",
        "Налаштування",
        "Настройки",
        "Settings",
        "/settings",
        "Підтримка",
        "/support",
        "Адмін панель",
        "Адмін панель 💻",
        "/admin",
        "Создать пост",
        "Копіювання",
        "Пошук постів",
    }
)


@router.message(StateFilter(PostCreation), CommandStart())
async def cancel_post_creation_on_start(message: types.Message, state: FSMContext):
    await state.clear()
    from handlers.client_handlers.client_handlers import start_command

    await start_command(message)


@router.message(StateFilter(PostCreation), F.text.in_(_POST_CREATION_EXIT_TEXTS))
async def cancel_post_creation_on_main_nav(message: types.Message, state: FSMContext):
    """Якщо користувач натискає іншу кнопку меню під час створення поста."""
    txt = (message.text or "").strip()
    await state.clear()

    if txt in {"Редагувати пост", "Редактировать пост", "Edit Post", "/edit_post"}:
        from handlers.client_handlers import edit_post_handlers

        await edit_post_handlers.start_edit_post(message, state)
        return

    if txt == "Створити пост" or txt == "Создать пост":
        await create_post_start(message, state)
        return

    if txt in {"Додати канал", "Добавить канал"}:
        from handlers.client_handlers.add_channel_handlers import add_channel_menu

        await add_channel_menu(message)
        return

    if txt in {
        "Контент-план",
        "Контент план",
        "📋 Контент-план",
        "📋 Контент план",
    }:
        from handlers.client_handlers.content_plan_handlers import content_plan_start

        await content_plan_start(message, state)
        return

    if txt in {"Налаштування", "Настройки", "Settings", "/settings"}:
        from handlers.client_handlers.settings_handlers import settings_menu

        await settings_menu(message, state)
        return

    if txt in {"Підтримка", "/support"}:
        from handlers.client_handlers.client_handlers import support

        await support(message)
        return

    if txt in {"Адмін панель", "Адмін панель 💻", "/admin"}:
        from handlers.admin_handlers.admin_handlers import admin_panel

        await admin_panel(message)
        return

    if txt == "Копіювання":
        from handlers.client_handlers.copy_handlers import copy_mirror_entry

        await copy_mirror_entry(message, state)
        return

    if txt == "Пошук постів":
        from handlers.client_handlers.post_search_handlers import search_start

        await search_start(message, state)
        return

    # Нові пункти меню без гілки — вже немає сценарію створення поста (стан скинуто).


# ID повідомлень чернеткового превʼю в особистому чаті (для видалення перед новим превʼю)
_POST_EDITING_PREVIEW_IDS_KEY = "post_editing_preview_message_ids"


async def _replace_editing_post_preview(
    bot, chat_id: int, post_data: dict, state: FSMContext
) -> None:
    """Видаляє попереднє превʼю чернетки та надсилає нове; оновлює список message_id у стані."""
    data = await state.get_data()
    for mid in data.get(_POST_EDITING_PREVIEW_IDS_KEY) or []:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass
    new_ids: list = []
    try:
        await send_post_preview(
            bot, chat_id, post_data, preview_message_ids=new_ids
        )
    except Exception as e:
        print(f"Помилка превʼю (чернетка): {e}")
    await state.update_data(**{_POST_EDITING_PREVIEW_IDS_KEY: new_ids})


def _transient_publish_error(error: str | None) -> bool:
    text = (error or "").lower()
    return any(token in text for token in ("timeout", "retry", "flood", "network", "bad gateway"))


async def _execute_immediate_publish(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    from services.posts.delivery import deliver_post_to_channel

    from database_functions.billing_db import denial

    reason = denial(callback.from_user.id, "posting")
    if reason:
        await callback.answer(reason, show_alert=True)
        return

    data = await state.get_data()
    post_data = data.get("post_data", {})
    selected_channels = data.get("selected_channels", [])

    await callback.message.edit_text(f"{E.send} <b>Публікація...</b>", parse_mode="HTML")

    success_count = 0
    failed_channels = []
    skipped_channels = []
    url_error = False
    published_links = []

    for channel_id in selected_channels:
        result = await deliver_post_to_channel(
            bot,
            user_id=callback.from_user.id,
            channel_id=channel_id,
            post_data=post_data,
        )
        if (
            not result.ok
            and not result.skipped
            and not result.url_error
            and _transient_publish_error(result.error)
        ):
            result = await deliver_post_to_channel(
                bot,
                user_id=callback.from_user.id,
                channel_id=channel_id,
                post_data=post_data,
            )
        if result.skipped:
            skipped_channels.append(channel_id)
            continue
        if result.ok:
            success_count += 1
            if result.post_link and result.channel_title:
                published_links.append(
                    {"title": result.channel_title, "link": result.post_link}
                )
        else:
            failed_channels.append(channel_id)
            if result.url_error:
                url_error = True

    if url_error:
        await callback.message.edit_text(
            text="""❌ <b>Помилка в URL-кнопках!</b>

⚠️ Одне або декілька посилань мають неправильний формат.

<b>Перевірте:</b>
• Посилання має починатися з <code>http://</code> або <code>https://</code>
• Після посилання не повинно бути зайвих символів або пробілів
• Формат: <code>Текст кнопки - https://приклад.com</code>

<b>Приклади правильного формату:</b>
<code>Сайт - https://example.com
Instagram - https://instagram.com/username
Telegram - https://t.me/channel</code>

<b>Приклади з кольорами:</b>
<code>Кнопка - https://site.com::red
!g Кнопка - https://site.com</code>

📝 Відредагуйте кнопки через меню редагування та спробуйте знову.""",
            parse_mode="HTML",
        )
    elif success_count > 0:
        result_text = (
            f"✅ <b>Пост опубліковано!</b>\n\n📢 Опубліковано в {success_count} канал(ів)"
        )

        if failed_channels:
            result_text += (
                f"\n⚠️ Не вдалося опублікувати в {len(failed_channels)} канал(ів)"
            )
        if skipped_channels:
            result_text += (
                f"\n🚫 Пропущено через чорний список: {len(skipped_channels)}"
            )
        if success_count and failed_channels:
            result_text += "\nСтатус: опубліковано частково"
        elif success_count:
            result_text += "\nСтатус: опубліковано"
        links_kb = None
        if published_links:
            link_rows = [
                [InlineKeyboardButton(text=f"{item['title'][:45]}", url=item["link"], icon_custom_emoji_id=Icon.doc)]
                for item in published_links
            ]
            links_kb = InlineKeyboardMarkup(inline_keyboard=link_rows[:20])

        await callback.message.edit_text(
            text=result_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=links_kb,
        )
    else:
        await callback.message.edit_text(
            text="❌ <b>Помилка публікації</b>\n\nПост не вдалося опублікувати в жоден канал.",
            parse_mode="HTML",
        )

    await state.clear()
    await callback.answer("✅ Готово!")


@router.message(F.text == "Створити пост")
async def create_post_start(message: types.Message, state: FSMContext):
    """Початок створення поста"""
    user_id = message.from_user.id
    update_user_activity(user_id)
    from database_functions.billing_db import denial

    reason = denial(user_id, "posting")
    if reason:
        await message.answer(reason)
        return

    await state.clear()
    
    # Отримуємо канали та папки користувача
    user_channels = get_all_channels(user_id=user_id, only_active=True)
    user_folders = get_user_folders(user_id)
    channels_no_folder = get_channels_without_folder(user_id)
    
    if not user_channels:
        # Отримуємо інформацію про бота для створення посилань
        bot_info = await bot.get_me()
        bot_username = bot_info.username
        
        # Створюємо посилання для додавання бота в канал/групу з правами адміністратора
        add_channel_url = f"https://t.me/{bot_username}?startchannel=&admin=post_messages+edit_messages+delete_messages"
        add_group_url = f"https://t.me/{bot_username}?startgroup=&admin=post_messages+edit_messages+delete_messages"
        
        # Створюємо інлайн-кнопки
        add_channel_button = InlineKeyboardButton(
            text="Додати канал",
            url=add_channel_url,
        icon_custom_emoji_id=Icon.add,
    )
        add_group_button = InlineKeyboardButton(
            text="Додати групу", 
            url=add_group_url,
        icon_custom_emoji_id=Icon.add,
    )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[add_channel_button, add_group_button]])
        
        await message.answer(
            text="""❌ <b>У вас немає доданих каналів!</b>

📢 <b>Як додати канал або групу:</b>

<b>Крок 1:</b> Натисніть одну з кнопок нижче
<b>Крок 2:</b> Оберіть канал або групу зі списку
<b>Крок 3:</b> Підтвердьте надання прав адміністратора боту

<i>⚠️ Важливо: Ви повинні бути адміністратором каналу/групи, яку додаєте.</i>

<blockquote>💡 Після додавання бота в адміни канал зазвичай зʼявляється в списку автоматично. Якщо цього не сталося — <b>перешліть у цей чат будь-яке повідомлення з каналу</b> (пересиланням), поки бот уже має права на постинг.</blockquote>

<blockquote>💡 Бот автоматично отримає необхідні права для публікації, редагування та видалення постів.</blockquote>""",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return
    
    # Якщо один канал - одразу починаємо створення
    if len(user_channels) == 1:
        channel = user_channels[0]
        channel_id = channel[1]
        channel_title = channel[2]
        
        await state.update_data(
            selected_channels=[channel_id],
            post_data={
                'text': None,
                'media_files': [],
                'url_buttons': [],
                'settings': default_post_settings()
            }
        )
        
        await message.answer(
            text=f"""{E.sign} <b>Створення поста</b>

📢 Канал: <b>{channel_title}</b>

📝 Надішліть текст поста або медіафайли (фото/відео/документ).

Ви можете надіслати:
• Текст
• Фото/Відео/Документ з підписом
• Медіагрупу (до 10 файлів)""",
            parse_mode="HTML",
            reply_markup=get_step_cancel_keyboard("cancel_post_creation"),
        )
        
        await state.set_state(PostCreation.waiting_for_content)
    
    # Якщо декілька каналів - показуємо меню з папками
    else:
        menu_text = post_msg.multi_channel_selection([], user_channels)

        await message.answer(
            text=menu_text,
            parse_mode="HTML",
            reply_markup=get_channels_main_menu_keyboard(
                user_folders, channels_no_folder, []
            ),
        )
        
        await state.update_data(
            selected_channels=[],
            all_channels=user_channels,
            user_folders=user_folders,
            channels_no_folder=channels_no_folder,
            selection_screen="menu",
            current_folder_id=None,
        )
        await state.set_state(PostCreation.selecting_channels)


@router.callback_query(F.data == "post_view_all_channels", PostCreation.selecting_channels)
async def post_view_all_channels_callback(
    callback: types.CallbackQuery, state: FSMContext
):
    data = await state.get_data()
    rows = data.get("all_channels") or []
    selected = data.get("selected_channels", [])
    await state.update_data(selection_screen="view_all")
    await callback.message.edit_text(
        text=post_msg.all_channels_view(selected, rows),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=get_post_all_channels_select_keyboard(rows, selected),
    )
    await callback.answer()


@router.callback_query(
    F.data.startswith("post_all_toggle_"), PostCreation.selecting_channels
)
async def post_all_toggle_channel_callback(
    callback: types.CallbackQuery, state: FSMContext
):
    channel_id = int(callback.data.removeprefix("post_all_toggle_"))
    data = await state.get_data()
    selected = list(data.get("selected_channels") or [])
    if channel_id in selected:
        selected.remove(channel_id)
        tip = "знято"
    else:
        selected.append(channel_id)
        tip = "обрано"

    await state.update_data(selected_channels=selected, selection_screen="view_all")
    rows = data.get("all_channels") or []
    await callback.message.edit_text(
        text=post_msg.all_channels_view(selected, rows),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=get_post_all_channels_select_keyboard(rows, selected),
    )
    await callback.answer(f"✅ {tip}")


@router.callback_query(F.data == "post_view_all_channels_back", PostCreation.selecting_channels)
async def post_view_all_channels_back_callback(
    callback: types.CallbackQuery, state: FSMContext
):
    data = await state.get_data()
    user_folders = data.get("user_folders", [])
    channels_no_folder = data.get("channels_no_folder", [])
    selected = data.get("selected_channels", [])
    all_ch = data.get("all_channels", [])
    await state.update_data(selection_screen="menu", current_folder_id=None)
    await callback.message.edit_text(
        text=post_msg.multi_channel_selection(selected, all_ch),
        parse_mode="HTML",
        reply_markup=get_channels_main_menu_keyboard(
            user_folders, channels_no_folder, selected
        ),
    )
    await callback.answer()


@router.message(PostCreation.selecting_channels, F.forward_from_chat)
async def post_selection_import_forwarded_channel(
    message: types.Message, state: FSMContext
):
    """Якщо бот уже адмін, а каналу не було в БД — додаємо за пересланим постом."""
    fc = message.forward_from_chat
    if fc is None or fc.type not in ("channel", "supergroup", "group"):
        return

    user_id = message.from_user.id
    try:
        user_member = await bot.get_chat_member(fc.id, user_id)
        if user_member.status not in ("administrator", "creator"):
            await message.answer(
                "❌ У цьому чаті потрібні права <b>адміністратора</b>, щоб привʼязати канал.",
                parse_mode="HTML",
            )
            return
    except TelegramBadRequest:
        await message.answer(
            "❌ Не вдалося перевірити ваші права в цьому чаті.",
            parse_mode="HTML",
        )
        return

    chat = await bot.get_chat(fc.id)
    link = get_chat_link(chat)
    perm = await check_bot_permissions(bot, fc.id)
    if not perm["has_all_permissions"]:
        await message.answer(
            get_permission_check_message(chat.title or "", link, perm),
            parse_mode="HTML",
        )
        return

    user_role = "owner" if user_member.status == "creator" else "admin"
    from database_functions.billing_db import ChannelLimitError

    try:
        add_channel(
        channel_id=chat.id,
        channel_title=chat.title or "",
        channel_username=chat.username or "",
        channel_link=link,
        added_by_user_id=user_id,
        chat_type=chat.type,
        folder_id=None,
        user_role=user_role,
        )
    except ChannelLimitError as exc:
        await message.answer(str(exc))
        return
    if chat.type == "channel":
        await auto_detect_discussion_group(bot, chat.id)

    user_channels = get_all_channels(user_id=user_id, only_active=True)
    user_folders = get_user_folders(user_id)
    channels_no_folder = get_channels_without_folder(user_id)
    await state.update_data(
        all_channels=user_channels,
        user_folders=user_folders,
        channels_no_folder=channels_no_folder,
    )
    data = await state.get_data()
    sel = data.get("selected_channels", [])

    await message.answer(
        text=(
            f"✅ <b>Канал додано:</b> {chat.title or chat.id}\n\n"
            + post_msg.multi_channel_selection(sel, user_channels)
        ),
        parse_mode="HTML",
        reply_markup=get_channels_main_menu_keyboard(
            user_folders, channels_no_folder, sel
        ),
    )

    folders = get_user_folders(user_id)
    if folders:
        from keyboards.client_keyboards.folder_keyboards import (
            get_folder_move_keyboard,
        )

        await message.answer(
            text=f"{E.folder} <b>Перемістити канал у папку?</b> Оберіть нижче або ігноруйте.",
            parse_mode="HTML",
            reply_markup=get_folder_move_keyboard(user_id, chat.id),
        )


@router.callback_query(F.data == "select_all_channels", PostCreation.selecting_channels)
async def select_all_channels_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обирає всі канали"""
    data = await state.get_data()
    all_channels = data.get('all_channels', [])
    
    selected = [ch[1] for ch in all_channels]
    await state.update_data(selected_channels=selected)

    data = await state.get_data()
    user_folders = data.get("user_folders", [])
    channels_no_folder = data.get("channels_no_folder", [])
    all_channels = data.get("all_channels", [])

    await callback.answer(f"✅ Обрано всі канали ({len(selected)})")

    await callback.message.edit_text(
        text=post_msg.multi_channel_selection(selected, all_channels),
        parse_mode="HTML",
        reply_markup=get_channels_main_menu_keyboard(
            user_folders, channels_no_folder, selected
        ),
    )


@router.callback_query(F.data == "select_all_folders", PostCreation.selecting_channels)
async def select_all_folders_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = list(data.get("selected_channels") or [])
    added = 0
    for folder in data.get("user_folders") or []:
        for channel in get_channels_by_folder(folder[0]):
            channel_id = channel[1]
            if channel_id not in selected:
                selected.append(channel_id)
                added += 1
    if not added and not selected:
        await callback.answer("У папках немає каналів", show_alert=True)
        return
    await state.update_data(selected_channels=selected)
    data = await state.get_data()
    await callback.message.edit_text(
        text=post_msg.multi_channel_selection(
            selected, data.get("all_channels", [])
        ),
        parse_mode="HTML",
        reply_markup=get_channels_main_menu_keyboard(
            data.get("user_folders", []),
            data.get("channels_no_folder", []),
            selected,
        ),
    )
    await callback.answer(f"✅ Папки додано, разом {len(selected)}")


@router.callback_query(F.data.startswith("select_post_folder_"), PostCreation.selecting_channels)
async def select_folder_callback(callback: types.CallbackQuery, state: FSMContext):
    """Показує канали з обраної папки"""
    folder_id = int(callback.data.split("_")[3])  # Змінено з [2] на [3] бо prefix довший
    
    data = await state.get_data()
    selected_channels = data.get('selected_channels', [])
    
    # Отримуємо канали папки
    folder_channels = get_channels_by_folder(folder_id)
    
    if not folder_channels:
        await callback.answer("❌ У папці немає каналів", show_alert=True)
        return
    
    # Отримуємо назву папки
    user_folders = data.get('user_folders', [])
    folder_name = next((f[1] for f in user_folders if f[0] == folder_id), "Папка")
    
    await callback.message.edit_text(
        text=post_msg.folder_selection(
            folder_name,
            folder_channels,
            selected_channels,
            data.get("all_channels", []),
        ),
        parse_mode="HTML",
        reply_markup=get_folder_channels_keyboard(
            folder_id, folder_channels, selected_channels
        ),
    )
    
    await state.update_data(current_folder_id=folder_id, selection_screen="folder")
    await callback.answer()


@router.callback_query(F.data.startswith("select_whole_folder_"), PostCreation.selecting_channels)
async def select_whole_folder_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обирає всю папку"""
    folder_id = int(callback.data.split("_")[3])
    
    data = await state.get_data()
    selected_channels = data.get('selected_channels', [])
    
    # Отримуємо всі канали папки
    folder_channels = get_channels_by_folder(folder_id)
    folder_channel_ids = [ch[1] for ch in folder_channels]
    
    # Додаємо до вибраних (без дублікатів)
    for ch_id in folder_channel_ids:
        if ch_id not in selected_channels:
            selected_channels.append(ch_id)
    
    await state.update_data(selected_channels=selected_channels)
    
    await callback.answer(f"✅ Обрано всю папку ({len(folder_channel_ids)} каналів)")

    data = await state.get_data()
    user_folders = data.get("user_folders", [])
    folder_name = next(
        (f[1] for f in user_folders if f[0] == folder_id), "Папка"
    )
    await callback.message.edit_text(
        text=post_msg.folder_selection(
            folder_name,
            folder_channels,
            selected_channels,
            data.get("all_channels", []),
        ),
        parse_mode="HTML",
        reply_markup=get_folder_channels_keyboard(
            folder_id, folder_channels, selected_channels
        ),
    )


@router.callback_query(F.data == "back_to_folders_menu", PostCreation.selecting_channels)
async def back_to_folders_menu_callback(callback: types.CallbackQuery, state: FSMContext):
    """Повертає до головного меню папок"""
    data = await state.get_data()
    user_folders = data.get('user_folders', [])
    channels_no_folder = data.get('channels_no_folder', [])
    
    await state.update_data(current_folder_id=None, selection_screen="menu")
    sel = data.get("selected_channels", [])
    all_ch = data.get("all_channels", [])
    await callback.message.edit_text(
        text=post_msg.multi_channel_selection(sel, all_ch),
        parse_mode="HTML",
        reply_markup=get_channels_main_menu_keyboard(
            user_folders, channels_no_folder, sel
        ),
    )
    
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_channel_"), PostCreation.selecting_channels)
async def toggle_channel_selection(callback: types.CallbackQuery, state: FSMContext):
    """Перемикає вибір окремого каналу"""
    channel_id = int(callback.data.removeprefix("toggle_channel_"))
    
    data = await state.get_data()
    selected = data.get('selected_channels', [])
    current_folder_id = data.get('current_folder_id')
    user_folders = data.get('user_folders', [])
    channels_no_folder = data.get('channels_no_folder', [])
    selection_screen = data.get('selection_screen', 'menu')
    
    if channel_id in selected:
        selected.remove(channel_id)
        action = "знято"
    else:
        selected.append(channel_id)
        action = "обрано"
    
    await state.update_data(selected_channels=selected)

    all_ch = data.get("all_channels", [])

    if selection_screen == "folder" and current_folder_id is not None:
        folder_channels = get_channels_by_folder(current_folder_id)
        folder_name = next(
            (f[1] for f in user_folders if f[0] == current_folder_id), "Папка"
        )
        await callback.message.edit_text(
            text=post_msg.folder_selection(
                folder_name,
                folder_channels,
                selected,
                all_ch,
            ),
            parse_mode="HTML",
            reply_markup=get_folder_channels_keyboard(
                current_folder_id, folder_channels, selected
            ),
        )
    elif selection_screen == "no_folder":
        user_id = callback.from_user.id
        ch_nf = get_channels_without_folder(user_id)
        from keyboards.client_keyboards.post_keyboards import (
            get_no_folder_channels_keyboard,
        )

        await callback.message.edit_reply_markup(
            reply_markup=get_no_folder_channels_keyboard(ch_nf, selected)
        )
    else:
        await callback.message.edit_text(
            text=post_msg.multi_channel_selection(selected, all_ch),
            parse_mode="HTML",
            reply_markup=get_channels_main_menu_keyboard(
                user_folders, channels_no_folder, selected
            ),
        )

    await callback.answer(f"✅ Канал {action}")


def default_post_settings() -> dict:
    return {
        "notification": True,
        "pin_message": False,
        "disable_comments": False,
        "autosign": False,
        "content_protection": False,
        "review": False,
        "ad_top": False,
        "autorepeat": False,
        "publish_mode": "copy",
        "reply_to": None,
    }


def _empty_post_data() -> dict:
    return {
        "text": None,
        "media_files": [],
        "url_buttons": [],
        "settings": default_post_settings(),
    }


def _selected_channels_prompt_html(selected: list, all_channels: list) -> str:
    import html

    channels_by_id = {row[1]: row for row in all_channels if len(row) > 2}
    selected_lines = []
    for channel_id in selected:
        row = channels_by_id.get(channel_id)
        if not row:
            continue
        title = html.escape(row[2] or "Канал")
        link = row[4] if len(row) > 4 and row[4] else "#"
        selected_lines.append(f'• <a href="{link}">{title}</a>')

    selected_text = "\n".join(selected_lines) if selected_lines else "• Канали недоступні"
    return (
        f"{E.sign} <b>Створення поста</b>\n\n"
        f"📢 Обрано каналів: <b>{len(selected)}</b>\n\n"
        f"{selected_text}\n\n"
        f"📝 Надішліть текст поста або медіафайли."
    )


@router.callback_query(F.data == "confirm_channel_selection", PostCreation.selecting_channels)
async def confirm_channels_selection(callback: types.CallbackQuery, state: FSMContext):
    """Підтверджує вибір каналів"""
    data = await state.get_data()
    selected = data.get("selected_channels", [])
    all_channels = data.get("all_channels", [])

    if not selected:
        await callback.answer("❌ Виберіть хоча б один канал!", show_alert=True)
        return

    await state.update_data(post_data=_empty_post_data())
    await callback.message.edit_text(
        text=_selected_channels_prompt_html(selected, all_channels),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=get_step_cancel_keyboard("cancel_post_creation"),
    )
    await state.set_state(PostCreation.waiting_for_content)
    await callback.answer("✅ Канали вибрано!")


@router.message(
    PostCreation.selecting_channels,
    F.text | F.photo | F.video | F.document | F.animation | F.audio | F.voice | F.video_note,
)
async def post_selection_receive_content(message: types.Message, state: FSMContext):
    """Одразу прийняти контент поста, якщо канали вже обрані."""
    if message.forward_from_chat is not None:
        return

    data = await state.get_data()
    selected = data.get("selected_channels") or []
    if not selected:
        await message.answer(
            "❌ Спочатку оберіть хоча б один канал, потім надішліть пост.",
            parse_mode="HTML",
        )
        return

    await state.update_data(post_data=_empty_post_data())
    await state.set_state(PostCreation.waiting_for_content)
    await process_post_content(message, state)


@router.message(PostCreation.waiting_for_content)
async def process_post_content(message: types.Message, state: FSMContext):
    """Текст, один файл або медіагрупа до 10 елементів."""
    album = await take_album(message)
    if album is None:
        return

    data = await state.get_data()
    post_data = data.get('post_data', {})
    text, media_files, trimmed = album_to_post_parts(album)
    if text:
        post_data['text'] = text
    if media_files:
        post_data['media_files'] = media_files
    if len(media_files) > 1:
        clear_url_buttons(post_data)

    await state.update_data(post_data=post_data)

    if trimmed:
        await message.answer("У групі більше 10 файлів — збережено перші 10.")

    await _replace_editing_post_preview(bot, message.chat.id, post_data, state)
    await message.answer(
        text=post_msg.EDITOR_HINT,
        parse_mode="HTML",
        reply_markup=get_post_editing_keyboard(post_data)
    )
    await state.set_state(PostCreation.editing_post)


@router.callback_query(F.data == "post_step_cancel")
async def post_step_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Leave the current input step and return to the post editor."""
    data = await state.get_data()
    post_data = data.get("post_data") or {}
    await state.set_state(PostCreation.editing_post)
    await callback.message.edit_text(
        text=post_msg.EDITOR_HINT,
        parse_mode="HTML",
        reply_markup=get_post_editing_keyboard(post_data),
    )
    await callback.answer()


@router.callback_query(F.data == "post_reply_cancel")
async def post_reply_cancel(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_data = data.get("post_data") or {}
    await state.set_state(PostCreation.editing_post)
    await safe_edit_text(
        callback.message,
        text=post_msg.PUBLISH_SETTINGS,
        parse_mode="HTML",
        reply_markup=get_publishing_menu_keyboard(post_data),
    )
    await callback.answer()


@router.callback_query(F.data == "edit_text", PostCreation.editing_post)
async def edit_text_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text=f"{E.sign} <b>Редагування тексту</b>\n\nНадішліть новий текст поста:",
        parse_mode="HTML",
        reply_markup=get_step_cancel_keyboard(),
    )
    await state.set_state(PostCreation.waiting_for_text)
    await callback.answer()


@router.message(PostCreation.waiting_for_text)
async def process_new_text(message: types.Message, state: FSMContext):
    from utils.message_html import message_to_html

    data = await state.get_data()
    post_data = data.get('post_data', {})

    post_data['text'] = message_to_html(message)
    await state.update_data(post_data=post_data)
    
    # Показуємо тільки превʼю
    await _replace_editing_post_preview(bot, message.chat.id, post_data, state)

    # Одразу клавіатуру редагування
    await message.answer(
        text=post_msg.EDITOR_HINT,
        parse_mode="HTML",
        reply_markup=get_post_editing_keyboard(post_data)
    )
    
    await state.set_state(PostCreation.editing_post)


def _plain_post_text(value: str) -> str:
    import html
    import re

    text = re.sub(r"<[^>]+>", " ", value or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()[:4000]


async def _attach_generated_photo(
    message: types.Message,
    state: FSMContext,
    prompt: str,
    user_id: int | None = None,
) -> None:
    from database_functions.billing_db import refund_tokens, spend_tokens

    payer_id = message.from_user.id if user_id is None else user_id
    token_error = spend_tokens(payer_id, "image")
    if token_error:
        await message.answer(token_error)
        return
    status = await message.answer("Генерую зображення…")
    try:
        from utils.copy_utils.ai import Ai

        image_bytes = await Ai().generate_image_from_news(prompt)
        uploaded = await bot.send_photo(
            message.chat.id,
            types.BufferedInputFile(image_bytes, filename="generated.jpg"),
            disable_notification=True,
        )
        file_id = uploaded.photo[-1].file_id
        try:
            await uploaded.delete()
        except Exception:
            pass
    except Exception as exc:
        import html

        refund_tokens(payer_id, "image")
        err = html.escape(str(exc))[:180]
        try:
            await status.edit_text(
                f"❌ Не вдалося згенерувати зображення.\n<code>{err}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass
        data = await state.get_data()
        post_data = data.get("post_data") or {}
        await state.set_state(PostCreation.editing_post)
        await message.answer(
            text=post_msg.EDITOR_HINT,
            parse_mode="HTML",
            reply_markup=get_post_editing_keyboard(post_data),
        )
        return

    data = await state.get_data()
    post_data = data.get("post_data") or {}
    caption = post_data.get("text") or ""
    post_data["media_files"] = [
        {"type": "photo", "file_id": file_id, "caption": caption}
    ]
    await state.update_data(post_data=post_data)
    try:
        await status.delete()
    except Exception:
        pass
    await state.set_state(PostCreation.editing_post)
    await _replace_editing_post_preview(bot, message.chat.id, post_data, state)
    await message.answer(
        text=post_msg.EDITOR_HINT,
        parse_mode="HTML",
        reply_markup=get_post_editing_keyboard(post_data),
    )


@router.callback_query(F.data == "post_generate_image", PostCreation.editing_post)
async def post_generate_image(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_data = data.get("post_data") or {}
    source = _plain_post_text(str(post_data.get("text") or ""))
    if not source:
        await state.set_state(PostCreation.waiting_for_image_prompt)
        await callback.message.edit_text(
            text=post_msg.GENERATE_IMAGE_ASK,
            parse_mode="HTML",
            reply_markup=get_step_cancel_keyboard(),
        )
        await callback.answer()
        return
    await callback.answer()
    await _attach_generated_photo(callback.message, state, source, callback.from_user.id)


@router.message(PostCreation.waiting_for_image_prompt, F.text)
async def post_image_prompt_received(message: types.Message, state: FSMContext):
    prompt = (message.text or "").strip()
    if not prompt:
        await message.answer(
            "Надішліть опис зображення.",
            reply_markup=get_step_cancel_keyboard(),
        )
        return
    await _attach_generated_photo(message, state, prompt)


@router.message(PostCreation.waiting_for_image_prompt)
async def post_image_prompt_invalid(message: types.Message):
    await message.answer(
        "Надішліть опис зображення текстом.",
        reply_markup=get_step_cancel_keyboard(),
    )


_AI_ACTIONS = {
    "improve": "Покращ текст: зроби його ясніше і сильніше. Сенс той самий. Не вигадуй HTML-розмітку. Поверни лише готовий текст.",
    "rewrite": "Перепиши текст іншими словами. Зміст той самий. Поверни лише готовий текст.",
    "heads": "Запропонуй рівно 3 заголовки. Кожен заголовок з нового рядка, без нумерації і пояснень.",
    "uk": "Переклади текст українською. Поверни лише переклад.",
    "en": "Переклади текст англійською. Поверни лише переклад.",
    "ideas": "Запропонуй рівно 3 короткі теми постів. Кожна тема з нового рядка, без нумерації і пояснень.",
    "proof": "Виправ мову тексту, не змінюючи зміст. Поверни лише виправлений текст.",
}
_AI_CHOICES = {"heads", "ideas"}


def _clean_ai_text(raw: str) -> str:
    import re

    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    return text


def _ai_variants(raw: str) -> list[str]:
    import re

    lines = []
    for line in _clean_ai_text(raw).splitlines():
        line = re.sub(r"^\s*(?:\d+[\.\)]\s*|[-•]\s*)", "", line).strip()
        if line:
            lines.append(line)
    return lines[:3]


async def _show_editor(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    post_data = data.get("post_data") or {}
    await state.set_state(PostCreation.editing_post)
    await message.answer(
        text=post_msg.EDITOR_HINT,
        parse_mode="HTML",
        reply_markup=get_post_editing_keyboard(post_data),
    )


async def _run_post_ai(
    message: types.Message,
    state: FSMContext,
    user_id: int,
    action: str,
    source: str,
) -> None:
    import html

    from database_functions.billing_db import refund_tokens, spend_tokens
    from utils.copy_utils.ai import Ai

    token_error = spend_tokens(user_id, "ai_text")
    if token_error:
        await message.answer(token_error)
        await _show_editor(message, state)
        return

    status = await message.answer("Готую текст…")
    try:
        raw = await Ai().async_get_response(source, _AI_ACTIONS[action])
    except Exception as exc:
        refund_tokens(user_id, "ai_text")
        try:
            await status.edit_text(
                f"❌ Не вдалося отримати відповідь.\n<code>{html.escape(str(exc))[:180]}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass
        await _show_editor(message, state)
        return

    cleaned = _clean_ai_text(raw or "")
    if not cleaned or cleaned == "Помилка API":
        refund_tokens(user_id, "ai_text")
        try:
            await status.edit_text("❌ Не вдалося отримати відповідь.")
        except Exception:
            pass
        await _show_editor(message, state)
        return

    data = await state.get_data()
    post_data = data.get("post_data") or {}
    if action in _AI_CHOICES:
        variants = _ai_variants(cleaned)
        if not variants:
            refund_tokens(user_id, "ai_text")
            try:
                await status.edit_text("❌ Не вдалося розібрати варіанти.")
            except Exception:
                pass
            await _show_editor(message, state)
            return
        await state.update_data(
            ai_variants=variants,
            ai_action=action,
            ai_base_text=post_data.get("text") or "",
        )
        await state.set_state(PostCreation.editing_post)
        try:
            await status.edit_text(
                post_msg.AI_VARIANTS,
                parse_mode="HTML",
                reply_markup=get_ai_variants_keyboard(variants),
            )
        except Exception:
            await message.answer(
                post_msg.AI_VARIANTS,
                parse_mode="HTML",
                reply_markup=get_ai_variants_keyboard(variants),
            )
        return

    post_data["text"] = html.escape(cleaned)[:4000]
    await state.update_data(post_data=post_data)
    try:
        await status.delete()
    except Exception:
        pass
    await state.set_state(PostCreation.editing_post)
    await _replace_editing_post_preview(bot, message.chat.id, post_data, state)
    await message.answer(
        text=post_msg.EDITOR_HINT,
        parse_mode="HTML",
        reply_markup=get_post_editing_keyboard(post_data),
    )


@router.callback_query(F.data == "post_ai_menu", PostCreation.editing_post)
async def post_ai_menu(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text=post_msg.AI_MENU,
        parse_mode="HTML",
        reply_markup=get_post_ai_keyboard(),
    )
    await callback.answer()


@router.callback_query(
    F.data.startswith("post_ai_"),
    ~F.data.startswith("post_ai_pick_"),
    F.data != "post_ai_menu",
    PostCreation.editing_post,
)
async def post_ai_action(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.removeprefix("post_ai_")
    if action not in _AI_ACTIONS:
        await callback.answer()
        return
    data = await state.get_data()
    post_data = data.get("post_data") or {}
    source = _plain_post_text(str(post_data.get("text") or ""))
    if not source:
        await state.update_data(ai_action=action)
        await state.set_state(PostCreation.waiting_for_ai_source)
        ask = post_msg.AI_ASK_IDEAS if action == "ideas" else post_msg.AI_ASK
        await callback.message.edit_text(
            text=ask,
            parse_mode="HTML",
            reply_markup=get_step_cancel_keyboard(),
        )
        await callback.answer()
        return
    await callback.answer()
    await _run_post_ai(callback.message, state, callback.from_user.id, action, source)


@router.message(PostCreation.waiting_for_ai_source, F.text)
async def post_ai_source_received(message: types.Message, state: FSMContext):
    source = (message.text or "").strip()
    data = await state.get_data()
    action = data.get("ai_action")
    if action not in _AI_ACTIONS or not source:
        ask = post_msg.AI_ASK_IDEAS if action == "ideas" else post_msg.AI_ASK
        await message.answer(ask, parse_mode="HTML", reply_markup=get_step_cancel_keyboard())
        return
    await _run_post_ai(message, state, message.from_user.id, action, source)


@router.message(PostCreation.waiting_for_ai_source)
async def post_ai_source_invalid(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ask = post_msg.AI_ASK_IDEAS if data.get("ai_action") == "ideas" else post_msg.AI_ASK
    await message.answer(ask, parse_mode="HTML", reply_markup=get_step_cancel_keyboard())


@router.callback_query(F.data.startswith("post_ai_pick_"), PostCreation.editing_post)
async def post_ai_pick(callback: types.CallbackQuery, state: FSMContext):
    import html

    try:
        index = int(callback.data.removeprefix("post_ai_pick_"))
    except ValueError:
        await callback.answer()
        return
    data = await state.get_data()
    variants = data.get("ai_variants") or []
    if index < 0 or index >= len(variants):
        await callback.answer("Варіант уже недоступний", show_alert=True)
        return
    chosen = html.escape(str(variants[index]))[:500]
    post_data = data.get("post_data") or {}
    base = data.get("ai_base_text") or ""
    if data.get("ai_action") == "heads" and str(base).strip():
        post_data["text"] = f"{chosen}\n\n{base}"[:4000]
    else:
        post_data["text"] = chosen[:4000]
    await state.update_data(post_data=post_data, ai_variants=[], ai_action=None, ai_base_text="")
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await _replace_editing_post_preview(bot, callback.message.chat.id, post_data, state)
    await callback.message.answer(
        text=post_msg.EDITOR_HINT,
        parse_mode="HTML",
        reply_markup=get_post_editing_keyboard(post_data),
    )


@router.callback_query(F.data == "edit_url_buttons", PostCreation.editing_post)
async def edit_url_buttons_callback(callback: types.CallbackQuery, state: FSMContext):
    """Callback редагування URL кнопок"""
    data = await state.get_data()
    post_data = data.get('post_data', {})
    
    # Перевіряємо чи є медіагрупа (більше 1 медіа)
    media_files = post_data.get('media_files', [])
    if len(media_files) > 1:
        await callback.answer(
            "⚠️ URL-кнопки не можна додати до постів з кількома медіа (медіагрупою).\n\n"
            "Залиште тільки одне фото/відео, щоб додати кнопки.",
            show_alert=True
        )
        return
    
    await callback.message.edit_text(
        text=post_msg.URL_BUTTONS_INSTRUCTION,
        parse_mode="HTML",
        reply_markup=get_url_buttons_prompt_keyboard(),
    )
    await state.set_state(PostCreation.waiting_for_url_buttons)
    await callback.answer()


@router.callback_query(
    F.data.startswith("post_url_style_"),
    StateFilter(PostCreation.waiting_for_url_buttons, PostEditing.waiting_for_url_buttons),
)
async def post_url_style(callback: types.CallbackQuery, state: FSMContext):
    choice = callback.data.removeprefix("post_url_style_")
    style = None if choice == "off" else choice
    await state.update_data(url_button_style=style)
    current = await state.get_state() or ""
    cancel = "ep_step_cancel" if "PostEditing" in current else "post_step_cancel"
    await callback.message.edit_reply_markup(
        reply_markup=get_url_buttons_prompt_keyboard(style, cancel_callback=cancel)
    )
    await callback.answer("Колір застосується до кнопок без власного кольору")


@router.callback_query(F.data == "edit_media", PostCreation.editing_post)
async def edit_media_callback(callback: types.CallbackQuery, state: FSMContext):
    """Callback редагування медіа"""
    data = await state.get_data()
    post_data = data.get('post_data', {})
    
    # Перевіряємо чи є URL-кнопки
    has_url_buttons = bool(post_data.get('url_buttons') or post_data.get('url_buttons_raw_text'))
    
    if has_url_buttons:
        await callback.message.edit_text(
            text=f"""🖼 <b>Додавання медіа</b>

{E.warn} <b>Увага!</b> У посту є URL-кнопки, тому ви можете додати <b>тільки одне</b> фото або відео.

<i>Telegram не дозволяє додавати кнопки до постів з кількома медіа (медіагрупою).</i>

📎 Надішліть <b>одне</b> фото, відео або документ.""",
            parse_mode="HTML",
            reply_markup=get_step_cancel_keyboard(),
        )
    else:
        await callback.message.edit_text(
            text="""🖼 <b>Додавання медіа</b>

📎 Надішліть:
• Одне фото/відео/документ
• Або кілька файлів одразу (медіагрупу до 10 файлів)

<i>⚠️ Примітка: Якщо ви додасте кілька медіа, то не зможете додати URL-кнопки до цього поста.</i>""",
            parse_mode="HTML",
            reply_markup=get_step_cancel_keyboard(),
        )
    
    await state.set_state(PostCreation.waiting_for_media)
    await callback.answer()


@router.message(PostCreation.waiting_for_media)
async def process_new_media(message: types.Message, state: FSMContext):
    """Замінює медіа поста: один файл або група до 10."""
    album = await take_album(message)
    if album is None:
        return

    data = await state.get_data()
    post_data = data.get('post_data', {})
    text, media_files, trimmed = album_to_post_parts(album)

    if not media_files:
        await message.answer(
            "❌ Надішліть фото, відео, документ або медіагрупу",
            reply_markup=get_step_cancel_keyboard(),
        )
        return

    has_url_buttons = bool(post_data.get('url_buttons') or post_data.get('url_buttons_raw_text'))
    if has_url_buttons and len(media_files) > 1:
        await message.answer(
            f"{E.warn} <b>Помилка!</b>\n\n"
            "У посту є URL-кнопки, тому не можна додавати медіагрупу.\n"
            "Надішліть <b>одне</b> фото або відео.",
            parse_mode="HTML",
            reply_markup=get_step_cancel_keyboard(),
        )
        return

    post_data['media_files'] = media_files
    if text and not post_data.get('text'):
        post_data['text'] = text
    if len(media_files) > 1:
        clear_url_buttons(post_data)

    await state.update_data(post_data=post_data)
    if trimmed:
        await message.answer("У групі більше 10 файлів — збережено перші 10.")

    await _replace_editing_post_preview(bot, message.chat.id, post_data, state)
    await message.answer(
        text=post_msg.EDITOR_HINT,
        parse_mode="HTML",
        reply_markup=get_post_editing_keyboard(post_data)
    )
    await state.set_state(PostCreation.editing_post)




@router.message(PostCreation.waiting_for_url_buttons)
async def process_url_buttons(message: types.Message, state: FSMContext):
    text_in = (message.text or "").strip()
    if text_in in (".", "-", "–"):
        data = await state.get_data()
        post_data = data.get("post_data", {})
        post_data["url_buttons"] = []
        post_data["url_buttons_raw_text"] = ""
        post_data["url_buttons_entities"] = []
        await state.update_data(post_data=post_data)
        await _replace_editing_post_preview(bot, message.chat.id, post_data, state)
        await message.answer(
            text=post_msg.EDITOR_HINT,
            parse_mode="HTML",
            reply_markup=get_post_editing_keyboard(post_data),
        )
        await state.set_state(PostCreation.editing_post)
        return

    entities = message.entities or []
    buttons = parse_url_buttons_with_entities(message.text, entities)
    
    if not buttons or url_button_count(buttons) > MAX_URL_BUTTONS:
        await message.answer(
            text="""❌ <b>Помилка формату кнопок!</b>

Перевірте формат і ліміт у 5 кнопок:
<code>Назва - https://example.com</code>

Для преміум емодзі просто додайте його на початку назви:
<code>🔥 Кнопка - https://example.com</code>

Спробуйте ще раз.""",
            parse_mode="HTML",
            reply_markup=get_step_cancel_keyboard(),
        )
        return
    
    data = await state.get_data()
    post_data = data.get('post_data', {})
    buttons = apply_palette_style(buttons, data.get("url_button_style"))

    # Зберігаємо кнопки
    post_data['url_buttons'] = buttons
    post_data['url_buttons_raw_text'] = message.text
    post_data['url_buttons_entities'] = [
        {
            'type': e.type,
            'offset': e.offset,
            'length': e.length,
            'custom_emoji_id': getattr(e, 'custom_emoji_id', None)
        } for e in entities
    ]
    
    await state.update_data(post_data=post_data)
    
    preview_data = post_data.copy()
    preview_data["url_buttons"] = buttons
    await _replace_editing_post_preview(bot, message.chat.id, preview_data, state)

    await message.answer(
        text=post_msg.EDITOR_HINT,
        parse_mode="HTML",
        reply_markup=get_post_editing_keyboard(post_data)
    )
    
    await state.set_state(PostCreation.editing_post)


@router.callback_query(F.data == "post_apply_channel_format", PostCreation.editing_post)
async def post_apply_channel_format(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_data = data.get("post_data", {}) or {}
    selected_channels = data.get("selected_channels", [])
    if not selected_channels:
        await callback.answer(
            "❌ Канали не обрані. Для кількох каналів спочатку підтвердіть вибір каналів.",
            show_alert=True,
        )
        return
    raw_ch = selected_channels[0]
    try:
        channel_id = int(raw_ch[0] if isinstance(raw_ch, (list, tuple)) else raw_ch)
    except (TypeError, ValueError, IndexError):
        await callback.answer("❌ Некоректний канал у стані поста", show_alert=True)
        return

    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    if (post_data.get("settings") or {}).get("skip_channel_format"):
        await callback.answer(
            "Увімкнено «Без форматування». Вимкніть його, щоб застосувати формат каналу.",
            show_alert=True,
        )
        return

    media_files = list(post_data.get("media_files") or [])
    post_data["media_files"] = media_files

    if post_data.get("channel_format_active"):
        saved_cid = post_data.get("channel_format_channel_id")
        if saved_cid != channel_id:
            post_data.pop("channel_format_active", None)
            post_data.pop("channel_format_channel_id", None)
            post_data.pop("channel_format_revert", None)
        else:
            rev = post_data.get("channel_format_revert") or {}
            post_data["text"] = rev.get("text", "")
            if media_files:
                if "caption" in rev:
                    media_files[0]["caption"] = rev["caption"]
                for index, file_id in rev.get("photo_file_ids") or []:
                    if index < len(media_files) and media_files[index].get("type") == "photo":
                        media_files[index]["file_id"] = file_id
                pf = rev.get("photo_file_id")
                if pf and media_files[0].get("type") == "photo" and not rev.get("photo_file_ids"):
                    media_files[0]["file_id"] = pf
            post_data["media_files"] = media_files
            post_data.pop("channel_format_active", None)
            post_data.pop("channel_format_channel_id", None)
            post_data.pop("channel_format_revert", None)
            await state.update_data(post_data=post_data)
            await _replace_editing_post_preview(bot, chat_id, post_data, state)
            await callback.message.answer(
                text=post_msg.EDITOR_HINT,
                parse_mode="HTML",
                reply_markup=get_post_editing_keyboard(post_data),
            )
            await callback.answer("✅ Формат каналу прибрано.")
            return

    revert: dict = {
        "text": (
            ""
            if post_data.get("text") is None
            else str(post_data.get("text"))
        ),
    }
    if media_files:
        revert["caption"] = media_files[0].get("caption")
        revert["photo_file_ids"] = [
            (index, item["file_id"])
            for index, item in enumerate(media_files)
            if item.get("type") == "photo" and item.get("file_id")
        ]

    base = post_data.get("text")
    if base is None:
        text = ""
    else:
        text = str(base)
    if not text.strip():
        for item in media_files:
            cap = item.get("caption")
            if cap:
                text = str(cap)
                break

    before_fmt = text

    ei, et = get_channel_start_emoji(channel_id)
    sig_row = get_auto_signature(channel_id)
    manual_sig = (sig_row[3] if sig_row else "") or ""

    if ei and et:
        prefix = f'<tg-emoji emoji-id="{ei}">{et}</tg-emoji> '
        if not (text.startswith("<tg-emoji") and f'emoji-id="{ei}"' in text[:120]):
            text = prefix + (text or "").lstrip()
    if manual_sig.strip():
        sep = "\n\n" if text else ""
        text = (text or "") + sep + manual_sig

    text_changed = text != before_fmt
    if text_changed:
        post_data["text"] = text
        if media_files:
            media_files[0]["caption"] = text

    wm_changed = False
    for index, item in enumerate(media_files):
        if item.get("type") != "photo":
            continue
        fid = item.get("file_id")
        if not fid:
            continue
        new_fid = await apply_watermark_to_telegram_photo(bot, chat_id, user_id, channel_id, fid)
        if new_fid:
            media_files[index]["file_id"] = new_fid
            wm_changed = True
    if wm_changed:
        post_data["media_files"] = media_files

    if text_changed or wm_changed:
        post_data["channel_format_active"] = True
        post_data["channel_format_channel_id"] = channel_id
        post_data["channel_format_revert"] = revert
    else:
        post_data.pop("channel_format_active", None)
        post_data.pop("channel_format_channel_id", None)
        post_data.pop("channel_format_revert", None)

    await state.update_data(post_data=post_data)
    await _replace_editing_post_preview(bot, chat_id, post_data, state)
    await callback.message.answer(
        text=post_msg.EDITOR_HINT,
        parse_mode="HTML",
        reply_markup=get_post_editing_keyboard(post_data),
    )
    tip = ""
    if len(selected_channels) > 1:
        tip = " Формат із першого обраного каналу."
    if text_changed or wm_changed:
        await callback.answer(f"✅ Формат застосовано.{tip}")
    else:
        await callback.answer(f"ℹ️ Немає емодзі каналу, автопідпису чи вотермарки для цього чату.{tip}")


_EDITOR_TOGGLES = {
    "pin": ("pin_message", False),
    "notification": ("notification", True),
    "autosign": ("autosign", False),
    "protect": ("content_protection", False),
    "review": ("review", False),
}


@router.callback_query(F.data.startswith("toggle_"), PostCreation.editing_post)
async def toggle_setting(callback: types.CallbackQuery, state: FSMContext):
    key = callback.data.removeprefix("toggle_")
    data = await state.get_data()
    post_data = data.get("post_data", {})
    settings = post_data.get("settings") or default_post_settings()

    restored_format = False
    if key == "plain":
        settings["skip_channel_format"] = not settings.get("skip_channel_format", False)
        if settings["skip_channel_format"]:
            restored_format = bool(post_data.get("channel_format_revert"))
            rev = post_data.get("channel_format_revert") or {}
            if rev:
                post_data["text"] = rev.get("text", post_data.get("text") or "")
                media_files = list(post_data.get("media_files") or [])
                for index, file_id in rev.get("photo_file_ids") or []:
                    if index < len(media_files) and media_files[index].get("type") == "photo":
                        media_files[index]["file_id"] = file_id
                post_data["media_files"] = media_files
            post_data.pop("channel_format_active", None)
            post_data.pop("channel_format_channel_id", None)
            post_data.pop("channel_format_revert", None)
    elif key == "comments":
        settings["disable_comments"] = not settings.get("disable_comments", False)
    elif key in _EDITOR_TOGGLES:
        field, default = _EDITOR_TOGGLES[key]
        settings[field] = not settings.get(field, default)
    else:
        await callback.answer()
        return

    post_data["settings"] = settings
    await state.update_data(post_data=post_data)
    if restored_format:
        await _replace_editing_post_preview(bot, callback.message.chat.id, post_data, state)
    await callback.message.edit_reply_markup(
        reply_markup=get_post_editing_keyboard(post_data)
    )
    await callback.answer("Оновлено")


@router.callback_query(F.data == "post_replace_links", PostCreation.editing_post)
async def post_replace_links(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PostCreation.waiting_for_link_replace)
    await callback.message.answer(
        "Надішліть заміну у форматі:\n<code>старе_посилання - нове_посилання</code>",
        parse_mode="HTML",
        reply_markup=get_step_cancel_keyboard(),
    )
    await callback.answer()


@router.message(PostCreation.waiting_for_link_replace, F.text)
async def apply_link_replace(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip()
    if " - " not in raw:
        await message.answer(
            "Формат: <code>старе_посилання - нове_посилання</code>",
            parse_mode="HTML",
            reply_markup=get_step_cancel_keyboard(),
        )
        return

    old, new = (part.strip() for part in raw.split(" - ", 1))
    if not old or not new:
        await message.answer(
            "Обидві частини мають бути заповнені.",
            reply_markup=get_step_cancel_keyboard(),
        )
        return

    data = await state.get_data()
    post_data = data.get("post_data") or _empty_post_data()
    if post_data.get("text"):
        post_data["text"] = str(post_data["text"]).replace(old, new)
    for item in post_data.get("media_files") or []:
        if item.get("caption"):
            item["caption"] = str(item["caption"]).replace(old, new)

    await state.update_data(post_data=post_data)
    await state.set_state(PostCreation.editing_post)
    await _replace_editing_post_preview(bot, message.chat.id, post_data, state)
    await message.answer(
        text=post_msg.EDITOR_HINT,
        parse_mode="HTML",
        reply_markup=get_post_editing_keyboard(post_data),
    )


@router.callback_query(
    F.data.in_({"pub_toggle_ad", "pub_toggle_repeat", "pub_mode_copy", "pub_mode_forward"}),
    PostCreation.editing_post,
)
async def publishing_option_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_data = data.get("post_data") or _empty_post_data()
    settings = post_data.get("settings") or default_post_settings()

    if callback.data == "pub_toggle_ad":
        settings["ad_top"] = not settings.get("ad_top", False)
    elif callback.data == "pub_toggle_repeat":
        settings["autorepeat"] = not settings.get("autorepeat", False)
    elif callback.data == "pub_mode_copy":
        settings["publish_mode"] = "copy"
    else:
        settings["publish_mode"] = "forward"

    post_data["settings"] = settings
    await state.update_data(post_data=post_data)
    await callback.message.edit_reply_markup(
        reply_markup=get_publishing_menu_keyboard(post_data)
    )
    await callback.answer("Оновлено")


@router.callback_query(F.data == "pub_reply", PostCreation.editing_post)
async def publishing_reply_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PostCreation.waiting_for_reply)
    await callback.message.answer(
        "Перешліть пост, на який треба відповісти, або надішліть посилання на нього.",
        parse_mode="HTML",
        reply_markup=get_step_cancel_keyboard("post_reply_cancel"),
    )
    await callback.answer()


@router.message(PostCreation.waiting_for_reply)
async def publishing_reply_received(message: types.Message, state: FSMContext):
    data = await state.get_data()
    post_data = data.get("post_data") or _empty_post_data()
    settings = post_data.get("settings") or default_post_settings()

    if message.forward_from_chat and message.forward_from_message_id:
        settings["reply_to"] = {
            "chat_id": message.forward_from_chat.id,
            "message_id": message.forward_from_message_id,
        }
    elif (message.text or "").strip():
        settings["reply_to"] = {"link": message.text.strip()}
    else:
        await message.answer(
            "Надішліть посилання або перешліть пост.",
            reply_markup=get_step_cancel_keyboard("post_reply_cancel"),
        )
        return

    post_data["settings"] = settings
    await state.update_data(post_data=post_data)
    await state.set_state(PostCreation.editing_post)
    await message.answer(
        text=post_msg.PUBLISH_SETTINGS,
        parse_mode="HTML",
        reply_markup=get_publishing_menu_keyboard(post_data),
    )


@router.callback_query(F.data == "post_next", PostCreation.editing_post)
async def post_next_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_data = data.get('post_data', {})
    
    is_valid, error = validate_post_data(post_data)
    if not is_valid:
        await callback.answer(error, show_alert=True)
        return
    
    await safe_edit_text(
        callback.message,
        text=post_msg.PUBLISH_SETTINGS,
        parse_mode="HTML",
        reply_markup=get_publishing_menu_keyboard(post_data),
    )

    await callback.answer()


@router.callback_query(F.data == "back_to_editing")
async def back_to_editing_callback(callback: types.CallbackQuery, state: FSMContext):       
    data = await state.get_data()
    post_data = data.get('post_data', {})
    
    # Показуємо превʼю
    await _replace_editing_post_preview(
        bot, callback.message.chat.id, post_data, state
    )

    # Клавіатуру редагування
    await callback.message.answer(
        text=post_msg.EDITOR_HINT,
        parse_mode="HTML",
        reply_markup=get_post_editing_keyboard(post_data)
    )
    
    await state.set_state(PostCreation.editing_post)
    await callback.answer()


@router.callback_query(F.data == "back_to_publishing")
async def back_to_publishing_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_data = data.get("post_data", {})
    await safe_edit_text(
        callback.message,
        text=post_msg.PUBLISH_SETTINGS,
        parse_mode="HTML",
        reply_markup=get_publishing_menu_keyboard(post_data),
    )

    await callback.answer()


@router.callback_query(F.data == "set_auto_delete")
async def set_auto_delete_callback(callback: types.CallbackQuery, state: FSMContext):       
    data = await state.get_data()
    post_data = data.get('post_data', {})
    settings = post_data.get('settings', {})
    
    current_delete = settings.get("auto_delete_minutes")
    current_text = ""
    if current_delete:
        if current_delete >= 60 and current_delete % 60 == 0:
            current_text = (
                f"\n\n<b>Поточне налаштування:</b> через {current_delete // 60} год"
            )
        else:
            current_text = (
                f"\n\n<b>Поточне налаштування:</b> через {current_delete} хв"
            )
    
    await callback.message.edit_text(
        text=f"""🗑 <b>Автовидалення поста</b>

Пост буде автоматично видалено через вказаний час після публікації.{current_text}

⏱ Оберіть час:""",
        parse_mode="HTML",
        reply_markup=get_auto_delete_keyboard()
    )
    
    await callback.answer()


@router.callback_query(F.data.startswith("autodel_"))
async def process_auto_delete(callback: types.CallbackQuery, state: FSMContext):
    """Обробка вибору часу автовидалення"""
    action = callback.data.split("_")[1]
    
    data = await state.get_data()
    post_data = data.get('post_data', {})
    
    if 'settings' not in post_data:
        post_data['settings'] = {}
    
    if action == "disable":
        post_data["settings"]["auto_delete_minutes"] = None
        message = "✅ Автовидалення вимкнено"
    else:
        minutes = int(action)
        post_data["settings"]["auto_delete_minutes"] = minutes
        if minutes >= 60 and minutes % 60 == 0:
            message = (
                f"✅ Пост буде видалено через {minutes // 60} год після публікації"
            )
        else:
            message = f"✅ Пост буде видалено через {minutes} хв після публікації"

    await state.update_data(post_data=post_data)

    await safe_edit_text(
        callback.message,
        text=post_msg.PUBLISH_SETTINGS,
        parse_mode="HTML",
        reply_markup=get_publishing_menu_keyboard(post_data),
    )

    await callback.answer(message, show_alert=True)


@router.callback_query(F.data == "post_publish_now", PostCreation.editing_post)
async def post_publish_now_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    post_data = data.get("post_data", {})
    selected_channels = data.get("selected_channels", [])

    if post_data.get("url_buttons_raw_text"):
        await ensure_post_url_buttons_in_state(state)

    channel_names = []
    for channel_id in selected_channels:
        channel = get_channel_by_id(channel_id)
        if channel:
            channel_names.append(channel[2])

    channels_text = "\n".join([f"• {name}" for name in channel_names[:5]])
    if len(channel_names) > 5:
        channels_text += f"\n• ... і ще {len(channel_names) - 5}"

    confirmation_text = f"""{E.send} <b>Підтвердження публікації</b>

<b>Канали для публікації ({len(selected_channels)}):</b>
{channels_text}

<b>Ви впевнені, що хочете опублікувати пост?</b>"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Так, опублікувати", callback_data="confirm_publish",
                icon_custom_emoji_id=Icon.ok,
            ),
                InlineKeyboardButton(text="Скасувати", callback_data="back_to_publishing", icon_custom_emoji_id=Icon.cancel),
            ]
        ]
    )

    if get_user_confirm_publish_status(callback.from_user.id):
        await callback.message.edit_text(
            text=confirmation_text,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        await callback.answer()
    else:
        await _execute_immediate_publish(callback, state)


@router.callback_query(F.data == "confirm_publish")
async def confirm_publish_callback(callback: types.CallbackQuery, state: FSMContext):
    await _execute_immediate_publish(callback, state)


@router.callback_query(F.data == "cancel_post_creation")
async def cancel_post(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        text="❌ Створення поста скасовано.",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "post_back")
async def post_back(callback: types.CallbackQuery):
    await callback.message.edit_text(
        text="◀️ Використовуйте кнопки нижче для навігації.",
        parse_mode="HTML"
    )
    await callback.answer()
