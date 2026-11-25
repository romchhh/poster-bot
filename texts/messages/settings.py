"""Settings hub screens."""

from __future__ import annotations

import html

from utils.ui_emoji import E

INTRO = f"{E.settings} <b>Налаштування SkyPost</b>\n\n"

HUB_FROM_MENU = INTRO + "Канали, папки, часовий пояс і сповіщення — усе поруч."
HUB_BACK = INTRO + "Оберіть розділ нижче."


def _uk_noun(count: int, one: str, few: str, many: str) -> str:
    n = abs(count)
    if n % 10 == 1 and n % 100 != 11:
        word = one
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = few
    else:
        word = many
    return f"{count} {word}"


def profile_screen(
    *,
    name: str,
    user_id: int,
    channels: int,
    groups: int,
    referrals: int,
    plan: str,
    tokens: float,
    bonus_days: int,
    next_goal: int | None,
    link: str,
    low_tokens: bool,
) -> str:
    safe_name = html.escape(name or "Користувач")
    connected = (
        f"{_uk_noun(channels, 'канал', 'канали', 'каналів')}"
        f" · {_uk_noun(groups, 'група', 'групи', 'груп')}"
    )
    progress = (
        f"{referrals} / {next_goal}"
        if next_goal
        else "усі пороги відкриті"
    )
    token_line = f"Токени: <b>{tokens:g}</b>"
    if low_tokens:
        token_line += " · мало для генерації"
    return (
        f"{E.user} <b>Мій профіль</b>\n\n"
        f"{safe_name} · ID <code>{user_id}</code>\n"
        f"Тариф: <b>{html.escape(plan)}</b>\n"
        f"{token_line}\n"
        f"Бонусні дні: <b>{bonus_days}</b>\n"
        f"{E.channel} Підключено: {connected}\n"
        f"{E.editors} Реферали: <b>{referrals}</b> · далі {progress}\n"
        f"Запрошення: <code>{html.escape(link)}</code>\n"
        f"Публікація, копіювання й автолінкування працюють з активним тарифом."
    )
