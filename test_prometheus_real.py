#!/usr/bin/env python3
"""Quick test of real Prometheus integration."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from prometheus_api_client import PrometheusConnect
from chaoswopr.infrastructure.testnet.kurtosis_client import KurtosisClient, KurtosisBackend

# Get Prometheus URL from current enclave
kurtosis = KurtosisClient(
    backend=KurtosisBackend.DOCKER,
    dry_run=False,
)

print("Testing Prometheus service discovery...")
print()

# Get services
services = kurtosis.get_services("chaoswopr-test-1771282108")
print(f"Found {len(services)} services")
print()

# Find Prometheus
for service in services:
    if "prometheus" in service.name.lower():
        print(f"Service: {service.name}")
        print(f"Ports: {service.ports}")

        # Test old method (wrong)
        old_port = service.get_host_port("http")
        print(f"  Old method (get_host_port): {old_port}")

        # Test new method (correct)
        new_url = service.get_url("http")
        print(f"  New method (get_url): {new_url}")
        print()

        if new_url:
            print(f"Testing connection to {new_url}...")
            try:
                prom = PrometheusConnect(url=new_url, disable_ssl=True)
                result = prom.custom_query(query="up")
                print(f"  ✅ SUCCESS: {len(result)} results")
                if result:
                    print(f"  Sample: {result[0]}")
            except Exception as e:
                print(f"  ❌ FAILED: {e}")
        break
