"""Unit tests for blast radius configuration and validation.

Safety-critical tests: these must never be skipped or weakened.
"""

from __future__ import annotations

import pytest

from chaoswopr.safety.blast_radius import (
    MAX_BLAST_RADIUS_PERCENT,
    BlastRadiusConfig,
    calculate_affected_nodes,
    get_next_rollout_phase,
    validate_blast_radius,
)


class TestBlastRadiusConfig:
    """Tests for BlastRadiusConfig creation and validation."""

    def test_default_config(self) -> None:
        config = BlastRadiusConfig()
        assert config.max_affected_percent == 33.0
        assert config.phased_rollout == [5.0, 10.0, 20.0, 33.0]
        assert config.per_client_max_percent == 50.0
        assert config.observation_window_seconds == 60

    def test_custom_config(self) -> None:
        config = BlastRadiusConfig(
            max_affected_percent=20.0,
            phased_rollout=[5.0, 10.0, 20.0],
            per_client_max_percent=30.0,
            observation_window_seconds=120,
        )
        assert config.max_affected_percent == 20.0
        assert config.per_client_max_percent == 30.0

    @pytest.mark.safety
    def test_exceeding_33_percent_raises(self) -> None:
        """SAFETY: Config with >33% max must raise ValueError."""
        with pytest.raises(ValueError, match="safety limit"):
            BlastRadiusConfig(max_affected_percent=50.0)

    @pytest.mark.safety
    def test_max_blast_radius_constant(self) -> None:
        """SAFETY: The absolute maximum must be 33%."""
        assert MAX_BLAST_RADIUS_PERCENT == 33.0

    def test_negative_max_percent_raises(self) -> None:
        with pytest.raises(ValueError, match="must be >= 0"):
            BlastRadiusConfig(max_affected_percent=-5.0)

    def test_non_ascending_rollout_raises(self) -> None:
        with pytest.raises(ValueError, match="ascending"):
            BlastRadiusConfig(phased_rollout=[20.0, 10.0, 5.0])

    def test_rollout_exceeding_safety_limit_raises(self) -> None:
        with pytest.raises(ValueError, match="safety limit"):
            BlastRadiusConfig(phased_rollout=[5.0, 10.0, 50.0])

    def test_negative_rollout_values_raise(self) -> None:
        with pytest.raises(ValueError, match="must be >= 0"):
            BlastRadiusConfig(phased_rollout=[-5.0, 10.0])

    def test_zero_max_percent_valid(self) -> None:
        """A baseline scenario with 0% blast radius should be valid."""
        config = BlastRadiusConfig(max_affected_percent=0.0, phased_rollout=[])
        assert config.max_affected_percent == 0.0

    def test_empty_rollout_valid(self) -> None:
        config = BlastRadiusConfig(phased_rollout=[])
        assert config.phased_rollout == []

    def test_from_dict(self) -> None:
        data = {
            "max_affected_percent": 20.0,
            "phased_rollout": [5.0, 10.0, 20.0],
            "per_client_max_percent": 40.0,
            "observation_window_seconds": 90,
        }
        config = BlastRadiusConfig.from_dict(data)
        assert config.max_affected_percent == 20.0
        assert config.phased_rollout == [5.0, 10.0, 20.0]

    def test_to_dict(self) -> None:
        config = BlastRadiusConfig()
        d = config.to_dict()
        assert d["max_affected_percent"] == 33.0
        assert d["phased_rollout"] == [5.0, 10.0, 20.0, 33.0]

    def test_from_dict_with_defaults(self) -> None:
        config = BlastRadiusConfig.from_dict({})
        assert config.max_affected_percent == 33.0

    def test_invalid_per_client_percent_raises(self) -> None:
        with pytest.raises(ValueError, match="per_client_max_percent"):
            BlastRadiusConfig(per_client_max_percent=150.0)

    def test_negative_observation_window_raises(self) -> None:
        with pytest.raises(ValueError, match="observation_window"):
            BlastRadiusConfig(observation_window_seconds=-1)


class TestCalculateAffectedNodes:
    """Tests for the calculate_affected_nodes utility."""

    def test_basic_calculation(self) -> None:
        assert calculate_affected_nodes(100, 33.0) == 33
        assert calculate_affected_nodes(100, 10.0) == 10
        assert calculate_affected_nodes(50, 20.0) == 10

    def test_zero_percent(self) -> None:
        assert calculate_affected_nodes(100, 0.0) == 0

    def test_rounding_down(self) -> None:
        # 33% of 50 = 16.5, should round down to 16
        assert calculate_affected_nodes(50, 33.0) == 16

    def test_small_testnet(self) -> None:
        assert calculate_affected_nodes(4, 33.0) == 1


