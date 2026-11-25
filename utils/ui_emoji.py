"""Premium (custom) emoji for SkyPost UI — pack ``tgmacicons`` (TG iOS & macOS Icons).

https://t.me/addemoji/tgmacicons

Use ``E.*`` in HTML texts (parse_mode=HTML).
Use ``Icon.*`` for ``icon_custom_emoji_id`` on KeyboardButton / InlineKeyboardButton.
Fallback unicode must match the sticker alt so non‑premium clients still see a sensible icon.
"""

from __future__ import annotations

from typing import Final


def pe(emoji_id: str, fallback: str) -> str:
    """HTML ``<tg-emoji>`` for Bot API parse_mode=HTML."""
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


# --- document ids from stickerset short_name=tgmacicons ---
class Icon:
    """Raw custom_emoji_id strings for button icons."""

    brand: Final = "5258185631355378853"  # ⭐️
    settings: Final = "5258096772776991776"  # ⚙
    channel: Final = "5260268501515377807"  # 📣
    folder: Final = "5257965810634202885"  # 📁
    folder_open: Final = "5258389041006518073"  # 📂
    calendar: Final = "5258105663359294787"  # 🗓
    clock: Final = "5258419835922030550"  # 🕔
    user: Final = "5258362837411045098"  # 👤
    users: Final = "5258513401784573443"  # 👥
    sign: Final = "5258331647358540449"  # ✍️
    notes: Final = "5257965174979042426"  # 📝
    doc: Final = "5258477770735885832"  # 📄
    send: Final = "5258073068852485953"  # ✈️
    art: Final = "5258430848218176413"  # 🎭
    photo: Final = "5258205968025525531"  # 📸
    info: Final = "5258503720928288433"  # ℹ️
    stats: Final = "5258391025281408576"  # 📈
    ok: Final = "5260726538302660868"  # ✅
    ok_alt: Final = "5258057130228849960"  # ✅
    cancel: Final = "5260342697075416641"  # ❌
    warn: Final = "5258474669769497337"  # ❗️
    back: Final = "5258236805890710909"  # ⬅️
    next: Final = "5260450573768990626"  # ➡️
    add: Final = "5258108352008823107"  # ➕
    chat: Final = "5258215846450305872"  # 💬
    support: Final = "5287595522993991899"  # 💬
    copy: Final = "5260379144167890225"  # 🔼 (used as «copy / lift» accent)
    edit_door: Final = "5258084656674250503"  # 🚪
    trash: Final = "5258130763148172425"  # 🗑
    refresh: Final = "5258420634785947640"  # 🔄
    pin: Final = "5258461531464539536"  # 📌
    link: Final = "5257991477358763590"  # ↗️
    gem: Final = "5280962371207077415"  # 💎
    lock: Final = "5258476306152038031"  # 🔒
    search: Final = "5429571366384842791"  # 🔎
    news: Final = "5249231689695115145"  # 📰
    package: Final = "5258134813302332906"  # 📦
    bell_off: Final = "5260264520080695245"  # 🔕
    star: Final = "5260412365739925015"  # ⭐️
    spark: Final = "5258212268742549391"  # 🌠
    list: Final = "5452165780579843515"  # 📁 (list/pack)
    check: Final = "5260416304224936047"  # ✅


class Plus:
    """Pack Plus | Color — https://t.me/addemoji/PlusColorFinal20261026_by_postplus"""

    text: Final = "5402246264756678352"  # 📝
    plus: Final = "5431797310495432237"  # ➕
    ok: Final = "5402561897608293585"  # ✅
    refresh: Final = "5400247670444960474"  # 🔄
    switch_off: Final = "5406920851327069779"  # 🔴
    switch_on: Final = "5406975410296632302"  # 🟢
    bell: Final = "5404737092385285091"  # 🔔
    bell_off: Final = "5404438798316644706"  # 🔕
    clock: Final = "5399887417178108677"  # ⏳
    calendar: Final = "5402282900827713315"  # 🗓️


class E:
    """Themed premium emoji snippets for UI copy (HTML)."""

    brand = pe(Icon.brand, "⭐️")
    settings = pe(Icon.settings, "⚙")
    art = pe(Icon.art, "🎭")
    channel = pe(Icon.channel, "📣")
    folder = pe(Icon.folder, "📁")
    notes = pe(Icon.notes, "📝")
    calendar = pe(Icon.calendar, "🗓")
    clock = pe(Icon.clock, "🕔")
    user = pe(Icon.user, "👤")
    editors = pe(Icon.users, "👥")
    stats = pe(Icon.stats, "📈")
    info = pe(Icon.info, "ℹ️")
    tools = pe(Icon.settings, "⚙")
    list = pe(Icon.doc, "📄")
    add = pe(Icon.add, "➕")
    sign = pe(Icon.sign, "✍️")
    send = pe(Icon.send, "✈️")
    photo = pe(Icon.photo, "📸")
    search = pe(Icon.search, "🔎")
    news = pe(Icon.news, "📰")
    gem = pe(Icon.gem, "💎")
    spark = pe(Icon.spark, "🌠")
    link = pe(Icon.link, "↗️")
    pin = pe(Icon.pin, "📌")
    refresh = pe(Icon.refresh, "🔄")
    trash = pe(Icon.trash, "🗑")
    lock = pe(Icon.lock, "🔒")
    chat = pe(Icon.chat, "💬")
    ok = pe(Icon.ok, "✅")
    fail = pe(Icon.cancel, "❌")
    warn = pe(Icon.warn, "❗️")
    # Plain unicode where pack has no good match (still fine in alerts)
    bell = "🔔"
    water = "💧"
