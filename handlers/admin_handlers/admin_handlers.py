from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.types import FSInputFile
from app.runtime import bot
from utils.filters import IsAdmin
from aiogram.fsm.context import FSMContext
from keyboards.client_keyboards.client_keyboards import get_start_keyboard
from keyboards.admin_keyboards.admin_keyboards import (
    admin_keyboard,
    client_card_keyboard,
    clients_list_keyboard,
    get_export_database_keyboard,
)
from database_functions.billing_db import (
    PLANS,
    adjust_tokens,
    grant_beta,
    grant_plan,
    recent_log,
    revoke_plan,
    search_clients,
    set_blocked,
    snapshot,
    extend_plan,
)
from database_functions.client_db import check_user
from states.admin_states import AdminClients
from texts import Admin
from utils.admin_functions import generate_database_export, format_statistics_message
from utils.billing_notify import send_billing_notice, send_billing_notices
from utils.datetime_ui import format_user_datetime
from texts.messages.billing import (
    beta_granted,
    plan_extended,
    plan_granted,
    tokens_credited,
    trial_granted,
)
from datetime import datetime
import os


router = Router()


@router.message(IsAdmin(), F.text.in_(["Адмін панель", "Адмін панель 💻", "/admin"]))
async def admin_panel(message: types.Message):
    await message.answer("Вітаю в адмін панелі. Ось ваші доступні опції.", reply_markup=admin_keyboard())
    
    
@router.message(IsAdmin(), F.text.in_(["Головне меню"]))
async def my_parcel(message: types.Message, state: FSMContext):
    user = message.from_user
    user_id = message.from_user.id
    keyboard = get_start_keyboard(user_id)
    await message.answer("Вітаю в головному меню. Ось ваші доступні опції.", reply_markup=keyboard)
    
    
@router.message(IsAdmin(), F.text.in_(["Статистика"]))
async def statistic_handler(message: types.Message):
    response_message = format_statistics_message()
    await message.answer(response_message, parse_mode="HTML", reply_markup=get_export_database_keyboard())
  
        
@router.callback_query(IsAdmin(), F.data == "export_database")
async def export_database(callback: types.CallbackQuery):
    response_message = (
            "<b>ВИГРУЗКА БАЗИ ДАНИХ</b>\n\n"
            f"Зачекайте поки ми сформуємо ексель файл з базою даних"
        )
    await callback.message.answer(response_message, parse_mode="HTML")
    
    filename, users_count, links_count = generate_database_export()
    
    file = FSInputFile(filename)
    await bot.send_document(
        callback.message.chat.id, 
        document=file, 
        caption=f"📊 База даних експортована\n\n"
                f"👥 Користувачів: {users_count}\n"
                f"🔗 Посилань: {links_count}\n"
                f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    
    if os.path.exists(filename):
        os.remove(filename)


def _client_card(user_id: int) -> str:
    info = snapshot(user_id, with_referrals=True)
    title = PLANS.get(info["stored_plan"], PLANS["none"])["title"]
    status = "заблоковано" if info["blocked"] else ("активний" if info["active"] else "неактивний")
    ends = format_user_datetime(info["ends_at"])
    lines = [
        "<b>Клієнт</b>",
        f"ID <code>{user_id}</code>",
        f"Тариф: <b>{title}</b> · {status}",
        f"До: {ends}",
        f"Токени: <b>{info['tokens']:g}</b>",
        f"Реферали: {info['referrals']}",
        f"Бонусні дні: {info['bonus_days']}",
    ]
    log_rows = recent_log(user_id, 5)
    if log_rows:
        lines.append("")
        lines.append("Журнал:")
        for created, action, detail in log_rows:
            lines.append(
                f"• {format_user_datetime(created)} {action} {detail or ''}".rstrip()
            )
    return "\n".join(lines)


async def _show_client(message: types.Message, user_id: int, *, edit: bool = False) -> None:
    info = snapshot(user_id)
    text = _client_card(user_id)
    markup = client_card_keyboard(user_id, info["blocked"])
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=markup)


_CLIENT_PAGE = 8
_CLIENT_MODES = {"a": "all", "p": "plan", "b": "blocked"}
_MENU_TEXTS = {
    Admin.clients,
    Admin.mailing,
    Admin.stats,
    Admin.admins,
    Admin.links,
    Admin.main_menu,
}


def _client_label(row: tuple) -> str:
    user_id, username, first_name, _last_name, plan, _tokens, blocked = row
    name = f"@{username}" if username else (first_name or str(user_id))
    title = PLANS.get(plan, PLANS["none"])["title"]
    prefix = "🚫 " if blocked else ""
    label = f"{prefix}{name} · {title}"
    return label if len(label) <= 60 else label[:57] + "…"


