from aiogram.fsm.state import State, StatesGroup


class AddChannelStates(StatesGroup):
    waiting_for_folder_choice = State()
    waiting_for_new_folder_name = State()
    channel_data_stored = State()


class PostSearch(StatesGroup):
    waiting_query = State()


class PostCreation(StatesGroup):
    waiting_for_content = State()  # Очікування контенту (текст/медіа)
    editing_post = State()  # Редагування поста
    waiting_for_text = State()  # Очікування тексту
    waiting_for_media = State()  # Очікування медіа
    waiting_for_url_buttons = State()  # Очікування URL кнопок
    waiting_for_schedule_time = State()  # Очікування часу планування
    waiting_for_link_replace = State()  # Заміна посилання в пості
    waiting_for_reply = State()  # Пост, на який відповісти
    waiting_for_image_prompt = State()  # Опис для генерації зображення
    waiting_for_ai_source = State()  # Текст або тема для AI-сценарію
    selecting_channels = State()  # Вибір каналів для публікації


class ContentPlan(StatesGroup):
    selecting_channel = State()
    viewing_calendar = State()
    viewing_date = State()
    viewing_post = State()
    editing_post_time_date = State()
    editing_post_time_hour = State()


class AutoSignatureSettings(StatesGroup):
    waiting_for_text = State()
    confirming_save = State()


class ChannelStartEmojiSettings(StatesGroup):
    waiting_for_emoji = State()


class WatermarkStates(StatesGroup):
    waiting_for_watermark_image = State()


class SettingsFolders(StatesGroup):
    waiting_new_folder_name = State()
    waiting_rename_folder = State()


class ChannelEditorsSettings(StatesGroup):
    waiting_for_editor_identifier = State()
    waiting_for_editor_add_confirm = State()


class PostEditing(StatesGroup):
    waiting_for_forwarded_post = State()  # Очікує переслане повідомлення
    editing_post = State()               # Редактор контенту
    waiting_for_text = State()           # Очікує новий текст
    waiting_for_media = State()          # Очікує нове медіа
    waiting_for_url_buttons = State()    # Очікує URL-кнопки
    confirming_edit = State()            # Підтвердження відправки змін


class CopySetup(StatesGroup):
    """Копіювання: вибір scope, група-отримувач (також реєструється в SkyPost для постингу)."""
    selecting_scope = State()
    waiting_for_destination_group = State()
    waiting_for_donor_link = State()
    managing = State()


class CopyMirrorCrosspost(StatesGroup):
    picking_channels = State()


class CopyMirrorReplaceMedia(StatesGroup):
    waiting_for_photo = State()


class CopyChannelSettings(StatesGroup):
    waiting_for_blacklist_word = State()


class AutolinkSetup(StatesGroup):
    waiting_name = State()
    waiting_url = State()
    waiting_phrases = State()
    waiting_extra_phrase = State()
    waiting_preview = State()
