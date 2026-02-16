"""Unit tests for the Beacon API client.

Tests the BeaconAPIClient against mocked HTTP responses, verifying
correct parsing of all beacon API endpoints without requiring a
real beacon node.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from chaoswopr.infrastructure.testnet.beacon_api import (
    BeaconAPIClient,
    BeaconBlockHeader,
    FinalityCheckpoint,
    FinalityWaitResult,
    NodeHealth,
    PeerInfo,
    SyncStatus,
)


@pytest.fixture
def mock_session() -> MagicMock:
    """Create a mock requests session."""
    return MagicMock(spec=requests.Session)


@pytest.fixture
def beacon_client(mock_session: MagicMock) -> BeaconAPIClient:
    """Create a BeaconAPIClient with a mocked session."""
    client = BeaconAPIClient(base_url="http://localhost:5052")
    client._session = mock_session
    return client


def _mock_json_response(
    data: dict, status_code: int = 200
) -> MagicMock:
    """Create a mock response with JSON data."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = data
    response.raise_for_status.return_value = None
    return response


class TestBeaconAPIClientInit:
    """Tests for client initialization."""

    def test_default_url(self) -> None:
        client = BeaconAPIClient()
        assert client.base_url == "http://localhost:5052"

    def test_custom_url(self) -> None:
        client = BeaconAPIClient(base_url="http://beacon:4000")
        assert client.base_url == "http://beacon:4000"

    def test_strips_trailing_slash(self) -> None:
        client = BeaconAPIClient(base_url="http://beacon:4000/")
        assert client.base_url == "http://beacon:4000"

    def test_context_manager(self) -> None:
        with BeaconAPIClient() as client:
            assert client.base_url == "http://localhost:5052"


class TestHealthCheck:
    """Tests for health_check endpoint."""

    def test_healthy_node(self, beacon_client: BeaconAPIClient, mock_session: MagicMock) -> None:
        # Health returns 200
        health_resp = _mock_json_response({}, status_code=200)
        # Sync returns not syncing
        sync_resp = _mock_json_response({
            "data": {
                "head_slot": "100",
                "sync_distance": "0",
                "is_syncing": False,
            }
        })
        # Peers returns some peers
        peers_resp = _mock_json_response({"data": [{"peer_id": "p1", "state": "connected", "direction": "inbound"}]})
        # Peer count
        peer_count_resp = _mock_json_response({"data": {"connected": "1"}})

        mock_session.get.side_effect = [health_resp, sync_resp, peers_resp]
        health = beacon_client.health_check()

        assert health.is_healthy is True
        assert health.status_code == 200

    def test_unhealthy_node_connection_error(
        self, beacon_client: BeaconAPIClient, mock_session: MagicMock
    ) -> None:
        mock_session.get.side_effect = requests.ConnectionError("Connection refused")
        health = beacon_client.health_check()

        assert health.is_healthy is False
        assert health.status_code == 0
        assert "Connection failed" in (health.error or "")

    def test_unhealthy_node_syncing(
        self, beacon_client: BeaconAPIClient, mock_session: MagicMock
    ) -> None:
        health_resp = _mock_json_response({}, status_code=206)
        mock_session.get.return_value = health_resp
        health = beacon_client.health_check()

        assert health.is_healthy is False
        assert health.status_code == 206


class TestSyncStatus:
    """Tests for get_sync_status endpoint."""

    def test_synced_node(self, beacon_client: BeaconAPIClient, mock_session: MagicMock) -> None:
        response = _mock_json_response({
            "data": {
                "head_slot": "1000",
                "sync_distance": "0",
                "is_syncing": False,
                "is_optimistic": False,
                "el_offline": False,
            }
        })
        mock_session.get.return_value = response

        status = beacon_client.get_sync_status()
        assert status.head_slot == 1000
        assert status.sync_distance == 0
        assert status.is_syncing is False
        assert status.is_healthy is True

    def test_syncing_node(self, beacon_client: BeaconAPIClient, mock_session: MagicMock) -> None:
        response = _mock_json_response({
            "data": {
                "head_slot": "500",
                "sync_distance": "500",
                "is_syncing": True,
            }
        })
        mock_session.get.return_value = response

        status = beacon_client.get_sync_status()
        assert status.is_syncing is True
        assert status.sync_distance == 500
        assert status.is_healthy is False

    def test_el_offline(self, beacon_client: BeaconAPIClient, mock_session: MagicMock) -> None:
        response = _mock_json_response({
            "data": {
                "head_slot": "1000",
                "sync_distance": "0",
                "is_syncing": False,
                "el_offline": True,
            }
        })
        mock_session.get.return_value = response

        status = beacon_client.get_sync_status()
        assert status.el_offline is True
        assert status.is_healthy is False


