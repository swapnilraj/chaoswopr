# chaoswopr

AI-driven chaos engineering tool for Ethereum operational resilience testing.

## Overview

chaoswopr deploys private Ethereum testnets (50-500 nodes), injects coordinated faults at network/node/protocol levels, and uses a multi-agent AI system to orchestrate experiments, analyze results, and generate incident response playbooks.

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Run tests
make test

# Deploy testnet (dry-run)
make testnet-up
```

## Project Status

Phase 1: Foundation (in progress)
