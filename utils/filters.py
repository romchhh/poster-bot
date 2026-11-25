from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery
from database_functions.admin_db import get_all_admin_ids, is_superadmin


class IsAdmin(Filter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user_id = event.from_user.id
        return user_id in get_all_admin_ids()


class IsSuperAdmin(Filter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user_id = event.from_user.id
        return is_superadmin(user_id)

