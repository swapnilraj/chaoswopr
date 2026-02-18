"""ChaosWopr Chat Tools.

This package provides all chat tools organized by category:
- infrastructure: Testnet, monitoring, metrics (12 tools)
- observability: Inspection, state visibility (15 tools)
- experiment: Scenarios, execution, faults (16 tools)
- analysis: Results, anomalies, RCA (10 tools)
- safety: Circuit breakers, snapshots (5 tools)
- agents: Fleet, orchestrator, observer (6 tools)

Total: 64 tools

Usage:
    from chaoswopr.chat.tools import TOOLS_REGISTRY, execute_tool

    # Get all tools for LLM
    tools = get_tools_for_llm()

    # Execute a tool
    result = execute_tool("deploy_testnet", {"num_validators": 256})
"""

from chaoswopr.chat.tools.base import (
    TOOLS_REGISTRY,
    TOOL_IMPLEMENTATIONS,
    SafetyTier,
    execute_tool,
    get_tools_for_llm,
    register_tool,
    validate_tool_params,
)

# Import all tool modules to trigger registration
try:
    from chaoswopr.chat.tools import infrastructure
except ImportError as e:
    import warnings
    warnings.warn(f"Could not import infrastructure tools: {e}")

try:
    from chaoswopr.chat.tools import observability
except ImportError as e:
    import warnings
    warnings.warn(f"Could not import observability tools: {e}")

try:
    from chaoswopr.chat.tools import experiment
except ImportError as e:
    import warnings
    warnings.warn(f"Could not import experiment tools: {e}")

try:
    from chaoswopr.chat.tools import analysis
except ImportError as e:
    import warnings
    warnings.warn(f"Could not import analysis tools: {e}")

try:
    from chaoswopr.chat.tools import safety
except ImportError as e:
    import warnings
    warnings.warn(f"Could not import safety tools: {e}")

try:
    from chaoswopr.chat.tools import agents
except ImportError as e:
    import warnings
    warnings.warn(f"Could not import agents tools: {e}")


__all__ = [
    "TOOLS_REGISTRY",
    "TOOL_IMPLEMENTATIONS",
    "SafetyTier",
    "execute_tool",
    "get_tools_for_llm",
    "register_tool",
    "validate_tool_params",
]
