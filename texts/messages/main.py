"""Start, support, and other top-level screens."""

from __future__ import annotations

from utils.ui_emoji import E

START = f"""{E.brand} <b>SkyPost</b> — SaaS-платформа для управління Telegram-каналами та сітками каналів.

<b>{E.settings} Що вміє бот:</b>
<blockquote>
{E.notes} Автопостинг і видалення постів
{E.sign} Ручне створення та редагування контенту
{E.calendar} Контент-план для стабільного постингу
{E.link} Автоматична вставка посилань у слова/фрази
{E.list} Клонування постів із заміною тексту
{E.send} Масовий постинг по папках/сітках каналів
</blockquote>

<i>SkyPost об'єднує всі ключові інструменти контент-менеджменту в одному місці.</i>"""

SUPPORT = """<b>SkyPost — постинг і AI для Telegram-каналів.</b>

<b>Соцмережі та контакти:</b>
• Підтримка: <a href="https://t.me/SkyPostHelp">@SkyPostHelp</a>
• Новини: <a href="https://t.me/SkyPost_News">@SkyPost_News</a>
• Менеджер: <a href="https://t.me/SkyPostHelp">@SkyPostHelp</a>

<b>Підтримка:</b>
Якщо у вас виникли запитання або проблеми, будь ласка, зверніться до нашої підтримки.
Наша команда завжди готова допомогти вам.
"""
