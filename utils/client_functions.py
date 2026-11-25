from utils.ui_emoji import E
from aiogram import Bot
from aiogram.types import Chat
import re

async def check_bot_permissions(bot: Bot, chat_id: int) -> dict:
    """
    Перевіряє права бота в каналі/групі
    Повертає словник з інформацією про права
    """
    from aiogram.exceptions import TelegramBadRequest
    
    try:
        chat = await bot.get_chat(chat_id)
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        
        required_permissions = {
            'can_post_messages': True,
            'can_edit_messages': True,
            'can_delete_messages': True,
        }
        
        missing_permissions = []
        has_all = True
        
        # Якщо бот не адміністратор
        if bot_member.status not in ['administrator', 'creator']:
            return {
                'has_all_permissions': False,
                'missing_permissions': ['Бот не є адміністратором'],
                'is_admin': False
            }
        
        # Перевіряємо кожне право
        for perm, required in required_permissions.items():
            bot_has = getattr(bot_member, perm, False)
            if required and not bot_has:
                missing_permissions.append(perm)
                has_all = False
        
        return {
            'has_all_permissions': has_all,
            'missing_permissions': missing_permissions,
            'is_admin': True
        }
    
    except TelegramBadRequest as e:
        error_message = str(e)
        print(f"❌ Помилка перевірки прав: {error_message}")
        
        if "member list is inaccessible" in error_message:
            # Бот не має доступу до списку учасників - найімовірніше не є адміністратором
            return {
                'has_all_permissions': False,
                'missing_permissions': ['Бот не є адміністратором або не має доступу до списку учасників'],
                'is_admin': False,
                'error_type': 'member_list_inaccessible'
            }
        elif "chat not found" in error_message:
            # Канал не знайдено
            return {
                'has_all_permissions': False,
                'missing_permissions': ['Канал не знайдено'],
                'is_admin': False,
                'error_type': 'chat_not_found'
            }
        else:
            return {
                'has_all_permissions': False,
                'missing_permissions': [f'Помилка перевірки прав: {error_message}'],
                'is_admin': False,
                'error_type': 'unknown'
            }
        
    except Exception as e:
        print(f"❌ Помилка перевірки прав бота: {e}")
        return {
            'has_all_permissions': False,
            'missing_permissions': ['Помилка перевірки прав'],
            'is_admin': False,
            'error_type': 'unknown'
        }


async def get_bot_username_for_tme(bot: Bot) -> str | None:
    """Username бота для посилань виду https://t.me/<username>/… (без @)."""
    me = await bot.get_me()
    u = getattr(me, "username", None)
    if not u:
        return None
    clean = str(u).strip().lstrip("@")
    return clean or None


def get_chat_link(chat: Chat) -> str:
    """Генерує посилання на канал/групу"""
    if chat.username:
        return f"https://t.me/{chat.username}"
    else:
        # Для приватних каналів/груп використовуємо правильний формат
        # Видаляємо префікс -100 якщо він є
        chat_id_str = str(chat.id)
        if chat_id_str.startswith('-100'):
            chat_id_for_link = chat_id_str[4:]  # Видаляємо -100
        else:
            chat_id_for_link = str(abs(chat.id))
        return f"https://t.me/c/{chat_id_for_link}/1"


def get_permission_check_message(chat_title: str, chat_link: str, 
                                 permission_result: dict) -> str:
    """Генерує повідомлення про результат перевірки прав"""
    if not permission_result['is_admin']:
        return (
            f"❌ <b>Бот не є адміністратором!</b>\n\n"
            f"📺 Канал: <a href=\"{chat_link}\">{chat_title}</a>\n\n"
            f"⚠️ Додайте бота як адміністратора з наступними правами:\n"
            f"• Публікувати повідомлення\n"
            f"• Редагувати повідомлення\n"
            f"• Видаляти повідомлення"
        )
    else:
        missing = permission_result['missing_permissions']
        permissions_text = '\n'.join([f"• {perm}" for perm in missing])
        return (
            f"{E.warn} <b>Недостатньо прав!</b>\n\n"
            f"📺 Канал: <a href=\"{chat_link}\">{chat_title}</a>\n\n"
            f"❌ Відсутні права:\n{permissions_text}\n\n"
            f"Надайте боту всі необхідні права адміністратора."
        )


async def delete_discussion_message_with_delay(bot, discussion_group_id: int, delay_seconds: int):
    """Заглушка для контент-плану; повну логіку можна додати за потреби."""
    _ = (bot, discussion_group_id, delay_seconds)
    pass

