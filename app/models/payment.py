from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class PaymentInvoice:
    invoice_id: str
    user_id: int
    tariff_code: str
    amount_minor: int
    amount: float
    currency: str
    payment_url: str


@dataclass
class PaymentResult:
    invoice_id: str
    status: str
    amount: float
    currency: str
    paid_at: datetime


@dataclass
class PaymentRecord:
    invoice_id: str
    telegram_id: int
    tariff_code: str
    amount_minor: int | None
    amount: float | None
    currency: str
    status: str
    attempts: int
    last_error: str | None
    subscription_link: str | None
    created_at: datetime | None
    updated_at: datetime | None
