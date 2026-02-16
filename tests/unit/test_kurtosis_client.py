"""Unit tests for the Kurtosis client wrapper."""

from __future__ import annotations

import pytest

from chaoswopr.infrastructure.testnet.kurtosis_client import (
    EnclaveInfo,
    EnclaveState,
    KurtosisBackend,
    KurtosisClient,
    KurtosisError,
    PortSpec,
    ServiceInfo,
)


class TestKurtosisBackend:
    """Tests for KurtosisBackend enum."""

    def test_backends(self) -> None:
        assert KurtosisBackend.DOCKER.value == "docker"
        assert KurtosisBackend.KUBERNETES.value == "kubernetes"


class TestEnclaveState:
    """Tests for EnclaveState enum."""

    def test_states(self) -> None:
        assert EnclaveState.RUNNING.value == "running"
        assert EnclaveState.STOPPED.value == "stopped"


class TestPortSpec:
    """Tests for PortSpec dataclass."""

    def test_create_port(self) -> None:
        port = PortSpec(number=8545, transport_protocol="TCP", url="http://127.0.0.1:32771")
        assert port.number == 8545
        assert port.url == "http://127.0.0.1:32771"

    def test_to_dict(self) -> None:
        port = PortSpec(number=4000, transport_protocol="TCP")
        d = port.to_dict()
        assert d["number"] == 4000
        assert d["transport_protocol"] == "TCP"


class TestEnclaveInfo:
    """Tests for EnclaveInfo dataclass."""

    def test_create_info(self) -> None:
        info = EnclaveInfo(
            enclave_id="test-001",
            name="test-enclave",
            state=EnclaveState.RUNNING,
        )
        assert info.enclave_id == "test-001"
        assert info.state == EnclaveState.RUNNING

    def test_to_dict(self) -> None:
        info = EnclaveInfo(
            enclave_id="test-001",
            name="test",
            state=EnclaveState.RUNNING,
        )
        d = info.to_dict()
        assert d["state"] == "running"
        assert d["name"] == "test"


class TestServiceInfo:
    """Tests for ServiceInfo dataclass."""

    def test_create_info(self) -> None:
        info = ServiceInfo(
            name="el-1-nethermind",
            uuid="abc123",
            status="running",
            ports={
                "rpc": PortSpec(number=8545),
                "ws": PortSpec(number=8546),
            },
            ip_address="10.0.0.5",
        )
        assert info.name == "el-1-nethermind"
        assert info.get_host_port("rpc") == 8545

    def test_get_port(self) -> None:
        info = ServiceInfo(
            name="test",
            uuid="abc",
            status="running",
            ports={"http": PortSpec(number=4000, url="http://127.0.0.1:32771")},
        )
        port = info.get_port("http")
        assert port is not None
        assert port.number == 4000

    def test_get_port_missing(self) -> None:
        info = ServiceInfo(name="test", uuid="abc", status="running")
        assert info.get_port("nonexistent") is None
        assert info.get_host_port("nonexistent") is None
        assert info.get_url("nonexistent") is None

    def test_get_url(self) -> None:
        info = ServiceInfo(
            name="test",
            uuid="abc",
            status="running",
            ports={"http": PortSpec(number=4000, url="http://127.0.0.1:32771")},
        )
        assert info.get_url("http") == "http://127.0.0.1:32771"

    def test_to_dict(self) -> None:
        info = ServiceInfo(
            name="test",
            uuid="abc",
            status="running",
            ports={"http": PortSpec(number=4000)},
        )
        d = info.to_dict()
        assert d["name"] == "test"
        assert d["status"] == "running"
        assert d["ports"]["http"]["number"] == 4000


