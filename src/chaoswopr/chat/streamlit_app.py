#!/usr/bin/env python3
"""Streamlit Chat Interface for ChaosWopr.

A comprehensive chat UI that exposes ALL chaos engineering functions via LLM tool calling.

Features:
- 64 tools across 6 categories (infrastructure, observability, experiment, analysis, safety, agents)
- Safety tier enforcement with approval workflows
- Conversation context tracking
- Multi-step operation support

Run with:
    streamlit run src/chaoswopr/chat/streamlit_app.py
"""

import json
import os
import sys
from pathlib import Path

import streamlit as st

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

# Load .env file
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

# Import tool framework
from chaoswopr.chat.tools import (
    TOOLS_REGISTRY,
    get_tools_for_llm,
    execute_tool,
    SafetyTier,
)
from chaoswopr.chat.conversation_context import ConversationContext
from chaoswopr.chat.approval_workflows import request_approval

# Try to import LLMConfig, fallback if not available
try:
    from config.llm_config import LLMConfig
except ImportError:
    # Fallback: just get API key from env
    LLMConfig = None


# ============================================================================
# Streamlit Session State Initialization
# ============================================================================

def initialize_session_state():
    """Initialize session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": """👋 Hi! I'm your chaos engineering assistant.

I can help you:
- 🔍 **Explore** chaos scenarios and testnet infrastructure
- 📊 **Analyze** experiment results and metrics
- 🎯 **Design** custom scenarios
- 🚀 **Run** controlled chaos experiments
- 🛡️ **Monitor** safety systems and circuit breakers

**Quick Start:**
- Ask "What scenarios are available?"
- Deploy a testnet: "Deploy a testnet with 256 validators"
- Check status: "Is there a testnet running?"

