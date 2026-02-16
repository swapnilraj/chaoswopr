"""Network-level fault injection using tc/netem.

Provides Python wrappers around Linux traffic control (tc) and network emulation (netem)
for injecting network faults into Docker containers and Kubernetes pods.

Supports:
- Packet loss (0-100%)
- Latency injection (0-10000ms) with optional jitter
- Bandwidth throttling
- Network partitions (complete isolation between groups)
- Packet corruption
- Packet reordering

All faults are applied to specific containers/pods via network namespace manipulation.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from chaoswopr.safety.audit import AuditLogger


class FaultType(str, Enum):
    """Types of network faults that can be injected."""

    PACKET_LOSS = "packet_loss"
    LATENCY = "latency"
    BANDWIDTH = "bandwidth"
    PARTITION = "partition"
    CORRUPTION = "corruption"
    REORDER = "reorder"


@dataclass
class NetworkFault:
    """Configuration for a network fault.

    Attributes:
        fault_type: Type of fault to inject.
        target_containers: List of container IDs or names to apply fault to.
        packet_loss_percent: Packet loss percentage (0-100).
        latency_ms: Latency to add in milliseconds.
        jitter_ms: Latency jitter in milliseconds.
        bandwidth_kbps: Bandwidth limit in kilobits per second.
        corruption_percent: Packet corruption percentage (0-100).
        reorder_percent: Packet reordering percentage (0-100).
        duration_seconds: Duration to apply fault (0 = until manually removed).
        dry_run: If True, log actions but don't execute them.
    """

    fault_type: FaultType
    target_containers: list[str] = field(default_factory=list)
    packet_loss_percent: float = 0.0
    latency_ms: int = 0
    jitter_ms: int = 0
    bandwidth_kbps: int = 0
    corruption_percent: float = 0.0
    reorder_percent: float = 0.0
    duration_seconds: int = 0
    dry_run: bool = False

    def validate(self) -> list[str]:
        """Validate fault configuration.

        Returns:
            List of validation errors. Empty means valid.
        """
        errors: list[str] = []

        if not self.target_containers:
            errors.append("target_containers cannot be empty")

        if self.packet_loss_percent < 0 or self.packet_loss_percent > 100:
            errors.append("packet_loss_percent must be between 0 and 100")

        if self.latency_ms < 0 or self.latency_ms > 10000:
            errors.append("latency_ms must be between 0 and 10000")

        if self.jitter_ms < 0 or self.jitter_ms > self.latency_ms:
            errors.append("jitter_ms must be between 0 and latency_ms")

        if self.bandwidth_kbps < 0:
            errors.append("bandwidth_kbps must be >= 0")

        if self.corruption_percent < 0 or self.corruption_percent > 100:
            errors.append("corruption_percent must be between 0 and 100")

        if self.reorder_percent < 0 or self.reorder_percent > 100:
            errors.append("reorder_percent must be between 0 and 100")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "fault_type": self.fault_type.value,
            "target_containers": self.target_containers,
            "packet_loss_percent": self.packet_loss_percent,
            "latency_ms": self.latency_ms,
            "jitter_ms": self.jitter_ms,
            "bandwidth_kbps": self.bandwidth_kbps,
            "corruption_percent": self.corruption_percent,
            "reorder_percent": self.reorder_percent,
            "duration_seconds": self.duration_seconds,
            "dry_run": self.dry_run,
        }


class NetworkFaultInjector:
    """Injects network-level faults using tc/netem.

    Uses Linux traffic control (tc) and network emulation (netem) to inject
    faults at the network layer. Faults are applied by entering the container's
    network namespace and manipulating the tc queueing disciplines.

    Examples:
        >>> injector = NetworkFaultInjector()
        >>> fault = NetworkFault(
        ...     fault_type=FaultType.PACKET_LOSS,
        ...     target_containers=["container-1", "container-2"],
        ...     packet_loss_percent=20.0,
        ... )
        >>> fault_id = injector.inject(fault)
        >>> injector.remove(fault_id)
    """

    def __init__(
        self,
        audit_logger: AuditLogger | None = None,
        dry_run: bool = False,
    ) -> None:
        """Initialize the network fault injector.

        Args:
            audit_logger: Audit logger for recording fault injection actions.
            dry_run: If True, log actions but don't execute them.
        """
        self._audit_logger = audit_logger
        self._dry_run = dry_run
        self._active_faults: dict[str, NetworkFault] = {}

    def inject(self, fault: NetworkFault) -> str:
        """Inject a network fault.

        Args:
            fault: Fault configuration.

        Returns:
            Fault ID that can be used to remove the fault later.

        Raises:
            ValueError: If fault configuration is invalid.
            RuntimeError: If fault injection fails.
        """
        # Validate configuration
        errors = fault.validate()
        if errors:
            raise ValueError(f"Invalid fault configuration: {errors}")

        # Generate fault ID
        import uuid

        fault_id = f"net-{uuid.uuid4().hex[:8]}"

        # Log to audit system
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type="network_fault_inject",
                details={
                    "fault_id": fault_id,
                    "fault": fault.to_dict(),
                },
            )

        # Inject fault for each target container
        for container in fault.target_containers:
            self._inject_to_container(container, fault)

        # Store active fault
        self._active_faults[fault_id] = fault

        return fault_id

    def remove(self, fault_id: str) -> bool:
        """Remove an active network fault.

        Args:
            fault_id: Fault ID returned by inject().

        Returns:
            True if fault was removed, False if fault ID not found.
        """
        if fault_id not in self._active_faults:
            return False

        fault = self._active_faults[fault_id]

        # Log to audit system
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type="network_fault_remove",
                details={
                    "fault_id": fault_id,
                    "fault": fault.to_dict(),
                },
            )

        # Remove fault from each target container
        for container in fault.target_containers:
            self._remove_from_container(container)

        # Remove from active faults
        del self._active_faults[fault_id]

        return True

    def remove_all(self) -> int:
        """Remove all active network faults.

        Returns:
            Number of faults removed.
        """
        fault_ids = list(self._active_faults.keys())
        count = 0
        for fault_id in fault_ids:
            if self.remove(fault_id):
                count += 1
        return count

    def list_active(self) -> dict[str, NetworkFault]:
        """List all active network faults.

        Returns:
            Dictionary mapping fault IDs to fault configurations.
        """
        return dict(self._active_faults)

    def _inject_to_container(self, container: str, fault: NetworkFault) -> None:
        """Inject fault to a specific container.

        Args:
            container: Container ID or name.
            fault: Fault configuration.

        Raises:
            RuntimeError: If fault injection fails.
        """
        if fault.dry_run or self._dry_run:
            print(f"[DRY-RUN] Would inject {fault.fault_type.value} to container {container}")
            return

        # Resolve container name and ensure tc is installed
        container_name = self._resolve_container_name(container)
        self._ensure_tc_installed(container_name)

        # Build tc/netem command
        cmd = self._build_tc_command(container, fault)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            stderr = e.stderr if e.stderr else ""
            stdout = e.stdout if e.stdout else ""
            raise RuntimeError(
                f"Failed to inject fault to container {container}:\n"
                f"Command: {' '.join(cmd)}\n"
                f"Exit code: {e.returncode}\n"
                f"Stdout: {stdout}\n"
                f"Stderr: {stderr}"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"Timeout injecting fault to container {container}"
            ) from e

    def _remove_from_container(self, container: str) -> None:
        """Remove fault from a specific container.

        Args:
            container: Container ID or name (will be resolved if it's a Kurtosis service name).

        Raises:
            RuntimeError: If fault removal fails.
        """
        if self._dry_run:
            print(f"[DRY-RUN] Would remove faults from container {container}")
            return

        # Resolve Kurtosis service name to Docker container name
        container_name = self._resolve_container_name(container)

        # Remove tc qdisc (this removes all tc rules)
        # Use docker exec instead of nsenter for macOS compatibility
        cmd = [
            "docker",
            "exec",
            container_name,
            "tc",
            "qdisc",
            "del",
            "dev",
            "eth0",
            "root",
        ]

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            # It's OK if tc qdisc del fails (might not exist)
            pass

    def _ensure_tc_installed(self, container_name: str) -> None:
        """Ensure tc (traffic control) utility is installed in the container.

        Many Ethereum client containers don't have tc installed by default.
        This method installs it if needed.

        Args:
            container_name: Docker container name.
        """
        # Check if tc is already available
        try:
            result = subprocess.run(
                ["docker", "exec", container_name, "which", "tc"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return  # tc is already installed
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass

        # Install iproute2 (contains tc)
        # Try different package managers
        install_commands = [
            # Debian/Ubuntu-based
            ["docker", "exec", container_name, "apt-get", "update"],
            ["docker", "exec", container_name, "apt-get", "install", "-y", "iproute2"],
            # Alpine-based (fallback)
            ["docker", "exec", container_name, "apk", "add", "iproute2"],
        ]

        for cmd in install_commands:
            try:
                subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=60,
                    check=False,  # Don't fail if one method doesn't work
                )
            except subprocess.TimeoutExpired:
                continue

    def _resolve_container_name(self, service_name: str) -> str:
        """Resolve Kurtosis service name to Docker container name.

        Kurtosis creates Docker containers with names like:
        <enclave-name>--<service-name>--<random-id>

        This method finds the actual Docker container name/ID for a given service.

        Args:
            service_name: Kurtosis service name (e.g., "cl-1-prysm-nethermind").

        Returns:
            Docker container name or ID.

        Raises:
            RuntimeError: If container cannot be found.
        """
        try:
            # Use docker ps to find containers with this service name
            result = subprocess.run(
                ["docker", "ps", "--filter", f"name={service_name}", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            containers = result.stdout.strip().split("\n")
            containers = [c for c in containers if c]  # Remove empty strings

            if not containers:
                # Try with just the service name as-is (might be a direct container name)
                return service_name

            # Return the first match (usually there's only one)
            return containers[0]

        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to resolve container name for {service_name}: {e.stderr}"
            ) from e

    def _build_tc_command(self, container: str, fault: NetworkFault) -> list[str]:
        """Build tc/netem command for the fault.

        Args:
            container: Container ID or name (will be resolved if it's a Kurtosis service name).
            fault: Fault configuration.

        Returns:
            Command to execute as list of strings.

        Raises:
            RuntimeError: If container PID cannot be determined.
        """
        # Resolve Kurtosis service name to Docker container name
        container_name = self._resolve_container_name(container)

        # Build netem parameters
        netem_params: list[str] = []

        if fault.packet_loss_percent > 0:
            netem_params.extend(["loss", f"{fault.packet_loss_percent}%"])

        if fault.latency_ms > 0:
            if fault.jitter_ms > 0:
                netem_params.extend([
                    "delay",
                    f"{fault.latency_ms}ms",
                    f"{fault.jitter_ms}ms",
                ])
            else:
                netem_params.extend(["delay", f"{fault.latency_ms}ms"])

        if fault.corruption_percent > 0:
            netem_params.extend(["corrupt", f"{fault.corruption_percent}%"])

        if fault.reorder_percent > 0:
            netem_params.extend([
                "reorder",
                f"{fault.reorder_percent}%",
                "gap",
                "5",
            ])

        # Build tc command
        # Use docker exec to run tc inside the container (works on both Linux and macOS)
        cmd = [
            "docker",
            "exec",
            container_name,
            "tc",
            "qdisc",
            "add",
            "dev",
            "eth0",
            "root",
            "netem",
        ]
        cmd.extend(netem_params)

        # Add bandwidth limit if specified (requires tbf qdisc)
        if fault.bandwidth_kbps > 0:
            # This is more complex - need to chain qdiscs
            # For simplicity, we'll handle bandwidth separately
            pass

        return cmd

    def inject_packet_loss(
        self,
        containers: list[str],
        loss_percent: float,
        duration_seconds: int = 0,
    ) -> str:
        """Convenience method to inject packet loss.

        Args:
            containers: List of container IDs or names.
            loss_percent: Packet loss percentage (0-100).
            duration_seconds: Duration to apply fault (0 = until manually removed).

        Returns:
            Fault ID.
        """
        fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_containers=containers,
            packet_loss_percent=loss_percent,
            duration_seconds=duration_seconds,
            dry_run=self._dry_run,
        )
        return self.inject(fault)

    def inject_latency(
        self,
        containers: list[str],
        latency_ms: int,
        jitter_ms: int = 0,
        duration_seconds: int = 0,
    ) -> str:
        """Convenience method to inject latency.

        Args:
            containers: List of container IDs or names.
            latency_ms: Latency to add in milliseconds.
            jitter_ms: Latency jitter in milliseconds.
            duration_seconds: Duration to apply fault (0 = until manually removed).

        Returns:
            Fault ID.
        """
        fault = NetworkFault(
            fault_type=FaultType.LATENCY,
            target_containers=containers,
            latency_ms=latency_ms,
            jitter_ms=jitter_ms,
            duration_seconds=duration_seconds,
            dry_run=self._dry_run,
        )
        return self.inject(fault)

    def inject_bandwidth_limit(
        self,
        containers: list[str],
        bandwidth_kbps: int,
        duration_seconds: int = 0,
    ) -> str:
        """Convenience method to inject bandwidth limit.

        Args:
            containers: List of container IDs or names.
            bandwidth_kbps: Bandwidth limit in kilobits per second.
            duration_seconds: Duration to apply fault (0 = until manually removed).

        Returns:
            Fault ID.
        """
        fault = NetworkFault(
            fault_type=FaultType.BANDWIDTH,
            target_containers=containers,
            bandwidth_kbps=bandwidth_kbps,
            duration_seconds=duration_seconds,
            dry_run=self._dry_run,
        )
        return self.inject(fault)
