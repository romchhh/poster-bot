from utils.ui_emoji import Icon
from texts import Btn, Copy, Post, Settings
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButtonRequestChat,
)

from database_functions.copy_mirror_db import SCOPE_CHANNEL, SCOPE_FOLDER, list_copy_donors

# Окремо від «Додати канал» (1) та «Додати групу» (2)
COPY_DESTINATION_GROUP_REQUEST_ID = 10


def get_copy_mirror_scope_keyboard(
    folder_rows: list,
    channel_rows: list,
    *,
    configured_scopes: set[tuple[str, int]] | None = None,
) -> InlineKeyboardMarkup:
    if configured_scopes is None:
        configured_scopes = set()

    rows: list[list[InlineKeyboardButton]] = []

    for f in folder_rows:
        fid, name = f[0], f[1]
        count = f[5] if len(f) > 5 else 0
        label = name[:48] + "…" if len(name) > 48 else name
        mark = " ✅" if (SCOPE_FOLDER, int(fid)) in configured_scopes else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{label} ({count}){mark}",
                    callback_data=f"cpy_open_f_{fid}",
                icon_custom_emoji_id=Icon.folder,
            )
            ]
        )

    for row in channel_rows:
        cid = row[1]
        title = (row[2] or Copy.fallback_chat)[:40]
        ctype = row[5] if len(row) > 5 and row[5] else "channel"
        icon = "📺" if ctype == "channel" else "👥"
        mark = " ✅" if (SCOPE_CHANNEL, int(cid)) in configured_scopes else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{icon} {title}{mark}",
                    callback_data=f"cpy_open_c_{cid}",
                icon_custom_emoji_id=Icon.doc,
            )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=Btn.cancel,
                callback_data="cpy_cancel",
                icon_custom_emoji_id=Icon.cancel,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_copy_donor_wait_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=Btn.cancel,
                    callback_data="cpy_cancel_donor",
                    icon_custom_emoji_id=Icon.cancel,
                )
            ],
        ]
    )


