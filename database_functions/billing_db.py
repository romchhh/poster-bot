"""Plans, tokens, blocks, and referral rewards. Issued by an admin, not by checkout."""

from __future__ import annotations

from datetime import datetime, timedelta

from database_functions.connection import conn, cursor

PLANS = {
    "none": {"title": "Немає", "channels": 0, "emoji": 0, "tokens": 0, "ai": False, "editors": False, "posting": False},
    "trial": {"title": "Trial", "channels": 2, "emoji": 1, "tokens": 0, "ai": False, "editors": False, "posting": True},
    "beta": {"title": "Бета", "channels": None, "emoji": 3, "tokens": 0, "ai": True, "editors": False, "posting": True},
    "start": {"title": "START", "channels": None, "emoji": 1, "tokens": 0, "ai": False, "editors": False, "posting": True},
    "pro": {"title": "PRO", "channels": None, "emoji": 3, "tokens": 150, "ai": True, "editors": False, "posting": True},
    "ultra": {"title": "ULTRA", "channels": None, "emoji": 10, "tokens": 500, "ai": True, "editors": True, "posting": True},
}

TOKEN_COSTS = {
    "image": 1.0,
    "ai_text": 0.1,
    "image_search": 0.3,
}

class ChannelLimitError(Exception):
    pass


TOKEN_PACKS = (50, 150, 500)
REFERRAL_THRESHOLDS = (5, 10, 20, 50, 100)
THRESHOLD_BONUS = {
    5: (7, 5),
    10: (14, 10),
    20: (30, 25),
    50: (60, 50),
    100: (90, 100),
}
PAID_REFERRAL_TOKENS = {"pro": 10, "ultra": 25}


def create_billing_tables() -> None:
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_billing (
            user_id INTEGER PRIMARY KEY,
            plan TEXT NOT NULL DEFAULT 'none',
            ends_at TEXT,
            token_balance REAL NOT NULL DEFAULT 0,
            bonus_days INTEGER NOT NULL DEFAULT 0,
            referred_by INTEGER,
            blocked INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS billing_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            actor_id INTEGER,
            action TEXT NOT NULL,
            detail TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS referral_rewards (
            user_id INTEGER NOT NULL,
            reward_key TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, reward_key)
        );
        """
    )
    conn.commit()


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _fmt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _ensure(user_id: int) -> None:
    cursor.execute("INSERT OR IGNORE INTO user_billing (user_id) VALUES (?)", (int(user_id),))
    conn.commit()


def _log(user_id: int, action: str, detail: str, actor_id: int | None = None) -> None:
    cursor.execute(
        """
        INSERT INTO billing_log (user_id, actor_id, action, detail, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (int(user_id), actor_id, action, (detail or "")[:300], _fmt(_now())),
    )
    conn.commit()


def _claim(user_id: int, key: str) -> bool:
    try:
        cursor.execute(
            "INSERT INTO referral_rewards (user_id, reward_key, created_at) VALUES (?, ?, ?)",
            (int(user_id), key, _fmt(_now())),
        )
        conn.commit()
        return True
    except Exception:
        return False


def snapshot(user_id: int, *, with_referrals: bool = False) -> dict:
    cursor.execute(
        """
        SELECT plan, ends_at, token_balance, bonus_days, referred_by, blocked
        FROM user_billing WHERE user_id = ?
        """,
        (int(user_id),),
    )
    row = cursor.fetchone()
    if row is None:
        _ensure(user_id)
        row = ("none", None, 0, 0, None, 0)
    plan = row[0] or "none"
    if plan not in PLANS:
        plan = "none"
    ends = _parse(row[1])
    blocked = bool(row[5])
    active = (not blocked) and plan != "none" and ends is not None and ends > _now()
    spec = PLANS[plan if active else "none"]
    if active:
        spec = PLANS[plan]
    referrals = 0
    next_goal = None
    if with_referrals:
        cursor.execute("SELECT COUNT(*) FROM user_billing WHERE referred_by = ?", (int(user_id),))
        referrals = int(cursor.fetchone()[0] or 0)
        next_goal = next((item for item in REFERRAL_THRESHOLDS if item > referrals), None)
    return {
        "user_id": int(user_id),
        "plan": plan if active else "none",
        "stored_plan": plan,
        "title": spec["title"] if active else "Немає",
        "ends_at": row[1],
        "active": active,
        "blocked": blocked,
        "tokens": float(row[2] or 0),
        "bonus_days": int(row[3] or 0),
        "referred_by": row[4],
        "referrals": referrals,
        "next_goal": next_goal,
        "channel_limit": spec["channels"],
        "emoji_limit": spec["emoji"],
        "posting": bool(spec["posting"]) and active,
        "ai": bool(spec["ai"]) and active,
        "editors": bool(spec["editors"]) and active,
    }


