# LLM Setup Guide

This guide explains how to configure chaoswopr to use real LLM APIs for hypothesis generation and root cause analysis.

## Overview

chaoswopr uses LLMs for two critical functions:

1. **Hypothesis Generation** (Priority 0): The Orchestrator Agent generates structured, testable hypotheses for chaos experiments using an LLM instead of static templates.
2. **Root Cause Analysis** (Priority 1): The Observer Agent uses an LLM to analyze anomalies and produce actionable root cause hypotheses.

By default, chaoswopr runs in **dry-run mode** with mock LLM responses. To use real LLMs, you need to configure an API provider.

## Supported Providers

| Provider | Description | Models |
|----------|-------------|--------|
| `openrouter` | Unified API for multiple LLM providers | claude-opus-4, claude-sonnet-4.5, gpt-4o, etc. |
| `anthropic` | Direct Anthropic API | claude-sonnet-4 |
| `mock` | Deterministic template responses (default) | mock-llm-v1 |

**Recommended**: Use OpenRouter for the best balance of model selection, cost, and reliability.

## Getting an OpenRouter API Key

1. Visit [https://openrouter.ai](https://openrouter.ai)
2. Sign up and create an account
3. Navigate to Keys and generate an API key
4. Add credits (approximately $5 is sufficient for 100+ experiments)

## Configuration

### Environment Variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Required variables:

```bash
# Your OpenRouter API key
export OPENROUTER_API_KEY=sk-or-v1-your-key-here

# Set provider to openrouter
export CHAOSWOPR_LLM_PROVIDER=openrouter
```

Optional variables:

```bash
# Models (defaults shown)
export HYPOTHESIS_MODEL=anthropic/claude-opus-4
export RCA_MODEL=anthropic/claude-sonnet-4.5

# API settings
export OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
export OPENROUTER_TIMEOUT=60
export OPENROUTER_MAX_RETRIES=3

# Force dry-run mode (uses mocks regardless of provider)
export CHAOSWOPR_DRY_RUN=false
```

### Programmatic Configuration

```python
from chaoswopr.agents.llm_client import create_llm_client
from chaoswopr.agents.hypothesis_engine import HypothesisEngine

# Create an OpenRouter client
llm = create_llm_client(
    provider="openrouter",
    api_key="sk-or-v1-...",
    model="anthropic/claude-opus-4",
)

# Use with HypothesisEngine
engine = HypothesisEngine(llm_client=llm, dry_run=False)
hypothesis = engine.generate(scenario={...})
```

### Using with ExperimentRunner

```python
from chaoswopr.agents.experiment_runner import ExperimentRunner, ExperimentRunnerConfig
from chaoswopr.agents.node_coordinator import FleetConfig

config = ExperimentRunnerConfig(
    fleet_config=FleetConfig(num_agents=10),
    dry_run=False,
    llm_provider="openrouter",
    llm_api_key="sk-or-v1-...",
    hypothesis_model="anthropic/claude-opus-4",
    rca_model="anthropic/claude-sonnet-4.5",
)

runner = ExperimentRunner(config)
result = runner.run_experiment(scenario)
```

## Model Selection Guide

| Use Case | Recommended Model | Cost/Experiment | Notes |
|----------|------------------|----------------|-------|
| Hypothesis Generation | `anthropic/claude-opus-4` | ~$0.03 | Best reasoning for experiment design |
| Root Cause Analysis | `anthropic/claude-sonnet-4.5` | ~$0.015 | Fast and accurate for analysis |
| Budget/Testing | `anthropic/claude-sonnet-4.5` | ~$0.015 | Good for both use cases at lower cost |

**Total cost per experiment**: approximately $0.045 (Opus + Sonnet) or $0.03 (Sonnet for both)

## Running Modes

### Dry-Run Mode (Default)

No API calls are made. Uses deterministic template-based responses.

```bash
# Either of these:
export CHAOSWOPR_DRY_RUN=true
# or
export CHAOSWOPR_LLM_PROVIDER=mock
```

### Real LLM Mode

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
export CHAOSWOPR_LLM_PROVIDER=openrouter
export CHAOSWOPR_DRY_RUN=false
```

### Graceful Fallback

If the LLM call fails (timeout, rate limit, API error), the system automatically falls back to template-based generation. This ensures experiments can always proceed.

## Running Integration Tests

To test with real API calls:

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
pytest tests/integration/test_llm_integration.py -v
```

Tests are automatically skipped when no API key is available.

## Troubleshooting

### "OPENROUTER_API_KEY not set"

Set the environment variable:
```bash
export OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

### "Rate limited" errors

The client includes automatic retry with exponential backoff. If you see persistent rate limiting:
- Check your OpenRouter usage dashboard
- Add more credits
- Reduce experiment frequency

### LLM returns invalid JSON

The system handles this gracefully:
1. Tries direct JSON parsing
2. Tries extracting from markdown code blocks
3. Tries finding JSON objects in the response
4. Falls back to template-based generation

### Mock fallback triggered unexpectedly

Check the logs for warnings about LLM client creation failures:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Architecture

```
ExperimentRunner
  |
  +-- HypothesisEngine
  |     +-- OpenRouterLLMClient (hypothesis_model)
  |     +-- Templates (fallback)
  |
  +-- ObserverAgent
        +-- RCAEngine
              +-- OpenRouterLLMClient (rca_model)
              +-- Mock responses (fallback)
```

The LLM clients are created by `ExperimentRunner` and passed to the engines. Each engine can independently fall back to non-LLM behavior if the client is unavailable or returns errors.
