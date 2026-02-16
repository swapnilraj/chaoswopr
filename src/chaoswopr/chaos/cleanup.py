"""Fault cleanup daemon for automatic fault removal on orchestrator failure.

Monitors the orchestrator's heartbeat and automatically removes all active faults
if the orchestrator crashes or becomes unresponsive. This prevents "stuck faults"
that could corrupt the testnet after an orchestrator failure.

The cleanup daemon runs as a separate process and monitors:
- Active network faults
- Active node faults
- Active network partitions
- Orchestrator heartbeat

If the orchestrator heartbeat stops for more than the timeout period,
all faults are automatically removed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from chaoswopr.chaos.network_faults import NetworkFaultInjector
from chaoswopr.chaos.node_faults import NodeFaultInjector
from chaoswopr.chaos.partition import PartitionSimulator
from chaoswopr.safety.audit import AuditLogger


@dataclass
class FaultRegistryEntry:
    """Entry in the fault registry.

    Attributes:
        fault_id: Unique fault identifier.
        fault_type: Type of fault (network, node, partition).
        created_at: Timestamp when fault was created.
        metadata: Optional metadata about the fault.
    """

    fault_id: str
    fault_type: str
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestratorHeartbeat:
    """Orchestrator heartbeat tracking.

    Attributes:
        last_heartbeat: Timestamp of last heartbeat.
        timeout_seconds: Heartbeat timeout in seconds.
        is_alive: Whether orchestrator is considered alive.
    """

    last_heartbeat: float = field(default_factory=time.time)
    timeout_seconds: int = 300  # 5 minutes default
    is_alive: bool = True

    def update(self) -> None:
        """Update heartbeat timestamp."""
        self.last_heartbeat = time.time()
        self.is_alive = True

    def check(self) -> bool:
        """Check if orchestrator is alive.

        Returns:
            True if alive, False if heartbeat timed out.
        """
        elapsed = time.time() - self.last_heartbeat
        self.is_alive = elapsed < self.timeout_seconds
        return self.is_alive

    def time_since_last_heartbeat(self) -> float:
        """Get time since last heartbeat in seconds.

        Returns:
            Seconds since last heartbeat.
        """
        return time.time() - self.last_heartbeat


class FaultRegistry:
    """Registry of all active faults for cleanup tracking.

    Tracks all active faults across network, node, and partition injectors.
    Provides methods to register, unregister, and list active faults.
    """

    def __init__(self) -> None:
        """Initialize fault registry."""
        self._faults: dict[str, FaultRegistryEntry] = {}

    def register(
        self,
        fault_id: str,
        fault_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a new fault.

        Args:
            fault_id: Unique fault identifier.
            fault_type: Type of fault (network, node, partition).
            metadata: Optional metadata about the fault.
        """
        self._faults[fault_id] = FaultRegistryEntry(
            fault_id=fault_id,
            fault_type=fault_type,
            metadata=metadata or {},
        )

    def unregister(self, fault_id: str) -> bool:
        """Unregister a fault.

        Args:
            fault_id: Fault identifier to remove.

        Returns:
            True if fault was registered and removed, False if not found.
        """
        if fault_id in self._faults:
            del self._faults[fault_id]
            return True
        return False

    def list_all(self) -> list[FaultRegistryEntry]:
        """List all registered faults.

        Returns:
            List of fault registry entries.
        """
        return list(self._faults.values())

    def count(self) -> int:
        """Get count of registered faults.

        Returns:
            Number of registered faults.
        """
        return len(self._faults)

    def count_by_type(self) -> dict[str, int]:
        """Get fault count by type.

        Returns:
            Dictionary mapping fault types to counts.
        """
        counts: dict[str, int] = {}
        for entry in self._faults.values():
            counts[entry.fault_type] = counts.get(entry.fault_type, 0) + 1
        return counts

    def clear(self) -> int:
        """Clear all registered faults.

        Returns:
            Number of faults cleared.
        """
        count = len(self._faults)
        self._faults.clear()
        return count