def _reason(info: dict, feature: str) -> str | None:
    if info["blocked"]:
        return "Акаунт заблоковано. Напишіть у підтримку."
    if feature == "ai":
        if not info["active"]:
            return "Потрібна активна підписка. Її видає адміністратор."
        if not info["ai"]:
            return "AI доступний на PRO, ULTRA і в беті."
        return None
    if feature == "editors":
        if not info["editors"]:
            return "Редакторів каналу може додавати лише тариф ULTRA."
        return None
    if not info["posting"]:
        return "Потрібна активна підписка. Її видає адміністратор."
    return None


def denial(user_id: int, feature: str) -> str | None:
    return _reason(snapshot(user_id), feature)


def refund_tokens(user_id: int, kind: str) -> None:
    cost = TOKEN_COSTS.get(kind)
    if not cost:
        return
    _add_tokens(user_id, cost)
    _log(user_id, "refund", f"{kind}:{cost:g}")


def spend_tokens(user_id: int, kind: str) -> str | None:
    info = snapshot(user_id)
    reason = _reason(info, "ai" if kind in TOKEN_COSTS else "posting")
    if reason:
        return reason
    cost = TOKEN_COSTS[kind]
    if info["tokens"] + 1e-9 < cost:
        return f"Не вистачає токенів: потрібно {cost:g}, на балансі {info['tokens']:g}."
    cursor.execute(
        "UPDATE user_billing SET token_balance = token_balance - ? WHERE user_id = ?",
        (cost, int(user_id)),
    )
    conn.commit()
    _log(user_id, "spend", f"{kind}:{cost:g}")
    return None


def _add_tokens(user_id: int, amount: float) -> None:
    _ensure(user_id)
    cursor.execute(
        "UPDATE user_billing SET token_balance = token_balance + ? WHERE user_id = ?",
        (float(amount), int(user_id)),
    )
    conn.commit()


def _add_days(user_id: int, days: int, *, as_plan: str | None = None, count_bonus: bool = True) -> str:
    _ensure(user_id)
    info = snapshot(user_id)
    base = _parse(info["ends_at"])
    start = base if base and base > _now() else _now()
    ends = start + timedelta(days=int(days))
    stored = info["stored_plan"]
    plan = as_plan or (stored if stored != "none" else "start")
    bonus = int(days) if count_bonus else 0
    cursor.execute(
        """
        UPDATE user_billing
        SET plan = ?, ends_at = ?, bonus_days = bonus_days + ?
        WHERE user_id = ?
        """,
        (plan, _fmt(ends), bonus, int(user_id)),
    )
    conn.commit()
    return _fmt(ends)


def grant_plan(user_id: int, plan: str, days: int, actor_id: int | None = None) -> list[tuple[int, str]]:
    if plan not in PLANS or plan == "none":
        raise ValueError(plan)
    _ensure(user_id)
    ends = _now() + timedelta(days=int(days))
    included = PLANS[plan]["tokens"]
    cursor.execute(
        """
        UPDATE user_billing
        SET plan = ?, ends_at = ?, token_balance = token_balance + ?, blocked = 0
        WHERE user_id = ?
        """,
        (plan, _fmt(ends), included, int(user_id)),
    )
    conn.commit()
    _log(user_id, "grant", f"{plan} +{days}д +{included} токенів", actor_id)
    notes = []
    if plan in PAID_REFERRAL_TOKENS:
        notes.extend(_reward_paid_plan(int(user_id), plan))
    return notes


