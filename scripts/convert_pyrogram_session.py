"""One-off: convert sessions/*.pyrogram.session.bak → Telethon sqlite session."""

from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.crypto import AuthKey
from telethon.sessions import SQLiteSession, StringSession

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SESS = ROOT / "sessions"
BAK = SESS / "copy_manager_session_new.pyrogram.session.bak"
DST = SESS / "copy_manager_session_new"

DC_IPV4 = {
    1: "149.154.175.53",
    2: "149.154.167.51",
    3: "149.154.175.100",
    4: "149.154.167.91",
    5: "91.108.56.130",
}


async def main() -> None:
    api_id = int(os.environ["API_ID"])
    api_hash = os.environ["API_HASH"]
    if not BAK.is_file():
        raise SystemExit(f"Missing backup: {BAK}")

    conn = sqlite3.connect(BAK)
    row = conn.execute(
        "SELECT dc_id, api_id, test_mode, auth_key, date, user_id, is_bot FROM sessions"
    ).fetchone()
    conn.close()
    if not row:
        raise SystemExit("Empty pyrogram session")

    dc_id, _sess_api_id, _test_mode, auth_key, _date, user_id, _is_bot = row
    print(f"pyrogram user_id={user_id} dc={dc_id}")

    ss = StringSession()
    ss.set_dc(int(dc_id), DC_IPV4[int(dc_id)], 443)
    ss.auth_key = AuthKey(data=auth_key)

    client = TelegramClient(ss, api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise SystemExit("Converted string session is not authorized")
    me = await client.get_me()
    print(f"string ok: id={me.id} phone={me.phone} username={me.username}")
    string = StringSession.save(client.session)
    await client.disconnect()

    for p in (DST.with_suffix(".session"), DST.with_suffix(".session-journal")):
        p.unlink(missing_ok=True)

    sqlite = SQLiteSession(str(DST))
    loaded = StringSession(string)
    sqlite.set_dc(loaded.dc_id, loaded.server_address, loaded.port)
    sqlite.auth_key = loaded.auth_key
    sqlite.save()

    client2 = TelegramClient(str(DST), api_id, api_hash)
    await client2.connect()
    ok = await client2.is_user_authorized()
    print(f"sqlite authorized={ok}")
    if ok:
        me2 = await client2.get_me()
        print(f"sqlite ok: id={me2.id} phone={me2.phone} username={me2.username}")
    await client2.disconnect()

    if not ok:
        raise SystemExit("SQLite session still unauthorized")

    print(f"saved {DST.with_suffix('.session')}")


if __name__ == "__main__":
    asyncio.run(main())
