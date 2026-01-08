from __future__ import annotations

from datetime import datetime

from app.db import Database
from app.models.user import User


class UserRepository:
    def __init__(self, db: Database):
        self._db = db

    async def upsert_user(self, user: User) -> None:
        await self._db.execute(
            """
            INSERT INTO users (
                telegram_id,
                marzban_username,
                marzban_uuid,
                subscription_expires_at,
                subscription_link,
                traffic_limit_gb,
                trial_used,
                referrer_telegram_id,
                referral_bonus_applied,
                reminder_3d_sent,
                reminder_1d_sent
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                marzban_username=excluded.marzban_username,
                marzban_uuid=excluded.marzban_uuid,
                subscription_expires_at=excluded.subscription_expires_at,
                subscription_link=excluded.subscription_link,
                traffic_limit_gb=excluded.traffic_limit_gb,
                trial_used=excluded.trial_used,
                referrer_telegram_id=excluded.referrer_telegram_id,
                referral_bonus_applied=excluded.referral_bonus_applied,
                reminder_3d_sent=excluded.reminder_3d_sent,
                reminder_1d_sent=excluded.reminder_1d_sent
            """,
            user.telegram_id,
            user.marzban_username,
            user.marzban_uuid,
            user.subscription_expires_at.isoformat() if user.subscription_expires_at else None,
            user.subscription_link,
            user.traffic_limit_gb,
            int(user.trial_used),
            user.referrer_telegram_id,
            int(user.referral_bonus_applied),
            int(user.reminder_3d_sent),
            int(user.reminder_1d_sent),
        )
        await self.register_telegram_user(user.telegram_id)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        row = await self._db.fetchone(
            """
            SELECT
                u.telegram_id,
                u.marzban_username,
                u.marzban_uuid,
                u.subscription_expires_at,
                u.subscription_link,
                u.traffic_limit_gb,
                COALESCE(t.trial_used, u.trial_used, 0),
                COALESCE(t.referrer_telegram_id, u.referrer_telegram_id),
                COALESCE(t.referral_bonus_applied, u.referral_bonus_applied, 0),
                u.reminder_3d_sent,
                u.reminder_1d_sent
            FROM users u
            LEFT JOIN telegram_users t ON t.telegram_id = u.telegram_id
            WHERE u.telegram_id = ?
            """,
            telegram_id,
        )
        if not row:
            return None
        subscription_expires_at = (
            datetime.fromisoformat(row[3]) if row[3] else None
        )
        return User(
            telegram_id=row[0],
            marzban_username=row[1],
            marzban_uuid=row[2],
            subscription_expires_at=subscription_expires_at,
            subscription_link=row[4],
            traffic_limit_gb=row[5],
            trial_used=bool(row[6]),
            referrer_telegram_id=row[7],
            referral_bonus_applied=bool(row[8]),
            reminder_3d_sent=bool(row[9]),
            reminder_1d_sent=bool(row[10]),
        )

    async def update_subscription(self, telegram_id: int, expires_at: datetime | None, link: str | None) -> None:
        await self._db.execute(
            """UPDATE users SET subscription_expires_at = ?, subscription_link = ? WHERE telegram_id = ?""",
            expires_at.isoformat() if expires_at else None,
            link,
            telegram_id,
        )

    async def get_user_meta(self, telegram_id: int) -> tuple[bool, int | None, bool]:
        row = await self._db.fetchone(
            """
            SELECT trial_used, referrer_telegram_id, referral_bonus_applied
            FROM telegram_users WHERE telegram_id = ?
            """,
            telegram_id,
        )
        if row:
            return bool(row[0]), row[1], bool(row[2])
        return False, None, False

    async def set_trial_used(self, telegram_id: int) -> None:
        await self.register_telegram_user(telegram_id)
        await self._db.execute(
            "UPDATE telegram_users SET trial_used = 1 WHERE telegram_id = ?",
            telegram_id,
        )
        await self._db.execute(
            "UPDATE users SET trial_used = 1 WHERE telegram_id = ?",
            telegram_id,
        )

    async def try_mark_trial_used(self, telegram_id: int) -> bool:
        await self.register_telegram_user(telegram_id)
        rowcount = await self._db.execute_with_rowcount(
            "UPDATE users SET trial_used = 1 WHERE telegram_id = ? AND trial_used = 0",
            telegram_id,
        )
        if rowcount == 0:
            rowcount = await self._db.execute_with_rowcount(
                "UPDATE telegram_users SET trial_used = 1 WHERE telegram_id = ? AND trial_used = 0",
                telegram_id,
            )
        await self._db.execute(
            "UPDATE users SET trial_used = 1 WHERE telegram_id = ?",
            telegram_id,
        )
        await self._db.execute(
            "UPDATE telegram_users SET trial_used = 1 WHERE telegram_id = ?",
            telegram_id,
        )
        return rowcount == 1

    async def set_referrer(self, invitee_id: int, referrer_id: int) -> bool:
        await self.register_telegram_user(invitee_id)
        row = await self._db.fetchone(
            "SELECT referrer_telegram_id FROM telegram_users WHERE telegram_id = ?",
            invitee_id,
        )
        if row and row[0] is not None:
            return False
        await self._db.execute(
            "UPDATE telegram_users SET referrer_telegram_id = ? WHERE telegram_id = ?",
            referrer_id,
            invitee_id,
        )
        await self._db.execute(
            "UPDATE users SET referrer_telegram_id = ? WHERE telegram_id = ?",
            referrer_id,
            invitee_id,
        )
        return True

    async def get_referrer_id(self, invitee_id: int) -> int | None:
        row = await self._db.fetchone(
            "SELECT referrer_telegram_id FROM telegram_users WHERE telegram_id = ?",
            invitee_id,
        )
        return row[0] if row else None

    async def has_referral_bonus_applied(self, invitee_id: int) -> bool:
        row = await self._db.fetchone(
            "SELECT referral_bonus_applied FROM telegram_users WHERE telegram_id = ?",
            invitee_id,
        )
        return bool(row[0]) if row else False

    async def mark_referral_bonus_applied(self, invitee_id: int) -> None:
        await self.register_telegram_user(invitee_id)
        await self._db.execute(
            "UPDATE telegram_users SET referral_bonus_applied = 1 WHERE telegram_id = ?",
            invitee_id,
        )
        await self._db.execute(
            "UPDATE users SET referral_bonus_applied = 1 WHERE telegram_id = ?",
            invitee_id,
        )

    async def try_mark_referral_bonus_applied(self, invitee_id: int) -> bool:
        await self.register_telegram_user(invitee_id)
        rowcount = await self._db.execute_with_rowcount(
            """
            UPDATE users
            SET referral_bonus_applied = 1
            WHERE telegram_id = ? AND referral_bonus_applied = 0
            """,
            invitee_id,
        )
        if rowcount == 0:
            rowcount = await self._db.execute_with_rowcount(
                """
                UPDATE telegram_users
                SET referral_bonus_applied = 1
                WHERE telegram_id = ? AND referral_bonus_applied = 0
                """,
                invitee_id,
            )
        await self._db.execute(
            "UPDATE users SET referral_bonus_applied = 1 WHERE telegram_id = ?",
            invitee_id,
        )
        await self._db.execute(
            "UPDATE telegram_users SET referral_bonus_applied = 1 WHERE telegram_id = ?",
            invitee_id,
        )
        return rowcount == 1

    async def count_users(self) -> int:
        row = await self._db.fetchone(
            """
            SELECT COUNT(*) FROM (
                SELECT telegram_id FROM telegram_users
                UNION
                SELECT telegram_id FROM users
            )
            """
        )
        return row[0] if row else 0

    async def count_active_subscriptions(self, now_iso: str) -> int:
        row = await self._db.fetchone(
            "SELECT COUNT(*) FROM users WHERE subscription_expires_at IS NOT NULL AND subscription_expires_at > ?",
            now_iso,
        )
        return row[0] if row else 0

    async def list_telegram_ids(self) -> list[int]:
        rows = await self._db.fetchall(
            """
            SELECT telegram_id FROM telegram_users
            UNION
            SELECT telegram_id FROM users
            """
        )
        return [row[0] for row in rows]

    async def list_paid_users(self) -> list[tuple[int, str]]:
        rows = await self._db.fetchall(
            """
            SELECT telegram_id, MIN(created_at) as first_paid
            FROM payments
            WHERE status IN ('paid', 'paid_pending')
            GROUP BY telegram_id
            ORDER BY first_paid DESC
            """
        )
        return [(row[0], row[1]) for row in rows]

    async def list_trial_only_users(self) -> list[tuple[int, str]]:
        rows = await self._db.fetchall(
            """
            SELECT t.telegram_id, t.created_at
            FROM telegram_users t
            WHERE t.trial_used = 1
              AND NOT EXISTS (
                SELECT 1 FROM payments p
                WHERE p.telegram_id = t.telegram_id
                  AND p.status IN ('paid', 'paid_pending')
              )
            ORDER BY t.created_at DESC
            """
        )
        return [(row[0], row[1]) for row in rows]

    async def list_active_subscription_ids(self, now_iso: str) -> list[int]:
        rows = await self._db.fetchall(
            """
            SELECT telegram_id
            FROM users
            WHERE subscription_expires_at IS NOT NULL AND subscription_expires_at > ?
            """,
            now_iso,
        )
        return [row[0] for row in rows]

    async def list_inactive_subscription_ids(self, now_iso: str) -> list[int]:
        rows = await self._db.fetchall(
            """
            WITH all_users AS (
                SELECT telegram_id FROM telegram_users
                UNION
                SELECT telegram_id FROM users
            )
            SELECT a.telegram_id
            FROM all_users a
            LEFT JOIN users u ON u.telegram_id = a.telegram_id
            WHERE u.subscription_expires_at IS NULL OR u.subscription_expires_at <= ?
            """,
            now_iso,
        )
        return [row[0] for row in rows]

    async def list_expiring_users(self, now_iso: str, until_iso: str) -> list[tuple[int, str, bool, bool]]:
        rows = await self._db.fetchall(
            """
            SELECT telegram_id, subscription_expires_at, reminder_3d_sent, reminder_1d_sent
            FROM users
            WHERE subscription_expires_at IS NOT NULL
              AND subscription_expires_at > ?
              AND subscription_expires_at <= ?
            """,
            now_iso,
            until_iso,
        )
        return [(row[0], row[1], bool(row[2]), bool(row[3])) for row in rows]

    async def mark_reminder_sent(self, telegram_id: int, days: int) -> None:
        column = "reminder_3d_sent" if days == 3 else "reminder_1d_sent"
        await self._db.execute(
            f"UPDATE users SET {column} = 1 WHERE telegram_id = ?",
            telegram_id,
        )

    async def register_telegram_user(self, telegram_id: int) -> None:
        await self._db.execute(
            "INSERT INTO telegram_users (telegram_id) VALUES (?) ON CONFLICT(telegram_id) DO NOTHING",
            telegram_id,
        )
