"""CLI login for the Telethon user that monitors donor channels.

Usage:
  python auth.py

Creates/refreshes sessions/<TELETHON_SESSION_NAME>.session using API_ID / API_HASH
from .env. After that: python main.py
"""

from __future__ import annotations

import asyncio
import getpass
import logging
import os
import re
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

from app.config import get_settings
from app.paths import SESSIONS_DIR, ensure_runtime_dirs

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _session_base() -> Path:
    ensure_runtime_dirs()
    settings = get_settings()
    raw = os.getenv("TELETHON_SESSION_PATH", "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = Path(__file__).resolve().parent / p
    else:
        name = settings.telethon_session_name
        if name.lower().endswith(".session"):
            name = name[:-8]
        p = SESSIONS_DIR / name
    if p.suffix.lower() == ".session":
        p = p.with_suffix("")
    return p


def _normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"[^\d+]", "", (raw or "").strip())
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if digits.isdigit():
        digits = "+" + digits
    if not re.fullmatch(r"\+\d{8,15}", digits):
        return None
    return digits


def _format_me(me) -> str:
    name = " ".join(p for p in (me.first_name, me.last_name) if p).strip()
    username = f"@{me.username}" if me.username else ""
    phone = me.phone or ""
    if phone and not str(phone).startswith("+"):
        phone = f"+{phone}"
    return " · ".join(p for p in (name, username, phone) if p) or str(me.id)


async def authorize() -> int:
    settings = get_settings()
    if not settings.api_id or not settings.api_hash:
        print("❌ Set API_ID and API_HASH in .env (https://my.telegram.org).")
        return 1

    phone_env = os.getenv("TELETHON_PHONE", "").strip()
    phone = _normalize_phone(phone_env or input("Phone (+380…): ").strip())
    if not phone:
        print("❌ Invalid phone. Example: +380XXXXXXXXX")
        return 1

    base = _session_base()
    base.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(base), settings.api_id, settings.api_hash)

    await client.connect()
    try:
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"✅ Already authorized: {_format_me(me)}")
        else:
            await client.send_code_request(phone)
            print("Code sent to Telegram. Enter digits only.")
            while True:
                code = re.sub(r"\D", "", input("Code: ").strip())
                if len(code) < 5:
                    print("Enter the login code from Telegram.")
                    continue
                try:
                    await client.sign_in(phone, code)
                    break
                except SessionPasswordNeededError:
                    password = (
                        os.getenv("TELETHON_2FA_PASSWORD", "").strip()
                        or getpass.getpass("2FA password: ")
                    )
                    await client.sign_in(password=password)
                    break
                except PhoneCodeInvalidError:
                    print("❌ Wrong code, try again.")
                except PhoneCodeExpiredError:
                    print("Code expired, requesting a new one…")
                    await client.send_code_request(phone)
                except FloodWaitError as e:
                    print(f"⏳ Wait {e.seconds}s and try again.")
                    return 1

            me = await client.get_me()
            print(f"✅ Authorized: {_format_me(me)}")
    except Exception:
        logger.exception("Telethon login failed")
        return 1
    finally:
        if client.is_connected():
            await client.disconnect()

    print(f"📁 Session: {base}.session")
    print("Next: python main.py")
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(authorize()))
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)


if __name__ == "__main__":
    main()
