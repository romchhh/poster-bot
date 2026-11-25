from texts import Main
from texts.messages import main as msg
from aiogram import F, Router, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from database_functions.client_db import add_user, check_user, update_user_activity
from database_functions.links_db import increment_link_count
from keyboards.client_keyboards.client_keyboards import (
    get_start_keyboard,
    get_support_keyboard,
)

router = Router()


@router.message(CommandStart())
async def start_command(message: types.Message, state: FSMContext):
    user = message.from_user
    user_id = user.id
    username = user.username
    args = (message.text or "").split()

    user_exists = check_user(user_id)

    ref_link = None
    if len(args) > 1 and args[1].startswith("linktowatch_"):
        try:
            ref_link = int(args[1].split("_")[1])
            if not user_exists:
                increment_link_count(ref_link)
        except (ValueError, IndexError):
            pass

    referrer_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].removeprefix("ref_"))
        except ValueError:
            referrer_id = None

    if not user_exists:
        add_user(
            user_id,
            username,
            user.first_name,
            user.last_name,
            user.language_code,
            ref_link,
        )
        from database_functions.billing_db import grant_plan, snapshot
        from texts.messages.billing import trial_granted
        from utils.billing_notify import send_billing_notice

        grant_plan(user_id, "trial", 3)
        info = snapshot(user_id)
        await send_billing_notice(user_id, trial_granted(ends_at=info["ends_at"]))
        if referrer_id and check_user(referrer_id):
            from database_functions.billing_db import register_referral

            notes = register_referral(user_id, referrer_id)
            for note in notes:
                try:
                    await message.bot.send_message(referrer_id, note, parse_mode="HTML")
                except Exception:
                    pass

    update_user_activity(user_id)

    if len(args) > 1:
        start_arg = args[1]
        mirror_pk: int | None = None
        if start_arg.startswith("edit_post_"):
            try:
                mirror_pk = int(start_arg.removeprefix("edit_post_"))
            except ValueError:
                mirror_pk = None
        elif start_arg.startswith("cpyed_"):
            try:
                mirror_pk = int(start_arg.removeprefix("cpyed_"))
            except ValueError:
                mirror_pk = None
        if mirror_pk is not None:
            from utils.copy_utils.mirror_flow import (
                mirror_open_editor_from_pending_start,
            )

            if await mirror_open_editor_from_pending_start(message, state, mirror_pk):
                return

    await message.answer(
        msg.START,
        parse_mode="HTML",
        reply_markup=get_start_keyboard(user_id),
    )


@router.message(F.text == Main.my_profile)
async def my_profile(message: types.Message):
    from handlers.client_handlers.settings_account_handlers import profile_payload_for

    update_user_activity(message.from_user.id)
    text, markup = await profile_payload_for(message.from_user)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=markup,
    )


@router.message(F.text.in_([Main.support, "/support"]))
async def support(message: types.Message):
    update_user_activity(message.from_user.id)
    await message.answer(
        text=msg.SUPPORT,
        parse_mode="HTML",
        reply_markup=get_support_keyboard(),
    )


# Kept for older import paths; prefer app.lifecycle
async def on_startup(router=None):
    from app.lifecycle import on_startup as _on_startup

    await _on_startup(router)


async def on_shutdown(router=None):
    from app.lifecycle import on_shutdown as _on_shutdown

    await _on_shutdown(router)
