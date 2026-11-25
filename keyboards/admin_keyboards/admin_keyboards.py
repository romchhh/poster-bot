from utils.ui_emoji import Icon
from texts import Admin, Btn
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup
from database_functions.admin_db import get_all_admins
from database_functions.links_db import get_all_links


# MAIN KEYBOARD
def admin_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text=Admin.clients, icon_custom_emoji_id=Icon.user)],
        [KeyboardButton(text=Admin.mailing, icon_custom_emoji_id=Icon.send) ,KeyboardButton(text=Admin.stats, icon_custom_emoji_id=Icon.stats)], 
        [KeyboardButton(text=Admin.admins, icon_custom_emoji_id=Icon.brand), KeyboardButton(text=Admin.links, icon_custom_emoji_id=Icon.link)],
        [KeyboardButton(text=Admin.main_menu, icon_custom_emoji_id=Icon.back)] 
    ]

    keyboard = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    return keyboard


def client_card_keyboard(user_id: int, blocked: bool) -> InlineKeyboardMarkup:
    uid = int(user_id)
    block_label = "Розблокувати" if blocked else "Заблокувати"
    rows = [
        [
            InlineKeyboardButton(text="START", callback_data=f"ac_grant_start_{uid}"),
            InlineKeyboardButton(text="PRO", callback_data=f"ac_grant_pro_{uid}"),
            InlineKeyboardButton(text="ULTRA", callback_data=f"ac_grant_ultra_{uid}"),
        ],
        [
            InlineKeyboardButton(text="Trial 3 дні", callback_data=f"ac_trial_{uid}"),
            InlineKeyboardButton(text="Бета 14 днів", callback_data=f"ac_beta_{uid}"),
            InlineKeyboardButton(text="Продовжити", callback_data=f"ac_extend_{uid}"),
        ],
        [
            InlineKeyboardButton(text="+50", callback_data=f"ac_tok_50_{uid}"),
            InlineKeyboardButton(text="+150", callback_data=f"ac_tok_150_{uid}"),
            InlineKeyboardButton(text="+500", callback_data=f"ac_tok_500_{uid}"),
        ],
        [
            InlineKeyboardButton(text="Списати токени", callback_data=f"ac_debit_{uid}"),
            InlineKeyboardButton(text="Забрати план", callback_data=f"ac_revoke_{uid}"),
        ],
        [InlineKeyboardButton(text=block_label, callback_data=f"ac_block_{uid}")],
        [InlineKeyboardButton(text="До списку", callback_data="acl_back", icon_custom_emoji_id=Icon.back)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def clients_list_keyboard(
    items: list[tuple[int, str]],
    *,
    page: int,
    pages: int,
    mode: str,
) -> InlineKeyboardMarkup:
    buttons = []
    for user_id, label in items:
        buttons.append(
            [InlineKeyboardButton(text=label, callback_data=f"acl_u_{int(user_id)}")]
        )
    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="‹",
                callback_data=f"acl_p_{page - 1}_{mode}",
                icon_custom_emoji_id=Icon.back,
            )
        )
    nav.append(
        InlineKeyboardButton(text=f"{page + 1}/{max(pages, 1)}", callback_data="acl_noop")
    )
    if page + 1 < pages:
        nav.append(
            InlineKeyboardButton(
                text="›",
                callback_data=f"acl_p_{page + 1}_{mode}",
                icon_custom_emoji_id=Icon.next,
            )
        )
    buttons.append(nav)
    filters = []
    for key, label in (("a", "Усі"), ("p", "З тарифом"), ("b", "Заблоковані")):
        filters.append(
            InlineKeyboardButton(
                text=f"• {label}" if key == mode else label,
                callback_data=f"acl_p_0_{key}",
            )
        )
    buttons.append(filters)
    buttons.append(
        [InlineKeyboardButton(text="Пошук", callback_data="acl_s", icon_custom_emoji_id=Icon.search)]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_export_database_keyboard() -> InlineKeyboardMarkup:
    inline_kb_list = [
        [InlineKeyboardButton(text=Admin.export_db, callback_data="export_database", icon_custom_emoji_id=Icon.search)]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_kb_list)


# BROADCAST KEYBOARD
def get_broadcast_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text=Admin.create_mailing, callback_data="create_post", icon_custom_emoji_id=Icon.doc)]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_post(user_data: dict, user_id: str, url_buttons: list = None) -> InlineKeyboardMarkup:
    inline_kb_list = []
    
    if url_buttons:
        for row in url_buttons:
            inline_kb_list.append([
                InlineKeyboardButton(text=button_text, url=button_url) for button_text, button_url in row
            ])

    inline_kb_list.append([
        InlineKeyboardButton(text=Admin.media, callback_data=f"media_", icon_custom_emoji_id=Icon.photo),
        InlineKeyboardButton(text=Admin.add_description, callback_data=f"description_", icon_custom_emoji_id=Icon.add)
    ])

    inline_kb_list.append([
        InlineKeyboardButton(
            text=Btn.sound,
            callback_data=f"bell_",
            icon_custom_emoji_id=Icon.spark if user_data.get(user_id, {}).get('bell', 0) == 1 else Icon.bell_off,
        ),
        InlineKeyboardButton(text=Admin.url_buttons, callback_data=f"url_buttons_", icon_custom_emoji_id=Icon.link)
    ])

    

    inline_kb_list.append([
        InlineKeyboardButton(text=Admin.abort, callback_data=f"back_to", icon_custom_emoji_id=Icon.back),
        InlineKeyboardButton(text=Btn.next, callback_data=f"nextmailing_", icon_custom_emoji_id=Icon.next)
    ])

    return InlineKeyboardMarkup(inline_keyboard=inline_kb_list)


