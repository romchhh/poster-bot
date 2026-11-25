"""Button labels only — used by keyboards and F.text filters.

No HTML screens here. Message copy lives in ``texts.messages``.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


class Btn:
    back = "Назад"
    cancel = "Скасувати"
    next = "Далі"
    yes = "Так"
    no = "Ні"
    save = "Зберегти"
    delete = "Видалити"
    confirm = "Підтвердити"
    update = "Оновити"
    edit = "Редагувати"
    add = "Додати"
    clear = "Очистити"
    sound = "Звук"
    channels = "Канали"
    groups = "Групи"
    settings = "Налаштування"
    support = "Підтримка"
    spacer = " "
    past_day = "·"


class Calendar:
    weekdays = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд")
    months = (
        "Січень",
        "Лютий",
        "Березень",
        "Квітень",
        "Травень",
        "Червень",
        "Липень",
        "Серпень",
        "Вересень",
        "Жовтень",
        "Листопад",
        "Грудень",
    )

    @staticmethod
    def month_title(month: int, year: int) -> str:
        return f"{Calendar.months[month - 1]} {year}"


# ---------------------------------------------------------------------------
# Main menu / support / add channel
# ---------------------------------------------------------------------------


class Main:
    add_channel = "Додати канал"
    create_post = "Створити пост"
    copy = "Копіювання"
    content_plan = "Контент-план"
    search_posts = "Пошук постів"
    edit_post = "Редагувати пост"
    settings = Btn.settings
    support = Btn.support
    my_profile = "Мій профіль"
    admin_panel = "Адмін панель"


class Support:
    support = Btn.support
    news = "Новини"
    manager = "Менеджер"


class AddChannel:
    add_channel = Main.add_channel
    add_group = "Додати групу"
    back = "Повернутися назад"


# ---------------------------------------------------------------------------
# Post
# ---------------------------------------------------------------------------


class Post:
    select_all_channels = "Обрати всі канали"
    all_folders = "Усі папки"
    view_all_channels = "Дивитись всі канали"
    confirm_selection = "Підтвердити вибір"
    select_whole_folder = "Обрати всю папку"
    select_all = "Обрати всі"
    back_to_folders = "Назад до папок"
    back_to_selection = "Назад до вибору"

    edit_text = "Редагувати текст"
    add_text = "Додати текст"
    edit_media = "Редагувати медіа"
    add_media = "Додати медіа"
    edit_buttons = "Редагувати кнопки"
    add_buttons = "Додати кнопки"
    pin = "Закріпити"
    sound = Btn.sound
    comments = "Коментарі"
    apply_channel_format = "Застосувати форматування"
    remove_channel_format = "Прибрати формат каналу"

    publish_now = "Опублікувати зараз"
    schedule = "Запланувати"
    autodel = "Автовидалення"
    no_autodel = "Не видаляти"

    # Create-post editor (screenshot layout)
    text_btn = "Текст"
    media_btn = "Медіа"
    generate_image = "Згенерувати зображення"
    ai = "AI"
    ai_improve = "Покращити"
    ai_rewrite = "Рерайт"
    ai_heads = "Заголовки"
    ai_uk = "UK"
    ai_en = "EN"
    ai_ideas = "Ідеї"
    ai_proof = "Редактура"
    replace_links = "Замінити посилання"
    autosign = "Автопідпис"
    with_sound = "Зі звуком"
    content_protect = "Захист контенту"
    review = "Перевірю"
    no_format = "Без форматування"

    # Publication settings
    delete_timer = "Таймер видалення"
    ad_top = "Рекламний топ"
    autorepeat = "Автоповтор"
    reply_post = "Пост-відповідь"
    copy_publish = "Копіювати"
    forward_publish = "Переслати"
    postpone = "Відкласти"
    publish = "Опублікувати"

    autodel_15m = "15 хв"
    autodel_30m = "30 хв"
    autodel_1h = "1 год"
    autodel_3h = "3 год"
    autodel_6h = "6 год"
    autodel_12h = "12 год"
    autodel_24h = "24 год"
    autodel_48h = "48 год"


def post_edit_button_labels(post_data: dict | None) -> dict[str, str]:
    """Dynamic labels for the post-editor keyboard."""
    post_data = post_data or {}
    has_text = bool(post_data.get("text"))
    has_media = bool(post_data.get("media_files") or post_data.get("media_file_id"))
    has_url = bool(post_data.get("url_buttons"))
    fmt_on = bool(post_data.get("channel_format_active"))
    return {
        "text": Post.edit_text if has_text else Post.add_text,
        "media": Post.edit_media if has_media else Post.add_media,
        "url": Post.edit_buttons if has_url else Post.add_buttons,
        "pin": Post.pin,
        "sound": Post.sound,
        "comments": Post.comments,
        "format": Post.remove_channel_format if fmt_on else Post.apply_channel_format,
    }


def post_autodel_button_label(post_data: dict | None = None) -> str:
    settings = (post_data or {}).get("settings") or {}
    minutes = settings.get("auto_delete_minutes")
    if not minutes:
        return f"{Post.delete_timer}: ні"
    if minutes >= 60 and minutes % 60 == 0:
        return f"{Post.delete_timer}: {minutes // 60} год"
    return f"{Post.delete_timer}: {minutes} хв"


def post_flag_label(title: str, enabled: bool) -> str:
    return f"{title}: {'так' if enabled else 'ні'}"


# ---------------------------------------------------------------------------
# Copy / mirror
# ---------------------------------------------------------------------------


class Copy:
    settings = "Налаштування каналу"
    add_donor = "Додати канал донор"
    change_receiver_group = "Змінити групу-отримувач"
    pick_receiver_group = "Оберіть групу для копії"
    publish_yes = "Так, опублікувати"
    publish_no = "Ні, відхилити"
    edit_post = "Редагувати пост"
    edit_post_news = "Редагувати пост (Новинне API)"
    publish_without_media = "Опублікувати без медіа"
    replace_media = "Замінити медіа"
    gen_media_ai = "Згенерувати медіа (AI)"
    gen_new_ai = "Згенерувати нове (AI)"
    gen_photo_ai = "Згенерувати фото (AI)"
    change_image_ai = "Змінити зображення (AI)"
    send_own_photo = "Надіслати своє фото"
    copy_to_channels = "Копіювати в інші канали"
    schedule_publish = "Запланувати публікацію"
    select_all_channels = Post.select_all_channels
    confirm_and_publish = "Підтвердити та опублікувати"
    schedule_on_date = "Запланувати на дату"
    back_to_folders = "Назад до списку папок"
    back_to_folders_short = "Назад до папок"
    sound_on = "Звук: увімкнений"
    sound_off = "Звук: вимкнений"
    start_copy = "Запустити копіювання"
    pause_copy = "Призупинити копіювання"
    emoji_prefix = "Емодзі на початку"
    emoji_prefix_ok = "Емодзі на початку ✓"
    autosign = "Автопідпис"
    autosign_ok = "Автопідпис ✓"
    ai_rewrite = "ШІ переробка тексту"
    blacklist = "Чорний список слів"
    watermark = "Водяний знак"
    watermark_ok = "Водяний знак ✓"
    add_word = "Додати слово/фразу"
    clear_list = "Очистити список"
    back_to_channel_settings = "Назад до налаштувань каналу"
    back_to_channel_summary = "До підсумку каналу"
    back_to_copy = "До екрану копіювання"
    fallback_chat = "Чат"
    fallback_donor = "Донор"
    fallback_folder = "Папка"


# ---------------------------------------------------------------------------
# Settings / folders / watermark / content plan / admin
# ---------------------------------------------------------------------------


class Settings:
    profile = Main.my_profile
    share = "Поділитися"
    subscription = "Моя підписка"
    my_folders = "Мої папки"
    channels_groups = "Канали та групи"
    all_channels_list = "Усі канали списком"
    to_settings = "У налаштування"
    to_main = "У головне меню"
    channel_settings = "Налаштування каналу"
    editors = "Редактори"
    add_editor = "Додати редактора"
    delete_channel = "Видалити канал"
    delete_last_post = "Видалити останній пост"
    delete_last_folder = "Видалити останній пост з усіх каналів"
    deletion_log = "Журнал видалень"
    delete_group = "Видалити групу"
    to_channels_list = "До списку каналів"
    change_folder_channel = "Змінити папку каналу"
    add_folder_channel = "Додати канал у папку"
    change_folder_group = "Змінити папку групи"
    add_folder_group = "Додати групу у папку"
    replace_emoji = "Замінити емодзі"
    add_premium_emoji = "Додати преміум емодзі"
    add_autosign = "Додати автопідпис"
    to_channel = "До каналу"
    to_folders = "До папок"
    to_settings_short = "До налаштування"
    add_channel_or_group = "Додати канал або групу"
    confirm_publish = "Підтвердження публікації"
    notifications = "Сповіщення бота"
    edit_text = "Редагувати текст"
    rename = "Перейменувати"
    create_folder = "Створити папку"
    create_new_folder = "Створити нову папку"
    get_subscription = "Отримати підписку"
    renew_subscription = "Оновити підписку"
    yes_delete = "Так, видалити"
    datetime_btn = "Дата та час"
    autolinks = "Автопосилання"


class Folder:
    create_new = Settings.create_new_folder
    add_without = "Додати без папки"
    leave_without = "Залишити без папки"
    remove_from = "Без папки (прибрати з папки)"
    to_channel_settings = "До налаштувань каналу"


class Watermark:
    settings = "Налаштування"
    change_image = "Змінити зображення"
    delete = Btn.delete
    add = "Додати водяний знак"
    to_channel = Settings.to_channel
    yes_delete = Settings.yes_delete
    no = Btn.no
    save = Btn.save


class ContentPlan:
    channels = Btn.channels
    groups = Btn.groups
    to_channel_menu = "До меню каналів"
    to_channels_list = Settings.to_channels_list
    to_calendar = "До календаря"
    to_day = "До дня"
    clear_plan = "Очистити план"
    clear_yes = "Очистити"
    clear_exact = "Так, точно очистити"
    from_plan = "З плану"
    open_post = "Відкрити пост"
    edit_now = "Відредагувати"
    publish_now = Post.publish_now
    yes_delete = Settings.yes_delete
    publish_yes = "Так, опублікувати"
    publish_no = Btn.no
    back_to_calendar = "Назад до календаря"


class Admin:
    clients = "Клієнти"
    mailing = "Розсилка"
    stats = "Статистика"
    admins = "Адміністратори"
    links = "Посилання"
    main_menu = "Головне меню"
    export_db = "Вигрузити БД"
    create_mailing = "Зробити розсилку"
    media = "Медіа"
    add_description = "Додати опис"
    url_buttons = "URL-кнопки"
    sound = Btn.sound
    abort = "Відміна"
    publish = "Опублікувати"
    yes = Btn.yes
    no = Btn.no
    add_link = "Додати посилання"
    link_clicks = "переходів"
    edit = Btn.edit
    delete = Btn.delete
    refresh = Btn.update
    add_admin = "Додати адміна"
    transfer_yes = "Так, передати"
    super_mark = "Супер"
