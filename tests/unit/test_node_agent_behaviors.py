"""Unit tests for Node Agent adversarial behaviors and honest mode.

Tests the behavior library including attestation manipulation, equivocation,
censoring, and coordinated exits.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from chaoswopr.agents.node_agent_behaviors import (
    AdversarialBehavior,
    AttestationDelay,
    AttestationWithholding,
    BlockEquivocation,
    CoordinatedExit,
    HonestBehavior,
    TransactionCensoring,
)


class TestHonestBehavior:
    """Test honest behavior implementation."""

    def test_honest_behavior_creation(self) -> None:
        """Test honest behavior creation."""
        behavior = HonestBehavior()
        assert behavior.name == "honest"
        assert behavior.description == "Pass-through proxy with audit logging"

    def test_honest_behavior_intercept(self) -> None:
        """Test honest behavior request interception (passthrough)."""
        behavior = HonestBehavior()

        # Honest behavior should return None (passthrough)
        result = behavior.intercept_request(
            path="/eth/v1/validator/duties/attester/123",
            params={"slot": "123"},
            body=None,
        )
        assert result is None

    def test_honest_behavior_with_audit_logging(self) -> None:
        """Test honest behavior with audit logging."""
        from chaoswopr.safety.audit import AuditLogger

        audit_logger = AuditLogger(default_agent_id="validator-1")
        behavior = HonestBehavior(audit_logger=audit_logger, node_id="validator-1")

        # Make a request
        behavior.intercept_request(
            path="/eth/v1/validator/duties/attester/123",
            params={"slot": "123"},
            body=None,
        )

        # Check audit log
        entries = audit_logger.get_entries()
        assert len(entries) > 0
        assert entries[0].action_type == "node_agent_request"


class TestAttestationWithholding:
    """Test attestation withholding behavior."""

    def test_attestation_withholding_creation(self) -> None:
        """Test attestation withholding creation."""
        behavior = AttestationWithholding(withhold_probability=0.5)
        assert behavior.name == "attestation_withholding"
        assert behavior.withhold_probability == 0.5

    def test_attestation_withholding_always(self) -> None:
        """Test withholding all attestations."""
        behavior = AttestationWithholding(withhold_probability=1.0)

        # Intercept attestation submission
        result = behavior.intercept_request(
            path="/eth/v1/beacon/pool/attestations",
            params={},
            body={"attestation": "data"},
        )

        # Should block the request
        assert result is not None
        assert result.get("blocked") is True

    def test_attestation_withholding_never(self) -> None:
        """Test never withholding attestations."""
        behavior = AttestationWithholding(withhold_probability=0.0)

        # Intercept attestation submission
        result = behavior.intercept_request(
            path="/eth/v1/beacon/pool/attestations",
            params={},
            body={"attestation": "data"},
        )

        # Should passthrough
        assert result is None

    def test_attestation_withholding_non_attestation(self) -> None:
        """Test that non-attestation requests passthrough."""
        behavior = AttestationWithholding(withhold_probability=1.0)

        # Intercept non-attestation request
        result = behavior.intercept_request(
            path="/eth/v1/node/health",
            params={},
            body=None,
        )

        # Should passthrough
        assert result is None


class TestAttestationDelay:
    """Test attestation delay behavior."""

    def test_attestation_delay_creation(self) -> None:
        """Test attestation delay creation."""
        behavior = AttestationDelay(delay_seconds=2.0)
        assert behavior.name == "attestation_delay"
        assert behavior.delay_seconds == 2.0

    def test_attestation_delay_intercept(self) -> None:
        """Test delaying attestation submission."""
        behavior = AttestationDelay(delay_seconds=0.1)

        import time

        start = time.monotonic()
        result = behavior.intercept_request(
            path="/eth/v1/beacon/pool/attestations",
            params={},
            body={"attestation": "data"},
        )
        elapsed = time.monotonic() - start

        # Should have delayed
        assert elapsed >= 0.1
        # Should eventually passthrough
        assert result is None

    def test_attestation_delay_non_attestation(self) -> None:
        """Test that non-attestation requests are not delayed."""
        behavior = AttestationDelay(delay_seconds=2.0)

        import time

        start = time.monotonic()
        result = behavior.intercept_request(
            path="/eth/v1/node/health",
            params={},
            body=None,
        )
        elapsed = time.monotonic() - start

        # Should not have delayed
        assert elapsed < 1.0
        assert result is None


class TestBlockEquivocation:
    """Test block equivocation behavior."""

    def test_block_equivocation_creation(self) -> None:
        """Test block equivocation creation."""
        behavior = BlockEquivocation(equivocate_probability=0.5)
        assert behavior.name == "block_equivocation"
        assert behavior.equivocate_probability == 0.5

    def test_block_equivocation_always(self) -> None:
        """Test always equivocating."""
        behavior = BlockEquivocation(equivocate_probability=1.0)

        # Intercept block proposal
        result = behavior.intercept_request(
            path="/eth/v1/validator/blocks/123",
            params={},
            body=None,
        )

        # Should modify the request
        assert result is not None
        assert result.get("equivocated") is True

    def test_block_equivocation_never(self) -> None:
        """Test never equivocating."""
        behavior = BlockEquivocation(equivocate_probability=0.0)

        # Intercept block proposal
        result = behavior.intercept_request(
            path="/eth/v1/validator/blocks/123",
            params={},
            body=None,
        )

        # Should passthrough
        assert result is None


class TestTransactionCensoring:
    """Test transaction censoring behavior."""

    def test_transaction_censoring_creation(self) -> None:
        """Test transaction censoring creation."""
        behavior = TransactionCensoring(
            target_addresses=["0x1234", "0x5678"],
            censor_probability=1.0,
        )
        assert behavior.name == "transaction_censoring"
        assert len(behavior.target_addresses) == 2
        assert behavior.censor_probability == 1.0

    def test_transaction_censoring_filter(self) -> None:
        """Test censoring transactions from target addresses."""
        behavior = TransactionCensoring(
            target_addresses=["0x1234"],
            censor_probability=1.0,
        )

        # Intercept block production
        result = behavior.intercept_request(
            path="/eth/v1/validator/blocks/123",
            params={},
            body={
                "transactions": [
                    {"from": "0x1234", "to": "0xabcd"},
                    {"from": "0x5678", "to": "0xabcd"},
                ]
            },
        )

        # Should censor transaction from 0x1234
        assert result is not None
        assert result.get("censored") is True
        assert len(result.get("transactions", [])) == 1
        assert result["transactions"][0]["from"] == "0x5678"

    def test_transaction_censoring_no_targets(self) -> None:
        """Test no censoring when no targets match."""
        behavior = TransactionCensoring(
            target_addresses=["0x9999"],
            censor_probability=1.0,
        )

        # Intercept block production
        result = behavior.intercept_request(
            path="/eth/v1/validator/blocks/123",
            params={},
            body={
                "transactions": [
                    {"from": "0x1234", "to": "0xabcd"},
                ]
            },
        )

        # Should passthrough (no targets found)
        assert result is None


class TestCoordinatedExit:
    """Test coordinated exit behavior."""

    def test_coordinated_exit_creation(self) -> None:
        """Test coordinated exit creation."""
        behavior = CoordinatedExit(trigger_slot=1000)
        assert behavior.name == "coordinated_exit"
        assert behavior.trigger_slot == 1000
        assert behavior.exit_triggered is False

    def test_coordinated_exit_before_trigger(self) -> None:
        """Test behavior before trigger slot."""
        behavior = CoordinatedExit(trigger_slot=1000)

        # Current slot is before trigger
        result = behavior.intercept_request(
            path="/eth/v1/beacon/states/head",
            params={},
            body=None,
        )

        # Should passthrough
        assert result is None
        assert behavior.exit_triggered is False

    def test_coordinated_exit_at_trigger(self) -> None:
        """Test exit triggering at specific slot."""
        behavior = CoordinatedExit(trigger_slot=1000)

        # Simulate reaching trigger slot
        behavior._current_slot = 1000

        result = behavior.intercept_request(
            path="/eth/v1/validator/voluntary_exit",
            params={},
            body={"message": "exit"},
        )

        # Should trigger exit
        assert result is not None
        assert result.get("exit_triggered") is True
        assert behavior.exit_triggered is True


class TestAdversarialBehavior:
    """Test base AdversarialBehavior class."""

    def test_adversarial_behavior_abstract(self) -> None:
        """Test that AdversarialBehavior is abstract."""
        # Can't instantiate directly
        with pytest.raises(TypeError):
            AdversarialBehavior()  # type: ignore

    def test_adversarial_behavior_subclass(self) -> None:
        """Test creating a custom adversarial behavior."""

        class CustomBehavior(AdversarialBehavior):
            @property
            def name(self) -> str:
                return "custom"

            @property
            def description(self) -> str:
                return "Custom behavior for testing"

            def intercept_request(
                self, path: str, params: dict, body: dict | None
            ) -> dict | None:
                if "custom" in path:
                    return {"custom": True}
                return None

        behavior = CustomBehavior()
        assert behavior.name == "custom"

        result = behavior.intercept_request("/custom/endpoint", {}, None)
        assert result == {"custom": True}

        result = behavior.intercept_request("/other/endpoint", {}, None)
        assert result is None
