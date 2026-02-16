"""Test NET_ADMIN capability addition for chaos injection."""

from __future__ import annotations

import pytest

from .conftest import require_kurtosis_engine


@require_kurtosis_engine
class TestNETAdminCapability:
    """Test that containers can be given NET_ADMIN for chaos injection."""

    @pytest.mark.timeout(600)
    def test_chaos_testnet_adds_net_admin(
        self,
        chaos_testnet_4node: tuple,
    ) -> None:
        """Test that chaos testnet deployer adds NET_ADMIN to containers."""
        deployer, result = chaos_testnet_4node

        if not result.success:
            pytest.skip(f"Testnet deployment failed: {result.error_message}")

        # Get services from the enclave
        services = deployer._kurtosis.get_services(deployer.enclave_name)

        print(f"Enclave name: {deployer.enclave_name}")
        print(f"Services: {[s.name for s in services]}")

        assert len(services) > 0, "No services deployed"

        # Check at least one EL container has NET_ADMIN
        el_services = [s for s in services if s.name.startswith("el-")]

        print(f"EL services: {[s.name for s in el_services]}")

        assert len(el_services) > 0, "No EL services found"

        # Get the first EL container and check NET_ADMIN
        service_name = el_services[0].name
        print(f"Looking for container for service: {service_name}")

        container_name = deployer._get_docker_container_name(service_name)
        print(f"Found container: {container_name}")

        assert container_name is not None, f"Could not find Docker container for service {service_name}"

        has_net_admin = deployer._check_net_admin(container_name)
        assert has_net_admin, f"Container {container_name} does not have NET_ADMIN capability"

        print(f"✓ Container {container_name} has NET_ADMIN capability")
