"""Конвертація MessageEntity (Telegram, зміщення в UTF-16) у HTML для parse_mode=HTML."""
from __future__ import annotations

import html as html_module
from typing import Any, Sequence


def _utf16_offset_to_py_index(text: str, utf16_offset: int) -> int:
    raw = text.encode("utf-16-le")
    byte_end = min(max(utf16_offset, 0) * 2, len(raw))
    return len(raw[:byte_end].decode("utf-16-le"))


def convert_entities_to_html(
    text: str, entities: Sequence | None, **kwargs: Any,
) -> str:
    if not text:
        return ""
    if not entities:
        return html_module.escape(text)

    sorted_entities = sorted(entities, key=lambda e: (e.offset, e.length))
    parts: list[str] = []
    prev_py_end = 0

    for entity in sorted_entities:
        start = _utf16_offset_to_py_index(text, entity.offset)
        end = _utf16_offset_to_py_index(text, entity.offset + entity.length)
        start = max(0, min(start, len(text)))
        end = max(start, min(end, len(text)))

        if start > prev_py_end:
            parts.append(html_module.escape(text[prev_py_end:start]))

        mid = html_module.escape(text[start:end])
        et = entity.type

        if et == "bold":
            parts.append(f"<b>{mid}</b>")
        elif et == "italic":
            parts.append(f"<i>{mid}</i>")
        elif et == "underline":
            parts.append(f"<u>{mid}</u>")
        elif et == "strikethrough":
            parts.append(f"<s>{mid}</s>")
        elif et == "spoiler":
            parts.append(f"<tg-spoiler>{mid}</tg-spoiler>")
        elif et == "code":
            parts.append(f"<code>{mid}</code>")
        elif et == "pre":
            lang = getattr(entity, "language", None) or ""
            if lang:
                parts.append(f'<pre><code class="language-{html_module.escape(lang)}">{mid}</code></pre>')
            else:
                parts.append(f"<pre>{mid}</pre>")
        elif et == "text_link":
            url = getattr(entity, "url", "") or ""
            parts.append(f'<a href="{html_module.escape(url)}">{mid}</a>')
        elif et == "text_mention":
            uid = getattr(getattr(entity, "user", None), "id", None)
            if uid is not None:
                parts.append(f'<a href="tg://user?id={uid}">{mid}</a>')
            else:
                parts.append(mid)
        elif et == "custom_emoji":
            eid = getattr(entity, "custom_emoji_id", None) or ""
            parts.append(f'<tg-emoji emoji-id="{html_module.escape(str(eid))}">{mid}</tg-emoji>')
        elif et in ("blockquote", "expandable_blockquote"):
            parts.append(f"<blockquote>{mid}</blockquote>")
        else:
            parts.append(mid)

        prev_py_end = end

    if prev_py_end < len(text):
        parts.append(html_module.escape(text[prev_py_end:]))

    return "".join(parts)