def get_copy_manage_keyboard(
    scope_type: str, scope_id: int, *, user_id: int | None = None
) -> InlineKeyboardMarkup:
    st = "f" if scope_type == SCOPE_FOLDER else "c"
    sid = str(scope_id)
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=Copy.add_donor,
                callback_data=f"cpy_add_donor_{st}_{sid}",
                icon_custom_emoji_id=Icon.calendar,
            )
        ],
        [
            InlineKeyboardButton(
                text=Copy.change_receiver_group,
                callback_data=f"cpy_chg_dest_{st}_{sid}",
                icon_custom_emoji_id=Icon.folder,
            )
        ],
    ]
    if user_id is not None:
        if scope_type == SCOPE_CHANNEL:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=Settings.channel_settings,
                        callback_data=f"cpy_stg:{st}:{scope_id}:cpy",
                        icon_custom_emoji_id=Icon.settings,
                    )
                ]
            )
        for did, dtitle, _ad in list_copy_donors(int(user_id), scope_type, int(scope_id)):
            raw = (dtitle or Copy.fallback_donor).strip() or Copy.fallback_donor
            label = raw[:38] + ("…" if len(raw) > 38 else "")
            prefix = "cpy_df" if scope_type == SCOPE_FOLDER else "cpy_dc"
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{label}",
                        callback_data=f"{prefix}:{scope_id}:{int(did)}",
                    icon_custom_emoji_id=Icon.doc,
                )
                ]
            )
    rows.append(
        [
            InlineKeyboardButton(
                text=Copy.back_to_folders_short,
                callback_data="cpy_back_scopes",
                icon_custom_emoji_id=Icon.back,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_copy_destination_group_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=Copy.pick_receiver_group,
                    icon_custom_emoji_id=Icon.folder,
                    request_chat=KeyboardButtonRequestChat(
                        request_id=COPY_DESTINATION_GROUP_REQUEST_ID,
                        chat_is_channel=False,
                        bot_administrator_rights=None,
                        user_administrator_rights=None,
                    ),
                ),
            ],
            [
                KeyboardButton(
                    text=Settings.to_main,
                    icon_custom_emoji_id=Icon.back,
                )
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )




def get_mirror_pending_ui_keyboard(
    pending_id: int,
    *,
    has_any_media: bool,
    has_photo_single: bool,
    photo_message_id: int | None,
    is_media_group: bool,
    bot_username: str | None = None,
):
    """Підтвердження копії з донора: префікси cpyma_/cpymr_/… не перетинаються з approve_post_."""
    pk = int(pending_id)
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=Copy.publish_yes,
                callback_data=f"cpyma_{pk}",
            icon_custom_emoji_id=Icon.ok,
        ),
            InlineKeyboardButton(
                text=Copy.publish_no,
                callback_data=f"cpymr_{pk}",
            icon_custom_emoji_id=Icon.cancel,
        ),
        ],
    ]
    uname = (bot_username or "").strip().lstrip("@")
    if uname:
        rows.append(
            [
                InlineKeyboardButton(
                    text=Copy.edit_post,
                    url=f"https://t.me/{uname}?start=edit_post_{pk}",
                icon_custom_emoji_id=Icon.sign,
            ),
            ],
        )
    if has_any_media:
        rows.append(
            [
                InlineKeyboardButton(
                    text=Copy.publish_without_media,
                    callback_data=f"cpymz_{pk}",
                icon_custom_emoji_id=Icon.ok,
            )
            ]
        )

    if not is_media_group and has_any_media and (has_photo_single or photo_message_id):
        rows.append(
            [
                InlineKeyboardButton(
                    text=Copy.replace_media,
                    callback_data=f"cpymrep_{pk}",
                icon_custom_emoji_id=Icon.refresh,
            )
            ]
        )

    if not is_media_group and (not has_any_media or not photo_message_id):
        rows.append(
            [
                InlineKeyboardButton(
                    text=Copy.gen_media_ai,
                    callback_data=f"cpyaig_{pk}",
                icon_custom_emoji_id=Icon.art,
            )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=Copy.copy_to_channels,
                callback_data=f"cpxst_{pk}",
            icon_custom_emoji_id=Icon.channel,
        ),
            InlineKeyboardButton(
                text=Copy.schedule_publish,
                callback_data=f"cpymt_{pk}",
            icon_custom_emoji_id=Icon.ok,
        ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_mirror_replace_media_keyboard(
    pending_id: int, *, photo_message_id: int | None = None
) -> InlineKeyboardMarkup:
    """Підменю «Замінити медіа»: AI або завантаження свого фото."""
    pk = int(pending_id)
    rows: list[list[InlineKeyboardButton]] = []
    if photo_message_id:
        rows.append(
            [
                InlineKeyboardButton(
                    text=Copy.gen_new_ai,
                    callback_data=f"cpyair_{pk}_{int(photo_message_id)}",
                icon_custom_emoji_id=Icon.art,
            )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text=Copy.gen_new_ai,
                    callback_data=f"cpyaig_{pk}",
                icon_custom_emoji_id=Icon.art,
            )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=Copy.send_own_photo,
                callback_data=f"cpymup_{pk}",
            icon_custom_emoji_id=Icon.photo,
        )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=Btn.back,
                callback_data=f"cpymrb_{pk}",
            icon_custom_emoji_id=Icon.back,
        )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mirror_cross_main_keyboard(pending_id: int, folders: list) -> InlineKeyboardMarkup:
    pk = int(pending_id)
    keyboard = [
        [InlineKeyboardButton(text=Copy.select_all_channels, callback_data=f"cpxmall_{pk}", icon_custom_emoji_id=Icon.ok)]
    ]
    for i, row in enumerate(folders, 1):
        fid, folder_name = row[0], row[1] or f"{Copy.fallback_folder} {fid}"
        text = f"{i}) {folder_name}"
        if len(text) > 55:
            text = text[:52] + "..."
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"cpxfld_{pk}_{fid}",
                    icon_custom_emoji_id=Icon.folder,
                )
            ]
        )
    keyboard.append([InlineKeyboardButton(text=Btn.cancel, callback_data=f"cpxcan_{pk}", icon_custom_emoji_id=Icon.cancel)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def mirror_cross_folder_keyboard(
    pending_id: int, folder_id: int, channels: list, selected_keys: set[str]
) -> InlineKeyboardMarkup:
    pk = int(pending_id)
    fid = int(folder_id)
    keyboard: list[list[InlineKeyboardButton]] = []
    for ch_id_i, ttl in channels:
        ch_id, title = str(ch_id_i), (ttl or str(ch_id_i))[:40]
        key = f"{fid}_{ch_id}"
        is_on = key in selected_keys
        btn_text = title
        if len(btn_text) > 55:
            btn_text = btn_text[:52] + "..."
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"cpxtog_{pk}_{fid}_{ch_id}",
                    icon_custom_emoji_id=Icon.ok if is_on else Icon.cancel,
                )
            ]
        )
    keyboard.append(
        [
            InlineKeyboardButton(
                text=Copy.confirm_and_publish,
                callback_data=f"cpxtok_{pk}",
            icon_custom_emoji_id=Icon.ok,
        )
        ]
    )
    keyboard.append(
        [
            InlineKeyboardButton(
                text=Copy.schedule_on_date,
                callback_data=f"cpxtsc_{pk}",
            icon_custom_emoji_id=Icon.ok,
        )
        ]
    )
    keyboard.append(
        [
            InlineKeyboardButton(
                text=Copy.back_to_folders,
                callback_data=f"cpxtbk_{pk}",
            icon_custom_emoji_id=Icon.back,
        )
        ]
    )
    keyboard.append([InlineKeyboardButton(text=Btn.cancel, callback_data=f"cpxcan_{pk}", icon_custom_emoji_id=Icon.cancel)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)




def get_post_approval_keyboard(
    post_id: int,
    has_media: bool = False,
    is_from_news_api: bool = False,
    photo_message_id: int = None,
    chat_id: str = None,
    *,
    bot_username: str | None = None,
):
    """Якщо потрібні кнопки «Редагувати пост», передайте bot_username з await get_bot_username_for_tme(bot)."""
    keyboard = [
        [
            InlineKeyboardButton(
                text=Copy.publish_yes, 
                callback_data=f"approve_news_api_post_{post_id}" if is_from_news_api else f"approve_post_{post_id}",
            icon_custom_emoji_id=Icon.ok,
        ),
            InlineKeyboardButton(
                text=Copy.publish_no, 
                callback_data=f"reject_post_{post_id}",
            icon_custom_emoji_id=Icon.cancel,
        )
        ]
    ]
    
    # Додаємо кнопки для видалення медіа, якщо є медіа
    if has_media:
        keyboard.append([
            InlineKeyboardButton(
                text=Copy.publish_without_media,
                callback_data=f"approve_news_api_post_no_media_{post_id}" if is_from_news_api else f"approve_post_no_media_{post_id}",
            icon_custom_emoji_id=Icon.ok,
        )
        ])
    
    if is_from_news_api and has_media and photo_message_id and chat_id:
        callback_data = f"regenerate_news_api_image_{post_id}|{photo_message_id}|{chat_id}"
        keyboard.append([
            InlineKeyboardButton(
                text=Copy.change_image_ai,
                callback_data=callback_data,
            icon_custom_emoji_id=Icon.refresh,
        )
        ])
    
    if is_from_news_api and not has_media and chat_id:
        callback_data = f"generate_news_api_image_{post_id}|{chat_id}"
        keyboard.append([
            InlineKeyboardButton(
                text=Copy.gen_photo_ai,
                callback_data=callback_data,
            icon_custom_emoji_id=Icon.art,
        )
        ])
    
    if not is_from_news_api and has_media and photo_message_id and chat_id:
        callback_data = f"regenerate_telegram_image_{post_id}|{photo_message_id}|{chat_id}"
        keyboard.append([
            InlineKeyboardButton(
                text=Copy.change_image_ai,
                callback_data=callback_data,
            icon_custom_emoji_id=Icon.refresh,
        )
        ])

    if not is_from_news_api and chat_id and (not has_media or not photo_message_id):
        callback_data = f"generate_telegram_image_{post_id}|{chat_id}"
        keyboard.append([
            InlineKeyboardButton(
                text=Copy.gen_media_ai,
                callback_data=callback_data,
            icon_custom_emoji_id=Icon.art,
        )
        ])
    
    # Кнопки «Копіювання в інші канали» та «Планування публікації»
    keyboard.append([
        InlineKeyboardButton(
            text=Copy.copy_to_channels,
            callback_data=f"copy_c_start_{post_id}",
        icon_custom_emoji_id=Icon.channel,
    ),
        InlineKeyboardButton(
            text=Copy.schedule_publish,
            callback_data=f"copy_c_start_schedule_{post_id}",
        icon_custom_emoji_id=Icon.ok,
    )
    ])
    u = (bot_username or "").strip().lstrip("@")
    if u:
        if is_from_news_api:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        text=Copy.edit_post_news,
                        url=f"https://t.me/{u}?start=edit_news_api_{post_id}",
                    icon_custom_emoji_id=Icon.sign,
                )
                ]
            )
        else:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        text=Copy.edit_post,
                        url=f"https://t.me/{u}?start=edit_{post_id}",
                    icon_custom_emoji_id=Icon.sign,
                )
                ]
            )

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_media_group_approval_keyboard(
    post_ids, *, bot_username: str | None = None
):
    """bot_username — з await get_bot_username_for_tme(bot); без нього рядок «Редагувати пост» не додається."""
    main_post_id = post_ids[0]
    post_ids_str = ",".join(map(str, post_ids))
    
    keyboard = [
        [
            InlineKeyboardButton(
                text=Copy.publish_yes, 
                callback_data=f"approve_media_group_{post_ids_str}",
            icon_custom_emoji_id=Icon.ok,
        ),
            InlineKeyboardButton(
                text=Copy.publish_no, 
                callback_data=f"reject_media_group_{post_ids_str}",
            icon_custom_emoji_id=Icon.cancel,
        )
        ],
        [
            InlineKeyboardButton(
                text=Copy.copy_to_channels,
                callback_data=f"copy_c_start_mg_{post_ids_str}",
            icon_custom_emoji_id=Icon.channel,
        ),
            InlineKeyboardButton(
                text=Copy.schedule_publish,
                callback_data=f"copy_c_start_mg_schedule_{post_ids_str}",
            icon_custom_emoji_id=Icon.ok,
        )
        ],
    ]
    u = (bot_username or "").strip().lstrip("@")
    if u:
        keyboard.append([
            InlineKeyboardButton(
                text=Copy.edit_post,
                url=f"https://t.me/{u}?start=edit_{main_post_id}",
            icon_custom_emoji_id=Icon.sign,
        )
        ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_copy_channels_main_keyboard(post_id: int, folders: list):
    """Головне меню: Обрати всі + список папок донорів."""
    keyboard = [
        [InlineKeyboardButton(text=Copy.select_all_channels, callback_data=f"copy_c_all_{post_id}", icon_custom_emoji_id=Icon.ok)]
    ]
    for i, row in enumerate(folders, 1):
        fid, folder_name = row[0], row[1] or f"{Copy.fallback_folder} {fid}"
        text = f"{i}) {folder_name}"
        if len(text) > 55:
            text = text[:52] + "..."
        keyboard.append([
            InlineKeyboardButton(
                text=text,
                callback_data=f"copy_c_folder_{post_id}_{fid}",
                icon_custom_emoji_id=Icon.folder,
            )
        ])
    keyboard.append([InlineKeyboardButton(text=Btn.cancel, callback_data=f"copy_c_cancel_{post_id}", icon_custom_emoji_id=Icon.cancel)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_copy_channels_folder_keyboard(post_id: int, folder_id: int, channels: list, selected_keys: set):
    """Список каналів папки з перемикачем ✅/❌ та кнопкою підтвердження."""
    keyboard = []
    for ch in channels:
        ch_id, title = str(ch[0]), (ch[1] or str(ch[0]))[:40]
        key = f"{folder_id}_{ch_id}"
        is_on = key in selected_keys
        btn_text = title
        if len(btn_text) > 55:
            btn_text = btn_text[:52] + "..."
        keyboard.append([InlineKeyboardButton(
            text=btn_text,
            callback_data=f"copy_c_tog_{post_id}_{folder_id}_{ch_id}",
            icon_custom_emoji_id=Icon.ok if is_on else Icon.cancel,
        )])
    keyboard.append([InlineKeyboardButton(
        text=Copy.confirm_and_publish,
        callback_data=f"copy_c_ok_{post_id}",
    icon_custom_emoji_id=Icon.ok,
)])
    keyboard.append([InlineKeyboardButton(
        text=Copy.schedule_on_date,
        callback_data=f"copy_c_sched_{post_id}",
    icon_custom_emoji_id=Icon.ok,
)])
    keyboard.append([InlineKeyboardButton(text=Copy.back_to_folders, callback_data=f"copy_c_back_{post_id}", icon_custom_emoji_id=Icon.back)])
    keyboard.append([InlineKeyboardButton(text=Btn.cancel, callback_data=f"copy_c_cancel_{post_id}", icon_custom_emoji_id=Icon.cancel)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_copy_channels_confirm_keyboard(post_id: int):
    """Підтвердження після «Обрати всі» або з папки: опублікувати зараз або запланувати."""
    keyboard = [
        [InlineKeyboardButton(
            text=Copy.confirm_and_publish,
            callback_data=f"copy_c_ok_{post_id}",
        icon_custom_emoji_id=Icon.ok,
    )],
        [InlineKeyboardButton(
            text=Copy.schedule_on_date,
            callback_data=f"copy_c_sched_{post_id}",
        icon_custom_emoji_id=Icon.ok,
    )],
        [InlineKeyboardButton(text=Copy.back_to_folders, callback_data=f"copy_c_back_{post_id}", icon_custom_emoji_id=Icon.back)],
        [InlineKeyboardButton(text=Btn.cancel, callback_data=f"copy_c_cancel_{post_id}", icon_custom_emoji_id=Icon.cancel)]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