def grant_beta(user_id: int, actor_id: int | None = None) -> None:
    _ensure(user_id)
    ends = _now() + timedelta(days=14)
    cursor.execute(
        "UPDATE user_billing SET plan = 'beta', ends_at = ?, blocked = 0 WHERE user_id = ?",
        (_fmt(ends), int(user_id)),
    )
    conn.commit()
    _log(user_id, "beta", "14 днів", actor_id)


def extend_plan(user_id: int, days: int, actor_id: int | None = None) -> str | None:
    info = snapshot(user_id)
    if info["stored_plan"] == "none":
        return "Спочатку видайте тариф."
    ends = _add_days(user_id, days, as_plan=info["stored_plan"], count_bonus=False)
    _log(user_id, "extend", f"+{days}д до {ends}", actor_id)
    return None


def revoke_plan(user_id: int, actor_id: int | None = None) -> None:
    _ensure(user_id)
    cursor.execute(
        "UPDATE user_billing SET plan = 'none', ends_at = NULL WHERE user_id = ?",
        (int(user_id),),
    )
    conn.commit()
    _log(user_id, "revoke", "план знято", actor_id)


def set_blocked(user_id: int, blocked: bool, actor_id: int | None = None) -> None:
    _ensure(user_id)
    cursor.execute(
        "UPDATE user_billing SET blocked = ? WHERE user_id = ?",
        (1 if blocked else 0, int(user_id)),
    )
    conn.commit()
    _log(user_id, "block" if blocked else "unblock", "", actor_id)


def adjust_tokens(user_id: int, amount: float, actor_id: int | None = None) -> str | None:
    info = snapshot(user_id)
    if info["tokens"] + amount < -1e-9:
        return "Баланс не може стати від'ємним."
    _add_tokens(user_id, amount)
    _log(user_id, "tokens", f"{amount:+g}", actor_id)
    return None


def can_add_channel(user_id: int) -> str | None:
    info = snapshot(user_id)
    reason = _reason(info, "posting")
    if reason:
        return reason
    limit = info["channel_limit"]
    if limit is None:
        return None
    from database_functions.channels_db import get_all_channels

    owned = len(get_all_channels(user_id, only_active=True) or [])
    if owned >= limit:
        return f"Ліміт каналів тарифу {info['title']}: {limit}."
    return None


def can_save_emoji(user_id: int, channel_id: int) -> str | None:
    info = snapshot(user_id)
    reason = _reason(info, "posting")
    if reason:
        return reason
    limit = info["emoji_limit"]
    cursor.execute(
        """
        SELECT
          EXISTS(SELECT 1 FROM channel_start_emoji WHERE channel_id = ?),
          (
            SELECT COUNT(*)
            FROM channel_start_emoji e
            JOIN channel_memberships m ON m.channel_id = e.channel_id
            JOIN channels c ON c.channel_id = e.channel_id
            WHERE m.user_id = ? AND c.is_active = 1
          )
        """,
        (int(channel_id), int(user_id)),
    )
    has_here, used = cursor.fetchone()
    if has_here:
        return None
    if int(used or 0) >= limit:
        return f"Ліміт premium-емодзі тарифу {info['title']}: {limit}."
    return None


