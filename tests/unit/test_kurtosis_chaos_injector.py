"""Unit tests for KurtosisChaosInjector."""

import pytest
from unittest.mock import Mock, MagicMock, patch

from chaoswopr.chaos.kurtosis_chaos_injector import (
    KurtosisChaosInjector,
    NetworkFault,
    FaultType,
)
from chaoswopr.infrastructure.testnet.kurtosis_client import KurtosisClient


@pytest.fixture
def mock_kurtosis_client():
    """Create mock KurtosisClient."""
    client = Mock(spec=KurtosisClient)
    client._binary = "/Users/swp/bin/kurtosis-capabilities"
    client.run_package = Mock(return_value={"status": "success"})
    return client


@pytest.fixture
def chaos_injector(mock_kurtosis_client):
    """Create KurtosisChaosInjector instance."""
    return KurtosisChaosInjector(
        kurtosis_client=mock_kurtosis_client,
        enclave_name="test-enclave",
        num_injectors=3,
    )


def test_initialization(chaos_injector, mock_kurtosis_client):
    """Test KurtosisChaosInjector initialization."""
    assert chaos_injector._client == mock_kurtosis_client
    assert chaos_injector._enclave == "test-enclave"
    assert chaos_injector._num_injectors == 3
    assert not chaos_injector.deployed
    assert chaos_injector.injector_services == []


def test_deploy_success(chaos_injector, mock_kurtosis_client):
    """Test successful deployment of chaos injectors."""
    result = chaos_injector.deploy()

    assert result["status"] == "success"
    assert chaos_injector.deployed
    assert len(chaos_injector.injector_services) == 3
    assert chaos_injector.injector_services == [
        "chaos-injector-1",
        "chaos-injector-2",
        "chaos-injector-3",
    ]

    # Verify run_package was called correctly
    mock_kurtosis_client.run_package.assert_called_once()
    call_args = mock_kurtosis_client.run_package.call_args[1]
    assert call_args["enclave_name"] == "test-enclave"
    assert call_args["args"]["num_injectors"] == 3


def test_deploy_already_deployed(chaos_injector):
    """Test deploying when already deployed."""
    # First deployment
    result1 = chaos_injector.deploy()
    assert result1["status"] == "success"

    # Second deployment
    result2 = chaos_injector.deploy()
    assert result2["status"] == "already_deployed"


def test_deploy_failure(mock_kurtosis_client):
    """Test deployment failure handling."""
    mock_kurtosis_client.run_package.side_effect = Exception("Deployment failed")

    injector = KurtosisChaosInjector(
        kurtosis_client=mock_kurtosis_client,
        enclave_name="test-enclave",
        num_injectors=1,
    )

    with pytest.raises(RuntimeError, match="Chaos injector deployment failed"):
        injector.deploy()

    assert not injector.deployed


@patch("subprocess.run")
def test_inject_fault_packet_loss(mock_subprocess, chaos_injector):
    """Test injecting packet loss fault."""
    # Deploy first
    chaos_injector.deploy()

    # Mock successful subprocess execution
    mock_subprocess.return_value = Mock(returncode=0, stdout="", stderr="")

    fault = NetworkFault(
        fault_type=FaultType.PACKET_LOSS,
        loss_percent=20.0,
    )

    success = chaos_injector.inject_fault("test-service", fault)

    assert success
    mock_subprocess.assert_called_once()

    # Verify command contains correct tc syntax
    call_args = mock_subprocess.call_args[0][0]
    command_str = " ".join(call_args)
    assert "tc" in command_str
    assert "netem" in command_str
    assert "loss 20.0%" in command_str


@patch("subprocess.run")
def test_inject_fault_latency(mock_subprocess, chaos_injector):
    """Test injecting latency fault."""
    chaos_injector.deploy()

    mock_subprocess.return_value = Mock(returncode=0, stdout="", stderr="")

    fault = NetworkFault(
        fault_type=FaultType.LATENCY,
        latency_ms=100,
        jitter_ms=20,
    )

    success = chaos_injector.inject_fault("test-service", fault)

    assert success

    # Verify command
    call_args = mock_subprocess.call_args[0][0]
    command_str = " ".join(call_args)
    assert "delay 100ms" in command_str
    assert "20ms" in command_str


