"""Experiment runner that wires orchestrator, node agents, and observer.

The ExperimentRunner is the top-level component that connects all agent
subsystems to execute a complete chaos engineering experiment end-to-end.

It performs the 5-phase workflow:
  1. PRE-FLIGHT: Health checks, baseline collection, fleet creation
  2. HYPOTHESIS: Generate testable hypothesis from scenario
  3. PLANNING/EXECUTING: Compile plan and dispatch faults
  4. MONITORING: Observe metrics, check SLOs, detect anomalies
  5. ANALYSIS/REPORTING: Collect results and generate report

The runner manages the lifecycle of:
  - OrchestratorAgent (state machine)
  - NodeAgentCoordinator (fleet management)
  - ObserverAgent (monitoring)
  - FaultDispatcher (fault injection)
  - MessageCoordinator (inter-agent communication)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from chaoswopr.agents.fault_dispatcher import FaultDispatcher
from chaoswopr.agents.hypothesis_engine import HypothesisEngine, Hypothesis
from chaoswopr.agents.messaging.coordinator import MessageCoordinator
from chaoswopr.agents.messaging.message_bus import MessageBus
from chaoswopr.agents.messaging.protocol import (
    AgentType,
    CommandType,
    EventType,
)
from chaoswopr.agents.node_coordinator import FleetConfig, NodeAgentCoordinator
from chaoswopr.agents.observer import ObserverAgent
from chaoswopr.agents.orchestrator import ExperimentContext, OrchestratorAgent, OrchestratorState
from chaoswopr.agents.plan_compiler import ExperimentPlan, PlanCompiler
from chaoswopr.agents.prometheus_tool import PrometheusQueryTool
from chaoswopr.agents.slo_monitor import SLODefinition, SLOMonitor
from chaoswopr.infrastructure.monitoring.prometheus import PrometheusClient
from chaoswopr.safety.audit import AuditLogger
from chaoswopr.safety.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


@dataclass
class ExperimentResult:
    """Complete result of an experiment run.

    Attributes:
        experiment_id: Unique experiment identifier.
        scenario_name: Name of the scenario executed.
        hypothesis: Generated hypothesis.
        plan: Compiled experiment plan.
        observation_events: Events from the observer agent.
        metrics_snapshots: Metrics collected during the experiment.
        duration_seconds: Total experiment duration.
        halted: Whether the experiment was halted by safety systems.
        halt_reason: Reason for halting if applicable.
        fleet_status: Final status of the node agent fleet.
        success: Whether the experiment completed successfully.
        error_message: Error message if the experiment failed.
    """

    experiment_id: str = ""
    scenario_name: str = ""
    hypothesis: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None
    observation_events: list[dict[str, Any]] = field(default_factory=list)
    metrics_snapshots: list[dict[str, Any]] = field(default_factory=list)
    duration_seconds: float = 0.0
    halted: bool = False
    halt_reason: str | None = None
    fleet_status: dict[str, Any] = field(default_factory=dict)
    success: bool = False
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "experiment_id": self.experiment_id,
            "scenario_name": self.scenario_name,
            "hypothesis": self.hypothesis,
            "plan": self.plan,
            "observation_event_count": len(self.observation_events),
            "metrics_snapshot_count": len(self.metrics_snapshots),
            "duration_seconds": self.duration_seconds,
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "fleet_status": self.fleet_status,
            "success": self.success,
            "error_message": self.error_message,
        }


@dataclass
class ExperimentRunnerConfig:
    """Configuration for the ExperimentRunner.

    Attributes:
        prometheus_url: Prometheus server URL.
        fleet_config: Node agent fleet configuration.
        monitoring_interval_seconds: How often to run observation cycles.
        max_experiment_duration_seconds: Maximum experiment duration.
        dry_run: If True, run without real infrastructure.
        llm_provider: LLM provider name (openrouter, anthropic, mock).
        llm_api_key: API key for the LLM provider.
        hypothesis_model: Model for hypothesis generation.
        rca_model: Model for root cause analysis.
    """

    prometheus_url: str = "http://localhost:9090"
    fleet_config: FleetConfig = field(default_factory=FleetConfig)
    monitoring_interval_seconds: float = 5.0
    max_experiment_duration_seconds: float = 900.0
    dry_run: bool = True
    llm_provider: str = "mock"
    llm_api_key: str = ""
    hypothesis_model: str = "anthropic/claude-opus-4"
    rca_model: str = "anthropic/claude-sonnet-4.5"


class ExperimentRunner:
    """Top-level experiment runner that coordinates all agents.

    Manages the complete lifecycle of a chaos engineering experiment,
    from pre-flight checks through analysis and reporting.

    Examples:
        >>> config = ExperimentRunnerConfig(dry_run=True)
        >>> runner = ExperimentRunner(config)
        >>> scenario = {
        ...     "name": "basic_withholding",
        ...     "hypothesis": "Network maintains finality with 30% attestation withholding",
        ...     "fault_sequence": [
        ...         {"time": "0s", "action": "baseline"},
        ...         {"time": "60s", "action": "attestation_withholding", "params": {"target_percent": 30}},
        ...     ],
        ...     "slo_thresholds": {"finality_delay_max_epochs": 5},
        ... }
        >>> result = runner.run_experiment(scenario)
        >>> assert result.success
    """

    def __init__(self, config: ExperimentRunnerConfig) -> None:
        """Initialize the experiment runner.

        Args:
            config: Runner configuration.
        """
        self._config = config
        self._dry_run = config.dry_run

        # Create message bus infrastructure
        self._message_bus = MessageBus()
        self._msg_coordinator = MessageCoordinator(self._message_bus)

        # Create safety components
        self._circuit_breaker = CircuitBreaker()
        self._audit_logger = AuditLogger(default_agent_id="experiment_runner")

        # Create orchestrator
        self._orchestrator = OrchestratorAgent(
            circuit_breaker=self._circuit_breaker,
            audit_logger=self._audit_logger,
            dry_run=self._dry_run,
        )

        # Create LLM clients for hypothesis and RCA engines
        hypothesis_llm = self._create_llm_client(config, model_override=config.hypothesis_model)
        rca_llm = self._create_llm_client(config, model_override=config.rca_model)

        # Create hypothesis engine and plan compiler
        self._hypothesis_engine = HypothesisEngine(
            llm_client=hypothesis_llm,
            dry_run=self._dry_run,
        )
        self._plan_compiler = PlanCompiler(
            total_nodes=config.fleet_config.num_agents,
            dry_run=self._dry_run,
        )

        # Create node agent coordinator first (needed by fault dispatcher)
        self._node_coordinator = NodeAgentCoordinator(
            fleet_config=config.fleet_config,
            message_coordinator=self._msg_coordinator,
            audit_logger=self._audit_logger,
            dry_run=self._dry_run,
        )

        # Create fault dispatcher with node coordinator as client
        self._fault_dispatcher = FaultDispatcher(
            node_agent_client=self._node_coordinator,
            audit_logger=self._audit_logger,
            dry_run=self._dry_run,
        )

        # Create Prometheus client and query tool
        prom_client = None
        if not self._dry_run:
            try:
                from prometheus_api_client import PrometheusConnect
                prom_client = PrometheusConnect(url=config.prometheus_url, disable_ssl=True)
                logger.info(f"Prometheus client connected to {config.prometheus_url}")
            except Exception as e:
                logger.warning(f"Failed to create Prometheus client: {e}. Metrics will not be available.")

        self._prometheus_client = PrometheusClient(
            base_url=config.prometheus_url,
            client=prom_client,
        )
        self._prometheus_tool = PrometheusQueryTool(
            prometheus_client=self._prometheus_client,
            dry_run=self._dry_run,
        )

        # Create RCA engine with LLM client
        from chaoswopr.agents.rca_engine import RCAEngine

        self._rca_engine = RCAEngine(
            llm_client=rca_llm,
            dry_run=self._dry_run,
        )

        # Create observer with RCA engine
        self._observer = ObserverAgent(
            prometheus_client=self._prometheus_client,
            rca_engine=self._rca_engine,
            dry_run=self._dry_run,
        )

        # Register orchestrator and observer with message coordinator
        self._msg_coordinator.register_agent("orchestrator", AgentType.ORCHESTRATOR)
        self._msg_coordinator.register_agent("observer", AgentType.OBSERVER)

        # Experiment state
        self._current_result: ExperimentResult | None = None

    @property
    def orchestrator(self) -> OrchestratorAgent:
        """Get the orchestrator agent."""
        return self._orchestrator

    @property
    def node_coordinator(self) -> NodeAgentCoordinator:
        """Get the node agent coordinator."""
        return self._node_coordinator

    @property
    def observer(self) -> ObserverAgent:
        """Get the observer agent."""
        return self._observer

    @property
    def message_coordinator(self) -> MessageCoordinator:
        """Get the message coordinator."""
        return self._msg_coordinator

    def run_experiment(self, scenario: dict[str, Any]) -> ExperimentResult:
        """Run a complete experiment from scenario definition.

        Executes the full 5-phase workflow:
          PRE-FLIGHT -> HYPOTHESIS -> PLANNING/EXECUTING -> MONITORING -> ANALYSIS

        Args:
            scenario: Scenario definition dictionary (from YAML).

        Returns:
            ExperimentResult with complete experiment data.
        """
        result = ExperimentResult(
            scenario_name=scenario.get("name", "unknown"),
        )
        self._current_result = result

        start_time = time.monotonic()

        try:
            # Phase 1: PRE-FLIGHT
            context = self._phase_preflight(scenario)
            result.experiment_id = context.experiment_id

            # Phase 2: HYPOTHESIS
            hypothesis = self._phase_hypothesis(scenario, context)
            result.hypothesis = hypothesis.to_dict()

            # Phase 3: PLANNING
            plan = self._phase_planning(hypothesis, context)
            result.plan = plan.to_dict()

            # Phase 4: EXECUTING + MONITORING
            self._phase_execute_and_monitor(plan, context)

            # Phase 5: ANALYSIS + REPORTING
            self._phase_analysis(context)

            # Collect results
            result.observation_events = [
                e.to_dict() for e in self._observer.get_events(
                    experiment_id=context.experiment_id,
                )
            ]
            result.metrics_snapshots = context.metrics_snapshots
            result.halted = context.halted
            result.halt_reason = context.halt_reason
            result.fleet_status = self._node_coordinator.get_fleet_status()
            result.success = not context.halted

        except Exception as e:
            result.success = False
            result.error_message = str(e)
            logger.error("Experiment failed: %s", e)

            # Emergency cleanup
            try:
                if self._orchestrator.state != OrchestratorState.IDLE:
                    self._orchestrator.halt_experiment(reason=f"Error: {e}")
                    self._orchestrator.reset()
            except Exception:
                pass

        finally:
            result.duration_seconds = time.monotonic() - start_time

            # Cleanup
            self._cleanup()

        logger.info(
            "Experiment %s completed (success=%s, duration=%.1fs)",
            result.experiment_id,
            result.success,
            result.duration_seconds,
        )

        return result

    def _phase_preflight(self, scenario: dict[str, Any]) -> ExperimentContext:
        """Execute the PRE-FLIGHT phase.

        - Start experiment in orchestrator
        - Run health checks
        - Create and start node agent fleet
        - Establish baseline metrics
        - Start observer

        Args:
            scenario: Scenario definition.

        Returns:
            ExperimentContext for the running experiment.
        """
        logger.info("=== PRE-FLIGHT PHASE ===")

        # Start experiment in orchestrator (transitions to PRE_FLIGHT)
        context = self._orchestrator.start_experiment(scenario)

        # Run pre-flight health check
        health = self._prometheus_tool.pre_flight_health_check()
        context.add_event("health_check", health.to_dict())

        # Create and start node agent fleet
        if not self._node_coordinator.fleet_created:
            fleet_result = self._node_coordinator.create_fleet()
            context.add_event("fleet_created", fleet_result)

        start_result = self._node_coordinator.start_all()
        context.add_event("fleet_started", start_result)

        # Collect baseline metrics
        baseline = self._prometheus_tool.collect_baseline()
        baseline_values = {
            name: summary.mean for name, summary in baseline.items()
        }
        context.add_event("baseline_collected", {"metrics": baseline_values})

        # Start observer
        self._observer.start_observing(experiment_id=context.experiment_id)

        # Emit experiment started event
        self._msg_coordinator.emit_event(
            source_agent_id="orchestrator",
            event_type=EventType.EXPERIMENT_STARTED,
            experiment_id=context.experiment_id,
            details={"scenario": scenario.get("name", "unknown")},
        )

        # Advance to HYPOTHESIS
        self._orchestrator.advance()

        return context

    def _phase_hypothesis(
        self,
        scenario: dict[str, Any],
        context: ExperimentContext,
    ) -> Hypothesis:
        """Execute the HYPOTHESIS phase.

        Generate a testable hypothesis from the scenario.

        Args:
            scenario: Scenario definition.
            context: Experiment context.

        Returns:
            Generated Hypothesis.
        """
        logger.info("=== HYPOTHESIS PHASE ===")

        # Query current cluster state for hypothesis calibration
        cluster_state = self._prometheus_tool.query_all()

        # Generate hypothesis
        hypothesis = self._hypothesis_engine.generate(
            scenario=scenario,
            cluster_state=cluster_state,
        )

        context.hypothesis = hypothesis.to_dict()
        context.add_event("hypothesis_generated", {
            "hypothesis_id": hypothesis.hypothesis_id,
            "prediction": hypothesis.prediction,
            "blast_radius_percent": hypothesis.blast_radius_percent,
            "confidence": hypothesis.confidence,
        })

        # Advance to PLANNING
        self._orchestrator.advance()

        return hypothesis

    def _phase_planning(
        self,
        hypothesis: Hypothesis,
        context: ExperimentContext,
    ) -> ExperimentPlan:
        """Execute the PLANNING phase.

        Compile the hypothesis into an executable experiment plan.

        Args:
            hypothesis: Generated hypothesis.
            context: Experiment context.

        Returns:
            Compiled ExperimentPlan.
        """
        logger.info("=== PLANNING PHASE ===")

        # Get available node IDs for target resolution
        available_nodes = self._node_coordinator.get_agent_ids()

        # Compile plan
        plan = self._plan_compiler.compile(
            hypothesis=hypothesis,
            available_nodes=available_nodes,
        )

        context.plan = plan.to_dict()
        context.add_event("plan_compiled", {
            "plan_id": plan.plan_id,
            "action_count": len(plan.actions),
            "total_duration_seconds": plan.total_duration_seconds,
        })

        # Advance to EXECUTING
        self._orchestrator.advance()

        return plan

    def _phase_execute_and_monitor(
        self,
        plan: ExperimentPlan,
        context: ExperimentContext,
    ) -> None:
        """Execute the EXECUTING and MONITORING phases.

        Dispatch fault injections and monitor the experiment.

        Args:
            plan: Experiment plan to execute.
            context: Experiment context.
        """
        logger.info("=== EXECUTING PHASE ===")

        # Dispatch the experiment plan
        dispatch_summary = self._fault_dispatcher.dispatch_plan(plan)
        context.add_event("faults_dispatched", dispatch_summary.to_dict())

        # Emit fault injection events
        self._msg_coordinator.emit_event(
            source_agent_id="orchestrator",
            event_type=EventType.FAULT_INJECTED,
            experiment_id=context.experiment_id,
            details={"dispatch_summary": dispatch_summary.to_dict()},
        )

        # Advance to MONITORING
        self._orchestrator.advance()

        logger.info("=== MONITORING PHASE ===")

        # Run monitoring cycles
        monitoring_start = time.monotonic()
        max_duration = min(
            self._config.max_experiment_duration_seconds,
            plan.total_duration_seconds + 60,  # Extra 60s for recovery observation
        )

        cycle = 0
        while (time.monotonic() - monitoring_start) < max_duration:
            cycle += 1

            # Check circuit breaker
            if self._circuit_breaker.is_tripped:
                context.halted = True
                context.halt_reason = "Circuit breaker tripped"
                break

            # Run observer cycle
            events = self._observer.observe()

            # Record any detected anomalies
            for event in events:
                context.add_event(event.event_type.value, event.to_dict())

            # Record metrics snapshot
            current_metrics = self._prometheus_tool.query_all()
            self._orchestrator.record_metrics(current_metrics)
            context.metrics_snapshots.append({
                "cycle": cycle,
                "metrics": current_metrics,
            })

            # In dry-run mode, don't actually wait
            if self._dry_run:
                # Run a few cycles then exit
                if cycle >= 3:
                    break
            else:
                time.sleep(self._config.monitoring_interval_seconds)

        # Remove all faults
        self._fault_dispatcher.remove_all_faults()
        self._msg_coordinator.emit_event(
            source_agent_id="orchestrator",
            event_type=EventType.FAULT_REMOVED,
            experiment_id=context.experiment_id,
        )

        # Advance to ANALYZING
        self._orchestrator.advance()

    def _phase_analysis(self, context: ExperimentContext) -> None:
        """Execute the ANALYSIS and REPORTING phases.

        Collect results and generate experiment report.

        Args:
            context: Experiment context.
        """
        logger.info("=== ANALYSIS PHASE ===")

        # Stop observer
        self._observer.stop_observing()

        # Collect observer events
        observer_events = self._observer.get_events(
            experiment_id=context.experiment_id,
        )
        context.add_event("analysis_complete", {
            "observation_event_count": len(observer_events),
            "metrics_snapshot_count": len(context.metrics_snapshots),
        })

        # Advance to REPORTING
        self._orchestrator.advance()

        logger.info("=== REPORTING PHASE ===")

        # Generate experiment report
        report = {
            "experiment_id": context.experiment_id,
            "scenario": context.scenario.get("name", "unknown"),
            "hypothesis": context.hypothesis,
            "duration_seconds": context.duration_seconds(),
            "halted": context.halted,
            "observation_events": len(observer_events),
            "metrics_snapshots": len(context.metrics_snapshots),
        }
        context.add_event("report_generated", report)

        # Emit completion event
        self._msg_coordinator.emit_event(
            source_agent_id="orchestrator",
            event_type=EventType.EXPERIMENT_COMPLETED,
            experiment_id=context.experiment_id,
            details=report,
        )

        # Advance to IDLE (finalize experiment)
        self._orchestrator.advance()

    def _cleanup(self) -> None:
        """Clean up after an experiment."""
        # Stop observer if still running
        if self._observer.state.value != "idle":
            self._observer.stop_observing()

        # Remove any remaining faults
        self._fault_dispatcher.remove_all_faults()

        # Stop node agents
        self._node_coordinator.stop_all()

    @staticmethod
    def _create_llm_client(
        config: ExperimentRunnerConfig,
        model_override: str | None = None,
    ) -> Any:
        """Create an LLM client from runner configuration.

        Returns None if dry_run is True or provider is mock, which causes
        downstream engines to use their template/mock fallbacks.

        Args:
            config: Runner configuration.
            model_override: Override the model for this client.

        Returns:
            LLMClient instance or None.
        """
        if config.dry_run or config.llm_provider == "mock":
            return None

        try:
            from chaoswopr.agents.llm_client import create_llm_client

            return create_llm_client(
                provider=config.llm_provider,
                api_key=config.llm_api_key,
                model=model_override,
            )
        except (ValueError, ImportError) as e:
            logger.warning("Failed to create LLM client: %s. Using mock fallback.", e)
            return None

    def get_status(self) -> dict[str, Any]:
        """Get the current runner status.

        Returns:
            Status dictionary.
        """
        return {
            "orchestrator_state": self._orchestrator.state.value,
            "observer_state": self._observer.state.value,
            "fleet_status": self._node_coordinator.get_fleet_status(),
            "bus_stats": self._message_bus.get_stats(),
            "experiment_count": self._orchestrator.experiment_count,
            "dry_run": self._dry_run,
        }
