"""Create / edit / schedule post — screen texts and helpers."""

from __future__ import annotations

import html
from typing import Optional

from texts.buttons import Post
from utils.ui_emoji import E

EDITOR_HINT = "Оберіть подальшу дію"

GENERATE_IMAGE_ASK = (
    f"{E.photo} <b>Згенерувати зображення</b>\n\n"
    "Надішліть короткий опис фото, яке потрібно створити."
)

AI_MENU = (
    f"{E.notes} <b>AI</b>\n\n"
    "Покращити, рерайт, заголовки, переклад, ідеї або редактура."
)

AI_ASK = (
    f"{E.notes} <b>Текст для AI</b>\n\n"
    "Надішліть текст, з яким треба працювати."
)

AI_ASK_IDEAS = (
    f"{E.notes} <b>Ідеї</b>\n\n"
    "Надішліть коротку тему."
)

AI_VARIANTS = f"{E.notes} <b>Оберіть варіант</b>"

PUBLISH_SETTINGS = (
    f"{E.settings} <b>НАЛАШТУВАННЯ ПУБЛІКАЦІЇ</b>\n\n"
    "Оберіть подальшу дію"
)

URL_BUTTONS_INSTRUCTION = """🔗 <b>URL-кнопки</b>

Надішліть список кнопок у форматі:
<code>Текст кнопки - https://посилання.com</code>

<b>Додаткові можливості:</b>
• Кілька кнопок в ряд: розділіть символом <code>|</code>
• До 5 кнопок
• Кольори: палітра нижче, <code>::red</code>, <code>::green</code>, <code>::blue</code> або HEX <code>::#FF8800</code>
• Або: <code>!r</code>, <code>!g</code>, <code>!b</code> перед текстом

<b>Приклад:</b>
<code>Сайт - https://site.com::red
Instagram - https://instagram.com/user::green
Telegram - https://t.me/channel</code>

<b>Кнопки в один ряд:</b>
<code>Кнопка 1 - https://site1.com | Кнопка 2 - https://site2.com</code>

<b>Щоб прибрати кнопки</b> — надішліть крапку або прочерк <code>.</code>, <code>-</code> чи довге тире <code>–</code>"""

_SELECT_INSTRUCTIONS = (
    "Ви можете:\n"
    "• Обрати всі канали одразу\n"
    "• Обрати всю папку\n"
    "• Обрати окремі канали з папки\n"
    "• Обрати канали без папки\n"
    "\n"
    "Оберіть варіант нижче:"
)


def channel_selection_summary(
    selected_ids: Optional[list], all_channel_rows: Optional[list]
) -> str:
    if not selected_ids:
        return f"{E.stats} <b>Поки нічого не обрано.</b>"

    id_set = set(selected_ids)
    folder_hit: dict[int, int] = {}
    no_folder = 0
    for row in all_channel_rows or []:
        if len(row) < 2:
            continue
        cid = row[1]
        if cid not in id_set:
            continue
        fid = row[11] if len(row) > 11 else None
        if fid:
            folder_hit[fid] = folder_hit.get(fid, 0) + 1
        else:
            no_folder += 1

    lines = [f"{E.stats} Обрано каналів: <b>{len(id_set)}</b>"]
    if folder_hit:
        lines.append(f"{E.folder} Папок у виборі: <b>{len(folder_hit)}</b>")
    if no_folder:
        lines.append(f"{E.folder} Без папки: <b>{no_folder}</b>")
    return "\n".join(lines)


def multi_channel_selection(
    selected_ids: Optional[list], all_channel_rows: Optional[list]
) -> str:
    summary = channel_selection_summary(selected_ids, all_channel_rows)
    return (
        f"{E.channel} <b>Вибір каналів для публікації</b>\n\n"
        f"{summary}\n\n"
        f"{_SELECT_INSTRUCTIONS}"
    )


def folder_selection(
    folder_name: str,
    folder_channels: list,
    selected_ids: Optional[list],
    all_channel_rows: Optional[list],
) -> str:
    summary = channel_selection_summary(selected_ids, all_channel_rows)
    safe_name = html.escape(folder_name or "Папка")
    return (
        f"{E.folder} <b>Папка: {safe_name}</b>\n\n"
        f"{summary}\n\n"
        f"Каналів у папці: <b>{len(folder_channels)}</b>\n\n"
        f"Оберіть канали або натисніть «{Post.select_whole_folder}»:"
    )


def all_channels_view(
    selected_ids: Optional[list], all_channel_rows: Optional[list]
) -> str:
    if not all_channel_rows:
        return (
            f"{E.list} <b>Каналів немає.</b> "
            f"Додайте канал або перешліть пост з каналу."
        )
    summary = channel_selection_summary(selected_ids, all_channel_rows)
    return (
        f"{E.list} <b>Усі канали та групи</b>\n\n"
        f"{summary}\n\n"
        f"Натисніть на рядок, щоб <b>додати або зняти</b> канал / групу з вибору.\n\n"
        f"Далі — «{Post.confirm_selection}» або одразу надішліть текст / медіа поста."
    )


# Aliases kept for readable call sites / gradual migration
build_post_multi_channel_selection_text = multi_channel_selection
build_post_folder_selection_text = folder_selection
build_post_all_channels_view_text = all_channels_view
format_post_channel_selection_summary = channel_selection_summary
