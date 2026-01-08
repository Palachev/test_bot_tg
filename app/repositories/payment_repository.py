from __future__ import annotations

from datetime import datetime

from app.db import Database
from app.models.payment import PaymentRecord


class PaymentRepository:
    def __init__(self, db: Database):
        self._db = db

    async def create_invoice(
        self,
        invoice_id: str,
        telegram_id: int,
        tariff_code: str,
        amount_minor: int,
        amount: float,
        currency: str,
    ) -> None:
        await self._db.execute(
            """
            INSERT OR IGNORE INTO payments (
                invoice_id,
                telegram_id,
                tariff_code,
                amount_minor,
                amount,
                currency,
                status,
                attempts
            )
            VALUES (?, ?, ?, ?, ?, ?, 'pending', 0)
            """,
            invoice_id,
            telegram_id,
            tariff_code,
            amount_minor,
            amount,
            currency,
        )

    async def mark_paid(self, invoice_id: str) -> None:
        await self._db.execute(
            """
            UPDATE payments
            SET status = 'paid', updated_at = CURRENT_TIMESTAMP
            WHERE invoice_id = ? AND status = 'pending'
            """,
            invoice_id,
        )

    async def mark_paid_pending(self, invoice_id: str, last_error: str | None = None) -> None:
        await self._db.execute(
            """
            UPDATE payments
            SET status = 'paid_pending',
                updated_at = CURRENT_TIMESTAMP,
                attempts = attempts + 1,
                last_error = ?
            WHERE invoice_id = ?
            """,
            last_error,
            invoice_id,
        )

    async def mark_completed(self, invoice_id: str, subscription_link: str | None = None) -> None:
        await self._db.execute(
            """
            UPDATE payments
            SET status = 'completed',
                updated_at = CURRENT_TIMESTAMP,
                subscription_link = ?
            WHERE invoice_id = ?
            """,
            subscription_link,
            invoice_id,
        )

    async def mark_failed(self, invoice_id: str, last_error: str | None = None) -> None:
        await self._db.execute(
            """
            UPDATE payments
            SET status = 'failed',
                updated_at = CURRENT_TIMESTAMP,
                last_error = ?
            WHERE invoice_id = ?
            """,
            last_error,
            invoice_id,
        )

    async def get_invoice(self, invoice_id: str) -> PaymentRecord | None:
        row = await self._db.fetchone(
            """
            SELECT
                invoice_id,
                telegram_id,
                tariff_code,
                amount_minor,
                amount,
                currency,
                status,
                attempts,
                last_error,
                subscription_link,
                created_at,
                updated_at
            FROM payments
            WHERE invoice_id = ?
            """,
            invoice_id,
        )
        if not row:
            return None
        created_at = datetime.fromisoformat(row[10]) if row[10] else None
        updated_at = datetime.fromisoformat(row[11]) if row[11] else None
        return PaymentRecord(
            invoice_id=row[0],
            telegram_id=row[1],
            tariff_code=row[2],
            amount_minor=row[3],
            amount=row[4],
            currency=row[5],
            status=row[6],
            attempts=row[7] or 0,
            last_error=row[8],
            subscription_link=row[9],
            created_at=created_at,
            updated_at=updated_at,
        )

    async def was_processed(self, invoice_id: str) -> bool:
        row = await self._db.fetchone(
            "SELECT status FROM payments WHERE invoice_id = ? AND status = 'paid'",
            invoice_id,
        )
        return row is not None

    async def complete_or_skip(self, invoice_id: str) -> bool:
        """Idempotent completion; returns True if marked newly."""
        rowcount = await self._db.execute_with_rowcount(
            """
            UPDATE payments
            SET status = 'paid', updated_at = CURRENT_TIMESTAMP
            WHERE invoice_id = ? AND status != 'paid'
            """,
            invoice_id,
        )
        return rowcount == 1

    async def count_successful_payments(self, telegram_id: int) -> int:
        row = await self._db.fetchone(
            "SELECT COUNT(*) FROM payments WHERE telegram_id = ? AND status = 'paid'",
            telegram_id,
        )
        return row[0] if row else 0

    async def count_paid_invoices(self) -> int:
        row = await self._db.fetchone(
            "SELECT COUNT(*) FROM payments WHERE status IN ('paid', 'paid_pending', 'completed')"
        )
        return row[0] if row else 0

    async def sum_paid_amount(self) -> float:
        row = await self._db.fetchone(
            "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status IN ('paid', 'paid_pending', 'completed')"
        )
        return float(row[0]) if row else 0.0

    async def list_pending_invoices(self) -> list[str]:
        rows = await self._db.fetchall(
            "SELECT invoice_id FROM payments WHERE status = 'paid_pending' ORDER BY updated_at ASC"
        )
        return [row[0] for row in rows]

    async def list_paid_pending(self) -> list[PaymentRecord]:
        rows = await self._db.fetchall(
            """
            SELECT
                invoice_id,
                telegram_id,
                tariff_code,
                amount_minor,
                amount,
                currency,
                status,
                attempts,
                last_error,
                subscription_link,
                created_at,
                updated_at
            FROM payments
            WHERE status IN ('paid', 'paid_pending')
            ORDER BY updated_at ASC
            """
        )
        records: list[PaymentRecord] = []
        for row in rows:
            created_at = datetime.fromisoformat(row[10]) if row[10] else None
            updated_at = datetime.fromisoformat(row[11]) if row[11] else None
            records.append(
                PaymentRecord(
                    invoice_id=row[0],
                    telegram_id=row[1],
                    tariff_code=row[2],
                    amount_minor=row[3],
                    amount=row[4],
                    currency=row[5],
                    status=row[6],
                    attempts=row[7] or 0,
                    last_error=row[8],
                    subscription_link=row[9],
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )
        return records
