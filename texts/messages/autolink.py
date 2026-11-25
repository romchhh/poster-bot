"""Autolink screens."""

from __future__ import annotations

import html

from utils.ui_emoji import E

INTRO = (
    f"{E.link} <b>Автопосилання (Автолінкування)</b>\n\n"
    "Ця функція дозволяє автоматично прикріплювати посилання "
    "до визначених слів у ваших текстах.\n\n"
    "⬇️ Оберіть канал для налаштування:"
)

EMPTY_CHANNELS = (
    f"{E.link} <b>Автопосилання</b>\n\n"
    "Спочатку додайте канал або групу — правила зберігаються окремо для кожного чату."
)


def channel_screen(title: str, count: int) -> str:
    safe = html.escape(title or "Канал")
    return (
        f"{E.link} <b>{safe}</b>\n\n"
        f"Наборів: <b>{count}</b>\n\n"
        "Кожен набір — це одне посилання і список слів або фраз. "
        "Довші фрази мають пріоритет. Уже існуючі посилання не перезаписуються."
    )


def ask_name() -> str:
    return (
        f"{E.sign} <b>Новий набір</b>\n\n"
        "Назва для себе, наприклад «Сайт» або «Каталог»."
    )


def ask_url(name: str) -> str:
    return (
        f"{E.link} <b>{html.escape(name)}</b>\n\n"
        "Надішліть посилання. Можна <code>https://…</code>, <code>t.me/…</code> або <code>@channel</code>."
    )


def ask_phrases(name: str, url: str) -> str:
    return (
        f"{E.notes} <b>{html.escape(name)}</b>\n"
        f"{html.escape(url)}\n\n"
        "Надішліть слова або фрази — <b>кожне з нового рядка</b>."
    )


def set_screen(name: str, url: str, enabled: bool, phrases: list[str]) -> str:
    status = "увімкнено" if enabled else "вимкнено"
    lines = "\n".join(f"• {html.escape(phrase)}" for phrase in phrases) or "• ще немає"
    return (
        f"{E.link} <b>{html.escape(name)}</b> — {status}\n"
        f"<a href=\"{html.escape(url, quote=True)}\">{html.escape(url)}</a>\n\n"
        f"<b>Фрази:</b>\n{lines}"
    )


ASK_PREVIEW = (
    f"{E.notes} Надішліть текст — покажу, як він виглядатиме з автопосиланнями цього каналу."
)

BAD_URL = "Це не схоже на посилання. Надішліть https://…, t.me/… або @username."