class TestKurtosisClientDryRun:
    """Tests for KurtosisClient in dry-run mode."""

    @pytest.fixture
    def client(self) -> KurtosisClient:
        return KurtosisClient(dry_run=True)

    def test_is_available(self, client: KurtosisClient) -> None:
        assert client.is_available() is True

    def test_dry_run_property(self, client: KurtosisClient) -> None:
        assert client.dry_run is True

    def test_backend(self, client: KurtosisClient) -> None:
        assert client.backend == KurtosisBackend.DOCKER

    def test_is_engine_running(self, client: KurtosisClient) -> None:
        assert client.is_engine_running() is True

    def test_start_engine(self, client: KurtosisClient) -> None:
        assert client.start_engine() is True

    def test_create_enclave(self, client: KurtosisClient) -> None:
        info = client.create_enclave("test-enclave")
        assert info.name == "test-enclave"
        assert info.state == EnclaveState.RUNNING

    def test_destroy_enclave(self, client: KurtosisClient) -> None:
        result = client.destroy_enclave("test-enclave")
        assert result is True

    def test_get_enclave_info(self, client: KurtosisClient) -> None:
        info = client.get_enclave_info("test-enclave")
        assert info is not None
        assert info.name == "test-enclave"

    def test_list_enclaves(self, client: KurtosisClient) -> None:
        enclaves = client.list_enclaves()
        assert isinstance(enclaves, list)

    def test_run_package(self, client: KurtosisClient) -> None:
        result = client.run_package(
            "test-enclave",
            "github.com/ethpandaops/ethereum-package",
            args={"participants": []},
        )
        assert result["status"] == "success"
        assert result["enclave"] == "test-enclave"

    def test_get_services(self, client: KurtosisClient) -> None:
        services = client.get_services("test-enclave")
        assert isinstance(services, list)

    def test_get_service_ports(self, client: KurtosisClient) -> None:
        ports = client.get_service_ports("test-enclave", "el-1-geth")
        assert isinstance(ports, dict)

    def test_find_beacon_services(self, client: KurtosisClient) -> None:
        services = client.find_beacon_services("test-enclave")
        assert isinstance(services, list)

    def test_find_execution_services(self, client: KurtosisClient) -> None:
        services = client.find_execution_services("test-enclave")
        assert isinstance(services, list)

    def test_clean_all(self, client: KurtosisClient) -> None:
        assert client.clean_all() is True

    def test_kubernetes_backend(self) -> None:
        client = KurtosisClient(backend=KurtosisBackend.KUBERNETES, dry_run=True)
        assert client.backend == KurtosisBackend.KUBERNETES


class TestKurtosisError:
    """Tests for KurtosisError exception."""

    def test_error_message(self) -> None:
        err = KurtosisError("test error", command="kurtosis run", output="stderr text")
        assert str(err) == "test error"
        assert err.command == "kurtosis run"
        assert err.output == "stderr text"


class TestParseEnclaveInspect:
    """Tests for _parse_enclave_inspect static method."""

    def test_parse_services_from_inspect_output(self) -> None:
        output = """
Name:           test-enclave
UUID:           abc123
Status:         RUNNING
Creation Time:  2024-01-15

========================================== User Services ==========================================
UUID           Name                          Ports                                                           Status
abc12345       cl-1-lighthouse-nethermind     http: 4000/tcp -> http://127.0.0.1:32771                       RUNNING
def67890       el-1-nethermind-lighthouse     rpc: 8545/tcp -> http://127.0.0.1:32772                        RUNNING
ghi11111       cl-2-prysm-geth               http: 3500/tcp -> http://127.0.0.1:32773                       RUNNING
"""
        services = KurtosisClient._parse_enclave_inspect(output)
        assert len(services) >= 2

        # Check first service
        names = [s.name for s in services]
        assert any("cl-1-lighthouse" in n for n in names)
        assert any("el-1-nethermind" in n for n in names)

    def test_parse_service_line_with_ports(self) -> None:
        line = "abc12345   cl-1-lighthouse-nethermind   http: 4000/tcp -> http://127.0.0.1:32771   RUNNING"
        service = KurtosisClient._parse_service_line(line)
        assert service is not None
        assert service.name == "cl-1-lighthouse-nethermind"
        assert service.uuid == "abc12345"
        assert "http" in service.ports
        assert service.ports["http"].number == 4000
        assert service.ports["http"].url == "http://127.0.0.1:32771"

    def test_parse_service_line_simple_port(self) -> None:
        line = "xyz789   validator-1   metrics: 8080/tcp   RUNNING"
        service = KurtosisClient._parse_service_line(line)
        assert service is not None
        assert service.name == "validator-1"
        assert "metrics" in service.ports
        assert service.ports["metrics"].number == 8080

    def test_parse_service_line_too_short(self) -> None:
        service = KurtosisClient._parse_service_line("name  uuid")
        assert service is None

    def test_parse_empty_output(self) -> None:
        services = KurtosisClient._parse_enclave_inspect("")
        assert services == []

    def test_parse_output_no_services_section(self) -> None:
        output = """
Name:           test-enclave
UUID:           abc123
Status:         RUNNING
"""
        services = KurtosisClient._parse_enclave_inspect(output)
        assert services == []


class TestParseEnclaveList:
    """Tests for _parse_enclave_list static method."""

    def test_parse_enclave_list(self) -> None:
        output = """
UUID           Name              Status     Created
abc12345678    test-enclave-1    RUNNING    2024-01-15
def90123456    test-enclave-2    STOPPED    2024-01-14
"""
        enclaves = KurtosisClient._parse_enclave_list(output)
        assert len(enclaves) == 2
        assert enclaves[0].name == "test-enclave-1"
        assert enclaves[0].state == EnclaveState.RUNNING
        assert enclaves[1].name == "test-enclave-2"
        assert enclaves[1].state == EnclaveState.STOPPED

    def test_parse_empty_list(self) -> None:
        output = """
UUID           Name              Status     Created
"""
        enclaves = KurtosisClient._parse_enclave_list(output)
        assert enclaves == []

    def test_parse_no_header(self) -> None:
        enclaves = KurtosisClient._parse_enclave_list("some random text")
        assert enclaves == []
