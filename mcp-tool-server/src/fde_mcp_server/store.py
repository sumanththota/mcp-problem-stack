"""In-memory mock data layer standing in for a real customer/billing system."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class CustomerRecord:
    customer_id: str
    name: str
    email: str
    balance_usd: float
    status: str  # "active" | "suspended"

    def to_dict(self) -> dict:
        return {
            "customer_id": self.customer_id,
            "name": self.name,
            "email": self.email,
            "balance_usd": self.balance_usd,
            "status": self.status,
        }


@dataclass
class RefundRecord:
    refund_id: str
    customer_id: str
    amount: float
    reason: str
    created_at: str

    def to_dict(self) -> dict:
        return {
            "refund_id": self.refund_id,
            "customer_id": self.customer_id,
            "amount": self.amount,
            "reason": self.reason,
            "created_at": self.created_at,
        }


_CUSTOMERS: dict[str, CustomerRecord] = {
    "CUST-10001": CustomerRecord("CUST-10001", "Ada Lovelace", "ada@example.com", 128.50, "active"),
    "CUST-10002": CustomerRecord("CUST-10002", "Grace Hopper", "grace@example.com", 0.0, "active"),
    "CUST-10003": CustomerRecord("CUST-10003", "Alan Turing", "alan@example.com", 42.00, "suspended"),
}

_refund_counter = 0


def get_customer(customer_id: str) -> CustomerRecord | None:
    return _CUSTOMERS.get(customer_id)


def record_refund(customer_id: str, amount: float, reason: str) -> RefundRecord:
    global _refund_counter
    _refund_counter += 1
    refund = RefundRecord(
        refund_id=f"REF-{_refund_counter:05d}",
        customer_id=customer_id,
        amount=amount,
        reason=reason,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    return refund
