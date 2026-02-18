"""Conversation Context Management for ChaosWopr Chat.

Tracks conversation state across multiple turns to enable natural references
like "the experiment", "the testnet", etc.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ConversationContext:
    """Tracks conversation state across chat turns."""

    # Current active resources
    current_experiment_id: Optional[str] = None
    current_enclave_name: Optional[str] = None
    current_runner: Optional[Any] = None  # ExperimentRunner instance

    # Last results for comparison/analysis
    last_scenario: Optional[dict] = None
    last_results: Optional[dict] = None
    last_metrics: Optional[dict] = None

    # Pending approvals (for multi-step workflows)
    pending_approval: Optional[dict] = None

    # Recent references (for pronoun resolution)
    recent_experiment_ids: list[str] = field(default_factory=list)
    recent_fault_ids: list[str] = field(default_factory=list)
    recent_snapshot_ids: list[str] = field(default_factory=list)

    def set_experiment(self, experiment_id: str) -> None:
        """Set current experiment and add to history."""
        self.current_experiment_id = experiment_id
        if experiment_id not in self.recent_experiment_ids:
            self.recent_experiment_ids.insert(0, experiment_id)
            # Keep only last 10
            self.recent_experiment_ids = self.recent_experiment_ids[:10]

    def set_enclave(self, enclave_name: str) -> None:
        """Set current enclave."""
        self.current_enclave_name = enclave_name

    def add_fault(self, fault_id: str) -> None:
        """Track a fault injection."""
        if fault_id not in self.recent_fault_ids:
            self.recent_fault_ids.insert(0, fault_id)
            self.recent_fault_ids = self.recent_fault_ids[:10]

    def add_snapshot(self, snapshot_id: str) -> None:
        """Track a snapshot creation."""
        if snapshot_id not in self.recent_snapshot_ids:
            self.recent_snapshot_ids.insert(0, snapshot_id)
            self.recent_snapshot_ids = self.recent_snapshot_ids[:10]

    def clear(self) -> None:
        """Clear all context (fresh start)."""
        self.current_experiment_id = None
        self.current_enclave_name = None
        self.current_runner = None
        self.last_scenario = None
        self.last_results = None
        self.last_metrics = None
        self.pending_approval = None
        self.recent_experiment_ids.clear()
        self.recent_fault_ids.clear()
        self.recent_snapshot_ids.clear()

    def get_experiment_id(self, experiment_id: Optional[str] = None) -> Optional[str]:
        """Resolve experiment ID from context if not provided."""
        if experiment_id:
            return experiment_id
        return self.current_experiment_id

    def get_enclave_name(self, enclave_name: Optional[str] = None) -> Optional[str]:
        """Resolve enclave name from context if not provided."""
        if enclave_name:
            return enclave_name
        return self.current_enclave_name
