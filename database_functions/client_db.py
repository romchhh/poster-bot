from datetime import datetime
import sqlite3
from database_functions.connection import conn, cursor


def create_table():
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            user_id NUMERIC,
            user_name TEXT,
            user_first_name TEXT,
            user_last_name TEXT,
            user_phone TEXT,
            language TEXT,
            join_date TEXT,
            last_activity TEXT,
            ref_link INTEGER
        )
    ''')
    conn.commit()
    
    
def add_user(user_id: str, user_name: str, user_first_name: str, user_last_name: str, language: str, ref_link: int = None):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    existing_user = cursor.fetchone()
    if existing_user is None:
        current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO users (user_id, user_name, user_first_name, user_last_name, language, join_date, last_activity, ref_link)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, user_name, user_first_name, user_last_name, language, current_date, current_date, ref_link))
        conn.commit()
        

def check_user(user_id: str):
    cursor.execute("SELECT 1 FROM users WHERE user_id = ? LIMIT 1", (user_id,))
    return cursor.fetchone() is not None


def update_user_activity(user_id: str):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute('''
        UPDATE users 
        SET last_activity = ? 
        WHERE user_id = ?
    ''', (current_time, user_id))
    conn.commit()


def get_user_id_by_username(username: str):
    cursor.execute("SELECT user_id FROM users WHERE user_name = ?", (username,))
    result = cursor.fetchone()
    return result[0] if result else None


def resolve_registered_user_id_from_input(text: str) -> int | None:
    """Юзернейм (@foo або foo) або числовий user_id, якщо користувач є в таблиці users."""
    raw = (text or "").strip()
    if not raw:
        return None
    token = raw.split()[0]
    if token.startswith("@"):
        token = token[1:].strip()
    if not token:
        return None
    if token.lstrip("-").isdigit():
        uid = int(token)
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (uid,))
        row = cursor.fetchone()
        return int(row[0]) if row else None
    cursor.execute(
        "SELECT user_id FROM users WHERE LOWER(user_name) = LOWER(?) LIMIT 1",
        (token,),
    )
    row = cursor.fetchone()
    return int(row[0]) if row else None


def get_username_by_user_id(user_id: str):
    cursor.execute("SELECT user_name FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else None


def migrate_users_settings_columns():
    cursor.execute("PRAGMA table_info(users)")
    existing = {row[1] for row in cursor.fetchall()}
    migrations = [
        ("timezone", "ALTER TABLE users ADD COLUMN timezone TEXT DEFAULT 'Europe/Kyiv'"),
        (
            "notifications_enabled",
            "ALTER TABLE users ADD COLUMN notifications_enabled INTEGER DEFAULT 1",
        ),
        (
            "confirm_publish",
            "ALTER TABLE users ADD COLUMN confirm_publish INTEGER DEFAULT 1",
        ),
    ]
    for col, sql in migrations:
        if col not in existing:
            try:
                cursor.execute(sql)
                conn.commit()
            except sqlite3.OperationalError:
                pass


def _tz_key(raw: str | None) -> str:
    if not raw:
        return "Europe/Kyiv"
    if raw == "Europe/Kiev":
        return "Europe/Kyiv"
    return raw


TIMEZONE_META_UK = {
    "Europe/Kyiv": "🇺🇦 Україна · Київ",
    "Europe/Warsaw": "🇵🇱 Польща · Варшава",
    "Europe/London": "🇬🇧 Велика Британія · Лондон",
    "Europe/Berlin": "🇩🇪 Німеччина · Берлін",
    "Europe/Paris": "🇫🇷 Франція · Париж",
    "Europe/Rome": "🇮🇹 Італія · Рим",
    "Europe/Madrid": "🇪🇸 Іспанія · Мадрид",
    "Europe/Amsterdam": "🇳🇱 Нідерланди · Амстердам",
    "Europe/Stockholm": "🇸🇪 Швеція · Стокгольм",
    "Europe/Oslo": "🇳🇴 Норвегія · Осло",
    "Europe/Helsinki": "🇫🇮 Фінляндія · Гельсінкі",
    "Europe/Copenhagen": "🇩🇰 Данія · Копенгаген",
    "Europe/Prague": "🇨🇿 Чехія · Прага",
    "Europe/Vienna": "🇦🇹 Австрія · Відень",
    "Europe/Budapest": "🇭🇺 Угорщина · Будапешт",
    "Europe/Bucharest": "🇷🇴 Румунія · Бухарест",
    "Europe/Sofia": "🇧🇬 Болгарія · Софія",
    "Europe/Athens": "🇬🇷 Греція · Афіни",
    "Europe/Istanbul": "🇹🇷 Туреччина · Стамбул",
    "America/New_York": "🇺🇸 США · Нью-Йорк",
    "America/Los_Angeles": "🇺🇸 США · Лос-Анджелес",
    "America/Chicago": "🇺🇸 США · Чикаго",
    "America/Denver": "🇺🇸 США · Денвер",
    "America/Toronto": "🇨🇦 Канада · Торонто",
    "America/Vancouver": "🇨🇦 Канада · Ванкувер",
    "Asia/Tokyo": "🇯🇵 Японія · Токіо",
    "Asia/Shanghai": "🇨🇳 Китай · Шанхай",
    "Asia/Dubai": "🇦🇪 ОАЕ · Дубай",
    "Asia/Kolkata": "🇮🇳 Індія · Калькутта",
    "Australia/Sydney": "🇦🇺 Австралія · Сідней",
    "Australia/Melbourne": "🇦🇺 Австралія · Мельбурн",
}


def get_timezone_info():
    from zoneinfo import ZoneInfo

    out = {}
    for tz_id, name_uk in TIMEZONE_META_UK.items():
        try:
            z = ZoneInfo(tz_id)
            now_t = datetime.now(z).strftime("%H:%M")
        except Exception:
            now_t = "--:--"
        out[tz_id] = {"name_uk": name_uk, "current_time": now_t}
    return out


def get_user_timezone(user_id: int) -> str:
    cursor.execute("SELECT timezone FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row and row[0]:
        key = _tz_key(row[0])
        if key not in TIMEZONE_META_UK:
            return "Europe/Kyiv"
        return key
    return "Europe/Kyiv"


def set_user_timezone(user_id: int, timezone_name: str):
    if timezone_name not in TIMEZONE_META_UK:
        return
    cursor.execute(
        "UPDATE users SET timezone = ? WHERE user_id = ?",
        (_tz_key(timezone_name), user_id),
    )
    conn.commit()


def user_timezone_label(user_id: int) -> str:
    """Коротка назва з прапором для відображення в плануванні постів тощо."""
    tid = get_user_timezone(user_id)
    return TIMEZONE_META_UK.get(tid, tid)


def get_user_language(user_id: int) -> str:
    return "uk"


def get_user_notifications_status(user_id: int) -> bool:
    cursor.execute(
        "SELECT notifications_enabled FROM users WHERE user_id = ?", (user_id,)
    )
    row = cursor.fetchone()
    if row is None or row[0] is None:
        return True
    return bool(row[0])


def toggle_user_notifications(user_id: int) -> bool:
    cur = get_user_notifications_status(user_id)
    new_val = 0 if cur else 1
    cursor.execute(
        "UPDATE users SET notifications_enabled = ? WHERE user_id = ?",
        (new_val, user_id),
    )
    conn.commit()
    return bool(new_val)


def get_user_confirm_publish_status(user_id: int) -> bool:
    cursor.execute(
        "SELECT confirm_publish FROM users WHERE user_id = ?", (user_id,)
    )
    row = cursor.fetchone()
    if row is None or row[0] is None:
        return True
    return bool(row[0])


def toggle_user_confirm_publish(user_id: int) -> bool:
    cur = get_user_confirm_publish_status(user_id)
    new_val = 0 if cur else 1
    cursor.execute(
        "UPDATE users SET confirm_publish = ? WHERE user_id = ?",
        (new_val, user_id),
    )
    conn.commit()
    return bool(new_val)


def is_scheduled_post_due(
    scheduled_time_raw: str, user_id: int, tz_name: str | None = None
) -> bool:
    from zoneinfo import ZoneInfo

    try:
        zi = ZoneInfo(tz_name or get_user_timezone(user_id))
    except Exception:
        zi = ZoneInfo("Europe/Kyiv")
    s = (scheduled_time_raw or "").replace("T", " ").strip()
    if len(s) >= 19:
        s = s[:19]
    else:
        return False
    try:
        naive = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False
    scheduled_local = naive.replace(tzinfo=zi)
    now_local = datetime.now(zi)
    return scheduled_local <= now_local


def get_user_stats(user_id: int):
    cursor.execute(
        "SELECT join_date, language, notifications_enabled FROM users WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    join_date_s, _lang, notif = row
    if not join_date_s:
        join_date_s = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        join_dt = datetime.strptime(join_date_s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        join_dt = datetime.now()
    days_with_us = max(0, (datetime.now() - join_dt).days)

    cursor.execute(
        '''
        SELECT COUNT(*)
        FROM channels c
        INNER JOIN channel_memberships cm ON cm.channel_id = c.channel_id
        WHERE cm.user_id = ? AND c.is_active = 1
        ''',
        (user_id,),
    )
    channels_count = cursor.fetchone()[0] or 0

    cursor.execute(
        "SELECT COUNT(*) FROM scheduled_posts WHERE user_id = ? AND status = 'pending'",
        (user_id,),
    )
    scheduled_posts = cursor.fetchone()[0] or 0

    return {
        "join_date": join_date_s,
        "days_with_us": days_with_us,
        "channels_count": channels_count,
        "total_posts": scheduled_posts,
        "scheduled_posts": scheduled_posts,
        "repeat_posts": 0,
        "notifications_enabled": bool(notif) if notif is not None else True,
        "language": "uk",
    }