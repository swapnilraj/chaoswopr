# Chat Interface for ChaosWopr - Assessment & Roadmap

## Is the Current Code a Good Foundation? ✅ **YES!**

### What You Already Have (Perfect for Tool Calling)

| Component | Status | Ready for Tools? |
|-----------|--------|------------------|
| **KurtosisClient** | ✅ Working | Yes - `deploy_testnet()`, `list_enclaves()` |
| **ExperimentRunner** | ✅ Working | Yes - `run_experiment()` |
| **FaultDispatcher** | ✅ Fixed (wired!) | Yes - `inject_fault()` |
| **PrometheusClient** | ✅ Fixed (URL!) | Yes - `query()`, `query_range()` |
| **HypothesisEngine** | ✅ Working | Yes - Already uses LLM! |
| **ScenarioBuilder** | ✅ Working | Yes - `attestation_withholding()`, etc. |
| **NodeAgentCoordinator** | ✅ Working | Yes - `create_fleet()` |
| **OpenRouter Integration** | ✅ Working | Yes - Already configured! |

**Why This Is Excellent:**
- ✅ All functions are **already Python** - no API layer needed
- ✅ **LLM integration working** - you're already using OpenRouter for hypotheses
- ✅ **Clean separation** - each component has clear responsibilities
- ✅ **Safety built-in** - blast radius limits, circuit breakers
- ✅ **Tested and working** - just ran a successful end-to-end experiment!

---

## What's Needed to Add Chat Interface?

### Option 1: Streamlit (Recommended) - **Can Build Today**

**Pros:**
- ✅ Python-native (no context switching)
- ✅ Built-in chat UI components
- ✅ Direct access to your existing code
- ✅ Fast to prototype (1-2 hours)
- ✅ Perfect for internal tools

**Cons:**
- ❌ Not as polished as custom web UI
- ❌ Limited customization for production
- ❌ Harder to embed in other apps

**Time to MVP:** 1-2 hours (already created `streamlit_app.py`!)

### Option 2: MCP Server - **Best for Integration**

**Pros:**
- ✅ Works with Claude Desktop, Cline, other MCP clients
- ✅ Standard protocol (good for ecosystem)
- ✅ Can be used from multiple frontends
- ✅ Clean tool definitions

**Cons:**
- ❌ Requires MCP-compatible client
- ❌ More setup than Streamlit
- ❌ Learning curve for MCP protocol

**Time to MVP:** 2-3 hours (already created `mcp_server.py`!)

### Option 3: Custom Web UI (FastAPI + React) - **Production-Ready**

**Pros:**
- ✅ Full control over UX
- ✅ Can make it beautiful
- ✅ RESTful API for other clients
- ✅ Production-grade

**Cons:**
- ❌ Requires frontend development
- ❌ More code to maintain
- ❌ Slower to build (days, not hours)

**Time to MVP:** 3-5 days

---

## Recommended Path: **Start with Streamlit**

### Why?

1. **Fastest validation** - Can demo to stakeholders today
2. **Uses existing code** - Zero refactoring needed
3. **Good enough for use cases 1,2,3,5** - Exploration, analysis, design, demos
4. **Easy to iterate** - Add features quickly
5. **Can migrate later** - If you need production UI, you'll know what works

### Phase 1: Streamlit MVP (1-2 hours)

**What I already created:**
- ✅ `src/chaoswopr/chat/streamlit_app.py` - Full working prototype

**What it does:**
- Chat interface with message history
- Tool calling via OpenRouter (your existing setup!)
- Tools: `explain_scenario`, `list_scenarios`, `check_testnet`, `design_scenario`
- Sidebar with quick actions

**To run:**
```bash
# Install Streamlit
pip install streamlit

# Run the app
streamlit run src/chaoswopr/chat/streamlit_app.py
```

### Phase 2: Add More Tools (2-3 hours)

Add these tools to make it fully functional:

```python
# Read-only tools (safe, no approval)
- analyze_experiment(experiment_id)
- query_metrics(metric_name, time_range)
- list_past_experiments(status, limit)
- explain_metric(metric_name)

# Design tools (generates artifacts)
- create_hypothesis(goal)
- estimate_impact(scenario_yaml)
- suggest_improvements(experiment_id)

# Execute tools (requires approval)
- run_demo_experiment()  # Pre-approved safe scenario
- deploy_testnet(num_validators)  # With confirmation dialog
```

### Phase 3: Add Safety Layer (1-2 hours)

Implement approval workflow:

```python
# In Streamlit
if tool requires approval:
    st.warning("⚠️ This action requires approval")

    st.info(f"""
    **Impact Summary:**
    - Blast radius: 20% (51/256 nodes)
    - Duration: ~12 minutes
    - Cost: ~$0.05
    """)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Approve"):
            execute_tool()
    with col2:
        if st.button("❌ Cancel"):
            st.info("Action cancelled")
```

### Phase 4: Polish & Deploy (2-3 hours)

- Add experiment history viewer
- Add real-time status updates
- Add Prometheus dashboard embeds
- Deploy to internal server

**Total time to production: ~1 week**

---

## Code Reuse Analysis

### What You Can Use Directly (90% of your code!)

```python
# ✅ Use as-is (no changes needed):

from chaoswopr.infrastructure.testnet.kurtosis_client import KurtosisClient
from chaoswopr.agents.experiment_runner import ExperimentRunner, ExperimentRunnerConfig
from chaoswopr.agents.fault_dispatcher import FaultDispatcher
from chaoswopr.infrastructure.monitoring.prometheus import PrometheusClient
from chaoswopr.agents.hypothesis_engine import HypothesisEngine
from chaoswopr.agents.scenario_loader import ScenarioBuilder
from config.llm_config import LLMConfig

# All of these work perfectly for tool calling!
```

### What Needs Wrapping (10% new code)

```python
# Just add tool definitions:

TOOLS = [
    {
        "name": "run_experiment",
        "description": "Run a chaos engineering experiment",
        "parameters": {...},
        "implementation": experiment_runner.run_experiment
    }
]
```

---

## Example Tool Calling Flow

### User Conversation:

```
User: "What happens if 30% of validators go offline?"