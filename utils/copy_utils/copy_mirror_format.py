"""Тексти екрана керування «Копіювання» (спільно для хендлерів і фонових задач)."""

from __future__ import annotations

from utils.ui_emoji import E
import html

from database_functions.channels_db import get_all_channels
from database_functions.copy_mirror_db import (
    SCOPE_FOLDER,
    get_copy_destination,
    list_copy_donors,
)
from database_functions.folders_db import get_user_folders


def format_manage_html(
    user_id: int,
    scope_type: str,
    scope_id: int,
    *,
    success_dest_html: str | None = None,
) -> str:
    dest_row = get_copy_destination(user_id, scope_type, scope_id)

    if scope_type == SCOPE_FOLDER:
        scope_human = "Папка"
        scope_name = None
        for f in get_user_folders(user_id):
            if f[0] == scope_id:
                scope_name = f[1] or str(scope_id)
                break
        scope_name = scope_name or str(scope_id)
        scope_name = html.escape(scope_name)
    else:
        scope_human = "Канал/група SkyPost"
        cn = None
        for r in get_all_channels(user_id=user_id, only_active=True):
            if r[1] == scope_id:
                cn = r[2] or str(scope_id)
                break
        cn = cn or str(scope_id)
        scope_name = html.escape(cn)

    parts = []
    if success_dest_html:
        parts.append(success_dest_html)
    parts.append(
        f"{E.list} <b>Копіювання</b>\n"
        f"{scope_human}: <b>{scope_name}</b>\n"
        f"<code>id {scope_id}</code>"
    )

    if dest_row:
        gid, gtitle = dest_row[0], dest_row[1]
        parts.append(
            f"\n{E.folder} <b>Група-отримувач:</b>\n"
            f"• {html.escape(gtitle or str(gid))}\n"
            f"<code>{gid}</code>\n\n"
            "<i>Групу додано до списку каналів/груп SkyPost для постингу.</i>"
        )
    else:
        parts.append(f"\n{E.warn} <b>Групу ще не обрано.</b>")

    donors = list_copy_donors(user_id, scope_type, scope_id)
    if donors:
        parts.append(
            f"\n{E.channel} <b>Канали-донори:</b> оберіть донора в <b>кнопках нижче</b>."
        )
    else:
        parts.append(f"\n{E.channel} <b>Канали-донори:</b> поки немає.")

    return "\n".join(parts)
