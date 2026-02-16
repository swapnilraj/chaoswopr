"""Node-level fault injection using chaos-mesh.

Provides Python client for chaos-mesh Kubernetes CRDs to inject node-level faults:
- PodChaos: pod kill, pod failure, container kill
- StressChaos: CPU stress, memory stress
- IOChaos: disk I/O delays, faults, and corruption

Supports label-based targeting to affect specific client types or roles.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from chaoswopr.safety.audit import AuditLogger


class NodeFaultType(str, Enum):
    """Types of node-level faults that can be injected."""

    POD_KILL = "pod_kill"
    POD_FAILURE = "pod_failure"
    CONTAINER_KILL = "container_kill"
    CPU_STRESS = "cpu_stress"
    MEMORY_STRESS = "memory_stress"
    IO_DELAY = "io_delay"
    IO_FAULT = "io_fault"


@dataclass
class NodeFault:
    """Configuration for a node-level fault using chaos-mesh.

    Attributes:
        fault_type: Type of fault to inject.
        namespace: Kubernetes namespace to target.
        label_selectors: Label selectors for pod targeting (e.g., {"app": "nethermind"}).
        cpu_workers: Number of CPU stress workers.
        cpu_load: CPU load percentage per worker (0-100).
        memory_workers: Number of memory stress workers.
        memory_size: Memory to consume per worker (e.g., "256MB").
        io_delay_ms: I/O delay in milliseconds.
        io_errno: I/O error number to inject.
        duration_seconds: Duration to apply fault (0 = until manually removed).
        dry_run: If True, log actions but don't execute them.
    """

    fault_type: NodeFaultType
    namespace: str = "default"
    label_selectors: dict[str, str] = field(default_factory=dict)
    cpu_workers: int = 1
    cpu_load: int = 100
    memory_workers: int = 1
    memory_size: str = "256MB"
    io_delay_ms: int = 0
    io_errno: int = 0
    duration_seconds: int = 0
    dry_run: bool = False

    def validate(self) -> list[str]:
        """Validate fault configuration.

        Returns:
            List of validation errors. Empty means valid.
        """
        errors: list[str] = []

        if not self.namespace:
            errors.append("namespace cannot be empty")

        if not self.label_selectors:
            errors.append("label_selectors cannot be empty")

        if self.cpu_workers < 1 or self.cpu_workers > 100:
            errors.append("cpu_workers must be between 1 and 100")

        if self.cpu_load < 0 or self.cpu_load > 100:
            errors.append("cpu_load must be between 0 and 100")

        if self.memory_workers < 1 or self.memory_workers > 100:
            errors.append("memory_workers must be between 1 and 100")

        if self.io_delay_ms < 0 or self.io_delay_ms > 60000:
            errors.append("io_delay_ms must be between 0 and 60000")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "fault_type": self.fault_type.value,
            "namespace": self.namespace,
            "label_selectors": self.label_selectors,
            "cpu_workers": self.cpu_workers,
            "cpu_load": self.cpu_load,
            "memory_workers": self.memory_workers,
            "memory_size": self.memory_size,
            "io_delay_ms": self.io_delay_ms,
            "io_errno": self.io_errno,
            "duration_seconds": self.duration_seconds,
            "dry_run": self.dry_run,
        }


class NodeFaultInjector:
    """Injects node-level faults using chaos-mesh.

    Uses chaos-mesh Kubernetes CRDs to inject faults at the node/pod level.
    Requires chaos-mesh to be installed in the target Kubernetes cluster.

    Examples:
        >>> injector = NodeFaultInjector()
        >>> fault = NodeFault(
        ...     fault_type=NodeFaultType.CPU_STRESS,
        ...     namespace="default",
        ...     label_selectors={"app": "nethermind"},
        ...     cpu_workers=2,
        ...     cpu_load=80,
        ... )
        >>> fault_id = injector.inject(fault)
        >>> injector.remove(fault_id)
    """

    def __init__(
        self,
        audit_logger: AuditLogger | None = None,
        dry_run: bool = False,
    ) -> None:
        """Initialize the node fault injector.

        Args:
            audit_logger: Audit logger for recording fault injection actions.
            dry_run: If True, log actions but don't execute them.
        """
        self._audit_logger = audit_logger
        self._dry_run = dry_run
        self._active_faults: dict[str, NodeFault] = {}

    def inject(self, fault: NodeFault) -> str:
        """Inject a node-level fault.

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

        fault_id = f"node-{uuid.uuid4().hex[:8]}"

        # Log to audit system
        if self._audit_logger:
            self._audit_logger.log_event(
                event_type="node_fault_inject",
                details={
                    "fault_id": fault_id,
                    "fault": fault.to_dict(),
                },
            )

        if fault.dry_run or self._dry_run:
            print(f"[DRY-RUN] Would inject {fault.fault_type.value} to {fault.namespace}")
            self._active_faults[fault_id] = fault
            return fault_id

        # Create chaos-mesh CR
        chaos_spec = self._build_chaos_spec(fault_id, fault)

        try:
            self._apply_chaos_spec(chaos_spec)
        except RuntimeError as e:
            if self._audit_logger:
                self._audit_logger.log_event(
                    event_type="node_fault_inject_failed",
                    details={
                        "fault_id": fault_id,
                        "error": str(e),
                    },
                )
            raise

        # Store active fault
        self._active_faults[fault_id] = fault

        return fault_id

    def remove(self, fault_id: str) -> bool:
        """Remove an active node-level fault.

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
                event_type="node_fault_remove",
                details={
                    "fault_id": fault_id,
                    "fault": fault.to_dict(),
                },
            )

        if fault.dry_run or self._dry_run:
            print(f"[DRY-RUN] Would remove {fault.fault_type.value} from {fault.namespace}")
            del self._active_faults[fault_id]
            return True

        # Delete chaos-mesh CR
        try:
            self._delete_chaos_spec(fault_id, fault)
        except RuntimeError:
            # Continue even if delete fails
            pass

        # Remove from active faults
        del self._active_faults[fault_id]

        return True

    def remove_all(self) -> int:
        """Remove all active node-level faults.

        Returns:
            Number of faults removed.
        """
        fault_ids = list(self._active_faults.keys())
        count = 0
        for fault_id in fault_ids:
            if self.remove(fault_id):
                count += 1
        return count

    def list_active(self) -> dict[str, NodeFault]:
        """List all active node-level faults.

        Returns:
            Dictionary mapping fault IDs to fault configurations.
        """
        return dict(self._active_faults)

    def _build_chaos_spec(self, fault_id: str, fault: NodeFault) -> dict[str, Any]:
        """Build chaos-mesh CRD spec for the fault.

        Args:
            fault_id: Unique fault identifier.
            fault: Fault configuration.

        Returns:
            Kubernetes resource specification.
        """
        # Build label selector
        label_selector = {
            "labelSelectors": fault.label_selectors,
        }

        # Build duration
        duration = None
        if fault.duration_seconds > 0:
            duration = f"{fault.duration_seconds}s"

        # Build spec based on fault type
        if fault.fault_type == NodeFaultType.POD_KILL:
            spec = {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "PodChaos",
                "metadata": {
                    "name": fault_id,
                    "namespace": fault.namespace,
                },
                "spec": {
                    "action": "pod-kill",
                    "mode": "all",
                    "selector": label_selector,
                },
            }
            if duration:
                spec["spec"]["duration"] = duration

        elif fault.fault_type == NodeFaultType.POD_FAILURE:
            spec = {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "PodChaos",
                "metadata": {
                    "name": fault_id,
                    "namespace": fault.namespace,
                },
                "spec": {
                    "action": "pod-failure",
                    "mode": "all",
                    "selector": label_selector,
                },
            }
            if duration:
                spec["spec"]["duration"] = duration

        elif fault.fault_type == NodeFaultType.CONTAINER_KILL:
            spec = {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "PodChaos",
                "metadata": {
                    "name": fault_id,
                    "namespace": fault.namespace,
                },
                "spec": {
                    "action": "container-kill",
                    "mode": "all",
                    "selector": label_selector,
                },
            }
            if duration:
                spec["spec"]["duration"] = duration

        elif fault.fault_type == NodeFaultType.CPU_STRESS:
            spec = {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "StressChaos",
                "metadata": {
                    "name": fault_id,
                    "namespace": fault.namespace,
                },
                "spec": {
                    "mode": "all",
                    "selector": label_selector,
                    "stressors": {
                        "cpu": {
                            "workers": fault.cpu_workers,
                            "load": fault.cpu_load,
                        },
                    },
                },
            }
            if duration:
                spec["spec"]["duration"] = duration

        elif fault.fault_type == NodeFaultType.MEMORY_STRESS:
            spec = {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "StressChaos",
                "metadata": {
                    "name": fault_id,
                    "namespace": fault.namespace,
                },
                "spec": {
                    "mode": "all",
                    "selector": label_selector,
                    "stressors": {
                        "memory": {
                            "workers": fault.memory_workers,
                            "size": fault.memory_size,
                        },
                    },
                },
            }
            if duration:
                spec["spec"]["duration"] = duration

        elif fault.fault_type == NodeFaultType.IO_DELAY:
            spec = {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "IOChaos",
                "metadata": {
                    "name": fault_id,
                    "namespace": fault.namespace,
                },
                "spec": {
                    "action": "latency",
                    "mode": "all",
                    "selector": label_selector,
                    "delay": f"{fault.io_delay_ms}ms",
                    "volumePath": "/",
                    "path": "/**/*",
                },
            }
            if duration:
                spec["spec"]["duration"] = duration

        elif fault.fault_type == NodeFaultType.IO_FAULT:
            spec = {
                "apiVersion": "chaos-mesh.org/v1alpha1",
                "kind": "IOChaos",
                "metadata": {
                    "name": fault_id,
                    "namespace": fault.namespace,
                },
                "spec": {
                    "action": "fault",
                    "mode": "all",
                    "selector": label_selector,
                    "errno": fault.io_errno,
                    "volumePath": "/",
                    "path": "/**/*",
                },
            }
            if duration:
                spec["spec"]["duration"] = duration

        else:
            raise ValueError(f"Unsupported fault type: {fault.fault_type}")

        return spec

    def _apply_chaos_spec(self, spec: dict[str, Any]) -> None:
        """Apply chaos-mesh CRD to Kubernetes.

        Args:
            spec: Kubernetes resource specification.

        Raises:
            RuntimeError: If kubectl apply fails.
        """
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            import yaml

            yaml.dump(spec, f)
            spec_file = f.name

        try:
            result = subprocess.run(
                ["kubectl", "apply", "-f", spec_file],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to apply chaos-mesh spec: {e.stderr}"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("Timeout applying chaos-mesh spec") from e
        finally:
            import os

            os.unlink(spec_file)

    def _delete_chaos_spec(self, fault_id: str, fault: NodeFault) -> None:
        """Delete chaos-mesh CRD from Kubernetes.

        Args:
            fault_id: Unique fault identifier.
            fault: Fault configuration.

        Raises:
            RuntimeError: If kubectl delete fails.
        """
        # Determine resource kind
        if fault.fault_type in (
            NodeFaultType.POD_KILL,
            NodeFaultType.POD_FAILURE,
            NodeFaultType.CONTAINER_KILL,
        ):
            kind = "podchaos"
        elif fault.fault_type in (
            NodeFaultType.CPU_STRESS,
            NodeFaultType.MEMORY_STRESS,
        ):
            kind = "stresschaos"
        elif fault.fault_type in (NodeFaultType.IO_DELAY, NodeFaultType.IO_FAULT):
            kind = "iochaos"
        else:
            return

        try:
            subprocess.run(
                ["kubectl", "delete", kind, fault_id, "-n", fault.namespace],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to delete chaos-mesh spec: {e.stderr}"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("Timeout deleting chaos-mesh spec") from e

    def inject_pod_kill(
        self,
        namespace: str,
        label_selectors: dict[str, str],
        duration_seconds: int = 0,
    ) -> str:
        """Convenience method to inject pod kill fault.

        Args:
            namespace: Kubernetes namespace.
            label_selectors: Label selectors for pod targeting.
            duration_seconds: Duration to apply fault.

        Returns:
            Fault ID.
        """
        fault = NodeFault(
            fault_type=NodeFaultType.POD_KILL,
            namespace=namespace,
            label_selectors=label_selectors,
            duration_seconds=duration_seconds,
            dry_run=self._dry_run,
        )
        return self.inject(fault)

    def inject_cpu_stress(
        self,
        namespace: str,
        label_selectors: dict[str, str],
        workers: int = 1,
        load: int = 100,
        duration_seconds: int = 0,
    ) -> str:
        """Convenience method to inject CPU stress fault.

        Args:
            namespace: Kubernetes namespace.
            label_selectors: Label selectors for pod targeting.
            workers: Number of CPU stress workers.
            load: CPU load percentage per worker.
            duration_seconds: Duration to apply fault.

        Returns:
            Fault ID.
        """
        fault = NodeFault(
            fault_type=NodeFaultType.CPU_STRESS,
            namespace=namespace,
            label_selectors=label_selectors,
            cpu_workers=workers,
            cpu_load=load,
            duration_seconds=duration_seconds,
            dry_run=self._dry_run,
        )
        return self.inject(fault)

    def inject_memory_stress(
        self,
        namespace: str,
        label_selectors: dict[str, str],
        workers: int = 1,
        size: str = "256MB",
        duration_seconds: int = 0,
    ) -> str:
        """Convenience method to inject memory stress fault.

        Args:
            namespace: Kubernetes namespace.
            label_selectors: Label selectors for pod targeting.
            workers: Number of memory stress workers.
            size: Memory to consume per worker.
            duration_seconds: Duration to apply fault.

        Returns:
            Fault ID.
        """
        fault = NodeFault(
            fault_type=NodeFaultType.MEMORY_STRESS,
            namespace=namespace,
            label_selectors=label_selectors,
            memory_workers=workers,
            memory_size=size,
            duration_seconds=duration_seconds,
            dry_run=self._dry_run,
        )
        return self.inject(fault)
