#!/usr/bin/env python3
"""Quick test of chaos injection fix."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from chaoswopr.agents.fault_dispatcher import FaultDispatcher
from chaoswopr.agents.node_coordinator import NodeAgentCoordinator, FleetConfig
from chaoswopr.agents.plan_compiler import PlanAction
from chaoswopr.agents.hypothesis_engine import FaultLevel
from chaoswopr.agents.messaging.coordinator import MessageCoordinator
from chaoswopr.agents.messaging.message_bus import MessageBus

print("=" * 80)
print("Testing Chaos Injection Fix")
print("=" * 80)
print()

# Test 1: Without node_agent_client (should fail)
print("Test 1: FaultDispatcher without node_agent_client")
dispatcher_no_client = FaultDispatcher(dry_run=False)

test_action = PlanAction(
    action_id="test-001",
    action_type="attestation_withholding",
    fault_level=FaultLevel.PROTOCOL,
    step_number=1,
    time_offset_seconds=60,
    target_nodes=["node-001", "node-002"],
    target_percent=20.0,
)

result1 = dispatcher_no_client.dispatch_action(test_action)
print(f"  Success: {result1.success}")
print(f"  Error: {result1.error_message}")
print(f"  Expected: 'No Node Agent client configured'")
print(f"  ✅ PASS" if result1.error_message == "No Node Agent client configured" else "  ❌ FAIL")
print()

# Test 2: With node_agent_client (should succeed)
print("Test 2: FaultDispatcher with node_agent_client")

# Create minimal components
bus = MessageBus()
msg_coordinator = MessageCoordinator(message_bus=bus)
fleet_config = FleetConfig(num_agents=256, adversarial_ratio=0.20)
node_coordinator = NodeAgentCoordinator(
    fleet_config=fleet_config,
    message_coordinator=msg_coordinator,
    dry_run=True,  # Dry run so we don't need real nodes
)

dispatcher_with_client = FaultDispatcher(
    node_agent_client=node_coordinator,
    dry_run=False,  # Not dry run for dispatcher
)

test_action2 = PlanAction(
    action_id="test-002",
    action_type="attestation_withholding",
    fault_level=FaultLevel.PROTOCOL,
    step_number=1,
    time_offset_seconds=60,
    target_nodes=["node-001", "node-002"],
    target_percent=20.0,
)

result2 = dispatcher_with_client.dispatch_action(test_action2)
print(f"  Success: {result2.success}")
print(f"  Fault ID: {result2.fault_id}")
print(f"  Error: {result2.error_message}")
print(f"  ✅ PASS" if result2.success else f"  ❌ FAIL: {result2.error_message}")
print()

print("=" * 80)
if result1.error_message == "No Node Agent client configured" and result2.success:
    print("✅ ALL TESTS PASSED - Chaos injection fix is working!")
else:
    print("❌ TESTS FAILED")
print("=" * 80)
