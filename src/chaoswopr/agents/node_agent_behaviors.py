"""Node Agent adversarial behaviors library.

Implements various Byzantine behaviors that can be injected at the protocol level:
- AttestationWithholding: Withhold attestations from the network
- AttestationDelay: Delay attestation submission
- BlockEquivocation: Propose conflicting blocks
- TransactionCensoring: Censor transactions from specific addresses
- CoordinatedExit: Trigger coordinated validator exits

These behaviors simulate real-world attack scenarios and allow testing
of network resilience under Byzantine conditions.
"""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from typing import Any

from chaoswopr.safety.audit import AuditLogger


class AdversarialBehavior(ABC):
    """Base class for adversarial behaviors.

    All adversarial behaviors must implement:
    - name: Human-readable behavior name
    - description: What this behavior does
    - intercept_request: How to modify/block requests
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the behavior name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Get the behavior description."""
        pass

    @abstractmethod
    def intercept_request(
        self, path: str, params: dict[str, Any], body: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Intercept a Beacon API request.

        Args:
            path: Request path.
            params: Query parameters.
            body: Request body.

        Returns:
            Modified response dict if request should be modified,
            None to passthrough to upstream.
        """
        pass


class HonestBehavior:
    """Honest behavior - passthrough with audit logging.

    This is the default behavior for 70% of nodes. It simply logs
    all requests for audit purposes and passes them through unchanged.
    """

    def __init__(
        self,
        audit_logger: AuditLogger | None = None,
        node_id: str = "unknown",
    ) -> None:
        """Initialize honest behavior.

        Args:
            audit_logger: Audit logger for recording requests.
            node_id: Node ID for audit logging.
        """
        self._audit_logger = audit_logger
        self._node_id = node_id

    @property
    def name(self) -> str:
        """Get the behavior name."""
        return "honest"

    @property
    def description(self) -> str:
        """Get the behavior description."""
        return "Pass-through proxy with audit logging"

    def intercept_request(
        self, path: str, params: dict[str, Any], body: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Log the request and passthrough.

        Args:
            path: Request path.
            params: Query parameters.
            body: Request body.

        Returns:
            None (passthrough to upstream).
        """
        if self._audit_logger:
            self._audit_logger.log(
                agent_id=self._node_id,
                action_type="node_agent_request",
                target=path,
                outcome="success",
                parameters={"params": params, "has_body": body is not None},
            )

        # Passthrough - return None
        return None


class AttestationWithholding(AdversarialBehavior):
    """Withhold attestations from the network.

    Simulates a validator that receives attestation duties but fails
    to submit them, reducing network participation rate. This tests
    the network's resilience to low participation.
    """

    def __init__(self, withhold_probability: float = 1.0) -> None:
        """Initialize attestation withholding behavior.

        Args:
            withhold_probability: Probability (0-1) of withholding each attestation.
        """
        self._withhold_probability = withhold_probability

    @property
    def name(self) -> str:
        """Get the behavior name."""
        return "attestation_withholding"

    @property
    def description(self) -> str:
        """Get the behavior description."""
        return f"Withhold attestations with {self._withhold_probability * 100}% probability"

    @property
    def withhold_probability(self) -> float:
        """Get the withhold probability."""
        return self._withhold_probability

    def intercept_request(
        self, path: str, params: dict[str, Any], body: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Intercept attestation submissions.

        Args:
            path: Request path.
            params: Query parameters.
            body: Request body.

        Returns:
            Block response if withholding, None to passthrough.
        """
        # Check if this is an attestation submission
        if "/beacon/pool/attestations" in path:
            # Randomly decide whether to withhold
            if random.random() < self._withhold_probability:
                return {
                    "blocked": True,
                    "reason": "attestation_withheld",
                }

        # Passthrough other requests
        return None


class AttestationDelay(AdversarialBehavior):
    """Delay attestation submission.

    Introduces artificial delay before submitting attestations, potentially
    causing them to miss the optimal inclusion slot. Tests the network's
    handling of late attestations.
    """

    def __init__(self, delay_seconds: float = 1.0) -> None:
        """Initialize attestation delay behavior.

        Args:
            delay_seconds: Delay in seconds before submitting attestations.
        """
        self._delay_seconds = delay_seconds

    @property
    def name(self) -> str:
        """Get the behavior name."""
        return "attestation_delay"

    @property
    def description(self) -> str:
        """Get the behavior description."""
        return f"Delay attestations by {self._delay_seconds} seconds"

    @property
    def delay_seconds(self) -> float:
        """Get the delay duration."""
        return self._delay_seconds

    def intercept_request(
        self, path: str, params: dict[str, Any], body: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Delay attestation submissions.

        Args:
            path: Request path.
            params: Query parameters.
            body: Request body.

        Returns:
            None (passthrough after delay).
        """
        # Check if this is an attestation submission
        if "/beacon/pool/attestations" in path:
            # Introduce delay
            time.sleep(self._delay_seconds)

        # Passthrough (after delay)
        return None


class BlockEquivocation(AdversarialBehavior):
    """Propose conflicting blocks.

    Simulates a validator proposing multiple different blocks for the same
    slot (equivocation), which is a slashable offense. Tests slashing detection
    and network handling of conflicting proposals.
    """

    def __init__(self, equivocate_probability: float = 1.0) -> None:
        """Initialize block equivocation behavior.

        Args:
            equivocate_probability: Probability (0-1) of equivocating on each proposal.
        """
        self._equivocate_probability = equivocate_probability

    @property
    def name(self) -> str:
        """Get the behavior name."""
        return "block_equivocation"

    @property
    def description(self) -> str:
        """Get the behavior description."""
        return f"Equivocate on block proposals with {self._equivocate_probability * 100}% probability"

    @property
    def equivocate_probability(self) -> float:
        """Get the equivocation probability."""
        return self._equivocate_probability

    def intercept_request(
        self, path: str, params: dict[str, Any], body: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Intercept block proposals.

        Args:
            path: Request path.
            params: Query parameters.
            body: Request body.

        Returns:
            Modified response if equivocating, None to passthrough.
        """
        # Check if this is a block proposal request
        if "/validator/blocks/" in path:
            # Randomly decide whether to equivocate
            if random.random() < self._equivocate_probability:
                return {
                    "equivocated": True,
                    "reason": "double_proposal",
                }

        # Passthrough other requests
        return None


class TransactionCensoring(AdversarialBehavior):
    """Censor transactions from specific addresses.

    Simulates a validator that excludes transactions from certain addresses
    when proposing blocks. Tests MEV manipulation and censorship resistance.
    """

    def __init__(
        self,
        target_addresses: list[str],
        censor_probability: float = 1.0,
    ) -> None:
        """Initialize transaction censoring behavior.

        Args:
            target_addresses: List of addresses to censor.
            censor_probability: Probability (0-1) of censoring matching transactions.
        """
        self._target_addresses = [addr.lower() for addr in target_addresses]
        self._censor_probability = censor_probability

    @property
    def name(self) -> str:
        """Get the behavior name."""
        return "transaction_censoring"

    @property
    def description(self) -> str:
        """Get the behavior description."""
        return f"Censor transactions from {len(self._target_addresses)} addresses"

    @property
    def target_addresses(self) -> list[str]:
        """Get the list of censored addresses."""
        return self._target_addresses.copy()

    @property
    def censor_probability(self) -> float:
        """Get the censoring probability."""
        return self._censor_probability

    def intercept_request(
        self, path: str, params: dict[str, Any], body: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Intercept block production to censor transactions.

        Args:
            path: Request path.
            params: Query parameters.
            body: Request body.

        Returns:
            Modified block with censored transactions, or None to passthrough.
        """
        # Check if this is a block production request
        if "/validator/blocks/" in path and body:
            # Check if body contains transactions
            if "transactions" in body:
                transactions = body.get("transactions", [])

                # Filter out transactions from target addresses
                censored_txs = []
                for tx in transactions:
                    tx_from = tx.get("from", "").lower()
                    if tx_from in self._target_addresses:
                        # Skip this transaction (censor it)
                        if random.random() < self._censor_probability:
                            continue
                    censored_txs.append(tx)

                # If we censored any transactions, return modified block
                if len(censored_txs) < len(transactions):
                    return {
                        "censored": True,
                        "transactions": censored_txs,
                        "censored_count": len(transactions) - len(censored_txs),
                    }

        # Passthrough
        return None


class CoordinatedExit(AdversarialBehavior):
    """Trigger coordinated validator exits.

    Simulates multiple validators exiting the network simultaneously,
    which can impact the active validator set and network security.
    Tests the network's handling of mass validator exits.
    """

    def __init__(self, trigger_slot: int) -> None:
        """Initialize coordinated exit behavior.

        Args:
            trigger_slot: Slot number at which to trigger the exit.
        """
        self._trigger_slot = trigger_slot
        self._exit_triggered = False
        self._current_slot = 0

    @property
    def name(self) -> str:
        """Get the behavior name."""
        return "coordinated_exit"

    @property
    def description(self) -> str:
        """Get the behavior description."""
        return f"Trigger validator exit at slot {self._trigger_slot}"

    @property
    def trigger_slot(self) -> int:
        """Get the trigger slot."""
        return self._trigger_slot

    @property
    def exit_triggered(self) -> bool:
        """Check if exit has been triggered."""
        return self._exit_triggered

    def intercept_request(
        self, path: str, params: dict[str, Any], body: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Intercept requests to trigger exit at specific slot.

        Args:
            path: Request path.
            params: Query parameters.
            body: Request body.

        Returns:
            Exit trigger response if conditions met, None to passthrough.
        """
        # Check if we should trigger exit
        if self._current_slot >= self._trigger_slot and not self._exit_triggered:
            # Check if this is a voluntary exit request
            if "/validator/voluntary_exit" in path:
                self._exit_triggered = True
                return {
                    "exit_triggered": True,
                    "trigger_slot": self._trigger_slot,
                }

        # Passthrough
        return None
