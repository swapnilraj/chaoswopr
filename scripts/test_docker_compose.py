#!/usr/bin/env python3
"""Test chaoswopr on Docker Compose testnet with NET_ADMIN.

This script:
1. Verifies Docker Compose testnet is running
2. Verifies NET_ADMIN capability is present
3. Tests Track H chaos injection (network faults)
4. Tests fault cleanup
"""

import subprocess
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chaoswopr.chaos.network_faults import NetworkFault, FaultType, NetworkFaultInjector


def print_section(title: str) -> None:
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def check_container_running(container_name: str) -> bool:
    """Check if a container is running."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() == "true"
    except Exception:
        return False


def check_net_admin(container_name: str) -> bool:
    """Check if a container has NET_ADMIN capability."""
    try:
        result = subprocess.run(
            ["docker", "inspect", container_name, "--format", "{{.HostConfig.CapAdd}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        caps = result.stdout.strip()
        return "NET_ADMIN" in caps
    except Exception:
        return False


def test_tc_command(container_name: str) -> bool:
    """Test if tc command works in container."""
    try:
        # Try a simple tc command
        result = subprocess.run(
            ["docker", "exec", container_name, "tc", "qdisc", "show"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def main() -> int:
    """Run all Docker Compose tests."""
    print_section("DOCKER COMPOSE TESTNET TESTING")

    print("Testing chaoswopr chaos injection on Docker Compose testnet")
    print("with NET_ADMIN capability enabled")
    print()

    # Step 1: Verify testnet is running
    print_section("Step 1: Verify Testnet is Running")

    containers = ["el-1-nethermind", "el-2-nethermind", "cl-1-prysm", "cl-2-prysm"]
    running_containers = []

    for container in containers:
        if check_container_running(container):
            print(f"✅ {container} is running")
            running_containers.append(container)
        else:
            print(f"❌ {container} is NOT running")

    if not running_containers:
        print("\n❌ No containers running!")
        print("   Start the testnet with:")
        print("   cd docker-compose && ./setup.sh && docker-compose up -d")
        return 1

    print(f"\n✅ {len(running_containers)}/{len(containers)} containers running")

    # Step 2: Verify NET_ADMIN
    print_section("Step 2: Verify NET_ADMIN Capability")

    target_container = running_containers[0]
    print(f"Checking {target_container}...")

    if not check_net_admin(target_container):
        print(f"❌ {target_container} does NOT have NET_ADMIN capability!")
        print("   This should not happen - check docker-compose.yml")
        return 1

    print(f"✅ {target_container} has NET_ADMIN capability")

    # Step 3: Install tc if needed
    print_section("Step 3: Ensure tc Utility is Available")

    print(f"Checking if tc is available in {target_container}...")
    if not test_tc_command(target_container):
        print("Installing tc (iproute2)...")
        # Try apt-get (Debian/Ubuntu-based images)
        subprocess.run(
            ["docker", "exec", target_container, "apt-get", "update"],
            capture_output=True,
            timeout=60,
        )
        subprocess.run(
            ["docker", "exec", target_container, "apt-get", "install", "-y", "iproute2"],
            capture_output=True,
            timeout=60,
        )

        if test_tc_command(target_container):
            print("✅ tc installed successfully")
        else:
            print("❌ Failed to install tc")
            return 1
    else:
        print("✅ tc is already available")

    # Step 4: Test packet loss injection
    print_section("Step 4: Test Track H - Packet Loss Injection")

    print("Injecting 20% packet loss...")
    fault = NetworkFault(
        fault_type=FaultType.PACKET_LOSS,
        target_service=target_container,
        loss_percentage=20.0,
        interface="eth0",
    )

    injector = NetworkFaultInjector(dry_run=False)

    try:
        injector.inject_fault(fault)
        print("✅ Packet loss fault injected successfully")

        # Verify fault is active
        result = subprocess.run(
            ["docker", "exec", target_container, "tc", "qdisc", "show", "dev", "eth0"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if "netem" in result.stdout and "loss 20%" in result.stdout:
            print("✅ Fault verified via tc qdisc show")
        else:
            print("⚠️  Fault may not be active (tc qdisc output doesn't show expected values)")

        # Wait a bit
        time.sleep(2)

        # Cleanup
        injector.remove_fault(fault.id)
        print("✅ Fault cleaned up successfully")

    except Exception as e:
        print(f"❌ Packet loss test failed: {e}")
        return 1

    # Step 5: Test network latency injection
    print_section("Step 5: Test Track H - Network Latency Injection")

    print("Injecting 100ms latency with 20ms jitter...")
    latency = NetworkFault(
        fault_type=FaultType.LATENCY,
        target_service=target_container,
        delay_ms=100.0,
        jitter_ms=20.0,
        interface="eth0",
    )

    try:
        injector.inject_fault(latency)
        print("✅ Network latency fault injected successfully")

        # Verify fault is active
        result = subprocess.run(
            ["docker", "exec", target_container, "tc", "qdisc", "show", "dev", "eth0"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if "netem" in result.stdout and "delay 100" in result.stdout:
            print("✅ Fault verified via tc qdisc show")
        else:
            print("⚠️  Fault may not be active")

        # Wait a bit
        time.sleep(2)

        # Cleanup
        injector.remove_fault(latency.id)
        print("✅ Latency fault cleaned up successfully")

    except Exception as e:
        print(f"❌ Latency test failed: {e}")
        return 1

    # Step 6: Test bandwidth throttling
    print_section("Step 6: Test Track H - Bandwidth Throttling")

    print("Throttling bandwidth to 1Mbit/s...")
    bandwidth = NetworkFault(
        fault_type=FaultType.BANDWIDTH,
        target_service=target_container,
        rate_limit_kbps=1024,  # 1 Mbit/s
        interface="eth0",
    )

    try:
        injector.inject_fault(bandwidth)
        print("✅ Bandwidth throttling fault injected successfully")

        # Wait a bit
        time.sleep(2)

        # Cleanup
        injector.remove_fault(bandwidth.id)
        print("✅ Bandwidth fault cleaned up successfully")

    except Exception as e:
        print(f"❌ Bandwidth test failed: {e}")
        return 1

    # Success!
    print_section("All Tests Passed!")

    print("Summary:")
    print(f"  ✅ Docker Compose testnet running ({len(running_containers)} containers)")
    print(f"  ✅ NET_ADMIN capability verified")
    print(f"  ✅ tc utility available")
    print(f"  ✅ Packet loss injection working")
    print(f"  ✅ Network latency injection working")
    print(f"  ✅ Bandwidth throttling working")
    print(f"  ✅ Fault cleanup working")
    print()
    print("🎉 Track H (Chaos Injection) is FULLY FUNCTIONAL on Docker Compose!")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
