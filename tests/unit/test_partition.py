"""Unit tests for network partition simulator."""

from __future__ import annotations

import pytest

from chaoswopr.chaos.partition import (
    Island,
    NetworkPartition,
    PartitionMode,
    PartitionSimulator,
)


class TestIsland:
    """Test Island configuration."""

    def test_create_island(self) -> None:
        """Create island with containers."""
        island = Island(
            name="majority",
            containers=["node-1", "node-2", "node-3"],
        )
        assert island.name == "majority"
        assert len(island) == 3
        assert island.containers == ["node-1", "node-2", "node-3"]

    def test_island_with_metadata(self) -> None:
        """Create island with metadata."""
        island = Island(
            name="minority",
            containers=["node-4", "node-5"],
            metadata={"client": "nethermind", "role": "validator"},
        )
        assert island.metadata["client"] == "nethermind"
        assert island.metadata["role"] == "validator"

    def test_island_length(self) -> None:
        """Island length returns container count."""
        island = Island(name="test", containers=["n1", "n2", "n3", "n4"])
        assert len(island) == 4


class TestNetworkPartition:
    """Test NetworkPartition configuration."""

    def test_valid_clean_partition(self) -> None:
        """Valid clean partition passes validation."""
        partition = NetworkPartition(
            mode=PartitionMode.CLEAN,
            islands=[
                Island(name="majority", containers=["n1", "n2", "n3"]),
                Island(name="minority", containers=["n4", "n5"]),
            ],
        )
        errors = partition.validate()
        assert errors == []

    def test_valid_degraded_partition(self) -> None:
        """Valid degraded partition passes validation."""
        partition = NetworkPartition(
            mode=PartitionMode.DEGRADED,
            islands=[
                Island(name="island1", containers=["n1", "n2"]),
                Island(name="island2", containers=["n3", "n4"]),
            ],
            degraded_packet_loss_percent=80.0,
            degraded_latency_ms=2000,
        )
        errors = partition.validate()
        assert errors == []

    def test_too_few_islands(self) -> None:
        """Partition with <2 islands fails validation."""
        partition = NetworkPartition(
            mode=PartitionMode.CLEAN,
            islands=[
                Island(name="only", containers=["n1", "n2"]),
            ],
        )
        errors = partition.validate()
        assert any("at least 2 islands" in e for e in errors)

    def test_empty_island(self) -> None:
        """Partition with empty island fails validation."""
        partition = NetworkPartition(
            mode=PartitionMode.CLEAN,
            islands=[
                Island(name="island1", containers=["n1", "n2"]),
                Island(name="empty", containers=[]),
            ],
        )
        errors = partition.validate()
        assert any("at least 1 container" in e for e in errors)

    def test_duplicate_containers(self) -> None:
        """Partition with duplicate containers fails validation."""
        partition = NetworkPartition(
            mode=PartitionMode.CLEAN,
            islands=[
                Island(name="island1", containers=["n1", "n2"]),
                Island(name="island2", containers=["n2", "n3"]),  # n2 duplicated
            ],
        )
        errors = partition.validate()
        assert any("cannot appear in multiple islands" in e for e in errors)

    def test_invalid_degraded_packet_loss(self) -> None:
        """Degraded partition with invalid packet loss fails validation."""
        partition = NetworkPartition(
            mode=PartitionMode.DEGRADED,
            islands=[
                Island(name="island1", containers=["n1"]),
                Island(name="island2", containers=["n2"]),
            ],
            degraded_packet_loss_percent=150.0,
        )
        errors = partition.validate()
        assert any("packet_loss_percent" in e for e in errors)

    def test_invalid_degraded_latency(self) -> None:
        """Degraded partition with invalid latency fails validation."""
        partition = NetworkPartition(
            mode=PartitionMode.DEGRADED,
            islands=[
                Island(name="island1", containers=["n1"]),
                Island(name="island2", containers=["n2"]),
            ],
            degraded_latency_ms=100000,
        )
        errors = partition.validate()
        assert any("latency_ms" in e for e in errors)

    def test_get_island_summary(self) -> None:
        """get_island_summary returns correct statistics."""
        partition = NetworkPartition(
            mode=PartitionMode.CLEAN,
            islands=[
                Island(name="majority", containers=["n1", "n2", "n3"]),
                Island(name="minority", containers=["n4", "n5"]),
            ],
        )
        summary = partition.get_island_summary()
        assert summary["mode"] == "clean"
        assert summary["num_islands"] == 2
        assert summary["island_sizes"] == [3, 2]
        assert summary["total_nodes"] == 5
        assert summary["island_names"] == ["majority", "minority"]


