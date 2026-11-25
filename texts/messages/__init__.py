"""HTML / plain message templates for handlers and utils.

Import domain modules explicitly, e.g.::

    from texts.messages import main as msg
    from texts.messages.post import channel_selection_screen
"""

from texts.messages import (
    add_channel,
    admin,
    autolink,
    content_plan,
    copy,
    main,
    post,
    settings,
)

__all__ = [
    "add_channel",
    "admin",
    "autolink",
    "content_plan",
    "copy",
    "main",
    "post",
    "settings",
]
