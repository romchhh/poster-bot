import re
from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from texts.messages.post import URL_BUTTONS_INSTRUCTION as URL_BUTTONS_INSTRUCTION_HTML

MAX_URL_BUTTONS = 5


def extract_custom_emoji_from_entities(text: str, entities: list) -> dict:
    """
    Витягує custom_emoji_id з entities для кожного символу тексту
    Повертає словник {позиція: custom_emoji_id}
    """
    if not entities:
        return {}
    
    emoji_map = {}
    
    for entity in entities:
        if entity.type == 'custom_emoji':
            custom_emoji_id = getattr(entity, 'custom_emoji_id', None)
            if custom_emoji_id:
                # Зберігаємо custom_emoji_id для кожної позиції в entity
                for pos in range(entity.offset, entity.offset + entity.length):
                    emoji_map[pos] = custom_emoji_id
    
    return emoji_map


def parse_url_buttons_with_entities(text: str, entities: list = None):
    """
    Парсить URL кнопки з тексту з підтримкою кольорів та преміум емодзі з entities
    
    Формат:
    Назва - URL
    Назва - URL::red (колір після посилання)
    !r Назва - URL (колір перед текстом)
    🔥 Назва - URL (преміум емодзі на початку - витягується з entities!)
    
    Кольори:
    - red, ::red, !r → style="danger" (червоний)
    - green, ::green, !g → style="success" (зелений)  
    - blue, ::blue, !b → style="primary" (синій)
    
    Для кількох кнопок в рядку: | розділювач
    """
    try:
        # Створюємо мапу преміум емодзі з entities
        emoji_map = extract_custom_emoji_from_entities(text, entities or [])
        
        lines = text.strip().split('\n')
        keyboard_rows = []
        
        # Мапа скорочень кольорів
        color_shortcuts = {
            '!r': 'danger',
            '!g': 'success',
            '!b': 'primary'
        }
        
        # Мапа повних назв кольорів
        color_names = {
            'red': 'danger',
            'green': 'success',
            'blue': 'primary'
        }
        
        current_position = 0  # Відстежуємо позицію в тексті для entities
        
        for line in lines:
            line = line.strip()
            if not line:
                current_position += 1  # Рахуємо порожні рядки
                continue
            
            # Визначаємо початкову позицію цього рядка в оригінальному тексті
            line_start = text.find(line, current_position)
            
            # Якщо в рядку є | - це кілька кнопок в одному рядку
            if '|' in line:
                buttons = line.split('|')
                row = []
                btn_position = line_start
                
                for button_text in buttons:
                    button_text_stripped = button_text.strip()
                    # Знаходимо позицію цієї кнопки
                    btn_start = line.find(button_text_stripped, btn_position - line_start) + line_start
                    
                    button = parse_single_button_with_emoji(
                        button_text_stripped, 
                        color_shortcuts, 
                        color_names,
                        emoji_map,
                        btn_start
                    )
                    if button:
                        row.append(button)
                    
                    btn_position = btn_start + len(button_text_stripped)
                
                if row:
                    keyboard_rows.append(row)
            # Інакше - одна кнопка в рядку
            else:
                button = parse_single_button_with_emoji(
                    line, 
                    color_shortcuts, 
                    color_names,
                    emoji_map,
                    line_start
                )
                if button:
                    keyboard_rows.append([button])
            
            current_position = line_start + len(line) + 1
        
        return keyboard_rows if keyboard_rows else None
    except Exception as e:
        print(f"❌ Помилка парсингу URL кнопок: {e}")
        import traceback
        traceback.print_exc()
        return None