class CleanupDaemon:
    """Daemon that monitors orchestrator health and cleans up faults.

    Runs in the background and periodically checks:
    1. Orchestrator heartbeat status
    2. If heartbeat timed out, removes all active faults

    Examples:
        >>> daemon = CleanupDaemon(
        ...     network_injector=network_injector,
        ...     node_injector=node_injector,
        ...     partition_simulator=partition_simulator,
        ... )
        >>> daemon.start()
        >>> # Orchestrator sends heartbeats
        >>> daemon.heartbeat()
        >>> # If orchestrator crashes, daemon automatically cleans up
        >>> daemon.cleanup_all()
        >>> daemon.stop()
    """

    def __init__(
        self,
        network_injector: NetworkFaultInjector,
        node_injector: NodeFaultInjector,
        partition_simulator: PartitionSimulator,
        audit_logger: AuditLogger | None = None,
        heartbeat_timeout_seconds: int = 300,
        check_interval_seconds: int = 30,
    ) -> None:
        """Initialize cleanup daemon.

        Args:
            network_injector: Network fault injector.
            node_injector: Node fault injector.
            partition_simulator: Partition simulator.
            audit_logger: Audit logger for recording cleanup events.
            heartbeat_timeout_seconds: Orchestrator heartbeat timeout.
            check_interval_seconds: How often to check heartbeat.
        """
        self._network_injector = network_injector
        self._node_injector = node_injector
        self._partition_simulator = partition_simulator
        self._audit_logger = audit_logger

        self._registry = FaultRegistry()
        self._heartbeat = OrchestratorHeartbeat(
            timeout_seconds=heartbeat_timeout_seconds
        )
        self._check_interval = check_interval_seconds

        self._running = False
        self._last_check_time = time.time()

    def heartbeat(self) -> None:
        """Update orchestrator heartbeat.

        Should be called regularly by the orchestrator to indicate it's alive.
        """
        self._heartbeat.update()

        if self._audit_logger:
            self._audit_logger.log_event(
                event_type="orchestrator_heartbeat",
                details={
                    "timestamp": self._heartbeat.last_heartbeat,
                },
            )

    def check_and_cleanup(self) -> dict[str, Any]:
        """Check orchestrator health and cleanup if needed.

        Returns:
            Dictionary with check results and cleanup stats.
        """
        self._last_check_time = time.time()

        # Check heartbeat
        is_alive = self._heartbeat.check()
        time_since_heartbeat = self._heartbeat.time_since_last_heartbeat()

        result = {
            "timestamp": self._last_check_time,
            "orchestrator_alive": is_alive,
            "time_since_heartbeat": time_since_heartbeat,
            "active_fault_count": self._registry.count(),
            "active_faults_by_type": self._registry.count_by_type(),
            "cleanup_triggered": False,
            "faults_removed": 0,
        }

        # If orchestrator is dead, cleanup all faults
        if not is_alive:
            if self._audit_logger:
                self._audit_logger.log_event(
                    event_type="orchestrator_timeout",
                    details={
                        "time_since_heartbeat": time_since_heartbeat,
                        "timeout_seconds": self._heartbeat.timeout_seconds,
                    },
                )

            cleanup_count = self.cleanup_all()
            result["cleanup_triggered"] = True
            result["faults_removed"] = cleanup_count

        return result

    def cleanup_all(self) -> int:
        """Cleanup all active faults.

        Returns:
            Number of faults removed.
        """
        total_removed = 0

        # Log cleanup initiation
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type="cleanup_initiated",
                details={
                    "active_fault_count": self._registry.count(),
                    "faults_by_type": self._registry.count_by_type(),
                },
            )

        # Remove network faults
        network_count = self._network_injector.remove_all()
        total_removed += network_count

        # Remove node faults
        node_count = self._node_injector.remove_all()
        total_removed += node_count

        # Remove partitions
        partition_count = self._partition_simulator.remove_all()
        total_removed += partition_count

        # Clear registry
        self._registry.clear()

        # Log cleanup completion
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type="cleanup_completed",
                details={
                    "faults_removed": total_removed,
                    "network_faults": network_count,
                    "node_faults": node_count,
                    "partitions": partition_count,
                },
            )

        return total_removed

    def register_fault(
        self,
        fault_id: str,
        fault_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a fault for tracking.

        Args:
            fault_id: Fault identifier.
            fault_type: Type of fault (network, node, partition).
            metadata: Optional metadata.
        """
        self._registry.register(fault_id, fault_type, metadata)

    def unregister_fault(self, fault_id: str) -> bool:
        """Unregister a fault.

        Args:
            fault_id: Fault identifier.

        Returns:
            True if fault was unregistered, False if not found.
        """
        return self._registry.unregister(fault_id)

    def get_status(self) -> dict[str, Any]:
        """Get current daemon status.

        Returns:
            Dictionary with daemon status information.
        """
        return {
            "running": self._running,
            "orchestrator_alive": self._heartbeat.is_alive,
            "time_since_heartbeat": self._heartbeat.time_since_last_heartbeat(),
            "heartbeat_timeout": self._heartbeat.timeout_seconds,
            "check_interval": self._check_interval,
            "active_fault_count": self._registry.count(),
            "faults_by_type": self._registry.count_by_type(),
            "last_check_time": self._last_check_time,
        }

    def start(self) -> None:
        """Start the cleanup daemon.

        Note: This is a synchronous start. For background execution,
        run in a separate thread or process.
        """
        self._running = True
        self._heartbeat.update()

        if self._audit_logger:
            self._audit_logger.log_event(
                event_type="cleanup_daemon_started",
                details={
                    "heartbeat_timeout": self._heartbeat.timeout_seconds,
                    "check_interval": self._check_interval,
                },
            )

    def stop(self) -> None:
        """Stop the cleanup daemon."""
        self._running = False

        if self._audit_logger:
            self._audit_logger.log_event(
                event_type="cleanup_daemon_stopped",
                details={
                    "final_fault_count": self._registry.count(),
                },
            )

    def is_running(self) -> bool:
        """Check if daemon is running.

        Returns:
            True if running, False otherwise.
        """
        return self._running
