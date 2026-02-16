"""Ethereum Beacon API client for chaoswopr.

Provides a Python interface for querying Ethereum consensus layer beacon
nodes via their standard REST API (https://ethereum.github.io/beacon-APIs/).

Used for:
- Real finality verification during testnet deployment
- Health checks and sync status monitoring
- Peer information and network state queries
- Integration with the monitoring and safety systems
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


@dataclass
class FinalityCheckpoint:
    """Finality checkpoint data from the beacon API."""

    finalized_epoch: int
    finalized_root: str
    justified_epoch: int
    justified_root: str
    current_epoch: int

    @property
    def epochs_since_finality(self) -> int:
        """Calculate epochs since last finality."""
        return self.current_epoch - self.finalized_epoch

    @property
    def is_finalizing(self) -> bool:
        """Check if the chain is finalizing normally (within 2 epochs)."""
        return self.epochs_since_finality <= 2


@dataclass
class SyncStatus:
    """Node sync status from the beacon API."""

    head_slot: int
    sync_distance: int
    is_syncing: bool
    is_optimistic: bool = False
    el_offline: bool = False

    @property
    def is_healthy(self) -> bool:
        """Check if the node is synced and healthy."""
        return not self.is_syncing and not self.el_offline


@dataclass
class PeerInfo:
    """Peer information from the beacon API."""

    peer_id: str
    state: str
    direction: str
    enr: str = ""


@dataclass
class NodeHealth:
    """Overall node health status."""

    is_healthy: bool
    status_code: int
    sync_status: SyncStatus | None = None
    peer_count: int = 0
    error: str | None = None


@dataclass
class BeaconBlockHeader:
    """Beacon block header information."""

    slot: int
    proposer_index: int
    parent_root: str
    state_root: str
    body_root: str


@dataclass
class FinalityWaitResult:
    """Result of waiting for finality."""

    achieved: bool
    finality_epoch: int | None = None
    wait_seconds: float = 0.0
    polls: int = 0
    error: str | None = None
    checkpoints: list[FinalityCheckpoint] = field(default_factory=list)


class BeaconAPIClient:
    """Client for the Ethereum Beacon API.

    Connects to a beacon node's REST API to query chain state,
    finality status, sync state, and peer information. Uses
    the standard Ethereum Beacon API specification.

    The client uses a requests.Session with retry logic to handle
    transient connection failures common during testnet startup.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:5052",
        timeout: float = 10.0,
        max_retries: int = 3,
        retry_backoff: float = 1.0,
    ) -> None:
        """Initialize the Beacon API client.

        Args:
            base_url: Beacon node API base URL.
            timeout: Request timeout in seconds.
            max_retries: Maximum retries for failed requests.
            retry_backoff: Backoff factor between retries.
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

        self._session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=retry_backoff,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    @property
    def base_url(self) -> str:
        """Get the beacon node base URL."""
        return self._base_url

    def _get(self, path: str) -> dict[str, Any]:
        """Make a GET request to the beacon API.

        Args:
            path: API endpoint path.

        Returns:
            Parsed JSON response.

        Raises:
            requests.RequestException: On HTTP errors.
        """
        url = f"{self._base_url}{path}"
        response = self._session.get(url, timeout=self._timeout)
        response.raise_for_status()
        return response.json()

    def health_check(self) -> NodeHealth:
        """Check beacon node health.

        Uses GET /eth/v1/node/health to check if the node is healthy.

        Returns:
            NodeHealth with the node's health status.
        """
        try:
            url = f"{self._base_url}/eth/v1/node/health"
            response = self._session.get(url, timeout=self._timeout)

            is_healthy = response.status_code == 200
            sync_status = None

            if is_healthy:
                try:
                    sync_status = self.get_sync_status()
                except Exception:
                    pass

            peer_count = 0
            try:
                peers = self.get_peers()
                peer_count = len(peers)
            except Exception:
                pass

            return NodeHealth(
                is_healthy=is_healthy,
                status_code=response.status_code,
                sync_status=sync_status,
                peer_count=peer_count,
            )
        except requests.ConnectionError as e:
            return NodeHealth(
                is_healthy=False,
                status_code=0,
                error=f"Connection failed: {e}",
            )
        except requests.RequestException as e:
            return NodeHealth(
                is_healthy=False,
                status_code=getattr(e.response, "status_code", 0) if e.response else 0,
                error=str(e),
            )

    def get_sync_status(self) -> SyncStatus:
        """Get node sync status.

        Uses GET /eth/v1/node/syncing.

        Returns:
            SyncStatus with current sync state.

        Raises:
            requests.RequestException: On HTTP errors.
        """
        data = self._get("/eth/v1/node/syncing")
        sync_data = data.get("data", {})
        return SyncStatus(
            head_slot=int(sync_data.get("head_slot", 0)),
            sync_distance=int(sync_data.get("sync_distance", 0)),
            is_syncing=sync_data.get("is_syncing", True),
            is_optimistic=sync_data.get("is_optimistic", False),
            el_offline=sync_data.get("el_offline", False),
        )

    def get_finality_checkpoints(
        self, state_id: str = "head"
    ) -> FinalityCheckpoint:
        """Get finality checkpoint information.

        Uses GET /eth/v1/beacon/states/{state_id}/finality_checkpoints.

        Args:
            state_id: State identifier (head, finalized, justified, genesis, slot number).

        Returns:
            FinalityCheckpoint with current finality state.

        Raises:
            requests.RequestException: On HTTP errors.
        """
        data = self._get(f"/eth/v1/beacon/states/{state_id}/finality_checkpoints")
        cp_data = data.get("data", {})

        finalized = cp_data.get("finalized", {})
        justified = cp_data.get("current_justified", {})

        # Get current epoch from head
        head_data = self._get("/eth/v1/beacon/headers/head")
        head_slot = int(head_data.get("data", {}).get("header", {}).get("message", {}).get("slot", 0))
        current_epoch = head_slot // 32  # 32 slots per epoch

        return FinalityCheckpoint(
            finalized_epoch=int(finalized.get("epoch", 0)),
            finalized_root=finalized.get("root", "0x"),
            justified_epoch=int(justified.get("epoch", 0)),
            justified_root=justified.get("root", "0x"),
            current_epoch=current_epoch,
        )

    def get_head_header(self) -> BeaconBlockHeader:
        """Get the head block header.

        Uses GET /eth/v1/beacon/headers/head.

        Returns:
            BeaconBlockHeader for the current head.

        Raises:
            requests.RequestException: On HTTP errors.
        """
        data = self._get("/eth/v1/beacon/headers/head")
        msg = data.get("data", {}).get("header", {}).get("message", {})
        return BeaconBlockHeader(
            slot=int(msg.get("slot", 0)),
            proposer_index=int(msg.get("proposer_index", 0)),
            parent_root=msg.get("parent_root", "0x"),
            state_root=msg.get("state_root", "0x"),
            body_root=msg.get("body_root", "0x"),
        )

    def get_peers(self) -> list[PeerInfo]:
        """Get connected peers.

        Uses GET /eth/v1/node/peers.

        Returns:
            List of PeerInfo for all connected peers.

        Raises:
            requests.RequestException: On HTTP errors.
        """
        data = self._get("/eth/v1/node/peers")
        peers = []
        for peer_data in data.get("data", []):
            peers.append(
                PeerInfo(
                    peer_id=peer_data.get("peer_id", ""),
                    state=peer_data.get("state", "unknown"),
                    direction=peer_data.get("direction", "unknown"),
                    enr=peer_data.get("enr", ""),
                )
            )
        return peers

    def get_peer_count(self) -> int:
        """Get the number of connected peers.

        Returns:
            Number of connected peers.
        """
        try:
            data = self._get("/eth/v1/node/peer_count")
            count_data = data.get("data", {})
            return int(count_data.get("connected", 0))
        except Exception:
            # Fall back to counting peers
            return len(self.get_peers())

    def get_validator_count(self) -> int:
        """Get the number of active validators.

        Uses GET /eth/v1/beacon/states/head/validators with status filter.

        Returns:
            Number of active validators.

        Raises:
            requests.RequestException: On HTTP errors.
        """
        data = self._get("/eth/v1/beacon/states/head/validators?status=active_ongoing")
        return len(data.get("data", []))

    def wait_for_node_ready(
        self,
        timeout_seconds: float = 120.0,
        poll_interval: float = 5.0,
    ) -> bool:
        """Wait for the beacon node to be ready and synced.

        Polls the health endpoint until the node is healthy or timeout.

        Args:
            timeout_seconds: Maximum time to wait.
            poll_interval: Time between polls.

        Returns:
            True if the node is ready within the timeout.
        """
        start = time.monotonic()
        while time.monotonic() - start < timeout_seconds:
            health = self.health_check()
            if health.is_healthy:
                logger.info(
                    "Beacon node ready at %s (peers=%d)",
                    self._base_url,
                    health.peer_count,
                )
                return True
            logger.debug(
                "Beacon node not ready at %s: %s (%.1fs elapsed)",
                self._base_url,
                health.error or "syncing",
                time.monotonic() - start,
            )
            time.sleep(poll_interval)
        return False

    def wait_for_finality(
        self,
        timeout_seconds: float = 300.0,
        poll_interval: float = 12.0,
        min_finalized_epoch: int = 1,
    ) -> FinalityWaitResult:
        """Wait for the chain to reach finality.

        Polls finality checkpoints until the finalized epoch exceeds
        min_finalized_epoch, or timeout is reached. This is used after
        testnet deployment to verify the network is producing and finalizing.

        Args:
            timeout_seconds: Maximum time to wait for finality.
            poll_interval: Time between polls (default: 1 slot = 12s).
            min_finalized_epoch: Minimum finalized epoch to consider finality achieved.

        Returns:
            FinalityWaitResult with the outcome.
        """
        start = time.monotonic()
        polls = 0
        checkpoints: list[FinalityCheckpoint] = []

        while time.monotonic() - start < timeout_seconds:
            polls += 1
            try:
                checkpoint = self.get_finality_checkpoints()
                checkpoints.append(checkpoint)

                logger.info(
                    "Finality check #%d: finalized_epoch=%d, current_epoch=%d, "
                    "epochs_since=%d",
                    polls,
                    checkpoint.finalized_epoch,
                    checkpoint.current_epoch,
                    checkpoint.epochs_since_finality,
                )

                if checkpoint.finalized_epoch >= min_finalized_epoch:
                    elapsed = time.monotonic() - start
                    logger.info(
                        "Finality achieved at epoch %d after %.1fs (%d polls)",
                        checkpoint.finalized_epoch,
                        elapsed,
                        polls,
                    )
                    return FinalityWaitResult(
                        achieved=True,
                        finality_epoch=checkpoint.finalized_epoch,
                        wait_seconds=elapsed,
                        polls=polls,
                        checkpoints=checkpoints,
                    )
            except requests.ConnectionError as e:
                logger.debug("Connection error during finality check: %s", e)
            except requests.RequestException as e:
                logger.debug("Request error during finality check: %s", e)

            time.sleep(poll_interval)

        elapsed = time.monotonic() - start
        return FinalityWaitResult(
            achieved=False,
            wait_seconds=elapsed,
            polls=polls,
            error=f"Finality not achieved within {timeout_seconds}s "
            f"(min_epoch={min_finalized_epoch})",
            checkpoints=checkpoints,
        )

    def close(self) -> None:
        """Close the HTTP session."""
        self._session.close()

    def __enter__(self) -> BeaconAPIClient:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()