class TestPartitionSimulator:
    """Test PartitionSimulator."""

    @pytest.fixture
    def simulator(self) -> PartitionSimulator:
        """Create a partition simulator in dry-run mode."""
        return PartitionSimulator(dry_run=True)

    def test_create_two_island_partition(
        self, simulator: PartitionSimulator
    ) -> None:
        """Create a valid two-island partition."""
        partition = NetworkPartition(
            mode=PartitionMode.CLEAN,
            islands=[
                Island(name="majority", containers=["n1", "n2", "n3"]),
                Island(name="minority", containers=["n4", "n5"]),
            ],
            dry_run=True,
        )
        partition_id = simulator.create_partition(partition)
        assert partition_id.startswith("partition-")

    def test_create_invalid_partition_raises(
        self, simulator: PartitionSimulator
    ) -> None:
        """Create invalid partition raises ValueError."""
        partition = NetworkPartition(
            mode=PartitionMode.CLEAN,
            islands=[
                Island(name="only", containers=["n1"]),
            ],
        )
        with pytest.raises(ValueError, match="Invalid partition configuration"):
            simulator.create_partition(partition)

    def test_remove_partition(self, simulator: PartitionSimulator) -> None:
        """Remove existing partition returns True."""
        partition = NetworkPartition(
            mode=PartitionMode.CLEAN,
            islands=[
                Island(name="island1", containers=["n1", "n2"]),
                Island(name="island2", containers=["n3", "n4"]),
            ],
            dry_run=True,
        )
        partition_id = simulator.create_partition(partition)
        assert simulator.remove_partition(partition_id) is True

    def test_remove_nonexistent_partition(
        self, simulator: PartitionSimulator
    ) -> None:
        """Remove nonexistent partition returns False."""
        assert simulator.remove_partition("partition-nonexistent") is False

    def test_list_active_empty(self, simulator: PartitionSimulator) -> None:
        """List active partitions when none exist."""
        active = simulator.list_active()
        assert active == {}

    def test_list_active_with_partitions(
        self, simulator: PartitionSimulator
    ) -> None:
        """List active partitions with created partitions."""
        partition1 = NetworkPartition(
            mode=PartitionMode.CLEAN,
            islands=[
                Island(name="i1", containers=["n1"]),
                Island(name="i2", containers=["n2"]),
            ],
            dry_run=True,
        )
        partition2 = NetworkPartition(
            mode=PartitionMode.DEGRADED,
            islands=[
                Island(name="i3", containers=["n3"]),
                Island(name="i4", containers=["n4"]),
            ],
            dry_run=True,
        )

        partition_id1 = simulator.create_partition(partition1)
        partition_id2 = simulator.create_partition(partition2)

        active = simulator.list_active()
        assert len(active) == 2
        assert partition_id1 in active
        assert partition_id2 in active

    def test_remove_all(self, simulator: PartitionSimulator) -> None:
        """Remove all partitions."""
        partition1 = NetworkPartition(
            mode=PartitionMode.CLEAN,
            islands=[
                Island(name="i1", containers=["n1"]),
                Island(name="i2", containers=["n2"]),
            ],
            dry_run=True,
        )
        partition2 = NetworkPartition(
            mode=PartitionMode.CLEAN,
            islands=[
                Island(name="i3", containers=["n3"]),
                Island(name="i4", containers=["n4"]),
            ],
            dry_run=True,
        )

        simulator.create_partition(partition1)
        simulator.create_partition(partition2)

        count = simulator.remove_all()
        assert count == 2
        assert simulator.list_active() == {}

    def test_create_two_island_partition_convenience(
        self, simulator: PartitionSimulator
    ) -> None:
        """Convenience method create_two_island_partition works."""
        partition_id = simulator.create_two_island_partition(
            majority_containers=["n1", "n2", "n3"],
            minority_containers=["n4", "n5"],
            mode=PartitionMode.CLEAN,
        )
        assert partition_id.startswith("partition-")
        assert len(simulator.list_active()) == 1

    def test_create_three_island_partition_convenience(
        self, simulator: PartitionSimulator
    ) -> None:
        """Convenience method create_three_island_partition works."""
        partition_id = simulator.create_three_island_partition(
            island1_containers=["n1", "n2"],
            island2_containers=["n3", "n4"],
            island3_containers=["n5", "n6"],
            mode=PartitionMode.CLEAN,
        )
        assert partition_id.startswith("partition-")
        assert len(simulator.list_active()) == 1

    def test_get_partition_topology(self, simulator: PartitionSimulator) -> None:
        """Get topology information for active partition."""
        partition = NetworkPartition(
            mode=PartitionMode.CLEAN,
            islands=[
                Island(
                    name="majority",
                    containers=["n1", "n2", "n3"],
                    metadata={"role": "validators"},
                ),
                Island(
                    name="minority",
                    containers=["n4", "n5"],
                    metadata={"role": "backup"},
                ),
            ],
            dry_run=True,
        )
        partition_id = simulator.create_partition(partition)

        topology = simulator.get_partition_topology(partition_id)
        assert topology is not None
        assert topology["partition_id"] == partition_id
        assert topology["summary"]["num_islands"] == 2
        assert topology["summary"]["total_nodes"] == 5
        assert len(topology["islands"]) == 2
        assert topology["islands"][0]["name"] == "majority"
        assert topology["islands"][0]["size"] == 3
        assert topology["islands"][0]["metadata"]["role"] == "validators"

    def test_get_partition_topology_nonexistent(
        self, simulator: PartitionSimulator
    ) -> None:
        """Get topology for nonexistent partition returns None."""
        topology = simulator.get_partition_topology("partition-nonexistent")
        assert topology is None

    def test_degraded_partition(self, simulator: PartitionSimulator) -> None:
        """Create degraded partition with custom parameters."""
        partition = NetworkPartition(
            mode=PartitionMode.DEGRADED,
            islands=[
                Island(name="island1", containers=["n1", "n2"]),
                Island(name="island2", containers=["n3", "n4"]),
            ],
            degraded_packet_loss_percent=60.0,
            degraded_latency_ms=1500,
            dry_run=True,
        )
        partition_id = simulator.create_partition(partition)
        assert partition_id.startswith("partition-")

        topology = simulator.get_partition_topology(partition_id)
        assert topology["summary"]["mode"] == "degraded"

    def test_three_island_partition(self, simulator: PartitionSimulator) -> None:
        """Create partition with three islands."""
        partition = NetworkPartition(
            mode=PartitionMode.CLEAN,
            islands=[
                Island(name="island1", containers=["n1", "n2"]),
                Island(name="island2", containers=["n3", "n4"]),
                Island(name="island3", containers=["n5", "n6"]),
            ],
            dry_run=True,
        )
        partition_id = simulator.create_partition(partition)

        topology = simulator.get_partition_topology(partition_id)
        assert topology["summary"]["num_islands"] == 3
        assert topology["summary"]["total_nodes"] == 6