class TestFinalityCheckpoints:
    """Tests for finality checkpoint queries."""

    def test_finality_checkpoints(self, beacon_client: BeaconAPIClient, mock_session: MagicMock) -> None:
        checkpoint_resp = _mock_json_response({
            "data": {
                "finalized": {"epoch": "10", "root": "0xabc"},
                "current_justified": {"epoch": "12", "root": "0xdef"},
            }
        })
        head_resp = _mock_json_response({
            "data": {"header": {"message": {"slot": "416"}}}  # epoch 13
        })
        mock_session.get.side_effect = [checkpoint_resp, head_resp]

        cp = beacon_client.get_finality_checkpoints()
        assert cp.finalized_epoch == 10
        assert cp.justified_epoch == 12
        assert cp.current_epoch == 13  # 416 // 32
        assert cp.epochs_since_finality == 3
        assert cp.is_finalizing is False  # > 2 epochs

    def test_finality_normal(self, beacon_client: BeaconAPIClient, mock_session: MagicMock) -> None:
        checkpoint_resp = _mock_json_response({
            "data": {
                "finalized": {"epoch": "11", "root": "0xabc"},
                "current_justified": {"epoch": "12", "root": "0xdef"},
            }
        })
        head_resp = _mock_json_response({
            "data": {"header": {"message": {"slot": "416"}}}  # epoch 13
        })
        mock_session.get.side_effect = [checkpoint_resp, head_resp]

        cp = beacon_client.get_finality_checkpoints()
        assert cp.epochs_since_finality == 2
        assert cp.is_finalizing is True


class TestHeadHeader:
    """Tests for get_head_header."""

    def test_head_header(self, beacon_client: BeaconAPIClient, mock_session: MagicMock) -> None:
        response = _mock_json_response({
            "data": {
                "header": {
                    "message": {
                        "slot": "1024",
                        "proposer_index": "42",
                        "parent_root": "0xparent",
                        "state_root": "0xstate",
                        "body_root": "0xbody",
                    }
                }
            }
        })
        mock_session.get.return_value = response

        header = beacon_client.get_head_header()
        assert header.slot == 1024
        assert header.proposer_index == 42
        assert header.parent_root == "0xparent"


class TestPeers:
    """Tests for peer-related endpoints."""

    def test_get_peers(self, beacon_client: BeaconAPIClient, mock_session: MagicMock) -> None:
        response = _mock_json_response({
            "data": [
                {"peer_id": "peer1", "state": "connected", "direction": "inbound", "enr": "enr:test1"},
                {"peer_id": "peer2", "state": "connected", "direction": "outbound", "enr": "enr:test2"},
            ]
        })
        mock_session.get.return_value = response

        peers = beacon_client.get_peers()
        assert len(peers) == 2
        assert peers[0].peer_id == "peer1"
        assert peers[1].direction == "outbound"

    def test_get_peers_empty(self, beacon_client: BeaconAPIClient, mock_session: MagicMock) -> None:
        response = _mock_json_response({"data": []})
        mock_session.get.return_value = response

        peers = beacon_client.get_peers()
        assert len(peers) == 0

    def test_get_peer_count(self, beacon_client: BeaconAPIClient, mock_session: MagicMock) -> None:
        response = _mock_json_response({"data": {"connected": "25", "disconnected": "3"}})
        mock_session.get.return_value = response

        count = beacon_client.get_peer_count()
        assert count == 25

    def test_get_peer_count_fallback(self, beacon_client: BeaconAPIClient, mock_session: MagicMock) -> None:
        """If peer_count endpoint fails, fall back to counting peers."""
        peer_count_err = requests.RequestException("not found")
        peers_resp = _mock_json_response({
            "data": [
                {"peer_id": "p1", "state": "connected", "direction": "inbound"},
                {"peer_id": "p2", "state": "connected", "direction": "outbound"},
            ]
        })
        mock_session.get.side_effect = [peer_count_err, peers_resp]

        count = beacon_client.get_peer_count()
        assert count == 2