def parse_single_button_with_emoji(button_text: str, color_shortcuts: dict, color_names: dict, 
                                   emoji_map: dict, text_position: int):
    """Парсить одну кнопку з тексту з урахуванням entities"""
    if ' - ' not in button_text:
        return None
    
    # Розділяємо на назву та URL
    parts = button_text.split(' - ', 1)
    if len(parts) != 2:
        return None
    
    name = parts[0].strip()
    url_part = parts[1].strip()
    
    # Ініціалізуємо параметри кнопки
    url = url_part
    style = None
    icon_emoji_id = None
    
    # Перевіряємо колір на початку назви (!r, !g, !b)
    for shortcut, button_style in color_shortcuts.items():
        if name.startswith(shortcut + ' '):
            style = button_style
            name = name[len(shortcut):].strip()
            # Оновлюємо позицію після видалення префікса
            text_position += len(shortcut) + 1
            break
    
    # Перевіряємо колір в кінці URL (::red, ::green, ::blue, ::#RRGGBB)
    for color, button_style in color_names.items():
        color_marker = f'::{color}'
        if url_part.endswith(color_marker):
            if style is None:  # Не перезаписуємо якщо вже є колір
                style = button_style
            url = url_part[:-len(color_marker)].strip()
            break
    if style is None:
        hex_match = re.search(r"::(#[0-9A-Fa-f]{6})$", url_part)
        if hex_match:
            style = _nearest_button_style(hex_match.group(1))
            url = url_part[: hex_match.start()].strip()
    
    # Очищаємо URL від неалфавітних символів в кінці (емодзі, пробіли тощо)
    # Але зберігаємо валідні символи URL
    # Видаляємо все що не є латинськими літерами, цифрами, або спеціальними символами URL
    url = re.sub(r'[^\x00-\x7F]+$', '', url).strip()
    
    # Витягуємо преміум емодзі з entities (перший символ назви)
    if emoji_map and text_position in emoji_map:
        icon_emoji_id = emoji_map[text_position]
        # Видаляємо емодзі з тексту кнопки (перший символ)
        if name:
            name = name[1:].strip() if len(name) > 1 else name
    
    # Перевіряємо чи URL валідний
    if not url or not name:
        return None
    
    # Додаткова валідація URL - має починатися з http:// або https://
    if not (url.startswith('http://') or url.startswith('https://')):
        return None
    
    # Перевіряємо чи немає зайвих символів після домену
    # URL не повинен містити emoji або інші незвичайні символи
    try:
        # Перевіряємо що URL можна закодувати в ASCII (окрім параметрів)
        url_without_params = url.split('?')[0]
        url_without_params.encode('ascii')
    except UnicodeEncodeError:
        # URL містить не-ASCII символи, що може бути помилкою
        return None
    
    # Створюємо кнопку з усіма параметрами
    button_params = {
        'text': name,
        'url': url
    }
    
    if style:
        button_params['style'] = style
    
    if icon_emoji_id:
        button_params['icon_custom_emoji_id'] = icon_emoji_id
    
    return InlineKeyboardButton(**button_params)


# Залишаємо стару функцію для сумісності
def _nearest_button_style(hex_color: str) -> str:
    value = hex_color.lstrip("#")
    red, green, blue = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    if red >= green and red >= blue:
        return "danger"
    if green >= red and green >= blue:
        return "success"
    return "primary"


def url_button_count(rows) -> int:
    return sum(len(row) for row in rows or [])


def apply_palette_style(rows, style: str | None):
    if not style or not rows:
        return rows
    painted = []
    for row in rows:
        painted_row = []
        for button in row:
            if getattr(button, "style", None):
                painted_row.append(button)
            else:
                painted_row.append(button.model_copy(update={"style": style}))
        painted.append(painted_row)
    return painted


def parse_url_buttons(text: str):
    """
    Парсить URL кнопки без entities (для сумісності)
    Рекомендується використовувати parse_url_buttons_with_entities
    """
    return parse_url_buttons_with_entities(text, None)


def parse_time_input(time_input):
    """Парсить введення часу в різних форматах"""
    time_input = time_input.strip()
    
    # Формат HH:MM
    match = re.match(r'^(\d{1,2}):(\d{2})$', time_input)
    if match:
        hours, minutes = map(int, match.groups())
        if 0 <= hours <= 23 and 0 <= minutes <= 59:
            return (hours, minutes)
    
    # Формат HHMM
    match = re.match(r'^(\d{4})$', time_input)
    if match:
        hours = int(time_input[:2])
        minutes = int(time_input[2:])
        if 0 <= hours <= 23 and 0 <= minutes <= 59:
            return (hours, minutes)
    
    # Формат HH (тільки години)
    match = re.match(r'^(\d{1,2})$', time_input)
    if match:
        hours = int(match.group(1))
        if 0 <= hours <= 23:
            return (hours, 0)
    
    return None


def serialize_url_buttons(keyboard_rows):
    """Серіалізує URL кнопки для збереження в БД (включно з кольором і преміум-емодзі)."""
    if not keyboard_rows:
        return None

    serialized = []
    for row in keyboard_rows:
        serialized_row = []
        for button in row:
            item = {
                "text": button.text,
                "url": button.url,
            }
            style = getattr(button, "style", None)
            if style:
                item["style"] = style
            icon_id = getattr(button, "icon_custom_emoji_id", None)
            if icon_id:
                item["icon_custom_emoji_id"] = icon_id
            serialized_row.append(item)
        serialized.append(serialized_row)

    return serialized


