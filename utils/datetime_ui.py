"""Format DB datetimes for user-visible copy (дд.мм.рррр ГГ:ХХ)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

_DB_PARSE = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)
_USER_DT = "%d.%m.%Y %H:%M"
_USER_DT_SEC = "%d.%m.%Y %H:%M:%S"
_USER_DATE = "%d.%m.%Y"
_ALREADY_USER = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{2,4}")


def format_user_datetime(
    value: Any,
    *,
    empty: str = "—",
    with_seconds: bool = False,
) -> str:
    if value is None:
        return empty
    if isinstance(value, datetime):
        fmt = _USER_DT_SEC if with_seconds else _USER_DT
        return value.strftime(fmt)
    if not isinstance(value, str):
        return empty
    raw = value.strip()
    if not raw:
        return empty
    if _ALREADY_USER.match(raw):
        return raw
    dt = None
    matched: str | None = None
    for pattern in _DB_PARSE:
        try:
            dt = datetime.strptime(raw, pattern)
            matched = pattern
            break
        except ValueError:
            continue
    if dt is None:
        return raw
    if matched == "%Y-%m-%d":
        return dt.strftime(_USER_DATE)
    fmt = _USER_DT_SEC if with_seconds else _USER_DT
    return dt.strftime(fmt)