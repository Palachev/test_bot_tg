from __future__ import annotations

import hashlib
from uuid import uuid4

from app.config import Settings
from app.models.payment import PaymentInvoice
from app.repositories.payment_repository import PaymentRepository


class PaymentService:
    def __init__(self, settings: Settings, payment_repo: PaymentRepository):
        self.settings = settings
        self.payment_repo = payment_repo

    async def create_invoice(self, user_id: int, tariff_code: str, amount_minor: int) -> PaymentInvoice:
        invoice_id = self._unique_invoice_id()
        amount = amount_minor / 100
        payment_url = ""
        await self.payment_repo.create_invoice(
            invoice_id=invoice_id,
            telegram_id=user_id,
            tariff_code=tariff_code,
            amount_minor=amount_minor,
            amount=amount,
            currency=self.settings.payment_currency,
        )
        return PaymentInvoice(
            invoice_id=invoice_id,
            user_id=user_id,
            tariff_code=tariff_code,
            amount_minor=amount_minor,
            amount=amount,
            currency=self.settings.payment_currency,
            payment_url=payment_url,
        )

    def _unique_invoice_id(self) -> str:
        return f"inv_{uuid4().hex}"

    def _payload_for_tariff(self, tariff_code: str) -> str:
        payloads = {
            "m1": "vpn_1m",
            "m3": "vpn_3m",
            "m6": "vpn_6m",
            "m12": "vpn_12m",
        }
        return payloads.get(tariff_code, hashlib.sha1(tariff_code.encode()).hexdigest())


def payload_to_days(payload: str) -> int:
    mapping = {
        "vpn_1m": 30,
        "vpn_3m": 90,
        "vpn_6m": 180,
        "vpn_12m": 365,
    }
    return mapping.get(payload, 0)


def simulate_payload_mapping() -> dict[str, int]:
    return {
        "vpn_1m": payload_to_days("vpn_1m"),
        "vpn_3m": payload_to_days("vpn_3m"),
        "vpn_6m": payload_to_days("vpn_6m"),
        "vpn_12m": payload_to_days("vpn_12m"),
    }


if __name__ == "__main__":
    print(simulate_payload_mapping())
