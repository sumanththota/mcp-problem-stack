import math

import pytest
from pydantic import ValidationError

from fde_mcp_server.models import GetCustomerRecordInput, TriggerRefundInput

VALID_ID = "CUST-10001"


class TestGetCustomerRecordInput:
    def test_accepts_valid_id(self):
        model = GetCustomerRecordInput(customer_id=VALID_ID)
        assert model.customer_id == VALID_ID

    @pytest.mark.parametrize(
        "bad_id",
        [
            "CUST-1234",       # 4 digits, too short
            "CUST-123456",     # 6 digits, too long
            "cust-10001",      # lowercase prefix
            "CUST10001",       # missing hyphen
            "CUST-ABCDE",      # non-digit suffix
            "CUST-10001 ",     # trailing whitespace
            " CUST-10001",     # leading whitespace
            "",                # empty
        ],
    )
    def test_rejects_malformed_id(self, bad_id):
        with pytest.raises(ValidationError):
            GetCustomerRecordInput(customer_id=bad_id)

    def test_rejects_non_string_id(self):
        with pytest.raises(ValidationError):
            GetCustomerRecordInput(customer_id=10001)  # type: ignore[arg-type]

    def test_rejects_missing_field(self):
        with pytest.raises(ValidationError):
            GetCustomerRecordInput()  # type: ignore[call-arg]

    def test_rejects_unknown_field(self):
        with pytest.raises(ValidationError):
            GetCustomerRecordInput(customer_id=VALID_ID, extra_field="nope")  # type: ignore[call-arg]


class TestTriggerRefundInput:
    def _make(self, **overrides):
        base = dict(customer_id=VALID_ID, amount=10.0, reason="duplicate charge")
        base.update(overrides)
        return TriggerRefundInput(**base)

    def test_accepts_valid_input(self):
        model = self._make()
        assert model.amount == 10.0

    def test_rejects_zero_amount(self):
        with pytest.raises(ValidationError):
            self._make(amount=0)

    def test_rejects_negative_amount(self):
        with pytest.raises(ValidationError):
            self._make(amount=-5.0)

    def test_rejects_nan_amount(self):
        with pytest.raises(ValidationError):
            self._make(amount=math.nan)

    def test_rejects_infinite_amount(self):
        with pytest.raises(ValidationError):
            self._make(amount=math.inf)

    def test_rejects_string_amount_in_strict_mode(self):
        with pytest.raises(ValidationError):
            self._make(amount="10.0")

    def test_rejects_reason_under_min_length(self):
        with pytest.raises(ValidationError):
            self._make(reason="short")  # 5 chars

    def test_accepts_reason_at_exactly_min_length(self):
        model = self._make(reason="1234567890")  # exactly 10 chars
        assert len(model.reason) == 10

    def test_rejects_reason_one_under_min_length(self):
        with pytest.raises(ValidationError):
            self._make(reason="123456789")  # 9 chars

    def test_rejects_malformed_customer_id(self):
        with pytest.raises(ValidationError):
            self._make(customer_id="BAD-ID")

    def test_rejects_missing_fields(self):
        with pytest.raises(ValidationError):
            TriggerRefundInput(customer_id=VALID_ID)  # type: ignore[call-arg]
