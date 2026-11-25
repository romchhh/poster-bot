from __future__ import annotations

from utils.ui_emoji import E
import html

from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardRemove

from app.runtime import bot
from database_functions.client_db import update_user_activity
from database_functions.channels_db import add_channel, get_all_channels, get_channel_by_id
from database_functions.folders_db import get_user_folders
from database_functions.copy_mirror_db import (
    SCOPE_CHANNEL,
    SCOPE_FOLDER,
    upsert_copy_destination,
    list_destinations_scopes_for_user,
    try_add_copy_donor,
    get_copy_destination,
    insert_copy_mirror_donor_pending,
)
from keyboards.client_keyboards.client_keyboards import get_start_keyboard
from keyboards.client_keyboards.copy_mirror_keyboards import (
    get_copy_mirror_scope_keyboard,
    get_copy_destination_group_reply_keyboard,
    get_copy_manage_keyboard,
    get_copy_donor_wait_keyboard,
    COPY_DESTINATION_GROUP_REQUEST_ID,
)
from states.client_states import CopySetup
from utils.client_functions import get_chat_link
from utils.copy_utils.copy_mirror_format import format_manage_html
from utils.copy_utils.telethon_copy_client import get_telethon_client
from utils.copy_utils.copy_donor_join import (
    JoinDonorKind,
    join_donor_from_parsed,
    parse_donor_channel_ref,
)

router = Router()


async def _try_delete_message(msg: types.Message) -> None:
    try:
        await msg.delete()
    except TelegramBadRequest:
        pass


def _folder_label(user_id: int, folder_id: int) -> str:
    for f in get_user_folders(user_id):
        if f[0] == folder_id:
            return f[1] or str(folder_id)
    return str(folder_id)


def _channel_label(user_id: int, channel_id: int) -> str:
    for r in get_all_channels(user_id=user_id, only_active=True):
        if r[1] == channel_id:
            return r[2] or str(channel_id)
    return str(channel_id)


def _user_owns_folder(user_id: int, folder_id: int) -> bool:
    return any(f[0] == folder_id for f in get_user_folders(user_id))


def _user_owns_channel_row(user_id: int, channel_id: int) -> bool:
    return any(c[1] == channel_id for c in get_all_channels(user_id=user_id, only_active=True))


async def bot_can_send_to_chat_as_admin(chat_id: int) -> tuple[bool, str]:
    try:
        chat = await bot.get_chat(chat_id)
    except TelegramBadRequest as e:
        return False, str(e)

    if getattr(chat, "type", None) == "channel":
        return False, "Потрібна саме <b>група</b> для збору копій, не канал."

    if getattr(chat, "type", None) not in ("group", "supergroup"):
        return False, "Непідтримуваний тип чату. Оберіть групу."

    try:
        m = await bot.get_chat_member(chat_id, bot.id)
    except TelegramBadRequest as e:
        return False, f"Не вдалося перевірити бота в чаті: {e}"

    if m.status == "creator":
        return True, ""

    if m.status != "administrator":
        return False, "Бот має бути <b>адміністратором</b> у цій групі."

    post_ch = getattr(m, "can_post_messages", None)
    if post_ch is False:
        return False, "У бота вимкнено право <b>надсилати повідомлення</b>."

    return True, ""


async def _send_manage_ui_after_reply_keyboard(
    message: types.Message,
    *,
    text: str,
    scope_type: str,
    scope_id: int,
    user_id: int,
) -> None:
    """Знімає reply-клавіатуру, показує меню копіювання з inline-кнопками.

    Повідомлення з ReplyKeyboardRemove у Telegram часто не підлягають edit —
    тому спочатку короткий службовий текст лише з remove (за можливості видаляємо), далі
    окреме повідомлення з текстом і inline-клавіатурою.
    """
    kb = get_copy_manage_keyboard(scope_type, scope_id, user_id=user_id)
    strip = await message.answer(
        "Оновлюю меню копіювання…",
        reply_markup=ReplyKeyboardRemove(),
    )
    try:
        await strip.delete()
    except TelegramBadRequest:
        pass
    await message.answer(
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=kb,
    )


