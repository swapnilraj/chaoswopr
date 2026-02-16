"""Unit tests for node-level fault injection."""

from __future__ import annotations

import pytest

from chaoswopr.chaos.node_faults import (
    NodeFault,
    NodeFaultInjector,
    NodeFaultType,
)


class TestNodeFault:
    """Test NodeFault configuration."""

    def test_valid_pod_kill_fault(self) -> None:
        """Valid pod kill fault passes validation."""
        fault = NodeFault(
            fault_type=NodeFaultType.POD_KILL,
            namespace="default",
            label_selectors={"app": "nethermind"},
        )
        errors = fault.validate()
        assert errors == []

    def test_valid_cpu_stress_fault(self) -> None:
        """Valid CPU stress fault passes validation."""
        fault = NodeFault(
            fault_type=NodeFaultType.CPU_STRESS,
            namespace="default",
            label_selectors={"app": "nethermind"},
            cpu_workers=2,
            cpu_load=80,
        )
        errors = fault.validate()
        assert errors == []

    def test_valid_memory_stress_fault(self) -> None:
        """Valid memory stress fault passes validation."""
        fault = NodeFault(
            fault_type=NodeFaultType.MEMORY_STRESS,
            namespace="default",
            label_selectors={"app": "lighthouse"},
            memory_workers=2,
            memory_size="512MB",
        )
        errors = fault.validate()
        assert errors == []

    def test_empty_namespace(self) -> None:
        """Empty namespace fails validation."""
        fault = NodeFault(
            fault_type=NodeFaultType.POD_KILL,
            namespace="",
            label_selectors={"app": "nethermind"},
        )
        errors = fault.validate()
        assert "namespace cannot be empty" in errors

    def test_empty_label_selectors(self) -> None:
        """Empty label selectors fails validation."""
        fault = NodeFault(
            fault_type=NodeFaultType.POD_KILL,
            namespace="default",
            label_selectors={},
        )
        errors = fault.validate()
        assert "label_selectors cannot be empty" in errors

    def test_invalid_cpu_workers(self) -> None:
        """Invalid CPU workers fails validation."""
        fault = NodeFault(
            fault_type=NodeFaultType.CPU_STRESS,
            namespace="default",
            label_selectors={"app": "nethermind"},
            cpu_workers=0,
        )
        errors = fault.validate()
        assert any("cpu_workers" in e for e in errors)

    def test_invalid_cpu_load(self) -> None:
        """Invalid CPU load fails validation."""
        fault = NodeFault(
            fault_type=NodeFaultType.CPU_STRESS,
            namespace="default",
            label_selectors={"app": "nethermind"},
            cpu_load=150,
        )
        errors = fault.validate()
        assert any("cpu_load" in e for e in errors)

    def test_to_dict(self) -> None:
        """to_dict returns proper dictionary."""
        fault = NodeFault(
            fault_type=NodeFaultType.POD_KILL,
            namespace="default",
            label_selectors={"app": "nethermind"},
        )
        data = fault.to_dict()
        assert data["fault_type"] == "pod_kill"
        assert data["namespace"] == "default"
        assert data["label_selectors"] == {"app": "nethermind"}


