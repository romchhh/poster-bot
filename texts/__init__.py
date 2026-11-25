"""UI copy for SkyPostBot.

Layout
------
- ``texts.buttons``   — labels for keyboards / ``F.text`` filters
- ``texts.messages``  — HTML / plain screens for handlers

Usage
-----
::

    from texts import Btn, Main, Post
    from texts.messages import main as msg
    from texts.messages.post import multi_channel_selection
"""

from texts.buttons import (
    AddChannel,
    Admin,
    Btn,
    Calendar,
    ContentPlan,
    Copy,
    Folder,
    Main,
    Post,
    Settings,
    Support,
    Watermark,
    post_autodel_button_label,
    post_edit_button_labels,
    post_flag_label,
)
from texts.messages.post import (
    all_channels_view as build_post_all_channels_view_text,
    channel_selection_summary as format_post_channel_selection_summary,
    folder_selection as build_post_folder_selection_text,
    multi_channel_selection as build_post_multi_channel_selection_text,
)

__all__ = [
    "AddChannel",
    "Admin",
    "Btn",
    "Calendar",
    "ContentPlan",
    "Copy",
    "Folder",
    "Main",
    "Post",
    "Settings",
    "Support",
    "Watermark",
    "build_post_all_channels_view_text",
    "build_post_folder_selection_text",
    "build_post_multi_channel_selection_text",
    "format_post_channel_selection_summary",
    "post_autodel_button_label",
    "post_edit_button_labels",
    "post_flag_label",
]