async def send_manage_views(
    message: types.Message,
    user_id: int,
    scope_type: str,
    scope_id: int,
    state: FSMContext,
    *,
    success_intro: str | None = None,
):
    await state.update_data(copy_scope_type=scope_type, copy_scope_id=scope_id)
    await state.set_state(CopySetup.managing)

    txt = format_manage_html(
        user_id, scope_type, scope_id, success_dest_html=success_intro
    )
    await _send_manage_ui_after_reply_keyboard(
        message, text=txt, scope_type=scope_type, scope_id=scope_id, user_id=user_id
    )
    await message.answer(
        text="Головне меню:",
        reply_markup=get_start_keyboard(user_id),
    )


async def process_copy_destination_shared(message: types.Message, state: FSMContext) -> None:
    shared = message.chat_shared
    if not shared:
        return

    if getattr(shared, "request_id", None) != COPY_DESTINATION_GROUP_REQUEST_ID:
        await message.answer(
            "❌ Натисніть кнопку <b>«Оберіть групу для копії»</b>.",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    scope_type = data.get("copy_scope_type")
    scope_id = data.get("copy_scope_id")
    user_id = message.from_user.id

    if scope_type not in (SCOPE_FOLDER, SCOPE_CHANNEL) or scope_id is None:
        await message.answer(
            "❌ Сесія прострочена. Відкрийте «Копіювання» знову.",
            parse_mode="HTML",
        )
        await state.clear()
        return

    chat_id = shared.chat_id
    try:
        chat = await bot.get_chat(chat_id)
        link = get_chat_link(chat)
        title = chat.title or str(chat_id)
    except TelegramBadRequest as e:
        err_raw = html.escape(str(e))
        await message.answer(
            "❌ <b>Не вдалося отримати чат.</b>\n\n"
            "Додайте <b>бота в цю групу як адміністратора</b> з правом "
            "<b>надсилання повідомлень</b> — інакше Telegram не віддасть чат боту "
            "(часто це виглядає як «chat not found»).\n\n"
            f"<i>Деталі: {err_raw}</i>",
            parse_mode="HTML",
        )
        return

    try:
        umem = await bot.get_chat_member(chat_id, user_id)
        if umem.status not in ("administrator", "creator"):
            await message.answer(
                "❌ Ви маєте бути <b>адміністратором</b> цієї групи.",
                parse_mode="HTML",
            )
            return
    except TelegramBadRequest:
        await message.answer(
            "❌ Не вдалося перевірити ваші права в групі.", parse_mode="HTML"
        )
        return

    ok, err = await bot_can_send_to_chat_as_admin(chat_id)
    if not ok:
        await message.answer(
            f"❌ <b>Група не підходить</b>\n\n{err}\n\n"
            f"Чат: <a href=\"{link}\">{html.escape(title)}</a>",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return

    upsert_copy_destination(
        user_id=user_id,
        scope_type=scope_type,
        scope_id=int(scope_id),
        destination_group_id=chat_id,
        destination_title=title,
    )

    folder_id = None
    if scope_type == SCOPE_FOLDER:
        folder_id = int(scope_id)
    elif scope_type == SCOPE_CHANNEL:
        crow = get_channel_by_id(int(scope_id), user_id=user_id)
        if crow and len(crow) > 11 and crow[11] is not None:
            folder_id = int(crow[11])

    user_role = "owner" if umem.status == "creator" else "admin"
    from database_functions.billing_db import ChannelLimitError

    try:
        add_channel(
            channel_id=int(chat_id),
            channel_title=title,
            channel_username=getattr(chat, "username", None) or "",
            channel_link=link,
            added_by_user_id=user_id,
            chat_type=chat.type,
            folder_id=folder_id,
            user_role=user_role,
        )
    except ChannelLimitError as exc:
        await message.answer(str(exc))
        return

    intro = (
        f"✅ <b>Групу для копіювання збережено</b>\n"
        f"Отримувач: <a href=\"{html.escape(link)}\">{html.escape(title)}</a>"
    )
    await send_manage_views(
        message,
        user_id,
        scope_type,
        int(scope_id),
        state,
        success_intro=intro,
    )


@router.message(F.text == "Копіювання")
async def copy_mirror_entry(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    update_user_activity(user_id)
    from database_functions.billing_db import denial

    reason = denial(user_id, "posting")
    if reason:
        await message.answer(reason)
        return
    await state.clear()

    folders = get_user_folders(user_id)
    channels = get_all_channels(user_id=user_id, only_active=True)

    if not folders and not channels:
        await message.answer(
            "❌ <b>Немає папок і каналів</b>\n\nСпочатку «Додати канал».",
            parse_mode="HTML",
        )
        return

    cf = list_destinations_scopes_for_user(user_id)
    await state.set_state(CopySetup.selecting_scope)
    await message.answer(
        text=(
            f"{E.list} <b>Копіювання</b>\n\n"
            "Оберіть <b>папку</b> або <b>канал/групу SkyPost</b> для налаштування.\n"
            "<i>✅ — уже є група-отримувач.</i>\n\n"
            "Якщо є конфігурація — відкриється меню донорів і зміни групи."
        ),
        parse_mode="HTML",
        reply_markup=get_copy_mirror_scope_keyboard(
            folders, channels, configured_scopes=cf
        ),
    )


def _open_scope_pick_or_manage(*, user_id: int, folder_id: int | None, channel_id: int | None):
    if folder_id is not None:
        return (
            SCOPE_FOLDER,
            folder_id,
            _folder_label(user_id, folder_id),
            f"{E.folder} Папка:",
        )
    if channel_id is not None:
        row = next(
            (
                c
                for c in get_all_channels(user_id=user_id, only_active=True)
                if c[1] == channel_id
            ),
            None,
        )
        title = row[2] if row else str(channel_id)
        return SCOPE_CHANNEL, channel_id, title, f"{E.channel} Область:"
    raise ValueError("folder_id or channel_id")


@router.callback_query(CopySetup.selecting_scope, F.data.startswith("cpy_open_f_"))
async def copy_open_folder(callback: types.CallbackQuery, state: FSMContext):
    folder_id = int(callback.data.removeprefix("cpy_open_f_"))
    user_id = callback.from_user.id
    if not _user_owns_folder(user_id, folder_id):
        await callback.answer("❌ Немає доступу", show_alert=True)
        return

    scope_type, scope_id, label, kind = _open_scope_pick_or_manage(
        user_id=user_id, folder_id=folder_id, channel_id=None
    )

    if get_copy_destination(user_id, scope_type, scope_id):
        await state.update_data(copy_scope_type=scope_type, copy_scope_id=scope_id)
        await state.set_state(CopySetup.managing)
        txt = format_manage_html(user_id, scope_type, scope_id)
        await callback.message.edit_text(
            text=txt,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=get_copy_manage_keyboard(
                scope_type, scope_id, user_id=user_id
            ),
        )
        await callback.answer()
        return

    await state.update_data(copy_scope_type=scope_type, copy_scope_id=scope_id)
    await state.set_state(CopySetup.waiting_for_destination_group)

    await callback.message.edit_text(
        text=(
            f"{kind} <b>{html.escape(label)}</b>\n\n"
            f"Натисніть «Оберіть групу для копії» нижче й оберіть групу.\n"
            f"<b>Бот має бути адміном</b> з правом надсилання повідомлень."
        ),
        parse_mode="HTML",
        reply_markup=None,
    )
    await callback.message.answer(
        text="Не використовуйте «Додати групу» з меню каналів — лише кнопку нижче.",
        parse_mode="HTML",
        reply_markup=get_copy_destination_group_reply_keyboard(),
    )
    await callback.answer()


@router.callback_query(CopySetup.selecting_scope, F.data.startswith("cpy_open_c_"))
async def copy_open_channel(callback: types.CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.removeprefix("cpy_open_c_"))
    user_id = callback.from_user.id
    if not _user_owns_channel_row(user_id, channel_id):
        await callback.answer("❌ Немає доступу", show_alert=True)
        return

    scope_type, scope_id, label, kind = _open_scope_pick_or_manage(
        user_id=user_id, folder_id=None, channel_id=channel_id
    )

    if get_copy_destination(user_id, scope_type, scope_id):
        await state.update_data(copy_scope_type=scope_type, copy_scope_id=scope_id)
        await state.set_state(CopySetup.managing)
        txt = format_manage_html(user_id, scope_type, scope_id)
        await callback.message.edit_text(
            text=txt,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=get_copy_manage_keyboard(
                scope_type, scope_id, user_id=user_id
            ),
        )
        await callback.answer()
        return

    await state.update_data(copy_scope_type=scope_type, copy_scope_id=scope_id)
    await state.set_state(CopySetup.waiting_for_destination_group)

    await callback.message.answer(
        text=(
            f"{kind} <b>{html.escape(label)}</b>\n\n"
            f"Натисніть «Оберіть групу для копії».\n"
            f"<b>Бот має бути адміном</b> з правом надсилання повідомлень."
        ),
        parse_mode="HTML",
        reply_markup=get_copy_destination_group_reply_keyboard(),
    )
    await callback.answer()


@router.callback_query(
    CopySetup.managing,
    (F.data.startswith("cpy_add_donor_f_")) | (F.data.startswith("cpy_add_donor_c_")),
)
async def copy_add_donor_cb(callback: types.CallbackQuery, state: FSMContext):
    raw = callback.data
    if raw.startswith("cpy_add_donor_f_"):
        scope_type = SCOPE_FOLDER
        scope_id = int(raw.removeprefix("cpy_add_donor_f_"))
    else:
        scope_type = SCOPE_CHANNEL
        scope_id = int(raw.removeprefix("cpy_add_donor_c_"))
    user_id = callback.from_user.id
    data = await state.get_data()
    if (
        data.get("copy_scope_type") != scope_type
        or int(data.get("copy_scope_id") or -1) != scope_id
    ):
        await callback.answer("Оновіть екран з «Копіювання»", show_alert=True)
        return
    own = (
        _user_owns_folder(user_id, scope_id)
        if scope_type == SCOPE_FOLDER
        else _user_owns_channel_row(user_id, scope_id)
    )
    if not own:
        await callback.answer("❌ Немає доступу", show_alert=True)
        return

    await state.set_state(CopySetup.waiting_for_donor_link)
    donor_txt = (
        "<b>Оберіть канал-донор</b>\n\n"
        "Надішліть посилання на канал або @username каналу, з якого "
        "потрібно клонувати пости (будь-який звичний формат: посилання "
        "<code>t.me</code>, <code>telegram.me</code> або текст на кшталт "
        "<code>@channelusername</code>).\n\n"
        "Якщо канал із підтвердженням запису — після вашого повідомлення "
        "тут буде статус очікування; після підтвердження адміністраторами канал він "
        "зʼявиться в списку донорів автоматично.\n\n"
        "<i>Донор не додається в SkyPost як ваш канал для постингу.</i>"
    )
    prompt_kb = get_copy_donor_wait_keyboard()
    m = callback.message
    prompt_mid: int
    prompt_cid: int
    try:
        await m.edit_text(
            text=donor_txt,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=prompt_kb,
        )
        prompt_mid, prompt_cid = m.message_id, m.chat.id
    except TelegramBadRequest:
        sent = await m.answer(
            text=donor_txt,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=prompt_kb,
        )
        prompt_mid, prompt_cid = sent.message_id, sent.chat.id
    await state.update_data(
        copy_donor_prompt_message_id=prompt_mid,
        copy_donor_prompt_chat_id=prompt_cid,
    )
    await callback.answer()


@router.callback_query(CopySetup.waiting_for_donor_link, F.data == "cpy_cancel_donor")
async def copy_cancel_donor_cb(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    scope_type = data.get("copy_scope_type")
    scope_id = data.get("copy_scope_id")
    if scope_type not in (SCOPE_FOLDER, SCOPE_CHANNEL) or scope_id is None:
        await callback.answer("Оновіть екран з «Копіювання»", show_alert=True)
        return
    own = (
        _user_owns_folder(user_id, int(scope_id))
        if scope_type == SCOPE_FOLDER
        else _user_owns_channel_row(user_id, int(scope_id))
    )
    if not own:
        await callback.answer("❌ Немає доступу", show_alert=True)
        return

    await state.set_state(CopySetup.managing)
    await state.update_data(
        copy_donor_prompt_message_id=None,
        copy_donor_prompt_chat_id=None,
    )
    txt = format_manage_html(user_id, scope_type, int(scope_id))
    try:
        await callback.message.edit_text(
            text=txt,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=get_copy_manage_keyboard(
                scope_type, int(scope_id), user_id=user_id
            ),
        )
    except TelegramBadRequest:
        await callback.message.answer(
            text=txt,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=get_copy_manage_keyboard(
                scope_type, int(scope_id), user_id=user_id
            ),
        )
    await callback.answer()


@router.message(
    CopySetup.waiting_for_donor_link,
    F.text,
    ~F.text.eq("У головне меню"),
)
async def copy_donor_link_received(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip()
    if raw.startswith("/"):
        await message.answer("Надішліть посилання або @канал без команди.")
        return

    data = await state.get_data()
    scope_type = data.get("copy_scope_type")
    scope_id = data.get("copy_scope_id")
    user_id = message.from_user.id

    if scope_type not in (SCOPE_FOLDER, SCOPE_CHANNEL) or scope_id is None:
        await message.answer(
            "❌ Сесія прострочена. Відкрийте «Копіювання» знову.",
            parse_mode="HTML",
        )
        await state.clear()
        return

    own = (
        _user_owns_folder(user_id, int(scope_id))
        if scope_type == SCOPE_FOLDER
        else _user_owns_channel_row(user_id, int(scope_id))
    )
    if not own:
        await message.answer("❌ Немає доступу до цієї області.", parse_mode="HTML")
        await state.clear()
        return

    parsed = parse_donor_channel_ref(raw)
    if not parsed:
        await message.answer(
            "Не розпізнано посилання. Надішліть посилання виду "
            "<code>t.me/+…</code>, <code>t.me/channel</code> або <code>@channel</code>.",
            parse_mode="HTML",
        )
        return

    tl = await get_telethon_client()
    if not tl:
        await message.answer(
            "<b>Сервіс тимчасово недоступний</b>\n\n"
            "Не вдалося активувати перевірку посилань каналів. Спробуйте пізніше.",
            parse_mode="HTML",
        )
        return

    dest_row = get_copy_destination(user_id, scope_type, int(scope_id))
    outcome = await join_donor_from_parsed(tl, parsed)

    if outcome.kind == JoinDonorKind.ERROR:
        await _try_delete_message(message)
        await message.answer(
            outcome.error_uk or "Не вдалося обробити посилання.", parse_mode="HTML"
        )
        return

    if outcome.kind == JoinDonorKind.PENDING_INVITE:
        pend_text = (
            "<b>Очікуємо підтвердження</b>\n\n"
            "Запит на запис до каналу надіслано його адміністраторам. "
            "Після схвалення канал зʼявиться в списку донорів автоматично.\n\n"
            "<i>Перевірка статусу відбувається у фоні — додаткових дій не потрібно.</i>"
        )
        data_p = await state.get_data()
        dm = data_p.get("copy_donor_prompt_message_id")
        dc = data_p.get("copy_donor_prompt_chat_id")
        pend_chat_id: int
        pend_msg_id: int
        if dm is not None and dc is not None:
            try:
                await bot.edit_message_text(
                    chat_id=int(dc),
                    message_id=int(dm),
                    text=pend_text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=get_copy_manage_keyboard(
                        scope_type, int(scope_id), user_id=user_id
                    ),
                )
                pend_chat_id, pend_msg_id = int(dc), int(dm)
            except TelegramBadRequest:
                pend_msg = await message.answer(
                    pend_text,
                    parse_mode="HTML",
                    reply_markup=get_copy_manage_keyboard(
                        scope_type, int(scope_id), user_id=user_id
                    ),
                )
                pend_chat_id = int(pend_msg.chat.id)
                pend_msg_id = int(pend_msg.message_id)
        else:
            pend_msg = await message.answer(
                pend_text,
                parse_mode="HTML",
                reply_markup=get_copy_manage_keyboard(
                    scope_type, int(scope_id), user_id=user_id
                ),
            )
            pend_chat_id = int(pend_msg.chat.id)
            pend_msg_id = int(pend_msg.message_id)

        ins = insert_copy_mirror_donor_pending(
            user_id=user_id,
            scope_type=scope_type,
            scope_id=int(scope_id),
            fingerprint=outcome.fingerprint or "",
            invite_hash=outcome.invite_hash,
            preview_title=outcome.preview_title,
            notify_chat_id=pend_chat_id,
            notify_message_id=pend_msg_id,
        )
        await state.set_state(CopySetup.managing)
        await state.update_data(
            copy_donor_prompt_message_id=None,
            copy_donor_prompt_chat_id=None,
        )
        if ins is None:
            await message.answer(
                "Для цього каналу вже очікується підтвердження запису.",
            )
        await _try_delete_message(message)
        return

    assert outcome.kind == JoinDonorKind.JOINED
    cid = outcome.channel_id
    if cid is None:
        await _try_delete_message(message)
        await message.answer("Не отримано id каналу. Спробуйте інше посилання.")
        return
    if dest_row and cid == dest_row[0]:
        await _try_delete_message(message)
        await message.answer(
            "Це ваш поточний чат або група-отримувач для копій, не канал-донор. "
            "Вкажіть інший канал.",
            parse_mode="HTML",
        )
        return

    title = outcome.title or str(cid)
    inserted = try_add_copy_donor(
        user_id, scope_type, int(scope_id), int(cid), title,
    )
    intro = (
        f"✅ Додано канал-донор: <b>{html.escape(title)}</b>"
        if inserted
        else "ℹ️ Цей канал уже в списку донорів."
    )
    data_ok = await state.get_data()
    donor_mid = data_ok.get("copy_donor_prompt_message_id")
    donor_cid = data_ok.get("copy_donor_prompt_chat_id")
    await state.update_data(copy_scope_type=scope_type, copy_scope_id=int(scope_id))
    await state.set_state(CopySetup.managing)
    await state.update_data(
        copy_donor_prompt_message_id=None,
        copy_donor_prompt_chat_id=None,
    )
    txt_ok = format_manage_html(
        user_id, scope_type, int(scope_id), success_dest_html=intro
    )
    edited_ok = False
    if donor_mid is not None and donor_cid is not None:
        try:
            await bot.edit_message_text(
                chat_id=int(donor_cid),
                message_id=int(donor_mid),
                text=txt_ok,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=get_copy_manage_keyboard(
                    scope_type, int(scope_id), user_id=user_id
                ),
            )
            edited_ok = True
        except TelegramBadRequest:
            pass
    if not edited_ok:
        await _send_manage_ui_after_reply_keyboard(
            message,
            text=txt_ok,
            scope_type=scope_type,
            scope_id=int(scope_id),
            user_id=user_id,
        )
    await _try_delete_message(message)


@router.callback_query(
    CopySetup.managing,
    (F.data.startswith("cpy_chg_dest_f_")) | (F.data.startswith("cpy_chg_dest_c_")),
)
async def copy_change_dest_cb(callback: types.CallbackQuery, state: FSMContext):
    raw = callback.data
    if raw.startswith("cpy_chg_dest_f_"):
        scope_type = SCOPE_FOLDER
        scope_id = int(raw.removeprefix("cpy_chg_dest_f_"))
    else:
        scope_type = SCOPE_CHANNEL
        scope_id = int(raw.removeprefix("cpy_chg_dest_c_"))
    user_id = callback.from_user.id
    data = await state.get_data()
    if (
        data.get("copy_scope_type") != scope_type
        or int(data.get("copy_scope_id") or -1) != scope_id
    ):
        await callback.answer("Оновіть екран", show_alert=True)
        return
    if not (
        _user_owns_folder(user_id, scope_id)
        if scope_type == SCOPE_FOLDER
        else _user_owns_channel_row(user_id, scope_id)
    ):
        await callback.answer("❌ Немає доступу", show_alert=True)
        return

    await state.set_state(CopySetup.waiting_for_destination_group)
    await callback.message.answer(
        text=(
            "🔄 <b>Нова група-отримувач</b>\n\n"
            "Натисніть «Оберіть групу для копії» та надішліть групу. "
            "Попередній запис буде замінено.\n\n"
            "<b>Бот має бути адміном</b> з правом надсилання."
        ),
        parse_mode="HTML",
        reply_markup=get_copy_destination_group_reply_keyboard(),
    )
    await callback.answer()


@router.callback_query(CopySetup.managing, F.data == "cpy_back_scopes")
async def copy_back_to_scopes(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    folders = get_user_folders(user_id)
    channels = get_all_channels(user_id=user_id, only_active=True)
    cf = list_destinations_scopes_for_user(user_id)
    await state.set_state(CopySetup.selecting_scope)
    await callback.message.edit_text(
        text=(
            f"{E.list} <b>Копіювання</b>\n\n"
            "Оберіть папку або канал/групу.\n<i>✅ — є група-отримувач.</i>"
        ),
        parse_mode="HTML",
        reply_markup=get_copy_mirror_scope_keyboard(
            folders, channels, configured_scopes=cf
        ),
    )
    await callback.answer()


@router.callback_query(
    CopySetup.selecting_scope,
    F.data == "cpy_cancel",
)
async def copy_mirror_cancel_inline(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text(text="Скасовано.", parse_mode="HTML")
    except Exception:
        pass
    await callback.message.answer(
        text="Головне меню:",
        reply_markup=get_start_keyboard(callback.from_user.id),
    )
    await callback.answer()


@router.message(StateFilter(CopySetup), F.text == "У головне меню")
async def copy_mirror_exit_any(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    await state.clear()
    await message.answer(text="Головне меню:", reply_markup=get_start_keyboard(uid))