def deserialize_url_buttons(serialized_data):
    """Десеріалізує URL кнопки з БД (відновлює колір і преміум-емодзі, якщо були збережені)."""
    if not serialized_data:
        return None

    keyboard_rows = []
    for row_data in serialized_data:
        row = []
        for button_data in row_data:
            kwargs = {
                "text": button_data["text"],
                "url": button_data["url"],
            }
            style = button_data.get("style")
            if style:
                kwargs["style"] = style
            icon_id = button_data.get("icon_custom_emoji_id")
            if icon_id:
                kwargs["icon_custom_emoji_id"] = icon_id
            row.append(InlineKeyboardButton(**kwargs))
        keyboard_rows.append(row)

    return keyboard_rows


def _album_bucket(media_type: str) -> str:
    if media_type in {"photo", "video", "animation"}:
        return "visual"
    if media_type == "document":
        return "document"
    if media_type == "audio":
        return "audio"
    return "single"


def _input_media(media_type: str, file_id: str, caption: str):
    from aiogram.types import (
        InputMediaAnimation,
        InputMediaAudio,
        InputMediaDocument,
        InputMediaPhoto,
        InputMediaVideo,
    )

    classes = {
        "photo": InputMediaPhoto,
        "video": InputMediaVideo,
        "animation": InputMediaAnimation,
        "document": InputMediaDocument,
        "audio": InputMediaAudio,
    }
    media_cls = classes.get(media_type)
    if media_cls is None:
        return None
    if caption:
        return media_cls(media=file_id, caption=caption, parse_mode="HTML")
    return media_cls(media=file_id)


async def _send_album(bot, chat_id, media_files, caption, *, disable_notification, protect_content):
    """Send up to 10 files, keeping order. Incompatible kinds become separate albums."""
    sent = []
    caption_left = caption or ""
    pending: list = []
    pending_kind = None

    async def _one(item, cap):
        media_type = item.get("type")
        file_id = item["file_id"]
        if media_type == "video_note":
            return await bot.send_video_note(
                chat_id=chat_id,
                video_note=file_id,
                disable_notification=disable_notification,
                protect_content=protect_content,
            )
        payload = {
            "chat_id": chat_id,
            "caption": cap or "",
            "parse_mode": "HTML",
            "disable_notification": disable_notification,
            "protect_content": protect_content,
        }
        if media_type == "photo":
            return await bot.send_photo(photo=file_id, **payload)
        if media_type == "video":
            return await bot.send_video(video=file_id, **payload)
        if media_type == "animation":
            return await bot.send_animation(animation=file_id, **payload)
        if media_type == "document":
            return await bot.send_document(document=file_id, **payload)
        if media_type == "audio":
            return await bot.send_audio(audio=file_id, **payload)
        if media_type == "voice":
            return await bot.send_voice(voice=file_id, **payload)
        return None

    async def _flush():
        nonlocal pending, pending_kind, caption_left
        if not pending:
            return
        if len(pending) == 1:
            msg = await _one(pending[0], caption_left)
            caption_left = ""
            if msg:
                sent.append(msg)
        else:
            group = []
            for index, item in enumerate(pending):
                built = _input_media(
                    item.get("type") or "",
                    item["file_id"],
                    caption_left if index == 0 else "",
                )
                if built is not None:
                    group.append(built)
            caption_left = ""
            if len(group) >= 2:
                messages = await bot.send_media_group(
                    chat_id=chat_id,
                    media=group,
                    disable_notification=disable_notification,
                    protect_content=protect_content,
                )
                sent.extend(messages)
            else:
                for item in pending:
                    msg = await _one(item, "")
                    if msg:
                        sent.append(msg)
        pending = []
        pending_kind = None

    for item in media_files:
        kind = _album_bucket(item.get("type") or "")
        if kind == "single":
            await _flush()
            used_caption = caption_left if item.get("type") != "video_note" else ""
            msg = await _one(item, used_caption)
            if item.get("type") != "video_note":
                caption_left = ""
            if msg:
                sent.append(msg)
            continue
        if pending and kind != pending_kind:
            await _flush()
        pending.append(item)
        pending_kind = kind
    await _flush()
    if caption_left:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=caption_left,
            parse_mode="HTML",
            disable_notification=disable_notification,
            protect_content=protect_content,
        )
        sent.append(msg)
    return sent