What would you like to explore?""",
            }
        ]

    if "chaoswopr_context" not in st.session_state:
        st.session_state.chaoswopr_context = ConversationContext()

    if "pending_approval" not in st.session_state:
        st.session_state.pending_approval = None


# ============================================================================
# LLM Integration
# ============================================================================

def call_llm_with_tools(messages: list) -> dict:
    """Call LLM with tool calling enabled.

    Uses OpenRouter API for Claude Opus with tool calling support.
    """
    import requests

    # Get API key
    if LLMConfig:
        llm_config = LLMConfig.from_env()
        api_key = llm_config.api_key or os.getenv("OPENROUTER_API_KEY")
    else:
        api_key = os.getenv("OPENROUTER_API_KEY")

    if not api_key:
        return {
            "role": "assistant",
            "content": "Error: OPENROUTER_API_KEY not configured. Please set it in .env file.",
        }

    # Get all tools in OpenAI-compatible format
    tools = get_tools_for_llm()

    # OpenRouter supports OpenAI-compatible tool calling
    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "anthropic/claude-opus-4",
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        },
        timeout=60,
    )

    if response.status_code != 200:
        return {
            "role": "assistant",
            "content": f"Error calling LLM: {response.status_code} - {response.text[:500]}",
        }

    # Try to parse JSON with better error handling
    try:
        result = response.json()
    except Exception as e:
        return {
            "role": "assistant",
            "content": f"Error parsing LLM response: {e}\n\nResponse preview:\n{response.text[:500]}",
        }

    # Check if response has expected structure
    if "choices" not in result or not result["choices"]:
        return {
            "role": "assistant",
            "content": f"Unexpected LLM response format: {result}",
        }

    return result["choices"][0]["message"]


# ============================================================================
# Tool Execution with Approval
# ============================================================================

def execute_tool_with_approval(tool_name: str, arguments: dict) -> str:
    """Execute a tool with safety tier checks and approval workflows.

    Args:
        tool_name: Name of the tool to execute
        arguments: Tool arguments

    Returns:
        Result string (markdown formatted)
    """
    # Get tool definition
    tool_def = TOOLS_REGISTRY.get(tool_name)
    if not tool_def:
        return f"❌ Unknown tool: {tool_name}"

    safety_tier = tool_def["safety_tier"]
    context = st.session_state.chaoswopr_context

    # Check if approval is needed
    if safety_tier >= SafetyTier.INFRASTRUCTURE:
        # Request approval
        approved = request_approval(tool_name, arguments, context)

        if not approved:
            return f"❌ Operation canceled by user: {tool_name}"

        # Execute with approval granted
        return execute_tool(tool_name, arguments, context, approval_granted=True)
    else:
        # No approval needed (READ_ONLY or DESIGN tier)
        return execute_tool(tool_name, arguments, context, approval_granted=False)


# ============================================================================
# Main Streamlit UI
# ============================================================================

def main():
    st.set_page_config(
        page_title="ChaosWopr Chat - Comprehensive Interface",
        page_icon="🔥",
        layout="wide",
    )

    # Initialize session state
    initialize_session_state()

    st.title("🔥 ChaosWopr Chat")
    st.caption("AI-powered Ethereum chaos engineering - **64 tools across 6 categories**")

    # Sidebar
    with st.sidebar:
        st.header("About")
        st.markdown(f"""
        **Tool Coverage:**
        - 🏗️ Infrastructure: 12 tools
        - 🔍 Observability: 15 tools
        - 🎯 Experiment: 16 tools
        - 📊 Analysis: 10 tools
        - 🛡️ Safety: 5 tools
        - 🤖 Agents: 6 tools

        **Total: {len(TOOLS_REGISTRY)} tools**

        **Safety Tiers:**
        - 🟢 Read-Only: No approval
        - 🟡 Design: No approval
        - 🟠 Infrastructure: Approval required
        - 🔴 Chaos: Approval + confirmation
        - ⛔ Safety Override: Warning + confirmation
        """)

        st.divider()

        # Check API key
        api_key = os.getenv("OPENROUTER_API_KEY")
        if api_key:
            st.success("✅ OpenRouter API configured")
        else:
            st.error("❌ OPENROUTER_API_KEY not set")
            st.info("Add to .env file to enable LLM")

        st.divider()

        st.header("Quick Actions")
        if st.button("📋 List Scenarios"):
            st.session_state.messages.append(
                {"role": "user", "content": "What scenarios are available?"}
            )
            st.rerun()

        if st.button("🔍 Check Testnet"):
            st.session_state.messages.append(
                {"role": "user", "content": "Is there a testnet running?"}
            )
            st.rerun()

        if st.button("📊 List All Tools"):
            st.session_state.messages.append(
                {"role": "user", "content": "Show me all available tools"}
            )
            st.rerun()

        st.divider()

        # Context display
        st.header("Context")
        context = st.session_state.chaoswopr_context

        if context.current_enclave_name:
            st.info(f"**Enclave:** {context.current_enclave_name}")
        if context.current_experiment_id:
            st.info(f"**Experiment:** {context.current_experiment_id[:8]}...")

        if st.button("🔄 Clear Context"):
            context.clear()
            st.success("Context cleared!")
            st.rerun()

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("Ask about chaos scenarios, design experiments, or analyze results..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Call LLM with tool calling
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                # Call LLM
                response = call_llm_with_tools(
                    messages=st.session_state.messages,
                )

                # Check if LLM wants to use a tool
                if response.get("tool_calls"):
                    tool_call = response["tool_calls"][0]
                    tool_name = tool_call["function"]["name"]
                    arguments = json.loads(tool_call["function"]["arguments"])

                    # Show what tool is being called
                    tool_def = TOOLS_REGISTRY.get(tool_name)
                    if tool_def:
                        safety_icon = {
                            SafetyTier.READ_ONLY: "🟢",
                            SafetyTier.DESIGN: "🟡",
                            SafetyTier.INFRASTRUCTURE: "🟠",
                            SafetyTier.CHAOS: "🔴",
                            SafetyTier.SAFETY_OVERRIDE: "⛔",
                        }.get(tool_def["safety_tier"], "❓")

                        st.info(f"{safety_icon} Using tool: `{tool_name}`")

                    # Execute tool with approval workflow
                    tool_result = execute_tool_with_approval(tool_name, arguments)

                    # Show result
                    st.markdown(tool_result)

                    # Save assistant response
                    st.session_state.messages.append(
                        {"role": "assistant", "content": tool_result}
                    )

                else:
                    # Regular text response
                    content = response.get("content", "Sorry, I couldn't generate a response.")
                    st.markdown(content)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": content}
                    )


if __name__ == "__main__":
    main()
