"""Network partition simulator for splitting validator sets into isolated islands.

Creates network partitions that split the testnet into multiple groups that cannot
communicate with each other, simulating real-world network splits and consensus failures.

Supports two partition modes:
- Clean partition: Complete isolation (100% packet drop between islands)
- Degraded partition: Partial isolation (high latency + packet loss between islands)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from chaoswopr.chaos.network_faults import (
    FaultType,
    NetworkFault,
    NetworkFaultInjector,
)
from chaoswopr.safety.audit import AuditLogger


class PartitionMode(str, Enum):
    """Network partition modes."""

    CLEAN = "clean"  # Complete isolation (100% packet drop)
    DEGRADED = "degraded"  # Partial isolation (high latency + packet loss)


@dataclass
class Island:
    """A group of nodes in a network partition.

    Attributes:
        name: Human-readable island identifier.
        containers: List of container IDs/names in this island.
        metadata: Optional metadata (e.g., client types, validator indices).
    """

    name: str
    containers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        """Return number of containers in this island."""
        return len(self.containers)


@dataclass
class NetworkPartition:
    """Configuration for a network partition.

    Attributes:
        mode: Partition mode (clean or degraded).
        islands: List of islands (groups of nodes).
        degraded_packet_loss_percent: Packet loss between islands in degraded mode.
        degraded_latency_ms: Latency between islands in degraded mode.
        dry_run: If True, log actions but don't execute them.
    """

    mode: PartitionMode
    islands: list[Island] = field(default_factory=list)
    degraded_packet_loss_percent: float = 80.0
    degraded_latency_ms: int = 2000
    dry_run: bool = False

    def validate(self) -> list[str]:
        """Validate partition configuration.

        Returns:
            List of validation errors. Empty means valid.
        """
        errors: list[str] = []

        if len(self.islands) < 2:
            errors.append("Must have at least 2 islands for a partition")

        if any(len(island) == 0 for island in self.islands):
            errors.append("All islands must have at least 1 container")

        # Check for duplicate containers
        all_containers: list[str] = []
        for island in self.islands:
            all_containers.extend(island.containers)

        if len(all_containers) != len(set(all_containers)):
            errors.append("Containers cannot appear in multiple islands")

        # Validate degraded mode parameters
        if self.mode == PartitionMode.DEGRADED:
            if (
                self.degraded_packet_loss_percent < 0
                or self.degraded_packet_loss_percent > 100
            ):
                errors.append("degraded_packet_loss_percent must be 0-100")

            if self.degraded_latency_ms < 0 or self.degraded_latency_ms > 60000:
                errors.append("degraded_latency_ms must be 0-60000")

        return errors

    def get_island_summary(self) -> dict[str, Any]:
        """Get summary of partition topology.

        Returns:
            Dictionary with partition statistics.
        """
        return {
            "mode": self.mode.value,
            "num_islands": len(self.islands),
            "island_sizes": [len(island) for island in self.islands],
            "total_nodes": sum(len(island) for island in self.islands),
            "island_names": [island.name for island in self.islands],
        }


class PartitionSimulator:
    """Simulates network partitions by splitting nodes into isolated islands.

    Uses the NetworkFaultInjector to create bidirectional communication barriers
    between islands. Each island can communicate internally but not with other islands.

    Examples:
        >>> simulator = PartitionSimulator()
        >>> island1 = Island(name="majority", containers=["node-1", "node-2", "node-3"])
        >>> island2 = Island(name="minority", containers=["node-4", "node-5"])
        >>> partition = NetworkPartition(
        ...     mode=PartitionMode.CLEAN,
        ...     islands=[island1, island2],
        ... )
        >>> partition_id = simulator.create_partition(partition)
        >>> simulator.remove_partition(partition_id)
    """

    def __init__(
        self,
        network_injector: NetworkFaultInjector | None = None,
        audit_logger: AuditLogger | None = None,
        dry_run: bool = False,
    ) -> None:
        """Initialize partition simulator.

        Args:
            network_injector: Network fault injector (created if not provided).
            audit_logger: Audit logger for recording partition events.
            dry_run: If True, log actions but don't execute them.
        """
        self._network_injector = network_injector or NetworkFaultInjector(
            audit_logger=audit_logger,
            dry_run=dry_run,
        )
        self._audit_logger = audit_logger
        self._dry_run = dry_run

        # Track active partitions: partition_id -> (NetworkPartition, list[fault_ids])
        self._active_partitions: dict[str, tuple[NetworkPartition, list[str]]] = {}

    def create_partition(self, partition: NetworkPartition) -> str:
        """Create a network partition.

        Args:
            partition: Partition configuration.

        Returns:
            Partition ID that can be used to remove the partition.

        Raises:
            ValueError: If partition configuration is invalid.
            RuntimeError: If partition creation fails.
        """
        # Validate configuration
        errors = partition.validate()
        if errors:
            raise ValueError(f"Invalid partition configuration: {errors}")

        # Generate partition ID
        import uuid

        partition_id = f"partition-{uuid.uuid4().hex[:8]}"

        # Log partition creation
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type="partition_create",
                details={
                    "partition_id": partition_id,
                    "summary": partition.get_island_summary(),
                },
            )

        # Create network faults to isolate islands
        fault_ids: list[str] = []

        try:
            # For each pair of islands, create bidirectional isolation
            for i, island_a in enumerate(partition.islands):
                for island_b in partition.islands[i + 1 :]:
                    # Island A cannot reach Island B
                    fault_id_a = self._isolate_island_from_island(
                        source_island=island_a,
                        target_island=island_b,
                        partition=partition,
                    )
                    fault_ids.append(fault_id_a)

                    # Island B cannot reach Island A
                    fault_id_b = self._isolate_island_from_island(
                        source_island=island_b,
                        target_island=island_a,
                        partition=partition,
                    )
                    fault_ids.append(fault_id_b)

        except Exception as e:
            # Rollback on failure
            for fault_id in fault_ids:
                try:
                    self._network_injector.remove(fault_id)
                except Exception:
                    pass
            raise RuntimeError(f"Failed to create partition: {e}") from e

        # Store active partition
        self._active_partitions[partition_id] = (partition, fault_ids)

        return partition_id

    def remove_partition(self, partition_id: str) -> bool:
        """Remove an active network partition.

        Args:
            partition_id: Partition ID returned by create_partition().

        Returns:
            True if partition was removed, False if partition ID not found.
        """
        if partition_id not in self._active_partitions:
            return False

        partition, fault_ids = self._active_partitions[partition_id]

        # Log partition removal
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type="partition_remove",
                details={
                    "partition_id": partition_id,
                    "summary": partition.get_island_summary(),
                },
            )

        # Remove all network faults
        for fault_id in fault_ids:
            try:
                self._network_injector.remove(fault_id)
            except Exception:
                # Continue even if some faults fail to remove
                pass

        # Remove from active partitions
        del self._active_partitions[partition_id]

        return True

    def remove_all(self) -> int:
        """Remove all active partitions.

        Returns:
            Number of partitions removed.
        """
        partition_ids = list(self._active_partitions.keys())
        count = 0
        for partition_id in partition_ids:
            if self.remove_partition(partition_id):
                count += 1
        return count

    def list_active(self) -> dict[str, NetworkPartition]:
        """List all active network partitions.

        Returns:
            Dictionary mapping partition IDs to partition configurations.
        """
        return {
            partition_id: partition
            for partition_id, (partition, _) in self._active_partitions.items()
        }

    def _isolate_island_from_island(
        self,
        source_island: Island,
        target_island: Island,
        partition: NetworkPartition,
    ) -> str:
        """Create network fault to isolate one island from another.

        Args:
            source_island: Island that will have communication blocked.
            target_island: Island that source_island cannot reach.
            partition: Partition configuration.

        Returns:
            Fault ID for the created network fault.
        """
        if partition.mode == PartitionMode.CLEAN:
            # Clean partition: 100% packet drop
            fault = NetworkFault(
                fault_type=FaultType.PACKET_LOSS,
                target_containers=source_island.containers,
                packet_loss_percent=100.0,
                dry_run=partition.dry_run or self._dry_run,
            )
        else:
            # Degraded partition: high latency + packet loss
            fault = NetworkFault(
                fault_type=FaultType.PACKET_LOSS,
                target_containers=source_island.containers,
                packet_loss_percent=partition.degraded_packet_loss_percent,
                latency_ms=partition.degraded_latency_ms,
                dry_run=partition.dry_run or self._dry_run,
            )

        return self._network_injector.inject(fault)

    def create_two_island_partition(
        self,
        majority_containers: list[str],
        minority_containers: list[str],
        mode: PartitionMode = PartitionMode.CLEAN,
    ) -> str:
        """Convenience method to create a two-island partition.

        Args:
            majority_containers: Containers in the majority island.
            minority_containers: Containers in the minority island.
            mode: Partition mode (clean or degraded).

        Returns:
            Partition ID.
        """
        partition = NetworkPartition(
            mode=mode,
            islands=[
                Island(name="majority", containers=majority_containers),
                Island(name="minority", containers=minority_containers),
            ],
            dry_run=self._dry_run,
        )
        return self.create_partition(partition)

    def create_three_island_partition(
        self,
        island1_containers: list[str],
        island2_containers: list[str],
        island3_containers: list[str],
        mode: PartitionMode = PartitionMode.CLEAN,
    ) -> str:
        """Convenience method to create a three-island partition.

        Args:
            island1_containers: Containers in first island.
            island2_containers: Containers in second island.
            island3_containers: Containers in third island.
            mode: Partition mode (clean or degraded).

        Returns:
            Partition ID.
        """
        partition = NetworkPartition(
            mode=mode,
            islands=[
                Island(name="island1", containers=island1_containers),
                Island(name="island2", containers=island2_containers),
                Island(name="island3", containers=island3_containers),
            ],
            dry_run=self._dry_run,
        )
        return self.create_partition(partition)

    def get_partition_topology(self, partition_id: str) -> dict[str, Any] | None:
        """Get topology information for an active partition.

        Args:
            partition_id: Partition ID.

        Returns:
            Topology information, or None if partition not found.
        """
        if partition_id not in self._active_partitions:
            return None

        partition, fault_ids = self._active_partitions[partition_id]

        return {
            "partition_id": partition_id,
            "summary": partition.get_island_summary(),
            "fault_count": len(fault_ids),
            "islands": [
                {
                    "name": island.name,
                    "size": len(island),
                    "containers": island.containers,
                    "metadata": island.metadata,
                }
                for island in partition.islands
            ],
        }