def _clients_text(total: int, page: int, pages: int, query: str, mode: str) -> str:
    mode_name = {"a": "усі", "p": "з тарифом", "b": "заблоковані"}[mode]
    found = f"Знайдено: <b>{total}</b> · {mode_name}"
    if query:
        import html

        found += f"\nПошук: <code>{html.escape(query)}</code>"
    return (
        f"<b>Клієнти</b>\n{found}\n"
        f"Сторінка {page + 1} з {max(pages, 1)}\n\n"
        "Оберіть клієнта або натисніть «Пошук»."
    )


async def _render_clients(
    message: types.Message,
    state: FSMContext,
    *,
    page: int = 0,
    mode: str = "a",
    edit: bool = False,
) -> None:
    data = await state.get_data()
    query = (data.get("client_query") or "").strip()
    rows, total = search_clients(
        query,
        _CLIENT_MODES.get(mode, "all"),
        offset=page * _CLIENT_PAGE,
        limit=_CLIENT_PAGE,
    )
    pages = max(1, (total + _CLIENT_PAGE - 1) // _CLIENT_PAGE)
    if page >= pages:
        page = pages - 1
        rows, total = search_clients(
            query,
            _CLIENT_MODES.get(mode, "all"),
            offset=page * _CLIENT_PAGE,
            limit=_CLIENT_PAGE,
        )
    await state.update_data(client_page=page, client_mode=mode)
    text = _clients_text(total, page, pages, query, mode)
    if not rows:
        text += "\n\nНікого не знайдено."
    markup = clients_list_keyboard(
        [(int(row[0]), _client_label(row)) for row in rows],
        page=page,
        pages=pages,
        mode=mode,
    )
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.message(IsAdmin(), F.text == Admin.clients)
async def clients_entry(message: types.Message, state: FSMContext):
    await state.clear()
    await state.update_data(client_query="", client_mode="a", client_page=0)
    await _render_clients(message, state)


@router.callback_query(IsAdmin(), F.data.startswith("acl_p_"))
async def clients_page(callback: types.CallbackQuery, state: FSMContext):
    _prefix, _mark, page_raw, mode = callback.data.split("_", 3)
    if mode not in _CLIENT_MODES or not page_raw.isdigit():
        await callback.answer()
        return
    await _render_clients(
        callback.message, state, page=int(page_raw), mode=mode, edit=True
    )
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "acl_noop")
async def clients_noop(callback: types.CallbackQuery):
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "acl_s")
async def clients_search_start(callback: types.CallbackQuery, state: FSMContext):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    await state.set_state(AdminClients.waiting_search)
    await callback.message.edit_text(
        "<b>Пошук клієнта</b>\n\nНадішліть ID, @username або ім'я.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Скасувати", callback_data="acl_back")]
            ]
        ),
    )
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "acl_back")
async def clients_back(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(None)
    await _render_clients(
        callback.message,
        state,
        page=int(data.get("client_page") or 0),
        mode=data.get("client_mode") or "a",
        edit=True,
    )
    await callback.answer()


@router.callback_query(IsAdmin(), F.data.startswith("acl_u_"))
async def clients_open(callback: types.CallbackQuery, state: FSMContext):
    raw = callback.data.removeprefix("acl_u_")
    if not raw.isdigit() or not check_user(int(raw)):
        await callback.answer("Користувача немає", show_alert=True)
        return
    await state.set_state(None)
    await _show_client(callback.message, int(raw), edit=True)
    await callback.answer()


@router.message(IsAdmin(), StateFilter(AdminClients.waiting_search))
async def clients_search_query(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    if text in _MENU_TEXTS:
        return
    await state.set_state(None)
    data = await state.get_data()
    await state.update_data(client_query=text, client_page=0)
    await _render_clients(message, state, page=0, mode=data.get("client_mode") or "a")


@router.callback_query(IsAdmin(), F.data.startswith("ac_grant_"))
async def clients_grant(callback: types.CallbackQuery, state: FSMContext):
    _, _, plan, user_raw = callback.data.split("_", 3)
    if plan not in ("start", "pro", "ultra"):
        await callback.answer()
        return
    await state.set_state(AdminClients.waiting_days)
    await state.update_data(target_id=int(user_raw), grant_plan=plan, day_mode="grant")
    await callback.message.answer(f"Скільки днів видати для {PLANS[plan]['title']}?")
    await callback.answer()


@router.callback_query(IsAdmin(), F.data.startswith("ac_extend_"))
async def clients_extend(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.removeprefix("ac_extend_"))
    await state.set_state(AdminClients.waiting_days)
    await state.update_data(target_id=user_id, day_mode="extend")
    await callback.message.answer("На скільки днів продовжити?")
    await callback.answer()


@router.message(IsAdmin(), StateFilter(AdminClients.waiting_days))
async def clients_days(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip()
    if raw in _MENU_TEXTS:
        return
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer("Надішліть кількість днів числом.")
        return
    data = await state.get_data()
    user_id = int(data["target_id"])
    days = int(raw)
    await state.clear()
    if data.get("day_mode") == "extend":
        error = extend_plan(user_id, days, message.from_user.id)
        if error:
            await message.answer(error)
            return
        info = snapshot(user_id)
        await send_billing_notice(
            user_id,
            plan_extended(
                title=info["title"],
                days=days,
                ends_at=info["ends_at"],
            ),
        )
    else:
        plan_key = data["grant_plan"]
        included = PLANS[plan_key]["tokens"]
        notes = grant_plan(user_id, plan_key, days, message.from_user.id)
        await send_billing_notices(notes)
        info = snapshot(user_id)
        await send_billing_notice(
            user_id,
            plan_granted(
                title=info["title"],
                days=days,
                ends_at=info["ends_at"],
                tokens=included,
                balance=info["tokens"],
            ),
        )
    await _show_client(message, user_id)


@router.callback_query(IsAdmin(), F.data.startswith("ac_trial_"))
async def clients_trial(callback: types.CallbackQuery):
    user_id = int(callback.data.removeprefix("ac_trial_"))
    notes = grant_plan(user_id, "trial", 3, callback.from_user.id)
    await send_billing_notices(notes)
    info = snapshot(user_id)
    await send_billing_notice(user_id, trial_granted(ends_at=info["ends_at"]))
    await _show_client(callback.message, user_id, edit=True)
    await callback.answer("Trial видано")


@router.callback_query(IsAdmin(), F.data.startswith("ac_beta_"))
async def clients_beta(callback: types.CallbackQuery):
    user_id = int(callback.data.removeprefix("ac_beta_"))
    grant_beta(user_id, callback.from_user.id)
    info = snapshot(user_id)
    await send_billing_notice(user_id, beta_granted(ends_at=info["ends_at"]))
    await _show_client(callback.message, user_id, edit=True)
    await callback.answer("Бета видана")


@router.callback_query(IsAdmin(), F.data.startswith("ac_revoke_"))
async def clients_revoke(callback: types.CallbackQuery):
    user_id = int(callback.data.removeprefix("ac_revoke_"))
    revoke_plan(user_id, callback.from_user.id)
    await _show_client(callback.message, user_id, edit=True)
    await callback.answer("План знято")


@router.callback_query(IsAdmin(), F.data.startswith("ac_block_"))
async def clients_block(callback: types.CallbackQuery):
    user_id = int(callback.data.removeprefix("ac_block_"))
    info = snapshot(user_id)
    set_blocked(user_id, not info["blocked"], callback.from_user.id)
    await _show_client(callback.message, user_id, edit=True)
    await callback.answer("Оновлено")


@router.callback_query(IsAdmin(), F.data.startswith("ac_tok_"))
async def clients_pack(callback: types.CallbackQuery):
    _, _, amount_raw, user_raw = callback.data.split("_", 3)
    user_id = int(user_raw)
    amount = int(amount_raw)
    error = adjust_tokens(user_id, amount, callback.from_user.id)
    if error:
        await callback.answer(error, show_alert=True)
        return
    info = snapshot(user_id)
    await send_billing_notice(
        user_id,
        tokens_credited(amount=float(amount), balance=info["tokens"]),
    )
    await _show_client(callback.message, user_id, edit=True)
    await callback.answer("Токени нараховано")


@router.callback_query(IsAdmin(), F.data.startswith("ac_debit_"))
async def clients_debit(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.removeprefix("ac_debit_"))
    await state.set_state(AdminClients.waiting_tokens)
    await state.update_data(target_id=user_id)
    await callback.message.answer("Скільки токенів списати?")
    await callback.answer()


@router.message(IsAdmin(), StateFilter(AdminClients.waiting_tokens))
async def clients_debit_amount(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip().replace(",", ".")
    if (message.text or "").strip() in _MENU_TEXTS:
        return
    try:
        amount = float(raw)
    except ValueError:
        await message.answer("Надішліть число.")
        return
    if amount <= 0:
        await message.answer("Сума має бути більшою за нуль.")
        return
    data = await state.get_data()
    user_id = int(data["target_id"])
    await state.clear()
    error = adjust_tokens(user_id, -amount, message.from_user.id)
    if error:
        await message.answer(error)
        return
    await _show_client(message, user_id)