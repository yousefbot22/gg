"""Repository for subscription_groups + members."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from src.db.connection import get_conn, fetch_one, fetch_all
from src.db.models import SubscriptionGroup, GroupMember


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_password(password: str, salt: str | None = None) -> str:
    """PBKDF2-like simple hashing (use bcrypt in production)."""
    salt = salt or secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}${h}"


def _verify(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
        return secrets.compare_digest(_hash_password(password, salt), stored)
    except ValueError:
        return False


def _row_to_group(r, members_count: int = 0, completed_count: int = 0) -> SubscriptionGroup:
    """يبني SubscriptionGroup من صف قاعدة البيانات، مع دعم الأعمدة الجديدة إن وُجدت."""
    keys = r.keys() if hasattr(r, "keys") else []

    def _get(key, default=None):
        return r[key] if key in keys else default

    return SubscriptionGroup(
        group_id=r["group_id"],
        password_hash=r["password_hash"],
        tier_name=r["tier_name"],
        max_users=r["max_users"],
        is_active=bool(r["is_active"]),
        members_count=members_count,
        completed_count=completed_count,
        is_one_time=bool(_get("is_one_time", 0) or 0),
        used_by_user_id=_get("used_by_user_id", None),
        used_at=_get("used_at", None),
    )


# ==============================================================
# CRUD
# ==============================================================

def create_group(
    group_id: str,
    password: str,
    tier_name: str,
    max_users: int,
    is_one_time: bool = False,
) -> None:
    """
    ينشئ أو يحدّث باقة.
    - is_one_time=True: الباسورد لمرة واحدة فقط (يُحرق بعد الاستخدام).
    """
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO subscription_groups (
                group_id, password_hash, tier_name, max_users,
                is_active, created_at,
                is_one_time, used_by_user_id, used_at
            ) VALUES (?, ?, ?, ?, 1, ?, ?, NULL, NULL)
            ON CONFLICT(group_id) DO UPDATE SET
                password_hash = excluded.password_hash,
                tier_name = excluded.tier_name,
                max_users = excluded.max_users,
                is_one_time = excluded.is_one_time
            """,
            (
                group_id,
                _hash_password(password),
                tier_name,
                max_users,
                _now(),
                int(is_one_time),
            ),
        )
        conn.commit()


def get_group(group_id: str) -> SubscriptionGroup | None:
    r = fetch_one("SELECT * FROM subscription_groups WHERE group_id = ?", (group_id,))
    if not r:
        return None
    members = fetch_one(
        "SELECT COUNT(*) as c FROM group_members WHERE group_id = ?", (group_id,)
    )
    completed = fetch_one(
        "SELECT COUNT(*) as c FROM completed_students WHERE group_id = ?", (group_id,)
    )
    return _row_to_group(
        r,
        members_count=int(members["c"]) if members else 0,
        completed_count=int(completed["c"]) if completed else 0,
    )


def list_groups() -> list[SubscriptionGroup]:
    rows = fetch_all("SELECT * FROM subscription_groups ORDER BY created_at DESC")
    result = []
    for r in rows:
        members = fetch_one(
            "SELECT COUNT(*) as c FROM group_members WHERE group_id = ?",
            (r["group_id"],),
        )
        completed = fetch_one(
            "SELECT COUNT(*) as c FROM completed_students WHERE group_id = ?",
            (r["group_id"],),
        )
        result.append(_row_to_group(
            r,
            members_count=int(members["c"]) if members else 0,
            completed_count=int(completed["c"]) if completed else 0,
        ))
    return result


def verify_password(group_id: str, password: str) -> bool:
    g = get_group(group_id)
    if not g:
        return False
    return _verify(password, g.password_hash)


def verify_by_password(password: str) -> SubscriptionGroup | None:
    """
    يجد الباقة بالباسورد.
    - يرفض الباسوردات لمرة واحدة التي استُخدمت بالفعل.
    - يرفض الباقات المعطلة.
    """
    for g in list_groups():
        if not _verify(password, g.password_hash):
            continue
        # ✅ الباسورد لمرة واحدة مُستهلك → ارفض
        if g.is_consumed:
            return None
        # ✅ الباقة معطلة → ارفض
        if not g.is_active:
            return None
        return g
    return None


def add_member(
    group_id: str,
    user_id: int,
    student_username: str | None = None,
) -> bool:
    """
    يضيف عضواً للباقة.
    - يرفض إذا كانت الباقة ممتلئة.
    - يرفض إذا كانت لمرة واحدة ومستخدمة من شخص آخر.
    - يستهلك الباسورد (يسجل used_by_user_id) إذا كانت لمرة واحدة.
    ترجع True عند النجاح، False عند الرفض.
    """
    g = get_group(group_id)
    if not g:
        return False

    # ✅ السعة
    if g.completed_count >= g.max_users:
        return False

    # ✅ المرة الواحدة
    if g.is_one_time:
        if g.used_by_user_id is not None and g.used_by_user_id != user_id:
            return False

    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO group_members
                (group_id, user_id, student_username, joined_at)
            VALUES (?, ?, ?, ?)
            """,
            (group_id, user_id, student_username, _now()),
        )
        # استهلك الباسورد إذا كانت لمرة واحدة
        if g.is_one_time:
            conn.execute(
                """
                UPDATE subscription_groups
                   SET used_by_user_id = ?, used_at = ?
                 WHERE group_id = ?
                """,
                (user_id, _now(), group_id),
            )
        conn.commit()

    return True


def get_user_group(user_id: int) -> SubscriptionGroup | None:
    r = fetch_one(
        "SELECT group_id FROM group_members WHERE user_id = ? ORDER BY joined_at DESC LIMIT 1",
        (user_id,),
    )
    if not r:
        return None
    return get_group(r["group_id"])


def record_completed(
    group_id: str, student_username: str, grade: str = ""
) -> bool:
    """Returns True if newly counted."""
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO completed_students (group_id, student_username, grade, completed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(group_id, student_username) DO NOTHING
            """,
            (group_id, student_username, grade, _now()),
        )
        conn.commit()
        return cur.rowcount > 0


# ==============================================================
# Toggle / Delete / Generate password
# ==============================================================

def toggle_active(group_id: str) -> bool:
    """يقلب حالة التفعيل. يرجع الحالة الجديدة."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE subscription_groups SET is_active = NOT is_active WHERE group_id = ?",
            (group_id,),
        )
        conn.commit()
    g = get_group(group_id)
    return bool(g and g.is_active)


def delete_group(group_id: str) -> None:
    """يحذف الباقة وكل أعضائها."""
    with get_conn() as conn:
        conn.execute("DELETE FROM group_members WHERE group_id = ?", (group_id,))
        conn.execute("DELETE FROM completed_students WHERE group_id = ?", (group_id,))
        conn.execute("DELETE FROM subscription_groups WHERE group_id = ?", (group_id,))
        conn.commit()


def generate_password(length: int = 10) -> str:
    """يولّد باسورد عشوائي سهل القراءة (بدون حروف متشابهة)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))