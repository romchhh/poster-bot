"""User notices for plans, tokens, and referral bonuses."""

from __future__ import annotations

from utils.datetime_ui import format_user_datetime
from utils.ui_emoji import E


def _fmt_ends(ends_at: str | None) -> str:
    return format_user_datetime(ends_at)


def plan_granted(*, title: str, days: int, ends_at: str | None, tokens: float, balance: float) -> str:
    token_line = ""
    if tokens > 0:
        token_line = (
            f"\n{E.list} <b>+{tokens:g} токенів</b> на балансі\n"
            f"Разом: <b>{balance:g}</b> токенів"
        )
    return (
        f"{E.gem} <b>Підписку активовано</b>\n\n"
        f"Тариф: <b>{title}</b>\n"
        f"Термін: <b>{days}</b> дн.\n"
        f"{E.calendar} Діє до: <b>{_fmt_ends(ends_at)}</b>"
        f"{token_line}\n\n"
        f"Публікація, копіювання й автолінкування вже доступні."
    )


def plan_extended(*, title: str, days: int, ends_at: str | None) -> str:
    return (
        f"{E.calendar} <b>Підписку продовжено</b>\n\n"
        f"Тариф: <b>{title}</b>\n"
        f"Додано: <b>+{days}</b> дн.\n"
        f"Нова дата кінця: <b>{_fmt_ends(ends_at)}</b>"
    )


def trial_granted(*, ends_at: str | None) -> str:
    return (
        f"{E.info} <b>Trial активовано</b>\n\n"
        f"3 дні на тестування SkyPost\n"
        f"До <b>2</b> каналів\n"
        f"{E.calendar} Діє до: <b>{_fmt_ends(ends_at)}</b>"
    )


def beta_granted(*, ends_at: str | None) -> str:
    return (
        f"{E.spark} <b>Бета-доступ</b>\n\n"
        f"14 днів із можливостями PRO\n"
        f"Публікація та AI ввімкнені\n"
        f"{E.calendar} Діє до: <b>{_fmt_ends(ends_at)}</b>"
    )


def tokens_credited(*, amount: float, balance: float) -> str:
    return (
        f"{E.list} <b>Токени нараховано</b>\n\n"
        f"Додано: <b>+{amount:g}</b>\n"
        f"Баланс: <b>{balance:g}</b> токенів"
    )


def referral_new_member() -> str:
    return (
        f"{E.editors} <b>Новий реферал</b>\n\n"
        f"Дякуємо за запрошення!\n"
        f"• <b>+3 дні</b> до підписки\n"
        f"• <b>+1 токен</b> на баланс"
    )


def referral_threshold(*, goal: int, days: int, tokens: float) -> str:
    return (
        f"{E.brand} <b>Реферальний поріг {goal}</b>\n\n"
        f"У вас уже <b>{goal}</b> запрошених друзів.\n"
        f"Бонус: <b>+{days}</b> дн. і <b>+{tokens:g}</b> токенів"
    )


def referral_friend_plan(*, plan_title: str, tokens: float) -> str:
    return (
        f"{E.gem} <b>Бонус за реферала</b>\n\n"
        f"Ваш запрошений отримав тариф <b>{plan_title}</b>.\n"
        f"Вам нараховано <b>+{tokens:g}</b> токенів"
    )