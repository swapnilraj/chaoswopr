"""Kurtosis-based chaos injector using NET_ADMIN capabilities.

Wraps Kurtosis services with NET_ADMIN capability to inject network faults
using tc/netem. This is the production implementation for Track H (Chaos Injection)
that integrates with Kurtosis-deployed Ethereum testnets.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Any

from chaoswopr.infrastructure.testnet.kurtosis_client import KurtosisClient

logger = logging.getLogger(__name__)


class FaultType(str, Enum):
    """Types of network faults that can be injected."""

    LATENCY = "latency"
    PACKET_LOSS = "packet_loss"
    BANDWIDTH = "bandwidth"
    CORRUPTION = "corruption"
    DUPLICATION = "duplication"
    REORDER = "reorder"


@dataclass
class NetworkFault:
    """Configuration for a network fault."""

    fault_type: FaultType
    interface: str = "eth0"
    latency_ms: int | None = None
    jitter_ms: int | None = None
    loss_percent: float | None = None
    bandwidth_kbps: int | None = None
    corruption_percent: float | None = None
    duplication_percent: float | None = None


class KurtosisChaosInjector:
    """Chaos injector using Kurtosis services with NET_ADMIN capability.

    This class deploys chaos injector containers within a Kurtosis enclave
    and uses tc/netem to inject network faults. Unlike the Docker Compose
    implementation, this integrates directly with Kurtosis-deployed testnets.
    """

    def __init__(
        self,
        kurtosis_client: KurtosisClient,
        enclave_name: str,
        num_injectors: int = 3,
    ) -> None:
        """Initialize the Kurtosis chaos injector.

        Args:
            kurtosis_client: KurtosisClient instance with capabilities support.
            enclave_name: Name of the Kurtosis enclave.
            num_injectors: Number of chaos injector containers to deploy.
        """
        self._client = kurtosis_client
        self._enclave = enclave_name
        self._num_injectors = num_injectors
        self._injector_services: list[str] = []
        self._deployed = False

    @property
    def deployed(self) -> bool:
        """Check if chaos injectors are deployed."""
        return self._deployed

    @property
    def injector_services(self) -> list[str]:
        """Get list of deployed injector service names."""
        return self._injector_services

    def deploy(self) -> dict[str, Any]:
        """Deploy chaos injector services to the enclave.

        Returns:
            Dictionary with deployment results.

        Raises:
            RuntimeError: If deployment fails.
        """
        if self._deployed:
            logger.warning("Chaos injectors already deployed")
            return {"status": "already_deployed"}

        package_path = "/Users/swp/dev/swapnilraj/chaoswopr/kurtosis-packages/chaos-injector"
        args = {
            "num_injectors": self._num_injectors,
        }

        try:
            result = self._client.run_package(
                enclave_name=self._enclave,
                package_path=package_path,
                args=args,
                timeout=300,
            )

            # Extract injector service names
            self._injector_services = [
                f"chaos-injector-{i+1}" for i in range(self._num_injectors)
            ]
            self._deployed = True

            logger.info(
                "Deployed %d chaos injectors to enclave '%s'",
                self._num_injectors,
                self._enclave,
            )

            return {
                "status": "success",
                "injector_services": self._injector_services,
                "enclave": self._enclave,
            }

        except Exception as e:
            logger.error("Failed to deploy chaos injectors: %s", e)
            raise RuntimeError(f"Chaos injector deployment failed: {e}") from e

    def inject_fault(
        self,
        target_service: str,
        fault: NetworkFault,
        duration_seconds: int | None = None,
    ) -> bool:
        """Inject a network fault into a target service.

        Args:
            target_service: Name of the service to inject fault into.
            fault: NetworkFault configuration.
            duration_seconds: Optional duration for the fault (for future recovery).

        Returns:
            True if fault injection succeeded.

        Raises:
            RuntimeError: If fault injection fails.
        """
        if not self._deployed:
            raise RuntimeError("Chaos injectors not deployed yet")

        # Build tc command based on fault type
        tc_command = self._build_tc_command(fault)

        # Execute tc command via kurtosis service exec
        # For now, use the first injector (could implement load balancing)
        injector_service = self._injector_services[0]

        try:
            cmd = [
                self._client._binary,
                "service",
                "exec",
                self._enclave,
                injector_service,
                tc_command,
            ]

            logger.debug("Executing fault injection: %s", " ".join(cmd))

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

            logger.info(
                "Injected %s fault into service '%s'",
                fault.fault_type.value,
                target_service,
            )

            return True

        except subprocess.CalledProcessError as e:
            error_msg = f"Fault injection failed: {e.stderr if e.stderr else e.stdout}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def clear_faults(self, target_service: str | None = None) -> bool:
        """Clear all network faults from a service.

        Args:
            target_service: Name of service to clear faults from (unused for now).

        Returns:
            True if faults were cleared successfully.
        """
        if not self._deployed:
            logger.warning("Chaos injectors not deployed")
            return False

        # Clear all tc rules
        clear_command = "tc qdisc del dev eth0 root || true"

        for injector in self._injector_services:
            try:
                cmd = [
                    self._client._binary,
                    "service",
                    "exec",
                    self._enclave,
                    injector,
                    clear_command,
                ]

                subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,  # Don't raise on failure (may not exist)
                )

            except Exception as e:
                logger.warning("Error clearing faults from %s: %s", injector, e)

        logger.info("Cleared faults from all chaos injectors")
        return True

    def get_fault_status(self, target_service: str) -> dict[str, Any]:
        """Get current fault status for a service.

        Args:
            target_service: Name of service to check.

        Returns:
            Dictionary with fault status.
        """
        if not self._deployed or not self._injector_services:
            return {"status": "not_deployed"}

        # Query tc qdisc show to get current rules
        injector = self._injector_services[0]
        query_command = "tc qdisc show dev eth0"

        try:
            cmd = [
                self._client._binary,
                "service",
                "exec",
                self._enclave,
                injector,
                query_command,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

            output = result.stdout.strip()

            return {
                "status": "active" if "netem" in output else "none",
                "rules": output,
                "injector": injector,
            }

        except Exception as e:
            logger.error("Error querying fault status: %s", e)
            return {"status": "error", "error": str(e)}

    def _build_tc_command(self, fault: NetworkFault) -> str:
        """Build tc command from fault configuration.

        Args:
            fault: NetworkFault to convert to tc command.

        Returns:
            tc command string.
        """
        interface = fault.interface

        # Base command
        parts = [f"tc qdisc add dev {interface} root netem"]

        # Add fault-specific parameters
        if fault.fault_type == FaultType.LATENCY and fault.latency_ms is not None:
            parts.append(f"delay {fault.latency_ms}ms")
            if fault.jitter_ms is not None:
                parts.append(f"{fault.jitter_ms}ms")

        elif fault.fault_type == FaultType.PACKET_LOSS and fault.loss_percent is not None:
            parts.append(f"loss {fault.loss_percent}%")

        elif fault.fault_type == FaultType.CORRUPTION and fault.corruption_percent is not None:
            parts.append(f"corrupt {fault.corruption_percent}%")

        elif fault.fault_type == FaultType.DUPLICATION and fault.duplication_percent is not None:
            parts.append(f"duplicate {fault.duplication_percent}%")

        # For bandwidth, use tbf instead of netem
        if fault.fault_type == FaultType.BANDWIDTH and fault.bandwidth_kbps is not None:
            return (
                f"tc qdisc add dev {interface} root tbf "
                f"rate {fault.bandwidth_kbps}kbit "
                f"burst 32kbit latency 400ms"
            )

        return " ".join(parts)
