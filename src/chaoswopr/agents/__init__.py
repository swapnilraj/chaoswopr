"""Agent system for chaoswopr.

This module contains the multi-agent system including:
- Orchestrator Agent: Master controller coordinating experiments (Track E)
- Node Agents: AI agents controlling individual validator nodes (Track F)
- Observer Agent: Specialized anomaly detection and root cause analysis (Track G)
"""

from __future__ import annotations

# Orchestrator Agent (Track E)
from chaoswopr.agents.fault_dispatcher import (
    DispatchResult,
    DispatchSummary,
    FaultDispatcher,
)
from chaoswopr.agents.hypothesis_engine import (
    ExpectedMetric,
    FaultAction,
    FaultLevel,
    Hypothesis,
    HypothesisEngine,
    HypothesisStatus,
)
from chaoswopr.agents.orchestrator import (
    ExperimentContext,
    OrchestratorAgent,
    OrchestratorState,
)
from chaoswopr.agents.plan_compiler import (
    ExperimentPlan,
    PlanAction,
    PlanCompiler,
    RollbackCondition,
)
from chaoswopr.agents.prometheus_tool import (
    HealthCheckResult,
    MetricSample,
    MetricSummary,
    PrometheusQueryTool,
)

# Node Agents (Track F)
from chaoswopr.agents.node_agent import (
    AgentMode,
    NodeAgent,
    NodeAgentConfig,
    NodeAgentStatus,
)

# Observer Agent (Track G)
from chaoswopr.agents.anomaly_detection import (
    Anomaly,
    AnomalyDetector,
    AnomalyType,
)
from chaoswopr.agents.observer import (
    ObservationEvent,
    ObservationEventType,
    ObserverAgent,
    ObserverState,
)
from chaoswopr.agents.rag_pipeline import (
    Document,
    RAGPipeline,
    RetrievalResult,
)
from chaoswopr.agents.rca_engine import (
    RCAEngine,
    RCAHypothesis,
    RCAResult,
)
from chaoswopr.agents.slo_monitor import (
    SLODefinition,
    SLOMonitor,
)

__all__ = [
    # Orchestrator Agent (Track E)
    "OrchestratorAgent",
    "OrchestratorState",
    "ExperimentContext",
    "HypothesisEngine",
    "Hypothesis",
    "HypothesisStatus",
    "FaultAction",
    "FaultLevel",
    "ExpectedMetric",
    "PlanCompiler",
    "ExperimentPlan",
    "PlanAction",
    "RollbackCondition",
    "FaultDispatcher",
    "DispatchResult",
    "DispatchSummary",
    "PrometheusQueryTool",
    "MetricSample",
    "MetricSummary",
    "HealthCheckResult",
    # Node Agents (Track F)
    "NodeAgent",
    "NodeAgentConfig",
    "AgentMode",
    "NodeAgentStatus",
    # Observer Agent (Track G)
    "ObserverAgent",
    "ObserverState",
    "ObservationEvent",
    "ObservationEventType",
    # Anomaly Detection
    "AnomalyDetector",
    "Anomaly",
    "AnomalyType",
    # SLO Monitoring
    "SLOMonitor",
    "SLODefinition",
    # RCA Engine
    "RCAEngine",
    "RCAHypothesis",
    "RCAResult",
    # RAG Pipeline
    "RAGPipeline",
    "Document",
    "RetrievalResult",
]
