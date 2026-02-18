"""Core tool registry and execution framework for ChaosWopr chat interface.

Provides:
- SafetyTier enum for categorizing tool safety levels
- Tool registration decorator
- Parameter validation
- Tool execution with safety checks
- Result formatting
"""

import json
import logging
from enum import IntEnum
from functools import wraps
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class SafetyTier(IntEnum):
    """Safety tiers for tool execution.

    Higher tiers require more stringent approval workflows.
    """
    READ_ONLY = 1  # No approval needed (get_*, list_*, check_*, view_*)
    DESIGN = 2  # No approval needed (hypothesis, scenario design, validation)
    INFRASTRUCTURE = 3  # Approval required (deploy, scale, destroy testnet)
    CHAOS = 4  # Approval + confirmation (run experiment, inject faults)
    SAFETY_OVERRIDE = 5  # Approval + warning (kill switch, restore snapshot)


# Global tool registry
TOOLS_REGISTRY: dict[str, dict] = {}
TOOL_IMPLEMENTATIONS: dict[str, Callable] = {}


def register_tool(
    name: str,
    safety_tier: SafetyTier,
    description: str,
    parameters: dict,
) -> Callable:
    """Decorator to register a tool in the global registry.

    Args:
        name: Tool name (must be unique)
        safety_tier: Safety tier for approval workflow
        description: Human-readable description for LLM
        parameters: JSON Schema for parameters (OpenAI-compatible)

    Returns:
        Decorator function

    Example:
        @register_tool(
            name="deploy_testnet",
            safety_tier=SafetyTier.INFRASTRUCTURE,
            description="Deploy an Ethereum testnet",
            parameters={
                "type": "object",
                "properties": {
                    "num_validators": {"type": "integer", "default": 256}
                },
                "required": ["num_validators"]
            }
        )
        def deploy_testnet(num_validators: int) -> str:
            # Implementation
            pass
    """
    def decorator(func: Callable) -> Callable:
        # Register tool definition
        TOOLS_REGISTRY[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "safety_tier": safety_tier,
        }

        # Register implementation
        TOOL_IMPLEMENTATIONS[name] = func

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        return wrapper

    return decorator


def validate_tool_params(tool_name: str, arguments: dict) -> tuple[bool, Optional[str]]:
    """Validate tool parameters against schema and custom rules.

    Args:
        tool_name: Name of the tool
        arguments: Tool arguments to validate

    Returns:
        (is_valid, error_message) tuple
    """
    tool_def = TOOLS_REGISTRY.get(tool_name)
    if not tool_def:
        return False, f"Unknown tool: {tool_name}"

    # Custom validation rules
    # Blast radius validation
    if "blast_radius_percent" in arguments:
        value = arguments["blast_radius_percent"]
        if value < 0 or value > 33:
            return False, f"blast_radius_percent must be 0-33%, got {value}%"

    # Node count validation (must be divisible by 128)
    if "num_validators" in arguments:
        value = arguments["num_validators"]
        if value % 128 != 0:
            return False, f"num_validators must be divisible by 128, got {value}"
        if value > 512:
            return False, f"num_validators max is 512, got {value}"

    # Target percent validation
    if "target_percent" in arguments:
        value = arguments["target_percent"]
        if value < 0 or value > 33:
            return False, f"target_percent must be 0-33%, got {value}%"

    # Timeout validation
    if "timeout_seconds" in arguments:
        value = arguments["timeout_seconds"]
        if value < 0 or value > 3600:
            return False, f"timeout_seconds must be 0-3600, got {value}"

    return True, None


def execute_tool(
    tool_name: str,
    arguments: dict,
    context: Any = None,
    approval_granted: bool = False,
) -> str:
    """Execute a tool with safety checks and error handling.

    Args:
        tool_name: Name of the tool to execute
        arguments: Tool arguments (already validated by LLM)
        context: ConversationContext instance
        approval_granted: Whether user has approved (for Tier 3+)

    Returns:
        Formatted result string (markdown)
    """
    # 1. Validate tool exists
    if tool_name not in TOOLS_REGISTRY:
        return f"❌ Unknown tool: {tool_name}"

    tool_def = TOOLS_REGISTRY[tool_name]

    # 2. Validate parameters
    is_valid, error_msg = validate_tool_params(tool_name, arguments)
    if not is_valid:
        return f"❌ Parameter validation failed: {error_msg}"

    # 3. Check safety tier (approval should be handled in streamlit_app.py)
    safety_tier = tool_def["safety_tier"]
    if safety_tier >= SafetyTier.INFRASTRUCTURE and not approval_granted:
        return f"⚠️ This operation requires approval (Safety Tier {safety_tier.name})"

    # 4. Execute with error handling
    try:
        implementation = TOOL_IMPLEMENTATIONS[tool_name]

        # Pass context if implementation supports it
        if context is not None and "context" in implementation.__code__.co_varnames:
            result = implementation(context=context, **arguments)
        else:
            result = implementation(**arguments)

        # 5. Log successful execution
        logger.info(f"Tool executed successfully: {tool_name}")

        return result

    except Exception as e:
        logger.error(f"Tool execution failed: {tool_name} - {e}", exc_info=True)
        return format_error(tool_name, e)


def format_error(tool_name: str, error: Exception) -> str:
    """Format error message for chat display.

    Args:
        tool_name: Tool that failed
        error: Exception raised

    Returns:
        Formatted error message (markdown)
    """
    error_msg = str(error)

    # Provide helpful context based on error type
    if "connection" in error_msg.lower():
        hint = "Check if Kurtosis engine is running: `kurtosis engine status`"
    elif "not found" in error_msg.lower():
        hint = "Resource may not exist. Use list/check tools to verify."
    elif "timeout" in error_msg.lower():
        hint = "Operation timed out. Try increasing timeout or checking infrastructure."
    else:
        hint = "Check logs for details."

    return f"""❌ **{tool_name} Failed**

**Error:** {error_msg}

**Troubleshooting:** {hint}
"""


def format_tool_result(tool_name: str, result: Any) -> str:
    """Format tool result for chat display (if not already formatted).

    Most tools return pre-formatted markdown strings, but this handles
    cases where raw data is returned.

    Args:
        tool_name: Tool that was executed
        result: Result returned by tool

    Returns:
        Formatted result (markdown)
    """
    # If already a string, assume it's formatted
    if isinstance(result, str):
        return result

    # If dict, format as JSON
    if isinstance(result, dict):
        return f"""**{tool_name} Result:**

```json
{json.dumps(result, indent=2)}
```
"""

    # If list, format as bullets
    if isinstance(result, list):
        items = "\n".join(f"- {item}" for item in result)
        return f"""**{tool_name} Result:**

{items}
"""

    # Default: convert to string
    return f"""**{tool_name} Result:**

{result}
"""


def get_tools_for_llm() -> list[dict]:
    """Get tool definitions in OpenAI-compatible format for LLM.

    Returns:
        List of tool definitions
    """
    return [
        {
            "name": tool_def["name"],
            "description": tool_def["description"],
            "parameters": tool_def["parameters"],
        }
        for tool_def in TOOLS_REGISTRY.values()
    ]