class TestWaitForFinality:
    """Tests for the wait_for_finality polling method."""

    def test_finality_achieved_immediately(
        self, beacon_client: BeaconAPIClient, mock_session: MagicMock
    ) -> None:
        checkpoint_resp = _mock_json_response({
            "data": {
                "finalized": {"epoch": "3", "root": "0xabc"},
                "current_justified": {"epoch": "4", "root": "0xdef"},
            }
        })
        head_resp = _mock_json_response({
            "data": {"header": {"message": {"slot": "160"}}}
        })
        mock_session.get.side_effect = [checkpoint_resp, head_resp]

        result = beacon_client.wait_for_finality(
            timeout_seconds=5.0,
            poll_interval=0.1,
            min_finalized_epoch=1,
        )
        assert result.achieved is True
        assert result.finality_epoch == 3
        assert result.polls == 1

    def test_finality_not_achieved_timeout(
        self, beacon_client: BeaconAPIClient, mock_session: MagicMock
    ) -> None:
        """Finality not reached before timeout."""
        checkpoint_resp = _mock_json_response({
            "data": {
                "finalized": {"epoch": "0", "root": "0x0"},
                "current_justified": {"epoch": "0", "root": "0x0"},
            }
        })
        head_resp = _mock_json_response({
            "data": {"header": {"message": {"slot": "10"}}}
        })
        mock_session.get.side_effect = [
            checkpoint_resp, head_resp,
            checkpoint_resp, head_resp,
            checkpoint_resp, head_resp,
        ]

        result = beacon_client.wait_for_finality(
            timeout_seconds=0.3,
            poll_interval=0.1,
            min_finalized_epoch=1,
        )
        assert result.achieved is False
        assert "not achieved" in (result.error or "")

    def test_finality_connection_errors_retried(
        self, beacon_client: BeaconAPIClient, mock_session: MagicMock
    ) -> None:
        """Connection errors during polling are retried."""
        # First poll: connection error
        conn_err = requests.ConnectionError("connection refused")
        # Second poll: success
        checkpoint_resp = _mock_json_response({
            "data": {
                "finalized": {"epoch": "2", "root": "0xabc"},
                "current_justified": {"epoch": "3", "root": "0xdef"},
            }
        })
        head_resp = _mock_json_response({
            "data": {"header": {"message": {"slot": "128"}}}
        })
        mock_session.get.side_effect = [
            conn_err,
            checkpoint_resp, head_resp,
        ]

        result = beacon_client.wait_for_finality(
            timeout_seconds=2.0,
            poll_interval=0.1,
            min_finalized_epoch=1,
        )
        assert result.achieved is True
        assert result.polls == 2


class TestWaitForNodeReady:
    """Tests for wait_for_node_ready."""

    def test_node_ready_immediately(
        self, beacon_client: BeaconAPIClient, mock_session: MagicMock
    ) -> None:
        health_resp = _mock_json_response({}, status_code=200)
        sync_resp = _mock_json_response({
            "data": {"head_slot": "100", "sync_distance": "0", "is_syncing": False}
        })
        peers_resp = _mock_json_response({"data": [{"peer_id": "p1", "state": "connected", "direction": "in"}]})
        mock_session.get.side_effect = [health_resp, sync_resp, peers_resp]

        result = beacon_client.wait_for_node_ready(
            timeout_seconds=1.0, poll_interval=0.1
        )
        assert result is True

    def test_node_not_ready_timeout(
        self, beacon_client: BeaconAPIClient, mock_session: MagicMock
    ) -> None:
        mock_session.get.side_effect = requests.ConnectionError("refused")

        result = beacon_client.wait_for_node_ready(
            timeout_seconds=0.3, poll_interval=0.1
        )
        assert result is False


class TestFinalityCheckpointDataclass:
    """Tests for the FinalityCheckpoint dataclass."""

    def test_epochs_since_finality(self) -> None:
        cp = FinalityCheckpoint(
            finalized_epoch=10,
            finalized_root="0x",
            justified_epoch=12,
            justified_root="0x",
            current_epoch=13,
        )
        assert cp.epochs_since_finality == 3
        assert cp.is_finalizing is False

    def test_is_finalizing_within_2_epochs(self) -> None:
        cp = FinalityCheckpoint(
            finalized_epoch=11,
            finalized_root="0x",
            justified_epoch=12,
            justified_root="0x",
            current_epoch=13,
        )
        assert cp.is_finalizing is True


class TestSyncStatusDataclass:
    """Tests for the SyncStatus dataclass."""

    def test_healthy_when_synced(self) -> None:
        status = SyncStatus(head_slot=1000, sync_distance=0, is_syncing=False)
        assert status.is_healthy is True

    def test_unhealthy_when_syncing(self) -> None:
        status = SyncStatus(head_slot=500, sync_distance=500, is_syncing=True)
        assert status.is_healthy is False

    def test_unhealthy_when_el_offline(self) -> None:
        status = SyncStatus(head_slot=1000, sync_distance=0, is_syncing=False, el_offline=True)
        assert status.is_healthy is False


class TestFinalityWaitResult:
    """Tests for the FinalityWaitResult dataclass."""

    def test_successful_result(self) -> None:
        result = FinalityWaitResult(
            achieved=True,
            finality_epoch=5,
            wait_seconds=60.0,
            polls=5,
        )
        assert result.achieved is True
        assert result.finality_epoch == 5

    def test_failed_result(self) -> None:
        result = FinalityWaitResult(
            achieved=False,
            error="Timeout",
        )
        assert result.achieved is False
        assert result.error == "Timeout"
