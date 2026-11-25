"""Insert autolinks into HTML without touching tags or existing anchors."""

from __future__ import annotations

import html
import re
from typing import Any

from modules.autolink.db import rules_for_channel

_TAG_RE = re.compile(r"(<[^>]+>)")
_OPEN_SKIP = ("<a ", "<a>", "<tg-emoji")
_CLOSE_SKIP = ("</a", "</tg-emoji")


def normalize_url(raw: str) -> str | None:
    url = (raw or "").strip()
    if not url or any(ch.isspace() for ch in url):
        return None
    if url.startswith("@"):
        url = "https://t.me/" + url[1:]
    elif url.startswith("t.me/") or url.startswith("telegram.me/"):
        url = "https://" + url
    elif not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.IGNORECASE):
        url = "https://" + url
    if not re.match(r"^https?://", url, re.IGNORECASE) and not url.startswith("tg://"):
        return None
    return url


def split_phrases(raw: str) -> list[str]:
    """One phrase per line. Blank lines are ignored, duplicates dropped."""
    seen: set[str] = set()
    phrases: list[str] = []
    for line in (raw or "").splitlines():
        phrase = " ".join(line.strip().strip("•-").split())
        key = phrase.casefold()
        if not phrase or key in seen:
            continue
        seen.add(key)
        phrases.append(phrase)
    return phrases


def apply_autolinks(text: str, channel_id: int) -> str:
    if not text:
        return text or ""
    rules = rules_for_channel(channel_id)
    if not rules:
        return text
    return _apply_rules(text, rules)


def apply_autolinks_to_post(post_data: dict[str, Any], channel_id: int) -> dict[str, Any]:
    """Return a copy of the draft with phrases linked for this channel."""
    if not post_data or (post_data.get("settings") or {}).get("autolinks") is False:
        return post_data
    rules = rules_for_channel(channel_id)
    if not rules:
        return post_data

    out = dict(post_data)
    text = out.get("text")
    if text:
        out["text"] = _apply_rules(str(text), rules)
    media = []
    changed = False
    for item in out.get("media_files") or []:
        caption = item.get("caption")
        if caption:
            linked = _apply_rules(str(caption), rules)
            if linked != caption:
                item = {**item, "caption": linked}
                changed = True
        media.append(item)
    if changed:
        out["media_files"] = media
    return out


def _apply_rules(source: str, rules: list[tuple[str, str]]) -> str:
    compiled = [
        (
            re.compile(rf"(?<![\w]){re.escape(phrase)}(?![\w])", re.IGNORECASE),
            url,
        )
        for phrase, url in rules
        if phrase and url
    ]
    if not compiled:
        return source

    skip = 0
    chunks: list[str] = []
    for part in _TAG_RE.split(source):
        if not part:
            continue
        if part.startswith("<"):
            lower = part.lower()
            if lower.startswith(_OPEN_SKIP):
                skip += 1
            elif lower.startswith(_CLOSE_SKIP):
                skip = max(0, skip - 1)
            chunks.append(part)
            continue
        chunks.append(part if skip else _link_plain(part, compiled))
    return "".join(chunks)


def _link_plain(text: str, compiled: list[tuple[re.Pattern[str], str]]) -> str:
    occupied = [False] * len(text)
    hits: list[tuple[int, int, str, str]] = []
    for pattern, url in compiled:
        for match in pattern.finditer(text):
            start, end = match.span()
            if any(occupied[start:end]):
                continue
            for index in range(start, end):
                occupied[index] = True
            hits.append((start, end, match.group(0), url))
    if not hits:
        return text

    hits.sort()
    pieces: list[str] = []
    cursor = 0
    for start, end, shown, url in hits:
        pieces.append(text[cursor:start])
        href = html.escape(url, quote=True)
        pieces.append(f'<a href="{href}">{shown}</a>')
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)