async def send_post_preview(
    bot,
    chat_id,
    post_data: dict,
    preview_message_ids: Optional[list] = None,
):
    """
    Відправляє превʼю поста.

    Якщо передано preview_message_ids (список), у нього додаються message_id усіх
    надісланих повідомлень превʼю (альбом, окреме повідомлення з кнопками тощо) —
    для подальшого видалення в чаті чернетки.
    """
    try:
        from aiogram.exceptions import TelegramBadRequest
        
        text = post_data.get('text', '')
        media_files = post_data.get('media_files', [])
        media_file_id = post_data.get('media_file_id')
        media_type = post_data.get('media_type')
        url_buttons = post_data.get('url_buttons', [])
        settings = post_data.get("settings") or {}
        disable_notification = not settings.get("notification", True)
        protect_content = settings.get("content_protection", False)

        async def _try_pin(sent_message):
            if not settings.get("pin_message") or not sent_message:
                return
            # У приватному чаті закріплення недоступне (превʼю); у каналах/групах chat_id відʼємний
            if isinstance(chat_id, int) and chat_id > 0:
                return
            try:
                await bot.pin_chat_message(
                    chat_id=chat_id,
                    message_id=sent_message.message_id,
                    disable_notification=disable_notification,
                )
            except Exception as e:
                print(f"Error pinning message: {e}")
        
        # URL-кнопки лише для одного повідомлення. Альбом їх не приймає.
        reply_markup = None
        if url_buttons and len(media_files) <= 1:
            reply_markup = InlineKeyboardMarkup(inline_keyboard=url_buttons)

        # Якщо є медіагрупа
        if len(media_files) > 1:
            sent_messages = await _send_album(
                bot,
                chat_id,
                media_files[:10],
                text or "",
                disable_notification=disable_notification,
                protect_content=protect_content,
            )
            main_msg = sent_messages[0] if sent_messages else None
            await _try_pin(main_msg)
            if preview_message_ids is not None:
                for sm in sent_messages:
                    preview_message_ids.append(sm.message_id)
            return main_msg
        
        # Якщо одне медіа
        elif media_files and len(media_files) == 1:
            media = media_files[0]
            if media['type'] == 'photo':
                msg = await bot.send_photo(
                    chat_id=chat_id,
                    photo=media['file_id'],
                    caption=text or "",
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_notification=disable_notification,
                    protect_content=protect_content,
                )
                if preview_message_ids is not None:
                    preview_message_ids.append(msg.message_id)
                await _try_pin(msg)
                return msg
            elif media['type'] == 'video':
                msg = await bot.send_video(
                    chat_id=chat_id,
                    video=media['file_id'],
                    caption=text or "",
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_notification=disable_notification,
                    protect_content=protect_content,
                )
                if preview_message_ids is not None:
                    preview_message_ids.append(msg.message_id)
                await _try_pin(msg)
                return msg
            elif media['type'] == 'document':
                msg = await bot.send_document(
                    chat_id=chat_id,
                    document=media['file_id'],
                    caption=text or "",
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_notification=disable_notification,
                    protect_content=protect_content,
                )
                if preview_message_ids is not None:
                    preview_message_ids.append(msg.message_id)
                await _try_pin(msg)
                return msg
            elif media['type'] == 'animation':
                msg = await bot.send_animation(
                    chat_id=chat_id,
                    animation=media['file_id'],
                    caption=text or "",
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_notification=disable_notification,
                    protect_content=protect_content,
                )
                if preview_message_ids is not None:
                    preview_message_ids.append(msg.message_id)
                await _try_pin(msg)
                return msg
            elif media['type'] == 'audio':
                msg = await bot.send_audio(
                    chat_id=chat_id,
                    audio=media['file_id'],
                    caption=text or "",
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_notification=disable_notification,
                    protect_content=protect_content,
                )
                if preview_message_ids is not None:
                    preview_message_ids.append(msg.message_id)
                await _try_pin(msg)
                return msg
            elif media['type'] == 'voice':
                msg = await bot.send_voice(
                    chat_id=chat_id,
                    voice=media['file_id'],
                    caption=text or "",
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_notification=disable_notification,
                    protect_content=protect_content,
                )
                if preview_message_ids is not None:
                    preview_message_ids.append(msg.message_id)
                await _try_pin(msg)
                return msg
            elif media['type'] == 'video_note':
                msg = await bot.send_video_note(
                    chat_id=chat_id,
                    video_note=media['file_id'],
                    disable_notification=disable_notification,
                    protect_content=protect_content,
                )
                if preview_message_ids is not None:
                    preview_message_ids.append(msg.message_id)
                await _try_pin(msg)
                return msg

        # Якщо старий формат (один медіафайл)
        elif media_file_id:
            if media_type == 'photo':
                msg = await bot.send_photo(
                    chat_id=chat_id,
                    photo=media_file_id,
                    caption=text or "",
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_notification=disable_notification,
                    protect_content=protect_content,
                )
                if preview_message_ids is not None:
                    preview_message_ids.append(msg.message_id)
                await _try_pin(msg)
                return msg
            elif media_type == 'video':
                msg = await bot.send_video(
                    chat_id=chat_id,
                    video=media_file_id,
                    caption=text or "",
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_notification=disable_notification,
                    protect_content=protect_content,
                )
                if preview_message_ids is not None:
                    preview_message_ids.append(msg.message_id)
                await _try_pin(msg)
                return msg
            elif media_type == 'document':
                msg = await bot.send_document(
                    chat_id=chat_id,
                    document=media_file_id,
                    caption=text or "",
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_notification=disable_notification,
                    protect_content=protect_content,
                )
                if preview_message_ids is not None:
                    preview_message_ids.append(msg.message_id)
                await _try_pin(msg)
                return msg

        if media_files or media_file_id:
            print("Медіа є в чернетці, але його не вдалося відправити")
            return None

        # Тільки текст
        msg = await bot.send_message(
            chat_id=chat_id,
            text=text or "Порожній пост",
            parse_mode="HTML",
            reply_markup=reply_markup,
            disable_web_page_preview=True,
            disable_notification=disable_notification,
            protect_content=protect_content,
        )
        if preview_message_ids is not None:
            preview_message_ids.append(msg.message_id)
        await _try_pin(msg)
        return msg
        
    except TelegramBadRequest as e:
        error_message = str(e)
        print(f"❌ Помилка відправки превʼю: {error_message}")
        
        # Перевіряємо чи це помилка з URL кнопками
        if "URL" in error_message or "invalid" in error_message.lower():
            err_msg = await bot.send_message(
                chat_id=chat_id,
                text="""❌ <b>Помилка в URL-кнопках!</b>

⚠️ Одне або декілька посилань мають неправильний формат.

<b>Перевірте:</b>
• Посилання має починатися з <code>http://</code> або <code>https://</code>
• Після посилання не повинно бути зайвих символів
• Формат: <code>Текст кнопки - https://приклад.com</code>

<b>Приклади правильного формату:</b>
<code>Сайт - https://example.com
Instagram - https://instagram.com/username
Telegram - https://t.me/channel</code>

<b>Приклади з кольорами:</b>
<code>Кнопка - https://site.com::red
!g Кнопка - https://site.com</code>

📝 Відредагуйте кнопки та спробуйте знову.""",
                parse_mode="HTML"
            )
            if preview_message_ids is not None:
                preview_message_ids.append(err_msg.message_id)
            return err_msg
        else:
            # Інша помилка Telegram
            err_msg = await bot.send_message(
                chat_id=chat_id,
                text=f"❌ <b>Помилка Telegram:</b>\n\n<code>{error_message}</code>\n\n⚠️ Спробуйте відредагувати пост.",
                parse_mode="HTML"
            )
            if preview_message_ids is not None:
                preview_message_ids.append(err_msg.message_id)
            return err_msg
    
    except Exception as e:
        print(f"❌ Помилка відправки превʼю: {e}")
        err_msg = await bot.send_message(
            chat_id=chat_id,
            text=post_data.get('text', 'Помилка відображення поста'),
            parse_mode="HTML"
        )
        if preview_message_ids is not None:
            preview_message_ids.append(err_msg.message_id)
        return err_msg


def validate_post_data(post_data: dict) -> tuple[bool, str]:
    """
    Перевіряє чи пост валідний для публікації
    Повертає (is_valid, error_message)
    """
    if not post_data.get('text') and not post_data.get('media_files') and not post_data.get('media_file_id'):
        return False, "❌ Пост повинен містити текст або медіа!"
    
    return True, ""