def publish_post() -> InlineKeyboardMarkup:
    inline_kb_list = [
        [InlineKeyboardButton(text=Admin.publish, callback_data=f"publish_", icon_custom_emoji_id=Icon.ok)],
        [InlineKeyboardButton(text=Btn.back, callback_data=f"back_to", icon_custom_emoji_id=Icon.back)]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_kb_list)


def confirm_mailing() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text=Btn.yes, callback_data=f"confirm_publish_", icon_custom_emoji_id=Icon.ok)],
        [InlineKeyboardButton(text=Btn.no, callback_data="cancel_publish", icon_custom_emoji_id=Icon.cancel)]  
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def back_mailing_keyboard() -> InlineKeyboardMarkup:
    inline_kb_list = [
        [InlineKeyboardButton(text=Btn.back, callback_data="back_to_my_post", icon_custom_emoji_id=Icon.back)]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_kb_list)

def post_keyboard(user_data: dict, user_id: str, url_buttons: list = None) -> InlineKeyboardMarkup:
    inline_kb_list = []
    if url_buttons:
        for row in url_buttons:
            inline_kb_list.append([InlineKeyboardButton(text=button_text, url=button_url) for button_text, button_url in row])

    return InlineKeyboardMarkup(inline_keyboard=inline_kb_list)


# LINKS KEYBOARD
def get_links_keyboard() -> InlineKeyboardMarkup:
    keyboard = []
    links = get_all_links()
    
    for link in links:
        keyboard.append([
            InlineKeyboardButton(
                text=f"{link[1]} ({link[3]} {Admin.link_clicks})",
                callback_data=f"link_stats_{link[0]}",
            icon_custom_emoji_id=Icon.doc,
        )
        ])
    
    keyboard.append([
        InlineKeyboardButton(
            text=Admin.add_link,
            callback_data="add_link",
        icon_custom_emoji_id=Icon.add,
    )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)



def cancel_button() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text=Btn.cancel, icon_custom_emoji_id=Icon.cancel)]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_link_stats_keyboard(link_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text=Admin.edit, callback_data=f"edit_link_{link_id}", icon_custom_emoji_id=Icon.sign),
            InlineKeyboardButton(text=Btn.delete, callback_data=f"delete_link_{link_id}", icon_custom_emoji_id=Icon.trash)
        ],
        [InlineKeyboardButton(text=Admin.refresh, callback_data=f"link_stats_{link_id}", icon_custom_emoji_id=Icon.refresh)],
        [InlineKeyboardButton(text=Btn.back, callback_data="back_to_links", icon_custom_emoji_id=Icon.back)]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_delete_link_confirm_keyboard(link_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text=Btn.yes, callback_data=f"confirm_delete_{link_id}", icon_custom_emoji_id=Icon.ok),
            InlineKeyboardButton(text=Btn.no, callback_data="back_to_links", icon_custom_emoji_id=Icon.cancel)
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ADMINISTRATORS KEYBOARD
def get_admin_list_keyboard(admins: list = None, is_super: bool = False) -> InlineKeyboardMarkup:
    if admins is None:
        admins = get_all_admins()
    
    keyboard = []
    
    for admin in admins:
        user_id = admin[0]
        username = admin[1]
        is_superadmin = admin[3]
        admin_user_name = admin[5] if len(admin) > 5 else None

        display_username = username or admin_user_name or f"ID: {user_id}"
        
        display_name = display_username
        
        # Суперадмін бачить передачу прав та видалення для звичайних адмінів
        if not is_superadmin and is_super:
            keyboard.append([
                InlineKeyboardButton(
                    text=display_name,
                    callback_data=f"admin_info_{user_id}",
                    icon_custom_emoji_id=Icon.user,
                ),
                InlineKeyboardButton(
                    text=Admin.super_mark,
                    callback_data=f"admin_transfer_super_ask_{user_id}",
                    icon_custom_emoji_id=Icon.brand,
                ),
                InlineKeyboardButton(
                    text=Btn.delete,
                    icon_custom_emoji_id=Icon.trash,
                    callback_data=f"admin_remove_id_{user_id}",
                ),
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(
                    text=display_name,
                    callback_data=f"admin_info_{user_id}",
                    icon_custom_emoji_id=Icon.brand if is_superadmin else Icon.user,
                )
            ])
    

    keyboard.append([
        InlineKeyboardButton(text=Admin.add_admin, callback_data="admin_add_new", icon_custom_emoji_id=Icon.add)
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text=Btn.cancel, icon_custom_emoji_id=Icon.cancel, callback_data="admin_cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_transfer_super_confirm_keyboard(target_user_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                text=Admin.transfer_yes,
                callback_data=f"admin_transfer_super_yes_{target_user_id}",
            icon_custom_emoji_id=Icon.ok,
        ),
            InlineKeyboardButton(text=Btn.no, icon_custom_emoji_id=Icon.cancel, callback_data="admin_transfer_super_no"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
