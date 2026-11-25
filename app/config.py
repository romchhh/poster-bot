from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str | None = None) -> str | None:
    value = os.getenv(key)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _env_int(key: str, default: int) -> int:
    raw = _env(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    raw = _env(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _parse_admin_ids(raw: str | None) -> list[int]:
    if not raw:
        return []
    text = raw.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    ids: list[int] = []
    for part in text.split(","):
        part = part.strip().strip("'\"")
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids


@dataclass(frozen=True, slots=True)
class Settings:
    token: str
    administrators: tuple[int, ...]
    api_id: int | None
    api_hash: str | None
    openai_api_key: str | None
    fal_key: str | None
    openai_model: str
    openai_temperature: float
    openai_top_p: float
    openai_frequency_penalty: float
    openai_presence_penalty: float
    openai_max_completion_tokens: int
    openai_seed: int
    openai_timeout: int
    openai_retries: int
    telethon_session_name: str
    timezone: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    token = _env("TOKEN")
    if not token:
        raise RuntimeError("TOKEN is missing in environment (.env)")

    api_id_raw = _env("API_ID")
    api_id: int | None
    try:
        api_id = int(api_id_raw) if api_id_raw else None
    except ValueError:
        api_id = None

    return Settings(
        token=token,
        administrators=tuple(_parse_admin_ids(_env("ADMINISTRATORS"))),
        api_id=api_id,
        api_hash=_env("API_HASH"),
        openai_api_key=_env("OPEN_AI_KEY") or _env("OPENAI_API_KEY"),
        fal_key=_env("FAL_KEY"),
        openai_model=_env("OPENAI_CHAT_MODEL", "gpt-4.1-mini") or "gpt-4.1-mini",
        openai_temperature=_env_float("OPENAI_TEMPERATURE", 0.5),
        openai_top_p=_env_float("OPENAI_TOP_P", 0.9),
        openai_frequency_penalty=_env_float("OPENAI_FREQUENCY_PENALTY", 0.4),
        openai_presence_penalty=_env_float("OPENAI_PRESENCE_PENALTY", 0.1),
        openai_max_completion_tokens=_env_int("OPENAI_MAX_COMPLETION_TOKENS", 1600),
        openai_seed=_env_int("OPENAI_SEED", 42),
        openai_timeout=_env_int("OPENAI_TIMEOUT", 60),
        openai_retries=_env_int("OPENAI_RETRIES", 3),
        telethon_session_name=_env("TELETHON_SESSION_NAME", "copy_manager_session_new")
        or "copy_manager_session_new",
        timezone=_env("BOT_TIMEZONE", "Europe/Kyiv") or "Europe/Kyiv",
    )


# Back-compat aliases used across the codebase
settings = get_settings()
token = settings.token
administrators = list(settings.administrators)
API_ID = str(settings.api_id) if settings.api_id is not None else None
API_HASH = settings.api_hash
DEFAULT_OPENAI_MODEL = settings.openai_model
OPENAI_TEMPERATURE = settings.openai_temperature
OPENAI_TOP_P = settings.openai_top_p
OPENAI_FREQUENCY_PENALTY = settings.openai_frequency_penalty
OPENAI_PRESENCE_PENALTY = settings.openai_presence_penalty
OPENAI_MAX_COMPLETION_TOKENS = settings.openai_max_completion_tokens
OPENAI_SEED = settings.openai_seed
OPENAI_TIMEOUT = settings.openai_timeout
OPENAI_RETRIES = settings.openai_retries
FAL_KEY = settings.fal_key
OPEN_AI_KEY = settings.openai_api_key

# Image generation via OpenAI (as in ReposterBot) — not fal.ai
OPENAI_IMAGE_MODEL = (
    _env("OPENAI_IMAGE_MODEL") or _env("OPENAI_MODEL") or "gpt-image-2.6-flare"
)
OPENAI_IMAGE_SIZE = _env("OPENAI_IMAGE_SIZE", "1024x1024") or "1024x1024"
OPENAI_IMAGE_QUALITY = _env("OPENAI_IMAGE_QUALITY", "high") or "high"
_openai_image_fallbacks = _env("OPENAI_IMAGE_FALLBACK_MODELS", "") or ""
OPENAI_IMAGE_FALLBACK_MODELS = [
    m.strip() for m in _openai_image_fallbacks.split(",") if m.strip()
]
