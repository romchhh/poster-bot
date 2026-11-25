"""Telethon user-session manager for donor copy / mirror."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.paths import PROJECT_ROOT, SESSIONS_DIR

load_dotenv()
logger = logging.getLogger(__name__)


class TelethonClientManager:
    """Single process-wide Telethon client with lazy connect / disconnect."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._client = None

    @staticmethod
    def _normalize_session_base(path: Path) -> Path:
        if path.suffix.lower() == ".session":
            return path.with_suffix("")
        return path

    def session_base_str(self) -> str:
        from app.config import get_settings

        raw = os.getenv("TELETHON_SESSION_PATH", "").strip()
        if raw:
            p = Path(raw).expanduser()
            if not p.is_absolute():
                p = PROJECT_ROOT / p
        else:
            name = get_settings().telethon_session_name
            if name.lower().endswith(".session"):
                name = name[:-8]
            p = SESSIONS_DIR / name
        return str(self._normalize_session_base(p))

    def resolve_sqlite_session(self) -> tuple[str, Path] | None:
        base = Path(self.session_base_str())
        session_file = base.with_suffix(".session")
        if not session_file.is_file():
            return None
        return str(base), session_file

    @staticmethod
    def interactive_login_disabled() -> bool:
        v = os.getenv("TELETHON_INTERACTIVE_LOGIN", "1").strip().lower()
        return v in ("0", "false", "no", "off")

    async def _run_interactive_login(
        self, session_base: str, api_id: int, api_hash: str
    ) -> None:
        from telethon import TelegramClient

        client = TelegramClient(session_base, api_id, api_hash)
        try:
            print(
                "\n"
                + "=" * 62
                + "\nSkyPost — вхід для копіювання з каналів (Telethon user)\n"
                + "Нижче введіть номер телефону (з +), потім код з Telegram.\n"
                + "Якщо увімкнено 2FA — пароль теж у цій консолі.\n"
                + "Після успіху сесію буде збережено у файлі (папка sessions/).\n"
                + "=" * 62
                + "\n",
                flush=True,
            )
            await client.start()
            print("\n✅ Telethon: сесію збережено. Запускаємо бота…\n", flush=True)
        finally:
            if client.is_connected():
                await client.disconnect()

    async def _sqlite_session_authorized(
        self, session_base: str, api_id: int, api_hash: str
    ) -> bool:
        from telethon import TelegramClient

        client = TelegramClient(session_base, api_id, api_hash)
        try:
            await client.connect()
            return bool(await client.is_user_authorized())
        except Exception:
            logger.exception("Telethon: не вдалося перевірити авторизацію сесії")
            return False
        finally:
            if client.is_connected():
                await client.disconnect()

    async def ensure_session_console(self) -> None:
        if self.interactive_login_disabled():
            return
        if not sys.stdin.isatty():
            return
        if os.getenv("TELETHON_SESSION_STRING", "").strip():
            return

        from app.config import get_settings

        settings = get_settings()
        if not settings.api_id or not settings.api_hash:
            return

        base_str = self.session_base_str()
        Path(base_str).parent.mkdir(parents=True, exist_ok=True)

        # Файл може існувати, але бути порожнім / простроченим / неавторизованим.
        if await self._sqlite_session_authorized(
            base_str, settings.api_id, settings.api_hash
        ):
            return

        try:
            await self._run_interactive_login(
                base_str, settings.api_id, settings.api_hash
            )
        except KeyboardInterrupt:
            print(
                "\n❌ Вхід Telethon скасовано (Ctrl+C). "
                "Моніторинг копій буде вимкнено.\n",
                flush=True,
            )
            raise
        except Exception:
            logger.exception("Telethon: інтерактивний вхід не вдався")

    async def get_client(self):
        async with self._lock:
            if self._client is not None:
                if self._client.is_connected():
                    return self._client
                await self._client.disconnect()

            from app.config import get_settings

            settings = get_settings()
            sid = os.getenv("TELETHON_SESSION_STRING", "").strip()
            if not settings.api_id or not settings.api_hash:
                logger.warning("Telethon: потрібні API_ID та API_HASH у середовищі")
                return None

            sqlite_pair = self.resolve_sqlite_session()
            if not sid and not sqlite_pair:
                logger.warning(
                    "Telethon: немає TELETHON_SESSION_STRING і не знайдено файлу сесії "
                    "(за замовчуванням: %s/<ім'я>.session або TELETHON_SESSION_PATH)",
                    SESSIONS_DIR,
                )
                return None

            try:
                from telethon import TelegramClient
                from telethon.sessions import StringSession

                if sid:
                    cli = TelegramClient(
                        StringSession(sid), settings.api_id, settings.api_hash
                    )
                else:
                    assert sqlite_pair is not None
                    base_str, session_file = sqlite_pair
                    cli = TelegramClient(base_str, settings.api_id, settings.api_hash)
                    logger.info("Telethon: файл сесії %s", session_file)

                await cli.connect()
                if not await cli.is_user_authorized():
                    logger.warning(
                        "Telethon: сесія не авторизована — оновіть TELETHON_SESSION_STRING "
                        "або залогіньтесь (python auth.py)."
                    )
                    await cli.disconnect()
                    return None
                self._client = cli
                logger.info("Telethon user client підключено.")
                return self._client
            except ImportError:
                logger.error("Telethon не встановлений (pip install telethon)")
                return None
            except Exception:
                logger.exception("Telethon: помилка підключення")
                self._client = None
                return None

    async def disconnect(self) -> None:
        async with self._lock:
            if not self._client:
                return
            try:
                await self._client.disconnect()
            except Exception:
                logger.exception("Telethon disconnect")
            finally:
                self._client = None


telethon_manager = TelethonClientManager()


# Back-compat function API
async def ensure_telethon_session_console() -> None:
    await telethon_manager.ensure_session_console()


async def get_telethon_client():
    return await telethon_manager.get_client()


async def disconnect_telethon():
    await telethon_manager.disconnect()
