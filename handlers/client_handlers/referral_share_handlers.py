"""Inline invite: photo + caption for «Поділитися» from profile."""

from __future__ import annotations

from aiogram import F, Router, types
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InputTextMessageContent,
)

from texts.messages.referral import invite_share_caption
from utils.referral_share import REFERRAL_SHARE_QUERY, get_referral_photo_file_id

router = Router()


@router.inline_query(F.query == REFERRAL_SHARE_QUERY)
async def referral_invite_inline(inline_query: types.InlineQuery):
    from app.runtime import bot

    user = inline_query.from_user
    if not user:
        await inline_query.answer([], cache_time=0, is_personal=True)
        return
    me = await bot.get_me()
    username = me.username or ""
    if not username:
        await inline_query.answer([], cache_time=0, is_personal=True)
        return
    link = f"https://t.me/{username}?start=ref_{user.id}"
    caption = invite_share_caption(link)
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Підписатися", url=link)],
        ]
    )
    file_id = await get_referral_photo_file_id(bot)
    if file_id:
        result = InlineQueryResultCachedPhoto(
            id=f"ref_{user.id}",
            photo_file_id=file_id,
            title="SkyPost",
            description="Запрошення в SkyPost",
            caption=caption,
            parse_mode="HTML",
            reply_markup=markup,
        )
    else:
        result = InlineQueryResultArticle(
            id=f"ref_{user.id}",
            title="SkyPost",
            description="Запрошення в SkyPost",
            input_message_content=InputTextMessageContent(
                message_text=caption,
                parse_mode="HTML",
                link_preview_options=types.LinkPreviewOptions(is_disabled=False, url=link),
            ),
            reply_markup=markup,
        )
    await inline_query.answer([result], cache_time=0, is_personal=True)