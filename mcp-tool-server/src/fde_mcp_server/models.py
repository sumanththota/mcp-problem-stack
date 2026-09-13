"""Strict input schemas for the two exposed tools.

Design choices worth noting:
- extra="forbid": unknown fields are a validation error, not silently dropped.
- strict=True: no implicit type coercion (e.g. the string "10.5" is NOT
  accepted for a float field just because it looks numeric).
- customer_id uses a regex `pattern` so the constraint also shows up in the
  generated JSON Schema (model_json_schema()), which becomes the tool's
  inputSchema advertised to clients.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, field_validator

CUSTOMER_ID_PATTERN = r"^CUST-\d{5}$"


class GetCustomerRecordInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    customer_id: str = Field(
        ...,
        pattern=CUSTOMER_ID_PATTERN,
        description="Customer identifier, format CUST-XXXXX (5 digits), e.g. CUST-10001.",
    )


class TriggerRefundInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    customer_id: str = Field(
        ...,
        pattern=CUSTOMER_ID_PATTERN,
        description="Customer identifier, format CUST-XXXXX (5 digits).",
    )
    amount: float = Field(
        ...,
        gt=0,
        description="Refund amount in USD. Must be a positive, finite number.",
    )
    reason: str = Field(
        ...,
        min_length=10,
        description="Justification for the refund, at least 10 characters.",
    )

    @field_validator("amount")
    @classmethod
    def _amount_must_be_finite(cls, v: float) -> float:
        # gt=0 already rejects NaN (any comparison with NaN is False), but not
        # +inf (inf > 0 is True). JSON's non-standard Infinity/NaN literals
        # are accepted by Python's json.loads, so this must be checked explicitly.
        if not math.isfinite(v):
            raise ValueError("amount must be a finite number")
        return v
