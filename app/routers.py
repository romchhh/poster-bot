from __future__ import annotations

from aiogram import Dispatcher


def register_routers(dp: Dispatcher) -> None:
    from handlers.admin_handlers.admin_handlers import router as admin_router
    from handlers.admin_handlers.admin_management_handlers import (
        router as admin_management_router,
    )
    from handlers.admin_handlers.links_handlers import router as links_router
    from handlers.admin_handlers.mailing_handlers import router as mailing_router
    from handlers.client_handlers.add_channel_handlers import router as add_channel_router
    from handlers.client_handlers.channel_track_handlers import (
        router as channel_track_router,
    )
    from handlers.client_handlers.client_handlers import router as client_router
    from handlers.client_handlers.referral_share_handlers import (
        router as referral_share_router,
    )
    from handlers.client_handlers.clone_settings_handlers import (
        router as clone_settings_router,
    )
    from handlers.client_handlers.content_plan_handlers import (
        router as content_plan_router,
    )
    from handlers.client_handlers.copy_handlers import router as copy_handlers_router
    from handlers.client_handlers.copy_mirror_publish_handlers import (
        router as copy_mirror_publish_router,
    )
    from handlers.client_handlers.edit_post_handlers import router as edit_post_router
    from handlers.client_handlers.last_post_handlers import router as last_post_router
    from handlers.client_handlers.post_handlers_simple import (
        router as post_handlers_router,
    )
    from handlers.client_handlers.post_search_handlers import (
        router as post_search_router,
    )
    from handlers.client_handlers.post_schedule_handlers import (
        router as post_schedule_router,
    )
    from handlers.client_handlers.autolink_handlers import router as autolink_router
    from handlers.client_handlers.settings_handlers import router as settings_router
    from handlers.client_handlers.watermark_handlers import router as watermark_router

    # Order matters: narrower / deep-link handlers before broad catch-alls.
    dp.include_router(client_router)
    dp.include_router(referral_share_router)
    dp.include_router(copy_handlers_router)
    dp.include_router(clone_settings_router)
    dp.include_router(copy_mirror_publish_router)
    dp.include_router(add_channel_router)
    dp.include_router(admin_router)
    dp.include_router(mailing_router)
    dp.include_router(links_router)
    dp.include_router(admin_management_router)
    dp.include_router(post_search_router)
    dp.include_router(last_post_router)
    dp.include_router(post_handlers_router)
    dp.include_router(post_schedule_router)
    dp.include_router(content_plan_router)
    dp.include_router(autolink_router)
    dp.include_router(settings_router)
    dp.include_router(edit_post_router)
    dp.include_router(watermark_router)
    dp.include_router(channel_track_router)