class TestValidateBlastRadius:
    """Tests for blast radius validation of injection requests."""

    @pytest.fixture
    def config(self) -> BlastRadiusConfig:
        return BlastRadiusConfig(max_affected_percent=33.0)

    @pytest.mark.safety
    def test_within_limits_passes(self, config: BlastRadiusConfig) -> None:
        is_valid, violations = validate_blast_radius(config, total_nodes=100, requested_nodes=20)
        assert is_valid
        assert violations == []

    @pytest.mark.safety
    def test_at_limit_passes(self, config: BlastRadiusConfig) -> None:
        is_valid, violations = validate_blast_radius(config, total_nodes=100, requested_nodes=33)
        assert is_valid

    @pytest.mark.safety
    def test_over_limit_fails(self, config: BlastRadiusConfig) -> None:
        is_valid, violations = validate_blast_radius(config, total_nodes=100, requested_nodes=50)
        assert not is_valid
        assert len(violations) > 0

    @pytest.mark.safety
    def test_over_absolute_limit_fails(self) -> None:
        """Even with a permissive config, >33% must fail."""
        # This config would be invalid to create, but test the validation logic directly
        config = BlastRadiusConfig.__new__(BlastRadiusConfig)
        config.max_affected_percent = 50.0  # bypass __post_init__
        config.phased_rollout = []
        config.per_client_max_percent = 50.0
        config.observation_window_seconds = 60

        is_valid, violations = validate_blast_radius(config, total_nodes=100, requested_nodes=40)
        assert not is_valid
        assert any("absolute safety limit" in v for v in violations)

    def test_zero_total_nodes_fails(self, config: BlastRadiusConfig) -> None:
        is_valid, violations = validate_blast_radius(config, total_nodes=0, requested_nodes=0)
        assert not is_valid
        assert any("total_nodes" in v for v in violations)

    def test_per_client_limit_check(self, config: BlastRadiusConfig) -> None:
        is_valid, violations = validate_blast_radius(
            config,
            total_nodes=100,
            requested_nodes=20,
            client_counts={"prysm": 40, "lighthouse": 30, "nethermind": 30},
            requested_by_client={"prysm": 25},  # 62.5% of prysm nodes
        )
        assert not is_valid
        assert any("per_client_max_percent" in v for v in violations)

    def test_per_client_within_limits(self, config: BlastRadiusConfig) -> None:
        is_valid, violations = validate_blast_radius(
            config,
            total_nodes=100,
            requested_nodes=10,
            client_counts={"prysm": 40, "lighthouse": 30},
            requested_by_client={"prysm": 10},  # 25% of prysm - under 50%
        )
        assert is_valid

    def test_zero_requested_passes(self, config: BlastRadiusConfig) -> None:
        is_valid, violations = validate_blast_radius(config, total_nodes=100, requested_nodes=0)
        assert is_valid


class TestGetNextRolloutPhase:
    """Tests for the phased rollout progression."""

    @pytest.fixture
    def config(self) -> BlastRadiusConfig:
        return BlastRadiusConfig(phased_rollout=[5.0, 10.0, 20.0, 33.0])

    def test_first_phase(self, config: BlastRadiusConfig) -> None:
        assert get_next_rollout_phase(config, 0.0) == 5.0

    def test_second_phase(self, config: BlastRadiusConfig) -> None:
        assert get_next_rollout_phase(config, 5.0) == 10.0

    def test_third_phase(self, config: BlastRadiusConfig) -> None:
        assert get_next_rollout_phase(config, 10.0) == 20.0

    def test_final_phase(self, config: BlastRadiusConfig) -> None:
        assert get_next_rollout_phase(config, 20.0) == 33.0

    def test_at_max_returns_none(self, config: BlastRadiusConfig) -> None:
        assert get_next_rollout_phase(config, 33.0) is None

    def test_over_max_returns_none(self, config: BlastRadiusConfig) -> None:
        assert get_next_rollout_phase(config, 50.0) is None

    def test_empty_rollout(self) -> None:
        config = BlastRadiusConfig(phased_rollout=[], max_affected_percent=0.0)
        assert get_next_rollout_phase(config, 0.0) is None
