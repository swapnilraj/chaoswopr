#!/usr/bin/env python3
"""Demo script showcasing Node Agent functionality.

Demonstrates:
1. Creating and starting node agents
2. Switching between honest and adversarial modes
3. Setting different adversarial behaviors
4. Batch operations on multiple agents
5. Status queries and monitoring

Run with: python scripts/demo_node_agents.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chaoswopr.agents import AgentMode, NodeAgent, NodeAgentConfig
from chaoswopr.agents.node_agent_api import batch_get_status, batch_mode_switch, batch_set_behavior
from chaoswopr.agents.node_agent_behaviors import (
    AttestationDelay,
    AttestationWithholding,
    HonestBehavior,
)
from chaoswopr.safety.audit import AuditLogger


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_status(agents: list[NodeAgent]) -> None:
    """Print status of all agents."""
    statuses = batch_get_status(agents)
    for status in statuses:
        print(f"  {status['node_id']}: {status['mode']} mode, {status['status']}, "
              f"uptime={status['uptime_seconds']:.1f}s")


def main() -> None:
    """Run the demo."""
    print("\n🎭 Node Agent System Demo")
    print("Demonstrating AI-controlled sidecar proxies for Ethereum chaos testing\n")

    # Initialize audit logger
    audit_logger = AuditLogger(default_agent_id="demo")

    print_section("1. Creating 10 Node Agents (simulating 50-node testnet)")

    # Create 10 agents representing 20% of a 50-node testnet
    agents = []
    for i in range(10):
        config = NodeAgentConfig(
            node_id=f"validator-{i}",
            beacon_api_url=f"http://localhost:{5052 + i}",
            proxy_port=6000 + i,
            mode=AgentMode.HONEST,
            audit_logging=True,
        )
        agent = NodeAgent(config=config, audit_logger=audit_logger, dry_run=True)
        agents.append(agent)
        print(f"  ✓ Created {agent.node_id} (proxy port {config.proxy_port})")

    print_section("2. Starting All Agents in Honest Mode")

    for agent in agents:
        agent.start()

    print("  All agents started successfully!")
    print("\n  Status:")
    print_status(agents)

    print_section("3. Switching 3 Agents to Adversarial Mode (30% Byzantine)")

    # Select 3 agents to be adversarial (30% of 10 agents)
    adversarial_agents = agents[0:3]
    results = batch_mode_switch(adversarial_agents, AgentMode.ADVERSARIAL)

    print(f"  Switched {len([r for r in results if r['success']])} agents to adversarial mode:")
    for result in results:
        print(f"    ✓ {result['node_id']} → {result['new_mode']}")

    print("\n  Updated Status:")
    print_status(agents)

    print_section("4. Setting Adversarial Behaviors")

    # Agent 0: Attestation withholding (80% probability)
    print("  validator-0: AttestationWithholding (80% probability)")
    behavior = AttestationWithholding(withhold_probability=0.8)
    agents[0].set_behavior(behavior)

    # Agent 1: Attestation delay (2 seconds)
    print("  validator-1: AttestationDelay (2 seconds)")
    behavior = AttestationDelay(delay_seconds=2.0)
    agents[1].set_behavior(behavior)

    # Agent 2: Mixed behavior (50% withholding)
    print("  validator-2: AttestationWithholding (50% probability)")
    behavior = AttestationWithholding(withhold_probability=0.5)
    agents[2].set_behavior(behavior)

    print("\n  ✓ All adversarial behaviors configured")

    print_section("5. Simulating Runtime (monitoring for 2 seconds)")

    print("  Agents running with mixed honest/adversarial behaviors...")
    time.sleep(2)
    print("  ✓ Monitoring complete")

    print("\n  Final Status:")
    print_status(agents)

    print_section("6. Batch Operation: Reset All to Honest Mode")

    results = batch_mode_switch(adversarial_agents, AgentMode.HONEST)
    print(f"  Reset {len([r for r in results if r['success']])} agents to honest mode")

    print("\n  Final Status:")
    print_status(agents)

    print_section("7. Audit Log Summary")

    # Show audit log entries
    entries = audit_logger.get_entries()
    print(f"  Total audit log entries: {len(entries)}")

    # Count by type
    start_events = [e for e in entries if e.action_type == "node_agent_start"]
    switch_events = [e for e in entries if e.action_type == "node_agent_mode_switch"]

    print(f"  - Agent starts: {len(start_events)}")
    print(f"  - Mode switches: {len(switch_events)}")

    print("\n  Recent events:")
    for entry in entries[-5:]:
        print(f"    [{entry.timestamp.strftime('%H:%M:%S')}] {entry.agent_id}: "
              f"{entry.action_type} → {entry.outcome}")

    print_section("8. Stopping All Agents")

    for agent in agents:
        agent.stop()

    print("  ✓ All agents stopped successfully")

    print_section("Demo Complete!")

    print("""
  Summary:
  ✓ Created 10 node agents
  ✓ Started all in honest mode
  ✓ Switched 3 to adversarial mode (30% Byzantine)
  ✓ Configured different adversarial behaviors
  ✓ Monitored runtime with mixed modes
  ✓ Reset all to honest mode
  ✓ Verified audit logging
  ✓ Clean shutdown

  Next Steps:
  - Scale to 50-500 agents for production testing
  - Integrate with Orchestrator Agent (Phase 2 Track E)
  - Add real HTTP server for production use
  - Deploy on actual Ethereum testnet
    """)


if __name__ == "__main__":
    main()
