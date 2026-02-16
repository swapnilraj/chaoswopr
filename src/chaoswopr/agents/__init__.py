"""Agent system for chaoswopr.

This module contains the multi-agent system including:
- Node Agents: AI agents controlling individual validator nodes
- Observer Agent: Specialized anomaly detection and root cause analysis
- Orchestrator Agent: Master controller coordinating experiments (future)
"""

from __future__ import annotations

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
