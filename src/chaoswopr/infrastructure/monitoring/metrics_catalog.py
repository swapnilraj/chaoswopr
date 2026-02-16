"""Core metrics catalog for chaoswopr monitoring.

Defines the 50+ metrics required by the spec:
- Consensus metrics: finality time, participation rate, attestation effectiveness
- Network metrics: peer counts, mempool depth, P2P message rates
- Resource metrics: CPU, memory, disk I/O per node
- Safety metrics: slashing count, voluntary exits, proposer effectiveness
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MetricCategory(str, Enum):
    """Categories of monitored metrics."""

    CONSENSUS = "consensus"
    NETWORK = "network"
    RESOURCE = "resource"
    SAFETY = "safety"
    MEV = "mev"
    CUSTOM = "custom"


class MetricSource(str, Enum):
    """Source of metric data."""

    BEACON_API = "beacon_api"
    NODE_EXPORTER = "node_exporter"
    CLIENT_METRICS = "client_metrics"
    CUSTOM_EXPORTER = "custom_exporter"


@dataclass
class MetricDefinition:
    """Definition of a single monitored metric.

    Attributes:
        name: Prometheus metric name.
        description: Human-readable description.
        category: Metric category.
        source: Where the metric comes from.
        promql: PromQL query to retrieve the metric.
        unit: Unit of measurement.
        critical: Whether this metric is safety-critical.
        alert_threshold: Optional threshold that triggers an alert.
    """

    name: str
    description: str
    category: MetricCategory
    source: MetricSource
    promql: str
    unit: str = ""
    critical: bool = False
    alert_threshold: float | None = None
    alert_operator: str = ">"  # ">", "<", ">=", "<="

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "source": self.source.value,
            "promql": self.promql,
            "unit": self.unit,
            "critical": self.critical,
            "alert_threshold": self.alert_threshold,
            "alert_operator": self.alert_operator,
        }


# The core metrics catalog - 50+ metrics as required by the spec
METRICS_CATALOG: list[MetricDefinition] = [
    # === CONSENSUS METRICS ===
    MetricDefinition(
        name="beacon_finality_delay_epochs",
        description="Number of epochs since last finality",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.BEACON_API,
        promql="beacon_head_slot - beacon_finalized_epoch * 32",
        unit="epochs",
        critical=True,
        alert_threshold=5.0,
        alert_operator=">",
    ),
    MetricDefinition(
        name="beacon_participation_rate",
        description="Percentage of validators participating in attestations",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.BEACON_API,
        promql='beacon_participation_rate{job="ethereum_cl"}',
        unit="percent",
        critical=True,
        alert_threshold=66.0,
        alert_operator="<",
    ),
    MetricDefinition(
        name="beacon_head_slot",
        description="Current head slot number",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.BEACON_API,
        promql="beacon_head_slot",
        unit="slot",
    ),
    MetricDefinition(
        name="beacon_finalized_epoch",
        description="Latest finalized epoch",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.BEACON_API,
        promql="beacon_finalized_epoch",
        unit="epoch",
    ),
    MetricDefinition(
        name="beacon_justified_epoch",
        description="Latest justified epoch",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.BEACON_API,
        promql="beacon_justified_epoch",
        unit="epoch",
    ),
    MetricDefinition(
        name="beacon_attestation_inclusion_delay",
        description="Average attestation inclusion delay",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.BEACON_API,
        promql="avg(beacon_attestation_inclusion_delay)",
        unit="slots",
    ),
    MetricDefinition(
        name="beacon_proposer_miss_rate",
        description="Rate of missed block proposals",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.BEACON_API,
        promql="rate(beacon_missed_proposals_total[5m])",
        unit="per_second",
    ),
    MetricDefinition(
        name="beacon_sync_committee_participation",
        description="Sync committee participation rate",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.BEACON_API,
        promql="beacon_sync_committee_participation_rate",
        unit="percent",
    ),
    MetricDefinition(
        name="beacon_epochs_since_finality",
        description="Number of epochs since the last finalized epoch",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.BEACON_API,
        promql="beacon_head_slot / 32 - beacon_finalized_epoch",
        unit="epochs",
        critical=True,
    ),
    MetricDefinition(
        name="beacon_validator_count_active",
        description="Number of active validators",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.BEACON_API,
        promql='count(beacon_validator_status{status="active"})',
        unit="count",
    ),
    # === SAFETY METRICS ===
    MetricDefinition(
        name="beacon_slashing_count",
        description="Total number of slashing events",
        category=MetricCategory.SAFETY,
        source=MetricSource.BEACON_API,
        promql="beacon_slashings_total",
        unit="count",
        critical=True,
        alert_threshold=1.0,
        alert_operator=">=",
    ),
    MetricDefinition(
        name="beacon_slashing_rate",
        description="Rate of slashing events as percentage of active validators",
        category=MetricCategory.SAFETY,
        source=MetricSource.BEACON_API,
        promql="beacon_slashings_total / beacon_validator_count_active * 100",
        unit="percent",
        critical=True,
        alert_threshold=5.0,
        alert_operator=">",
    ),
    MetricDefinition(
        name="beacon_voluntary_exit_count",
        description="Number of voluntary validator exits",
        category=MetricCategory.SAFETY,
        source=MetricSource.BEACON_API,
        promql="beacon_voluntary_exits_total",
        unit="count",
    ),
    MetricDefinition(
        name="beacon_voluntary_exit_rate",
        description="Rate of voluntary exits per epoch",
        category=MetricCategory.SAFETY,
        source=MetricSource.BEACON_API,
        promql="rate(beacon_voluntary_exits_total[5m])",
        unit="per_second",
    ),
    MetricDefinition(
        name="beacon_balance_decrease_rate",
        description="Rate of validator balance decrease (potential slashing indicator)",
        category=MetricCategory.SAFETY,
        source=MetricSource.BEACON_API,
        promql="rate(beacon_total_validator_balance[5m])",
        unit="gwei_per_second",
    ),
    # === NETWORK METRICS ===
    MetricDefinition(
        name="p2p_peer_count",
        description="Number of connected P2P peers per node",
        category=MetricCategory.NETWORK,
        source=MetricSource.CLIENT_METRICS,
        promql='p2p_peers{job="ethereum_cl"}',
        unit="count",
    ),
    MetricDefinition(
        name="p2p_peer_count_avg",
        description="Average peer count across all nodes",
        category=MetricCategory.NETWORK,
        source=MetricSource.CLIENT_METRICS,
        promql="avg(p2p_peers)",
        unit="count",
    ),
    MetricDefinition(
        name="p2p_gossipsub_messages_received",
        description="Rate of gossipsub messages received",
        category=MetricCategory.NETWORK,
        source=MetricSource.CLIENT_METRICS,
        promql="rate(p2p_gossipsub_messages_received_total[5m])",
        unit="per_second",
    ),
    MetricDefinition(
        name="p2p_gossipsub_messages_sent",
        description="Rate of gossipsub messages sent",
        category=MetricCategory.NETWORK,
        source=MetricSource.CLIENT_METRICS,
        promql="rate(p2p_gossipsub_messages_sent_total[5m])",
        unit="per_second",
    ),
    MetricDefinition(
        name="p2p_bandwidth_in",
        description="Incoming network bandwidth",
        category=MetricCategory.NETWORK,
        source=MetricSource.NODE_EXPORTER,
        promql="rate(node_network_receive_bytes_total[5m])",
        unit="bytes_per_second",
    ),
    MetricDefinition(
        name="p2p_bandwidth_out",
        description="Outgoing network bandwidth",
        category=MetricCategory.NETWORK,
        source=MetricSource.NODE_EXPORTER,
        promql="rate(node_network_transmit_bytes_total[5m])",
        unit="bytes_per_second",
    ),
    MetricDefinition(
        name="el_mempool_depth",
        description="Number of pending transactions in the execution layer mempool",
        category=MetricCategory.NETWORK,
        source=MetricSource.CLIENT_METRICS,
        promql='txpool_pending{job="ethereum_el"}',
        unit="count",
    ),
    MetricDefinition(
        name="el_mempool_queued",
        description="Number of queued transactions",
        category=MetricCategory.NETWORK,
        source=MetricSource.CLIENT_METRICS,
        promql='txpool_queued{job="ethereum_el"}',
        unit="count",
    ),
    MetricDefinition(
        name="el_block_number",
        description="Current execution layer block number",
        category=MetricCategory.NETWORK,
        source=MetricSource.CLIENT_METRICS,
        promql="chain_head_block",
        unit="block",
    ),
    MetricDefinition(
        name="el_block_time",
        description="Time between execution layer blocks",
        category=MetricCategory.NETWORK,
        source=MetricSource.CLIENT_METRICS,
        promql="rate(chain_head_block[1m]) * 60",
        unit="seconds",
    ),
    MetricDefinition(
        name="el_gas_used",
        description="Gas used in the latest block",
        category=MetricCategory.NETWORK,
        source=MetricSource.CLIENT_METRICS,
        promql="chain_head_gas_used",
        unit="gas",
    ),
    MetricDefinition(
        name="p2p_discovery_peers",
        description="Number of peers discovered via DHT",
        category=MetricCategory.NETWORK,
        source=MetricSource.CLIENT_METRICS,
        promql="p2p_discovery_peers",
        unit="count",
    ),
    # === RESOURCE METRICS ===
    MetricDefinition(
        name="node_cpu_usage",
        description="CPU usage per node",
        category=MetricCategory.RESOURCE,
        source=MetricSource.NODE_EXPORTER,
        promql='rate(process_cpu_seconds_total[5m]) * 100',
        unit="percent",
    ),
    MetricDefinition(
        name="node_memory_usage",
        description="Memory usage per node",
        category=MetricCategory.RESOURCE,
        source=MetricSource.NODE_EXPORTER,
        promql="process_resident_memory_bytes",
        unit="bytes",
    ),
    MetricDefinition(
        name="node_memory_usage_percent",
        description="Memory usage as percentage of total",
        category=MetricCategory.RESOURCE,
        source=MetricSource.NODE_EXPORTER,
        promql="process_resident_memory_bytes / node_memory_MemTotal_bytes * 100",
        unit="percent",
    ),
    MetricDefinition(
        name="node_disk_io_read",
        description="Disk read I/O rate",
        category=MetricCategory.RESOURCE,
        source=MetricSource.NODE_EXPORTER,
        promql="rate(node_disk_read_bytes_total[5m])",
        unit="bytes_per_second",
    ),
    MetricDefinition(
        name="node_disk_io_write",
        description="Disk write I/O rate",
        category=MetricCategory.RESOURCE,
        source=MetricSource.NODE_EXPORTER,
        promql="rate(node_disk_written_bytes_total[5m])",
        unit="bytes_per_second",
    ),
    MetricDefinition(
        name="node_disk_usage",
        description="Disk space usage",
        category=MetricCategory.RESOURCE,
        source=MetricSource.NODE_EXPORTER,
        promql="node_filesystem_avail_bytes / node_filesystem_size_bytes * 100",
        unit="percent",
    ),
    MetricDefinition(
        name="node_network_errors",
        description="Network error rate",
        category=MetricCategory.RESOURCE,
        source=MetricSource.NODE_EXPORTER,
        promql="rate(node_network_receive_errs_total[5m])",
        unit="per_second",
    ),
    MetricDefinition(
        name="node_open_file_descriptors",
        description="Number of open file descriptors",
        category=MetricCategory.RESOURCE,
        source=MetricSource.NODE_EXPORTER,
        promql="process_open_fds",
        unit="count",
    ),
    MetricDefinition(
        name="node_goroutine_count",
        description="Number of goroutines (Go clients)",
        category=MetricCategory.RESOURCE,
        source=MetricSource.CLIENT_METRICS,
        promql="go_goroutines",
        unit="count",
    ),
    MetricDefinition(
        name="node_gc_duration",
        description="GC pause duration (Go clients)",
        category=MetricCategory.RESOURCE,
        source=MetricSource.CLIENT_METRICS,
        promql="go_gc_duration_seconds",
        unit="seconds",
    ),
    MetricDefinition(
        name="el_db_size",
        description="Execution layer database size",
        category=MetricCategory.RESOURCE,
        source=MetricSource.CLIENT_METRICS,
        promql="chain_db_size",
        unit="bytes",
    ),
    MetricDefinition(
        name="cl_db_size",
        description="Consensus layer database size",
        category=MetricCategory.RESOURCE,
        source=MetricSource.CLIENT_METRICS,
        promql="beacon_db_size",
        unit="bytes",
    ),
    MetricDefinition(
        name="node_uptime",
        description="Node uptime duration",
        category=MetricCategory.RESOURCE,
        source=MetricSource.NODE_EXPORTER,
        promql="process_uptime_seconds",
        unit="seconds",
    ),
    # === MEV METRICS ===
    MetricDefinition(
        name="mev_relay_bids",
        description="Number of MEV relay bids",
        category=MetricCategory.MEV,
        source=MetricSource.CUSTOM_EXPORTER,
        promql="mev_relay_bids_total",
        unit="count",
    ),
    MetricDefinition(
        name="mev_builder_blocks",
        description="Number of builder-produced blocks",
        category=MetricCategory.MEV,
        source=MetricSource.CUSTOM_EXPORTER,
        promql="mev_builder_blocks_total",
        unit="count",
    ),
    MetricDefinition(
        name="mev_inclusion_time",
        description="Time from bid to block inclusion",
        category=MetricCategory.MEV,
        source=MetricSource.CUSTOM_EXPORTER,
        promql="mev_inclusion_time_seconds",
        unit="seconds",
    ),
    # === ADDITIONAL CONSENSUS METRICS ===
    MetricDefinition(
        name="beacon_validator_balance_avg",
        description="Average validator balance",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.BEACON_API,
        promql="avg(beacon_validator_balance)",
        unit="gwei",
    ),
    MetricDefinition(
        name="beacon_epoch_processing_time",
        description="Time to process an epoch",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.CLIENT_METRICS,
        promql="beacon_epoch_processing_duration_seconds",
        unit="seconds",
    ),
    MetricDefinition(
        name="beacon_block_processing_time",
        description="Time to process a block",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.CLIENT_METRICS,
        promql="beacon_block_processing_duration_seconds",
        unit="seconds",
    ),
    MetricDefinition(
        name="beacon_attestation_count",
        description="Number of attestations per epoch",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.BEACON_API,
        promql="beacon_attestations_total",
        unit="count",
    ),
    MetricDefinition(
        name="beacon_reorg_count",
        description="Number of chain reorganizations",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.CLIENT_METRICS,
        promql="beacon_reorgs_total",
        unit="count",
        critical=True,
    ),
    MetricDefinition(
        name="beacon_orphaned_blocks",
        description="Number of orphaned blocks",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.CLIENT_METRICS,
        promql="beacon_orphaned_blocks_total",
        unit="count",
    ),
    MetricDefinition(
        name="beacon_fork_choice_time",
        description="Fork choice computation time",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.CLIENT_METRICS,
        promql="beacon_fork_choice_duration_seconds",
        unit="seconds",
    ),
    MetricDefinition(
        name="el_sync_status",
        description="Execution layer sync status (0=synced, 1=syncing)",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.CLIENT_METRICS,
        promql="el_syncing",
        unit="bool",
    ),
    MetricDefinition(
        name="cl_sync_status",
        description="Consensus layer sync status",
        category=MetricCategory.CONSENSUS,
        source=MetricSource.BEACON_API,
        promql="cl_syncing",
        unit="bool",
    ),
]


class MetricsCatalog:
    """Catalog of all monitored metrics.

    Provides methods for querying, filtering, and validating
    the metrics catalog.
    """

    def __init__(
        self, metrics: list[MetricDefinition] | None = None
    ) -> None:
        """Initialize the catalog.

        Args:
            metrics: Custom metrics list. Defaults to METRICS_CATALOG.
        """
        self._metrics = metrics if metrics is not None else METRICS_CATALOG.copy()

    @property
    def count(self) -> int:
        """Get the total number of metrics."""
        return len(self._metrics)

    @property
    def metrics(self) -> list[MetricDefinition]:
        """Get all metrics."""
        return self._metrics.copy()

    def get_by_name(self, name: str) -> MetricDefinition | None:
        """Get a metric by name."""
        for m in self._metrics:
            if m.name == name:
                return m
        return None

    def get_by_category(self, category: MetricCategory) -> list[MetricDefinition]:
        """Get metrics by category."""
        return [m for m in self._metrics if m.category == category]

    def get_critical_metrics(self) -> list[MetricDefinition]:
        """Get all safety-critical metrics."""
        return [m for m in self._metrics if m.critical]

    def get_alert_metrics(self) -> list[MetricDefinition]:
        """Get metrics that have alert thresholds defined."""
        return [m for m in self._metrics if m.alert_threshold is not None]

    def get_by_source(self, source: MetricSource) -> list[MetricDefinition]:
        """Get metrics by data source."""
        return [m for m in self._metrics if m.source == source]

    def validate(self) -> list[str]:
        """Validate the catalog.

        Returns:
            List of validation errors.
        """
        errors: list[str] = []

        # Check for duplicate names
        names = [m.name for m in self._metrics]
        duplicates = [n for n in names if names.count(n) > 1]
        if duplicates:
            errors.append(f"Duplicate metric names: {set(duplicates)}")

        # Check minimum count
        if len(self._metrics) < 50:
            errors.append(f"Catalog has {len(self._metrics)} metrics, minimum is 50")

        # Check critical metrics exist
        critical = self.get_critical_metrics()
        if len(critical) < 3:
            errors.append(f"Only {len(critical)} critical metrics, need at least 3")

        return errors

    def to_dict(self) -> list[dict[str, Any]]:
        """Convert to list of dictionaries."""
        return [m.to_dict() for m in self._metrics]
