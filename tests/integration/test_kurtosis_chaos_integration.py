"""Integration tests for Kurtosis chaos injection with NET_ADMIN capabilities.

Tests the full integration of:
- Kurtosis client with capabilities-enabled build
- Chaos injector package deployment
- Network fault injection using tc/netem
- Fault status monitoring and cleanup
"""

import pytest
import subprocess
import time

from chaoswopr.chaos.kurtosis_chaos_injector import (
    KurtosisChaosInjector,
    NetworkFault,
    FaultType,
)
from chaoswopr.infrastructure.testnet.kurtosis_client import (
    KurtosisClient,
    KurtosisBackend,
)


@pytest.fixture(scope="module")
def kurtosis_client():
    """Create KurtosisClient with capabilities support."""
    client = KurtosisClient(
        backend=KurtosisBackend.DOCKER,
        kurtosis_binary="/Users/swp/bin/kurtosis-capabilities",
        dry_run=False,
    )

    # Ensure engine is running
    if not client.is_engine_running():
        assert client.start_engine(), "Failed to start Kurtosis engine"

    yield client

    # Cleanup
    client.clean_all()


@pytest.fixture(scope="module")
def test_enclave(kurtosis_client):
    """Create a test enclave."""
    enclave_name = "chaos-integration-test"

    # Clean up any existing enclave
    kurtosis_client.destroy_enclave(enclave_name)

    # Create new enclave
    enclave = kurtosis_client.create_enclave(enclave_name)
    assert enclave.name == enclave_name

    yield enclave_name

    # Cleanup
    kurtosis_client.destroy_enclave(enclave_name)


@pytest.fixture(scope="module")
def chaos_injector(kurtosis_client, test_enclave):
    """Deploy chaos injector to test enclave."""
    injector = KurtosisChaosInjector(
        kurtosis_client=kurtosis_client,
        enclave_name=test_enclave,
        num_injectors=1,
    )

    result = injector.deploy()
    assert result["status"] == "success"
    assert injector.deployed

    yield injector

    # Cleanup faults
    injector.clear_faults()


def test_kurtosis_client_available(kurtosis_client):
    """Test that Kurtosis CLI is available."""
    assert kurtosis_client.is_available(), "Kurtosis CLI not available"


def test_engine_running(kurtosis_client):
    """Test that Kurtosis engine is running."""
    assert kurtosis_client.is_engine_running(), "Kurtosis engine not running"


def test_enclave_created(kurtosis_client, test_enclave):
    """Test that test enclave was created."""
    info = kurtosis_client.get_enclave_info(test_enclave)
    assert info is not None
    assert info.name == test_enclave


def test_chaos_injector_deployed(chaos_injector):
    """Test that chaos injector was deployed successfully."""
    assert chaos_injector.deployed
    assert len(chaos_injector.injector_services) == 1
    assert chaos_injector.injector_services[0] == "chaos-injector-1"


def test_injector_has_net_admin(kurtosis_client, test_enclave):
    """Test that injector container has NET_ADMIN capability."""
    # Get container ID for chaos-injector-1
    cmd = [
        "docker",
        "ps",
        "--filter",
        "name=chaos-injector-1",
        "--format",
        "{{.ID}}",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=10,
    )

    container_id = result.stdout.strip()
    assert container_id, "Chaos injector container not found"

    # Check capabilities
    cmd = [
        "docker",
        "inspect",
        container_id,
        "--format",
        "{{.HostConfig.CapAdd}}",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=10,
    )

    capabilities = result.stdout.strip()
    assert "NET_ADMIN" in capabilities, f"NET_ADMIN not in capabilities: {capabilities}"


def test_inject_packet_loss(chaos_injector):
    """Test injecting packet loss fault."""
    fault = NetworkFault(
        fault_type=FaultType.PACKET_LOSS,
        loss_percent=10.0,
    )

    success = chaos_injector.inject_fault(
        target_service="chaos-injector-1",
        fault=fault,
    )

    assert success, "Fault injection failed"

    # Wait for rule to apply
    time.sleep(1)

    # Verify fault is active
    status = chaos_injector.get_fault_status("chaos-injector-1")
    assert status["status"] == "active"
    assert "netem" in status["rules"]
    assert "loss 10%" in status["rules"]


def test_inject_latency(chaos_injector):
    """Test injecting latency fault."""
    # Clear previous faults first
    chaos_injector.clear_faults()
    time.sleep(1)

    fault = NetworkFault(
        fault_type=FaultType.LATENCY,
        latency_ms=100,
        jitter_ms=20,
    )

    success = chaos_injector.inject_fault(
        target_service="chaos-injector-1",
        fault=fault,
    )

    assert success, "Latency injection failed"

    # Wait for rule to apply
    time.sleep(1)

    # Verify fault is active
    status = chaos_injector.get_fault_status("chaos-injector-1")
    assert status["status"] == "active"
    assert "delay 100ms" in status["rules"]
    assert "20ms" in status["rules"]


def test_clear_faults(chaos_injector):
    """Test clearing all faults."""
    # First inject a fault
    fault = NetworkFault(
        fault_type=FaultType.PACKET_LOSS,
        loss_percent=5.0,
    )

    chaos_injector.inject_fault(
        target_service="chaos-injector-1",
        fault=fault,
    )

    time.sleep(1)

    # Verify fault is active
    status = chaos_injector.get_fault_status("chaos-injector-1")
    assert status["status"] == "active"

    # Clear faults
    success = chaos_injector.clear_faults()
    assert success

    time.sleep(1)

    # Verify faults cleared
    status = chaos_injector.get_fault_status("chaos-injector-1")
    # After clearing, should have default qdisc (not netem)
    assert "netem" not in status["rules"]


def test_tc_command_execution(kurtosis_client, test_enclave):
    """Test direct tc command execution via Kurtosis service exec."""
    # Test basic tc command
    cmd = [
        kurtosis_client._binary,
        "service",
        "exec",
        test_enclave,
        "chaos-injector-1",
        "tc qdisc show dev eth0",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )

    assert result.returncode == 0
    assert len(result.stdout) > 0


@pytest.mark.parametrize(
    "fault_config",
    [
        {"fault_type": FaultType.PACKET_LOSS, "loss_percent": 15.0},
        {"fault_type": FaultType.LATENCY, "latency_ms": 50},
        {"fault_type": FaultType.CORRUPTION, "corruption_percent": 2.0},
        {"fault_type": FaultType.DUPLICATION, "duplication_percent": 5.0},
    ],
)
def test_multiple_fault_types(chaos_injector, fault_config):
    """Test injecting different fault types."""
    # Clear previous faults
    chaos_injector.clear_faults()
    time.sleep(1)

    fault = NetworkFault(**fault_config)

    success = chaos_injector.inject_fault(
        target_service="chaos-injector-1",
        fault=fault,
    )

    assert success, f"Failed to inject {fault.fault_type.value}"

    time.sleep(1)

    # Verify fault is active
    status = chaos_injector.get_fault_status("chaos-injector-1")
    assert status["status"] == "active"


def test_redeployment_protection(kurtosis_client, test_enclave):
    """Test that redeploying chaos injector is prevented."""
    injector = KurtosisChaosInjector(
        kurtosis_client=kurtosis_client,
        enclave_name=test_enclave,
        num_injectors=1,
    )

    # First deployment
    result1 = injector.deploy()
    assert result1["status"] == "success"

    # Second deployment should be prevented
    result2 = injector.deploy()
    assert result2["status"] == "already_deployed"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
