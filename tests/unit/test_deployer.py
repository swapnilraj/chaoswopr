"""Unit tests for the testnet deployer."""

from __future__ import annotations

import pytest

from chaoswopr.infrastructure.testnet.client_config import ClientConfig
from chaoswopr.infrastructure.testnet.deployer import (
    DeploymentResult,
    DeploymentState,
    TestnetDeployer,
)
from chaoswopr.infrastructure.testnet.ethereum_package import EthereumPackageConfig
from chaoswopr.infrastructure.testnet.kurtosis_client import KurtosisClient


class TestDeploymentState:
    """Tests for DeploymentState enum."""

    def test_states(self) -> None:
        assert DeploymentState.NOT_STARTED.value == "not_started"
        assert DeploymentState.RUNNING.value == "running"
        assert DeploymentState.FAILED.value == "failed"
        assert DeploymentState.DESTROYED.value == "destroyed"


class TestDeploymentResult:
    """Tests for DeploymentResult."""

    def test_success_when_running(self) -> None:
        result = DeploymentResult(
            state=DeploymentState.RUNNING,
            enclave_name="test",
        )
        assert result.success is True

    def test_failure_when_failed(self) -> None:
        result = DeploymentResult(
            state=DeploymentState.FAILED,
            enclave_name="test",
            error_message="something went wrong",
        )
        assert result.success is False

    def test_to_dict(self) -> None:
        result = DeploymentResult(
            state=DeploymentState.RUNNING,
            enclave_name="test",
        )
        d = result.to_dict()
        assert d["state"] == "running"
        assert d["success"] is True
        assert d["enclave_name"] == "test"


class TestTestnetDeployer:
    """Tests for the TestnetDeployer."""

    @pytest.fixture
    def deployer(self) -> TestnetDeployer:
        """Create a deployer with dry-run Kurtosis client."""
        return TestnetDeployer(
            kurtosis_client=KurtosisClient(dry_run=True),
            enclave_name="test-enclave",
        )

    def test_initial_state(self, deployer: TestnetDeployer) -> None:
        assert deployer.state == DeploymentState.NOT_STARTED
        assert deployer.enclave_name == "test-enclave"

    def test_deploy_success(self, deployer: TestnetDeployer) -> None:
        result = deployer.deploy()
        assert result.success
        assert result.state == DeploymentState.RUNNING
        assert deployer.state == DeploymentState.RUNNING

    def test_deploy_with_custom_config(self) -> None:
        config = EthereumPackageConfig(
            client_config=ClientConfig(node_count=100),
        )
        deployer = TestnetDeployer(
            kurtosis_client=KurtosisClient(dry_run=True),
            package_config=config,
            enclave_name="custom-test",
        )
        result = deployer.deploy()
        assert result.success

    def test_deploy_invalid_config_fails(self) -> None:
        config = EthereumPackageConfig(
            client_config=ClientConfig(node_count=0),
        )
        deployer = TestnetDeployer(
            kurtosis_client=KurtosisClient(dry_run=True),
            package_config=config,
        )
        result = deployer.deploy()
        assert not result.success
        assert result.state == DeploymentState.FAILED
        assert "Configuration errors" in (result.error_message or "")

    def test_deploy_without_waiting(self, deployer: TestnetDeployer) -> None:
        result = deployer.deploy(wait_for_finality=False)
        assert result.success

    def test_destroy(self, deployer: TestnetDeployer) -> None:
        deployer.deploy()
        assert deployer.destroy() is True
        assert deployer.state == DeploymentState.DESTROYED

    def test_status(self, deployer: TestnetDeployer) -> None:
        deployer.deploy()
        status = deployer.status()
        assert status["state"] == "running"
        assert status["enclave_name"] == "test-enclave"

    def test_status_before_deploy(self, deployer: TestnetDeployer) -> None:
        status = deployer.status()
        assert status["state"] == "not_started"

    def test_get_last_deployment(self, deployer: TestnetDeployer) -> None:
        assert deployer.get_last_deployment() is None
        deployer.deploy()
        last = deployer.get_last_deployment()
        assert last is not None
        assert last.success

    def test_deploy_records_duration(self, deployer: TestnetDeployer) -> None:
        result = deployer.deploy()
        assert result.duration_seconds >= 0

    def test_config_accessible(self, deployer: TestnetDeployer) -> None:
        config = deployer.config
        assert config is not None
        assert config.client_config.node_count == 50  # default
