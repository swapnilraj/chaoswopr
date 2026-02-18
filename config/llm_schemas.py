"""JSON schemas for structured LLM output.

Defines the expected JSON structure for LLM responses used by:
  - HypothesisEngine: Generating structured hypotheses
  - RCAEngine: Root cause analysis results

These schemas are passed to the LLM as part of the prompt to ensure
structured, parseable output that downstream components can process
deterministically.
"""

from __future__ import annotations

from typing import Any

# Schema for hypothesis generation output
HYPOTHESIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "prediction": {
            "type": "string",
            "description": "What we predict will happen under the specified fault conditions",
        },
        "rationale": {
            "type": "string",
            "description": "Technical reasoning for why we expect this outcome",
        },
        "blast_radius_percent": {
            "type": "number",
            "minimum": 0,
            "maximum": 33,
            "description": "Maximum percentage of nodes affected (must not exceed 33%)",
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Confidence level in the prediction (0.0 to 1.0)",
        },
        "fault_timeline": {
            "type": "array",
            "description": "Ordered sequence of fault injection actions",
            "items": {
                "type": "object",
                "properties": {
                    "time_offset_seconds": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "When to execute this action relative to experiment start",
                    },
                    "action_type": {
                        "type": "string",
                        "description": "Type of fault to inject (e.g., inject_network_latency, attestation_withholding, kill_nodes, cpu_stress, baseline, observe, remove_faults, complete)",
                    },
                    "fault_level": {
                        "type": "string",
                        "enum": ["network", "node", "protocol"],
                        "description": "Level at which the fault operates",
                    },
                    "target_percent": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 33,
                        "description": "Percentage of nodes to target (0 for non-fault actions)",
                    },
                    "parameters": {
                        "type": "object",
                        "description": "Fault-specific parameters (e.g., latency_ms, loss_percent)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Human-readable description of this action",
                    },
                },
                "required": ["time_offset_seconds", "action_type", "fault_level", "target_percent"],
            },
        },
        "expected_metrics": {
            "type": "array",
            "description": "Predicted metric ranges during/after fault injection",
            "items": {
                "type": "object",
                "properties": {
                    "metric_name": {"type": "string"},
                    "baseline_value": {"type": "number"},
                    "expected_min": {"type": "number"},
                    "expected_max": {"type": "number"},
                    "recovery_time_seconds": {"type": "integer"},
                },
                "required": ["metric_name"],
            },
        },
        "success_criteria": {
            "type": "string",
            "description": "Conditions that confirm the hypothesis",
        },
        "failure_criteria": {
            "type": "string",
            "description": "Conditions that refute the hypothesis",
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Classification tags for the hypothesis",
        },
    },
    "required": [
        "prediction",
        "rationale",
        "blast_radius_percent",
        "confidence",
        "fault_timeline",
        "success_criteria",
    ],
}

# Schema for root cause analysis output
RCA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "hypotheses": {
            "type": "array",
            "description": "Root cause hypotheses ordered by confidence",
            "items": {
                "type": "object",
                "properties": {
                    "root_cause": {
                        "type": "string",
                        "description": "Description of the hypothesized root cause",
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": "Confidence score (0.0 to 1.0)",
                    },
                    "evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Evidence supporting this hypothesis",
                    },
                    "recommendations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Recommended actions for operators",
                    },
                },
                "required": ["root_cause", "confidence", "evidence", "recommendations"],
            },
        },
    },
    "required": ["hypotheses"],
}

# System prompts for different LLM use cases
HYPOTHESIS_SYSTEM_PROMPT = """You are an expert Ethereum consensus layer engineer specializing in chaos engineering and resilience testing.

Your role is to generate structured, testable hypotheses for chaos experiments on Ethereum testnets.

Key constraints:
- Blast radius must NEVER exceed 33% of nodes (Ethereum's fault tolerance threshold)
- Fault timeline must be chronologically ordered
- Each fault action's target_percent must not exceed the overall blast_radius_percent
- Predictions must be specific and falsifiable
- Success criteria must be measurable
- Rationale must reference actual Ethereum consensus mechanisms

Fault levels:
- "network": tc/netem-based (latency, packet loss, partitions)
- "node": chaos-mesh-based (pod kills, CPU/memory stress)
- "protocol": Custom injectors (attestation withholding, equivocation, censorship)

Common action types:
- baseline: Collect baseline metrics (target_percent=0)
- inject_network_latency: Add latency to node connections
- inject_packet_loss: Drop packets on node connections
- kill_nodes: Terminate validator nodes
- attestation_withholding: Withhold attestations from validators
- cpu_stress: Apply CPU stress to nodes
- observe: Passive observation period (target_percent=0)
- remove_faults: Remove all injected faults (target_percent=0)
- complete: Mark experiment complete (target_percent=0)

Always structure your response as valid JSON matching the provided schema."""

RCA_SYSTEM_PROMPT = """You are an expert Ethereum consensus layer engineer performing root cause analysis on testnet anomalies.

Your role is to analyze observation events and metrics to determine the most likely root causes of detected issues.

When analyzing:
1. Consider Ethereum-specific failure modes (finality delays, participation drops, slashing)
2. Cross-reference multiple metrics for correlated failures
3. Distinguish between network-level, node-level, and protocol-level causes
4. Provide actionable recommendations for operators
5. Assign calibrated confidence scores (0.0-1.0)

Key Ethereum metrics to consider:
- finality_delay_seconds: Time since last finalized epoch
- participation_rate_percent: Validator participation rate
- slashing_rate_percent: Rate of slashing events
- attestation_inclusion_delay: Average attestation inclusion delay
- block_proposal_rate: Rate of successful block proposals

Always structure your response as valid JSON matching the provided schema."""