@patch("subprocess.run")
def test_inject_fault_not_deployed(mock_subprocess, chaos_injector):
    """Test injecting fault when not deployed."""
    fault = NetworkFault(
        fault_type=FaultType.PACKET_LOSS,
        loss_percent=10.0,
    )

    with pytest.raises(RuntimeError, match="Chaos injectors not deployed yet"):
        chaos_injector.inject_fault("test-service", fault)

    mock_subprocess.assert_not_called()


@patch("subprocess.run")
def test_inject_fault_command_failure(mock_subprocess, chaos_injector):
    """Test fault injection command failure."""
    chaos_injector.deploy()

    # Mock subprocess failure
    from subprocess import CalledProcessError
    mock_subprocess.side_effect = CalledProcessError(
        returncode=1,
        cmd=["tc"],
        stderr="Operation not permitted",
    )

    fault = NetworkFault(
        fault_type=FaultType.PACKET_LOSS,
        loss_percent=10.0,
    )

    with pytest.raises(RuntimeError, match="Fault injection failed"):
        chaos_injector.inject_fault("test-service", fault)


@patch("subprocess.run")
def test_clear_faults(mock_subprocess, chaos_injector):
    """Test clearing faults."""
    chaos_injector.deploy()

    mock_subprocess.return_value = Mock(returncode=0, stdout="", stderr="")

    success = chaos_injector.clear_faults()

    assert success
    # Should be called once per injector
    assert mock_subprocess.call_count == 3


@patch("subprocess.run")
def test_get_fault_status(mock_subprocess, chaos_injector):
    """Test getting fault status."""
    chaos_injector.deploy()

    mock_subprocess.return_value = Mock(
        returncode=0,
        stdout="qdisc netem 8001: root refcnt 2 limit 1000 loss 10%\n",
        stderr="",
    )

    status = chaos_injector.get_fault_status("test-service")

    assert status["status"] == "active"
    assert "netem" in status["rules"]
    assert status["injector"] == "chaos-injector-1"


def test_build_tc_command_packet_loss(chaos_injector):
    """Test building tc command for packet loss."""
    fault = NetworkFault(
        fault_type=FaultType.PACKET_LOSS,
        loss_percent=15.0,
    )

    command = chaos_injector._build_tc_command(fault)

    assert "tc qdisc add dev eth0 root netem" in command
    assert "loss 15.0%" in command


def test_build_tc_command_latency(chaos_injector):
    """Test building tc command for latency."""
    fault = NetworkFault(
        fault_type=FaultType.LATENCY,
        latency_ms=50,
        jitter_ms=10,
    )

    command = chaos_injector._build_tc_command(fault)

    assert "delay 50ms" in command
    assert "10ms" in command


def test_build_tc_command_bandwidth(chaos_injector):
    """Test building tc command for bandwidth limiting."""
    fault = NetworkFault(
        fault_type=FaultType.BANDWIDTH,
        bandwidth_kbps=1000,
    )

    command = chaos_injector._build_tc_command(fault)

    assert "tc qdisc add dev eth0 root tbf" in command
    assert "rate 1000kbit" in command


def test_build_tc_command_corruption(chaos_injector):
    """Test building tc command for corruption."""
    fault = NetworkFault(
        fault_type=FaultType.CORRUPTION,
        corruption_percent=3.0,
    )

    command = chaos_injector._build_tc_command(fault)

    assert "corrupt 3.0%" in command


def test_build_tc_command_duplication(chaos_injector):
    """Test building tc command for duplication."""
    fault = NetworkFault(
        fault_type=FaultType.DUPLICATION,
        duplication_percent=5.0,
    )

    command = chaos_injector._build_tc_command(fault)

    assert "duplicate 5.0%" in command


def test_injector_services_property(chaos_injector):
    """Test injector_services property."""
    assert chaos_injector.injector_services == []

    chaos_injector.deploy()

    assert len(chaos_injector.injector_services) == 3


def test_deployed_property(chaos_injector):
    """Test deployed property."""
    assert not chaos_injector.deployed

    chaos_injector.deploy()

    assert chaos_injector.deployed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
