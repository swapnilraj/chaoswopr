"""Agent system for chaoswopr.

This module contains the multi-agent system including:
- Orchestrator Agent: Master controller coordinating experiments (Track E)
- Node Agents: AI agents controlling individual validator nodes (Track F)
- Observer Agent: Specialized anomaly detection and root cause analysis (Track G)
- LLM Clients: OpenRouter, Anthropic, and Mock LLM integrations
- Messaging: Inter-agent communication infrastructure
- Experiment Runner: Top-level end-to-end experiment orchestration
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
from chaoswopr.agents.node_coordinator import (
    FleetConfig,
    NodeAgentCoordinator,
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

# Messaging Infrastructure
from chaoswopr.agents.messaging import (
    AgentRegistry,
    AgentState,
    AgentType,
    Command,
    CommandType,
    Event,
    EventType,
    Message,
    MessageBus,
    MessageCoordinator,
    MessageType,
    Response,
    StatusUpdate,
    Subscription,
)

# LLM Clients
from chaoswopr.agents.llm_client import (
    AnthropicLLMClient,
    LLMClient,
    LLMResponse,
    MockLLMClient,
    create_llm_client,
    create_llm_client_from_config,
)
from chaoswopr.agents.openrouter_client import (
    OpenRouterAPIError,
    OpenRouterLLMClient,
)

# Experiment Runner (End-to-End)
from chaoswopr.agents.experiment_runner import (
    ExperimentResult,
    ExperimentRunner,
    ExperimentRunnerConfig,
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
    "FleetConfig",
    "NodeAgentCoordinator",
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
    # Messaging Infrastructure
    "Message",
    "MessageType",
    "Command",
    "CommandType",
    "Response",
    "StatusUpdate",
    "Event",
    "EventType",
    "AgentType",
    "MessageBus",
    "Subscription",
    "MessageCoordinator",
    "AgentRegistry",
    "AgentState",
    # LLM Clients
    "LLMClient",
    "LLMResponse",
    "MockLLMClient",
    "AnthropicLLMClient",
    "OpenRouterLLMClient",
    "OpenRouterAPIError",
    "create_llm_client",
    "create_llm_client_from_config",
    # Experiment Runner
    "ExperimentRunner",
    "ExperimentRunnerConfig",
    "ExperimentResult",
]
