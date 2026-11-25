from database_functions.client_db import create_table, migrate_users_settings_columns
from database_functions.links_db import create_table_links
from database_functions.admin_db import create_admins_table, init_superadmin
from database_functions.channels_db import create_channels_table
from database_functions.folders_db import create_folders_table
from database_functions.posts_db import (
    create_post_deletion_log_table,
    create_posts_table,
    create_scheduled_posts_table,
)
from database_functions.migrations import run_posts_migrations
from database_functions.auto_signatures_db import create_auto_signatures_tables
from database_functions.channel_start_emoji_db import create_channel_start_emoji_table
from database_functions.watermark_db import create_watermark_table
from database_functions.copy_mirror_db import create_copy_mirror_tables
from database_functions.clone_db import create_clone_tables
from database_functions.billing_db import create_billing_tables
from modules.autolink.db import create_autolink_tables
from app.config import administrators


def create_dbs():
    create_table()
    create_table_links()
    create_admins_table()
    create_channels_table()
    create_folders_table()
    create_scheduled_posts_table()
    create_posts_table()
    create_post_deletion_log_table()
    run_posts_migrations()
    migrate_users_settings_columns()
    create_auto_signatures_tables()
    create_channel_start_emoji_table()
    create_watermark_table()
    create_copy_mirror_tables()
    create_clone_tables()  # copy_scope_settings, copy_scope_blacklist, copy_scope_auto_subscribe
    create_autolink_tables()
    create_billing_tables()

    if administrators:
        superadmin_id = administrators[0]
        init_superadmin(superadmin_id)

