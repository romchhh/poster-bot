"""Per-channel autolinks: phrase → URL, applied when a post is published."""

from modules.autolink.apply import apply_autolinks, apply_autolinks_to_post
from modules.autolink.db import create_autolink_tables

__all__ = [
    "apply_autolinks",
    "apply_autolinks_to_post",
    "create_autolink_tables",
]