def register_referral(new_user_id: int, referrer_id: int) -> list[str]:
    if int(new_user_id) == int(referrer_id):
        return []
    _ensure(referrer_id)
    _ensure(new_user_id)
    cursor.execute("SELECT referred_by FROM user_billing WHERE user_id = ?", (int(new_user_id),))
    current = cursor.fetchone()
    if current and current[0]:
        return []
    cursor.execute(
        "UPDATE user_billing SET referred_by = ? WHERE user_id = ? AND referred_by IS NULL",
        (int(referrer_id), int(new_user_id)),
    )
    if cursor.rowcount == 0:
        conn.commit()
        return []
    conn.commit()
    _add_days(referrer_id, 3, as_plan=None)
    _add_tokens(referrer_id, 1)
    _log(referrer_id, "referral", f"новий користувач {new_user_id}")
    from texts.messages.billing import referral_new_member

    messages = [referral_new_member()]
    messages.extend(_threshold_rewards(referrer_id))
    return messages


def _threshold_rewards(user_id: int) -> list[str]:
    count = snapshot(user_id, with_referrals=True)["referrals"]
    notes = []
    for goal, (days, tokens) in THRESHOLD_BONUS.items():
        if count < goal:
            continue
        if not _claim(user_id, f"threshold_{goal}"):
            continue
        _add_days(user_id, days)
        _add_tokens(user_id, tokens)
        _log(user_id, "threshold", f"{goal}: +{days}д +{tokens} токенів")
        from texts.messages.billing import referral_threshold

        notes.append(referral_threshold(goal=goal, days=days, tokens=tokens))
    return notes


def _reward_paid_plan(referred_user_id: int, plan: str) -> list[tuple[int, str]]:
    info = snapshot(referred_user_id)
    referrer_id = info["referred_by"]
    if not referrer_id:
        return []
    if not _claim(int(referrer_id), f"paid_{plan}_{referred_user_id}"):
        return []
    tokens = PAID_REFERRAL_TOKENS[plan]
    _add_tokens(int(referrer_id), tokens)
    _log(int(referrer_id), "referral_plan", f"{plan} від {referred_user_id}: +{tokens}")
    from texts.messages.billing import referral_friend_plan

    return [
        (
            int(referrer_id),
            referral_friend_plan(plan_title=PLANS[plan]["title"], tokens=tokens),
        )
    ]


def search_clients(
    query: str = "",
    mode: str = "all",
    *,
    offset: int = 0,
    limit: int = 8,
) -> tuple[list[tuple], int]:
    clauses = ["1 = 1"]
    params: list = []
    if mode == "plan":
        clauses.append("COALESCE(b.plan, 'none') != 'none'")
    elif mode == "blocked":
        clauses.append("COALESCE(b.blocked, 0) = 1")
    text = (query or "").strip().lstrip("@")
    if text:
        safe = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{safe}%"
        clauses.append(
            """
            (
                CAST(u.user_id AS TEXT) LIKE ? ESCAPE '\\'
                OR IFNULL(u.user_name, '') LIKE ? ESCAPE '\\'
                OR IFNULL(u.user_first_name, '') LIKE ? ESCAPE '\\'
                OR IFNULL(u.user_last_name, '') LIKE ? ESCAPE '\\'
            )
            """
        )
        params.extend([like, like, like, like])
    where = " AND ".join(clauses)
    cursor.execute(
        f"""
        SELECT COUNT(*)
        FROM users u
        LEFT JOIN user_billing b ON b.user_id = u.user_id
        WHERE {where}
        """,
        params,
    )
    total = int(cursor.fetchone()[0] or 0)
    cursor.execute(
        f"""
        SELECT u.user_id, u.user_name, u.user_first_name, u.user_last_name,
               COALESCE(b.plan, 'none'), COALESCE(b.token_balance, 0), COALESCE(b.blocked, 0)
        FROM users u
        LEFT JOIN user_billing b ON b.user_id = u.user_id
        WHERE {where}
        ORDER BY u.user_id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, int(limit), int(offset)],
    )
    return cursor.fetchall(), total


def recent_log(user_id: int, limit: int = 6) -> list[tuple]:
    cursor.execute(
        """
        SELECT created_at, action, detail FROM billing_log
        WHERE user_id = ? ORDER BY id DESC LIMIT ?
        """,
        (int(user_id), limit),
    )
    return cursor.fetchall()