class TestNodeFaultInjector:
    """Test NodeFaultInjector."""

    @pytest.fixture
    def injector(self) -> NodeFaultInjector:
        """Create a node fault injector in dry-run mode."""
        return NodeFaultInjector(dry_run=True)

    def test_inject_valid_fault(self, injector: NodeFaultInjector) -> None:
        """Inject valid fault returns fault ID."""
        fault = NodeFault(
            fault_type=NodeFaultType.POD_KILL,
            namespace="default",
            label_selectors={"app": "nethermind"},
            dry_run=True,
        )
        fault_id = injector.inject(fault)
        assert fault_id.startswith("node-")
        assert len(fault_id) == 13  # "node-" + 8 hex chars

    def test_inject_invalid_fault_raises(
        self, injector: NodeFaultInjector
    ) -> None:
        """Inject invalid fault raises ValueError."""
        fault = NodeFault(
            fault_type=NodeFaultType.POD_KILL,
            namespace="",
            label_selectors={},
        )
        with pytest.raises(ValueError, match="Invalid fault configuration"):
            injector.inject(fault)

    def test_remove_existing_fault(self, injector: NodeFaultInjector) -> None:
        """Remove existing fault returns True."""
        fault = NodeFault(
            fault_type=NodeFaultType.POD_KILL,
            namespace="default",
            label_selectors={"app": "nethermind"},
            dry_run=True,
        )
        fault_id = injector.inject(fault)
        assert injector.remove(fault_id) is True

    def test_remove_nonexistent_fault(
        self, injector: NodeFaultInjector
    ) -> None:
        """Remove nonexistent fault returns False."""
        assert injector.remove("node-12345678") is False

    def test_list_active_empty(self, injector: NodeFaultInjector) -> None:
        """List active faults when none exist."""
        active = injector.list_active()
        assert active == {}

    def test_list_active_with_faults(
        self, injector: NodeFaultInjector
    ) -> None:
        """List active faults with injected faults."""
        fault1 = NodeFault(
            fault_type=NodeFaultType.POD_KILL,
            namespace="default",
            label_selectors={"app": "nethermind"},
            dry_run=True,
        )
        fault2 = NodeFault(
            fault_type=NodeFaultType.CPU_STRESS,
            namespace="default",
            label_selectors={"app": "lighthouse"},
            dry_run=True,
        )
        fault_id1 = injector.inject(fault1)
        fault_id2 = injector.inject(fault2)

        active = injector.list_active()
        assert len(active) == 2
        assert fault_id1 in active
        assert fault_id2 in active

    def test_remove_all(self, injector: NodeFaultInjector) -> None:
        """Remove all faults."""
        fault1 = NodeFault(
            fault_type=NodeFaultType.POD_KILL,
            namespace="default",
            label_selectors={"app": "nethermind"},
            dry_run=True,
        )
        fault2 = NodeFault(
            fault_type=NodeFaultType.CPU_STRESS,
            namespace="default",
            label_selectors={"app": "lighthouse"},
            dry_run=True,
        )
        injector.inject(fault1)
        injector.inject(fault2)

        count = injector.remove_all()
        assert count == 2
        assert injector.list_active() == {}

    def test_inject_pod_kill_convenience(
        self, injector: NodeFaultInjector
    ) -> None:
        """Convenience method inject_pod_kill works."""
        fault_id = injector.inject_pod_kill(
            namespace="default",
            label_selectors={"app": "nethermind"},
        )
        assert fault_id.startswith("node-")
        assert len(injector.list_active()) == 1

    def test_inject_cpu_stress_convenience(
        self, injector: NodeFaultInjector
    ) -> None:
        """Convenience method inject_cpu_stress works."""
        fault_id = injector.inject_cpu_stress(
            namespace="default",
            label_selectors={"app": "nethermind"},
            workers=2,
            load=80,
        )
        assert fault_id.startswith("node-")
        assert len(injector.list_active()) == 1

    def test_inject_memory_stress_convenience(
        self, injector: NodeFaultInjector
    ) -> None:
        """Convenience method inject_memory_stress works."""
        fault_id = injector.inject_memory_stress(
            namespace="default",
            label_selectors={"app": "lighthouse"},
            workers=1,
            size="512MB",
        )
        assert fault_id.startswith("node-")
        assert len(injector.list_active()) == 1

    def test_pod_failure_fault(self, injector: NodeFaultInjector) -> None:
        """Pod failure fault validates and injects."""
        fault = NodeFault(
            fault_type=NodeFaultType.POD_FAILURE,
            namespace="default",
            label_selectors={"app": "prysm"},
            dry_run=True,
        )
        errors = fault.validate()
        assert errors == []
        fault_id = injector.inject(fault)
        assert fault_id.startswith("node-")

    def test_container_kill_fault(self, injector: NodeFaultInjector) -> None:
        """Container kill fault validates and injects."""
        fault = NodeFault(
            fault_type=NodeFaultType.CONTAINER_KILL,
            namespace="default",
            label_selectors={"app": "geth"},
            dry_run=True,
        )
        errors = fault.validate()
        assert errors == []
        fault_id = injector.inject(fault)
        assert fault_id.startswith("node-")

    def test_io_delay_fault(self, injector: NodeFaultInjector) -> None:
        """I/O delay fault validates and injects."""
        fault = NodeFault(
            fault_type=NodeFaultType.IO_DELAY,
            namespace="default",
            label_selectors={"app": "besu"},
            io_delay_ms=100,
            dry_run=True,
        )
        errors = fault.validate()
        assert errors == []
        fault_id = injector.inject(fault)
        assert fault_id.startswith("node-")

    def test_io_fault_fault(self, injector: NodeFaultInjector) -> None:
        """I/O fault validates and injects."""
        fault = NodeFault(
            fault_type=NodeFaultType.IO_FAULT,
            namespace="default",
            label_selectors={"app": "teku"},
            io_errno=5,
            dry_run=True,
        )
        errors = fault.validate()
        assert errors == []
        fault_id = injector.inject(fault)
        assert fault_id.startswith("node-")

    def test_multiple_label_selectors(
        self, injector: NodeFaultInjector
    ) -> None:
        """Fault with multiple label selectors."""
        fault = NodeFault(
            fault_type=NodeFaultType.POD_KILL,
            namespace="default",
            label_selectors={"app": "nethermind", "role": "validator"},
            dry_run=True,
        )
        errors = fault.validate()
        assert errors == []
        fault_id = injector.inject(fault)
        active = injector.list_active()
        assert len(active[fault_id].label_selectors) == 2

    def test_cpu_stress_with_custom_params(
        self, injector: NodeFaultInjector
    ) -> None:
        """CPU stress with custom workers and load."""
        fault = NodeFault(
            fault_type=NodeFaultType.CPU_STRESS,
            namespace="default",
            label_selectors={"app": "nethermind"},
            cpu_workers=4,
            cpu_load=50,
            dry_run=True,
        )
        errors = fault.validate()
        assert errors == []
        fault_id = injector.inject(fault)
        active = injector.list_active()
        assert active[fault_id].cpu_workers == 4
        assert active[fault_id].cpu_load == 50
