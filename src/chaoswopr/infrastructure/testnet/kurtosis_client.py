"""Kurtosis CLI wrapper for chaoswopr.

Provides a Python interface for managing Kurtosis enclaves:
- Create, inspect, and destroy enclaves
- Run packages within enclaves
- Service discovery and health checks
- Parse real Kurtosis CLI output for service ports/IPs

Supports both Docker and Kubernetes backends.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class KurtosisBackend(str, Enum):
    """Kurtosis execution backend."""

    DOCKER = "docker"
    KUBERNETES = "kubernetes"


class EnclaveState(str, Enum):
    """State of a Kurtosis enclave."""

    RUNNING = "running"
    STOPPED = "stopped"
    CREATING = "creating"
    DESTROYING = "destroying"
    UNKNOWN = "unknown"


class KurtosisError(Exception):
    """Error from Kurtosis CLI operations."""

    def __init__(self, message: str, command: str = "", output: str = "") -> None:
        super().__init__(message)
        self.command = command
        self.output = output


@dataclass
class PortSpec:
    """Port specification for a service."""

    number: int
    transport_protocol: str = "TCP"
    application_protocol: str = ""
    url: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "number": self.number,
            "transport_protocol": self.transport_protocol,
            "application_protocol": self.application_protocol,
            "url": self.url,
        }


@dataclass
class EnclaveInfo:
    """Information about a Kurtosis enclave."""

    enclave_id: str
    name: str
    state: EnclaveState
    creation_time: str | None = None
    services: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enclave_id": self.enclave_id,
            "name": self.name,
            "state": self.state.value,
            "creation_time": self.creation_time,
            "services": self.services,
        }


@dataclass
class ServiceInfo:
    """Information about a service within an enclave."""

    name: str
    uuid: str
    status: str
    ports: dict[str, PortSpec] = field(default_factory=dict)
    ip_address: str | None = None

    def get_port(self, port_name: str) -> PortSpec | None:
        """Get a specific port by name."""
        return self.ports.get(port_name)

    def get_host_port(self, port_name: str) -> int | None:
        """Get the host-mapped port number by name."""
        port = self.ports.get(port_name)
        return port.number if port else None

    def get_url(self, port_name: str) -> str | None:
        """Get the URL for a specific port."""
        port = self.ports.get(port_name)
        return port.url if port and port.url else None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "uuid": self.uuid,
            "status": self.status,
            "ports": {k: v.to_dict() for k, v in self.ports.items()},
            "ip_address": self.ip_address,
        }


class KurtosisClient:
    """Client for interacting with the Kurtosis CLI.

    Wraps Kurtosis CLI commands in a Python API for programmatic
    testnet management. Falls back to mock mode when dry_run=True.
    In real mode, parses actual Kurtosis CLI output to extract
    service information, ports, and enclave state.
    """

    def __init__(
        self,
        backend: KurtosisBackend = KurtosisBackend.DOCKER,
        kurtosis_binary: str = "kurtosis",
        dry_run: bool = False,
    ) -> None:
        """Initialize the Kurtosis client.

        Args:
            backend: Docker or Kubernetes backend.
            kurtosis_binary: Path to the kurtosis CLI binary.
            dry_run: If True, don't execute actual commands.
        """
        self._backend = backend
        self._binary = kurtosis_binary
        self._dry_run = dry_run

    @property
    def backend(self) -> KurtosisBackend:
        """Get the configured backend."""
        return self._backend

    @property
    def dry_run(self) -> bool:
        """Check if running in dry-run mode."""
        return self._dry_run

    def is_available(self) -> bool:
        """Check if Kurtosis CLI is available.

        Returns:
            True if kurtosis binary is found and responsive.
        """
        if self._dry_run:
            return True
        try:
            result = subprocess.run(
                [self._binary, "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def is_engine_running(self) -> bool:
        """Check if the Kurtosis engine is running.

        Returns:
            True if the engine is running and responsive.
        """
        if self._dry_run:
            return True
        try:
            result = subprocess.run(
                [self._binary, "engine", "status"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return result.returncode == 0 and "RUNNING" in result.stdout.upper()
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            return False

    def start_engine(self) -> bool:
        """Start the Kurtosis engine if not running.

        Returns:
            True if the engine is now running.
        """
        if self._dry_run:
            return True
        if self.is_engine_running():
            return True
        try:
            self._run_command([self._binary, "engine", "start"], timeout=60)
            return True
        except (subprocess.CalledProcessError, KurtosisError):
            return False

    def create_enclave(
        self,
        name: str,
        production_mode: bool = False,
    ) -> EnclaveInfo:
        """Create a new Kurtosis enclave.

        Args:
            name: Name for the enclave.
            production_mode: If True, enable production mode settings.

        Returns:
            EnclaveInfo for the created enclave.

        Raises:
            KurtosisError: If enclave creation fails.
        """
        if self._dry_run:
            return EnclaveInfo(
                enclave_id=f"dry-run-{name}",
                name=name,
                state=EnclaveState.RUNNING,
            )

        cmd = [self._binary, "enclave", "add"]
        if name:
            cmd.extend(["--name", name])
        try:
            result = self._run_command(cmd)
            logger.info("Created enclave '%s'", name)
            return EnclaveInfo(
                enclave_id=name,
                name=name,
                state=EnclaveState.RUNNING,
            )
        except subprocess.CalledProcessError as e:
            raise KurtosisError(
                f"Failed to create enclave '{name}': {e.stderr}",
                command=" ".join(cmd),
                output=e.stderr,
            ) from e

    def destroy_enclave(self, name: str) -> bool:
        """Destroy a Kurtosis enclave.

        Args:
            name: Name of the enclave to destroy.

        Returns:
            True if the enclave was destroyed successfully.
        """
        if self._dry_run:
            return True

        cmd = [self._binary, "enclave", "rm", name, "--force"]
        try:
            self._run_command(cmd)
            logger.info("Destroyed enclave '%s'", name)
            return True
        except subprocess.CalledProcessError:
            logger.warning("Failed to destroy enclave '%s'", name)
            return False

    def get_enclave_info(self, name: str) -> EnclaveInfo | None:
        """Get information about an enclave.

        Args:
            name: Name of the enclave.

        Returns:
            EnclaveInfo or None if not found.
        """
        if self._dry_run:
            return EnclaveInfo(
                enclave_id=f"dry-run-{name}",
                name=name,
                state=EnclaveState.RUNNING,
            )

        cmd = [self._binary, "enclave", "inspect", name]
        try:
            result = self._run_command(cmd)
            services = self._parse_enclave_inspect(result.stdout)
            return EnclaveInfo(
                enclave_id=name,
                name=name,
                state=EnclaveState.RUNNING,
                services={s.name: s.to_dict() for s in services},
            )
        except subprocess.CalledProcessError:
            return None

    def list_enclaves(self) -> list[EnclaveInfo]:
        """List all Kurtosis enclaves.

        Returns:
            List of EnclaveInfo objects.
        """
        if self._dry_run:
            return []

        cmd = [self._binary, "enclave", "ls"]
        try:
            result = self._run_command(cmd)
            return self._parse_enclave_list(result.stdout)
        except subprocess.CalledProcessError:
            return []

    def run_package(
        self,
        enclave_name: str,
        package_path: str,
        args: dict[str, Any] | None = None,
        args_file: str | None = None,
        timeout: int = 600,
    ) -> dict[str, Any]:
        """Run a Kurtosis package within an enclave.

        Args:
            enclave_name: Name of the target enclave.
            package_path: Path or URL to the Kurtosis package.
            args: Package arguments as a dictionary.
            args_file: Path to a JSON file with package arguments.
            timeout: Timeout in seconds (default 600 for real deployments).

        Returns:
            Dictionary with execution results.

        Raises:
            KurtosisError: If package execution fails.
        """
        if self._dry_run:
            return {
                "status": "success",
                "enclave": enclave_name,
                "package": package_path,
            }

        cmd = [self._binary, "run", "--enclave", enclave_name, package_path]

        if args:
            # Args are passed as a positional argument (JSON string) at the end
            args_json = json.dumps(args)
            cmd.append(args_json)
        elif args_file:
            cmd.extend(["--args-file", args_file])

        try:
            result = self._run_command(cmd, timeout=timeout)
            logger.info(
                "Package '%s' deployed to enclave '%s'",
                package_path,
                enclave_name,
            )
            return {
                "status": "success",
                "enclave": enclave_name,
                "package": package_path,
                "output": result.stdout,
            }
        except subprocess.CalledProcessError as e:
            # Kurtosis outputs errors to stdout, not stderr
            error_output = e.stdout if e.stdout else e.stderr
            raise KurtosisError(
                f"Package execution failed in enclave '{enclave_name}': {error_output}",
                command=" ".join(cmd),
                output=error_output,
            ) from e

    def get_services(self, enclave_name: str) -> list[ServiceInfo]:
        """Get all services in an enclave.

        Args:
            enclave_name: Name of the enclave.

        Returns:
            List of ServiceInfo objects.
        """
        if self._dry_run:
            return []

        cmd = [self._binary, "enclave", "inspect", enclave_name]
        try:
            result = self._run_command(cmd)
            return self._parse_enclave_inspect(result.stdout)
        except subprocess.CalledProcessError:
            return []

    def get_service_ports(
        self, enclave_name: str, service_name: str
    ) -> dict[str, PortSpec]:
        """Get port mappings for a specific service.

        Args:
            enclave_name: Name of the enclave.
            service_name: Name of the service.

        Returns:
            Dictionary of port_name -> PortSpec.
        """
        services = self.get_services(enclave_name)
        for svc in services:
            if svc.name == service_name:
                return svc.ports
        return {}

    def find_beacon_services(self, enclave_name: str) -> list[ServiceInfo]:
        """Find all beacon (consensus layer) services in an enclave.

        Looks for services whose names contain 'cl-' or 'beacon' patterns
        typical of ethpandaops/ethereum-package deployments.

        Args:
            enclave_name: Name of the enclave.

        Returns:
            List of beacon ServiceInfo objects.
        """
        services = self.get_services(enclave_name)
        beacon_services = []
        for svc in services:
            if any(
                pattern in svc.name.lower()
                for pattern in ["cl-", "beacon", "prysm", "lighthouse", "teku", "nimbus", "lodestar"]
            ):
                beacon_services.append(svc)
        return beacon_services

    def find_execution_services(self, enclave_name: str) -> list[ServiceInfo]:
        """Find all execution layer services in an enclave.

        Args:
            enclave_name: Name of the enclave.

        Returns:
            List of execution layer ServiceInfo objects.
        """
        services = self.get_services(enclave_name)
        el_services = []
        for svc in services:
            if any(
                pattern in svc.name.lower()
                for pattern in ["el-", "nethermind", "geth", "besu", "erigon"]
            ):
                el_services.append(svc)
        return el_services

    def clean_all(self) -> bool:
        """Remove all Kurtosis enclaves and clean up resources.

        Returns:
            True if cleanup succeeded.
        """
        if self._dry_run:
            return True

        cmd = [self._binary, "clean", "-a"]
        try:
            self._run_command(cmd)
            logger.info("Cleaned all Kurtosis resources")
            return True
        except subprocess.CalledProcessError:
            return False

    def _run_command(
        self,
        cmd: list[str],
        timeout: int = 300,
        retries: int = 0,
        retry_delay: float = 5.0,
    ) -> subprocess.CompletedProcess[str]:
        """Execute a CLI command with optional retry logic.

        Args:
            cmd: Command and arguments.
            timeout: Timeout in seconds.
            retries: Number of retries on failure.
            retry_delay: Delay between retries in seconds.

        Returns:
            CompletedProcess result.

        Raises:
            subprocess.CalledProcessError: If the command fails after retries.
        """
        last_error: subprocess.CalledProcessError | None = None
        for attempt in range(retries + 1):
            try:
                logger.debug("Running command: %s (attempt %d)", " ".join(cmd), attempt + 1)
                return subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                last_error = e
                if attempt < retries:
                    logger.warning(
                        "Command failed (attempt %d/%d): %s",
                        attempt + 1,
                        retries + 1,
                        e.stderr[:200] if e.stderr else str(e),
                    )
                    time.sleep(retry_delay)
        assert last_error is not None
        raise last_error

    @staticmethod
    def _parse_enclave_inspect(output: str) -> list[ServiceInfo]:
        """Parse the output of `kurtosis enclave inspect`.

        Extracts service names, UUIDs, ports and status from the
        inspect output. The output format has a table of services
        with columns for Name, UUID, Ports, and Status.

        Args:
            output: stdout from `kurtosis enclave inspect`.

        Returns:
            List of parsed ServiceInfo objects.
        """
        services: list[ServiceInfo] = []

        # The output contains a table under "User Services" with
        # a header row (UUID Name Ports Status) followed by service lines like:
        #   abc12345   cl-1-lighthouse-nethermind   http: 4000/tcp -> http://127.0.0.1:32771   RUNNING
        in_services = False
        for line in output.splitlines():
            stripped = line.strip()

            # Detect the start of services table
            if "User Services" in stripped:
                in_services = True
                continue

            # Skip separator lines and empty lines
            if not stripped or stripped.startswith("=") or stripped.startswith("-"):
                continue

            if not in_services:
                continue

            # Skip the header row
            if "UUID" in stripped and "Name" in stripped and "Status" in stripped:
                continue

            # Try to parse a service line
            service = KurtosisClient._parse_service_line(stripped)
            if service:
                services.append(service)

        return services

    @staticmethod
    def _parse_service_line(line: str) -> ServiceInfo | None:
        """Parse a single service line from enclave inspect output.

        Kurtosis enclave inspect output has columns: UUID  Name  Ports  Status.
        Example lines:
            abc12345   cl-1-lighthouse-nethermind   http: 4000/tcp -> http://127.0.0.1:32771   RUNNING
            efgh5678   el-1-nethermind-lighthouse   rpc: 8545/tcp -> http://127.0.0.1:32772     RUNNING

        Args:
            line: A single line from the services table.

        Returns:
            ServiceInfo or None if the line could not be parsed.
        """
        # Split by 2+ spaces (column separator in Kurtosis output)
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 3:
            return None

        # Kurtosis format: UUID  Name  Ports  Status
        uuid = parts[0].strip()
        name = parts[1].strip()
        status = parts[-1].strip() if len(parts) > 3 else "UNKNOWN"

        # Parse ports from the middle columns
        ports: dict[str, PortSpec] = {}
        port_text = " ".join(parts[2:-1]) if len(parts) > 3 else parts[2] if len(parts) > 2 else ""

        # Port patterns: "http: 4000/tcp -> http://127.0.0.1:32771"
        port_entries = re.findall(
            r"(\w+):\s*(\d+)/(\w+)\s*->\s*([\w:/.]+(?::\d+)?)",
            port_text,
        )
        for port_name, port_num, protocol, url in port_entries:
            ports[port_name] = PortSpec(
                number=int(port_num),
                transport_protocol=protocol.upper(),
                url=url,
            )

        # If no structured ports found, try simpler pattern
        if not ports:
            simple_ports = re.findall(r"(\w+):\s*(\d+)/(\w+)", port_text)
            for port_name, port_num, protocol in simple_ports:
                ports[port_name] = PortSpec(
                    number=int(port_num),
                    transport_protocol=protocol.upper(),
                )

        if not name or name.startswith("="):
            return None

        return ServiceInfo(
            name=name,
            uuid=uuid,
            status=status,
            ports=ports,
        )

    @staticmethod
    def _parse_enclave_list(output: str) -> list[EnclaveInfo]:
        """Parse the output of `kurtosis enclave ls`.

        Args:
            output: stdout from `kurtosis enclave ls`.

        Returns:
            List of parsed EnclaveInfo objects.
        """
        enclaves: list[EnclaveInfo] = []
        in_table = False

        for line in output.splitlines():
            stripped = line.strip()

            # Detect table header
            if "UUID" in stripped and "Name" in stripped and "Status" in stripped:
                in_table = True
                continue

            if not stripped or stripped.startswith("="):
                continue

            if not in_table:
                continue

            # Parse enclave line: UUID  Name  Status  Created
            parts = re.split(r"\s{2,}", stripped)
            if len(parts) >= 3:
                uuid = parts[0].strip()
                name = parts[1].strip()
                status_str = parts[2].strip().upper()

                state = EnclaveState.UNKNOWN
                if "RUNNING" in status_str:
                    state = EnclaveState.RUNNING
                elif "STOPPED" in status_str:
                    state = EnclaveState.STOPPED

                creation_time = parts[3].strip() if len(parts) > 3 else None

                enclaves.append(
                    EnclaveInfo(
                        enclave_id=uuid,
                        name=name,
                        state=state,
                        creation_time=creation_time,
                    )
                )

        return enclaves
