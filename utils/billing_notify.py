"""Send formatted billing notices to users."""

from __future__ import annotations

from app.runtime import bot

BillingNotice = tuple[int, str]


async def send_billing_notice(user_id: int, text: str) -> None:
    try:
        await bot.send_message(int(user_id), text, parse_mode="HTML")
    except Exception:
        pass


async def send_billing_notices(notices: list[BillingNotice]) -> None:
    for user_id, text in notices:
        await send_billing_notice(user_id, text)