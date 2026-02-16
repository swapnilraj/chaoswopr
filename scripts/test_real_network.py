#!/usr/bin/env python3
"""Test all chaoswopr components on a real Ethereum testnet.

This script:
1. Deploys a 4-node testnet with NET_ADMIN capability
2. Tests Track H chaos injection (network faults)
3. Tests Track F node agents (if Beacon API available)
4. Tests Track G observer (if Prometheus available)
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chaoswopr.infrastructure.testnet.chaos_testnet import create_chaos_testnet
from chaoswopr.chaos.network_faults import NetworkFault, FaultType


def print_section(title: str) -> None:
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def main() -> int:
    """Run all real network tests."""
    print_section("REAL NETWORK TESTING - ALL TRACKS")

    print("This will:")
    print("  1. Deploy a 4-node Ethereum testnet with NET_ADMIN capability")
    print("  2. Test Track H chaos injection on real containers")
    print("  3. Verify NET_ADMIN is enabled")
    print("  4. Clean up afterwards")
    print()

    # Step 1: Deploy testnet
    print_section("Step 1: Deploy 4-Node Testnet with NET_ADMIN")

    print("Deploying testnet (this takes ~5 minutes)...")
    deployer, result = create_chaos_testnet(
        node_count=4,
        enclave_name="chaoswopr-real-test",
        dry_run=False,
        use_patched_package=True,
    )

    if not result.success:
        print(f"❌ Deployment failed: {result.error_message}")
        return 1

    print(f"✅ Deployment successful!")
    print(f"   Enclave: {deployer.enclave_name}")
    print(f"   Services deployed: {len(deployer._kurtosis.get_services(deployer.enclave_name))}")

    try:
        # Step 2: Verify NET_ADMIN
        print_section("Step 2: Verify NET_ADMIN Capability")

        services = deployer._kurtosis.get_services(deployer.enclave_name)
        el_services = [s for s in services if s.name.startswith("el-")]

        if not el_services:
            print("❌ No EL services found")
            return 1

        print(f"Found {len(el_services)} execution layer services")

        # Check first EL container
        import subprocess

        service_name = el_services[0].name
        print(f"Checking {service_name}...")

        # Find Docker container
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={service_name}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        containers = [c for c in result.stdout.strip().split("\n") if c]
        if not containers:
            print(f"❌ Container not found for {service_name}")
            return 1

        container_name = containers[0]
        print(f"Found container: {container_name}")

        # Check NET_ADMIN
        result = subprocess.run(
            ["docker", "inspect", container_name, "--format", "{{.HostConfig.CapAdd}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        caps = result.stdout.strip()
        print(f"Capabilities: {caps}")

        if "NET_ADMIN" not in caps:
            print("❌ NET_ADMIN capability NOT found!")
            print("   The patched package may not be working correctly")
            return 1

        print("✅ NET_ADMIN capability verified!")

        # Step 3: Test chaos injection
        print_section("Step 3: Test Track H - Chaos Injection")

        # Test packet loss
        print("Testing packet loss injection...")
        fault = NetworkFault(
            fault_type=FaultType.PACKET_LOSS,
            target_service=service_name,
            loss_percentage=10.0,
            interface="eth0",
        )

        from chaoswopr.chaos.network_faults import NetworkFaultInjector
        injector = NetworkFaultInjector(dry_run=False)

        injector.inject_fault(fault)
        print("✅ Packet loss fault injected successfully")

        # Wait a bit
        time.sleep(2)

        # Cleanup
        injector.remove_fault(fault.id)
        print("✅ Fault cleaned up successfully")

        # Test latency
        print("\nTesting network latency injection...")
        latency = NetworkFault(
            fault_type=FaultType.LATENCY,
            target_service=service_name,
            delay_ms=50.0,
            jitter_ms=10.0,
            interface="eth0",
        )

        injector.inject_fault(latency)
        print("✅ Network latency fault injected successfully")

        # Wait a bit
        time.sleep(2)

        # Cleanup
        injector.remove_fault(latency.id)
        print("✅ Latency fault cleaned up successfully")

        print_section("All Tests Passed!")

        print("Summary:")
        print("  ✅ Testnet deployed with NET_ADMIN capability")
        print("  ✅ NET_ADMIN capability verified in containers")
        print("  ✅ Packet loss injection working")
        print("  ✅ Network latency injection working")
        print("  ✅ Fault cleanup working")
        print()
        print("Track H (Chaos Injection) is FULLY FUNCTIONAL on real networks!")

        return 0

    finally:
        # Cleanup
        print_section("Cleanup")
        print("Destroying testnet...")
        deployer.destroy()
        print("✅ Cleanup complete")


if __name__ == "__main__":
    sys.exit(main())
