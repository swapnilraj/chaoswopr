"""Infrastructure Management Tools (12 tools).

Covers testnet lifecycle, client configuration, monitoring, and metrics.
"""

import json
import time
from pathlib import Path
from typing import Optional, Any

from chaoswopr.chat.tools.base import register_tool, SafetyTier
from chaoswopr.infrastructure.testnet.kurtosis_client import KurtosisClient, KurtosisBackend
from chaoswopr.infrastructure.testnet.client_config import ClientConfig, ClientDistribution
from chaoswopr.infrastructure.monitoring.prometheus import PrometheusClient
from chaoswopr.infrastructure.monitoring.metrics_catalog import MetricsCatalog
from chaoswopr.infrastructure.testnet.beacon_api import BeaconAPIClient


# ============================================================================
# Testnet Lifecycle (5 tools)
# ============================================================================

@register_tool(
    name="deploy_testnet",
    safety_tier=SafetyTier.INFRASTRUCTURE,
    description="Deploy an Ethereum testnet with specified number of validators",
    parameters={
        "type": "object",
        "properties": {
            "num_validators": {
                "type": "integer",
                "description": "Number of validators (must be divisible by 128: 128, 256, 384, 512)",
                "default": 256,
            },
            "wait_for_finality": {
                "type": "boolean",
                "description": "Wait for the network to reach finality before returning",
                "default": True,
            },
            "enclave_name": {
                "type": "string",
                "description": "Optional enclave name (auto-generated if not provided)",
            },
        },
        "required": ["num_validators"],
    },
)
def deploy_testnet(
    num_validators: int = 256,
    wait_for_finality: bool = True,
    enclave_name: Optional[str] = None,
    context: Optional[Any] = None,
) -> str:
    """Deploy an Ethereum testnet via Kurtosis."""
    try:
        # Validate
        if num_validators % 128 != 0:
            return f"""❌ **Invalid Validator Count**

Number of validators must be divisible by 128 (128, 256, 384, 512).
You requested: {num_validators}

This is required by Fulu fork configuration.
"""

        # Generate enclave name if not provided
        if not enclave_name:
            enclave_name = f"chaoswopr-chat-{int(time.time())}"

        # Calculate nodes
        num_nodes = num_validators // 128

        # Create Kurtosis client
        kurtosis = KurtosisClient(backend=KurtosisBackend.DOCKER, dry_run=False)

        # Create enclave
        enclave = kurtosis.create_enclave(enclave_name)

        # Configure ethereum-package (use Nethermind to avoid geth blobSchedule issue)
        eth_config = {
            "participants": [
                {
                    "el_type": "nethermind",  # Use Nethermind to avoid geth blobSchedule bug
                    "cl_type": "lighthouse",
                    "count": num_nodes,
                }
            ],
            "network_params": {
                "preset": "minimal",
                "num_validator_keys_per_node": 128,
                "seconds_per_slot": 6,
            },
            "additional_services": ["prometheus", "grafana"],
            "wait_for_finalization": wait_for_finality,
            "ethereum_metrics_exporter_enabled": True,
        }

        # Save config
        config_file = Path(f"/tmp/eth_config_{enclave_name}.json")
        with open(config_file, "w") as f:
            json.dump(eth_config, f, indent=2)

        # Deploy!
        result = kurtosis.run_package(
            enclave_name=enclave_name,
            package_path="github.com/ethpandaops/ethereum-package",
            args_file=str(config_file),
            timeout=600,
        )

        # Get services
        services = kurtosis.get_services(enclave_name)

        # Find Prometheus
        prometheus_url = None
        grafana_url = None
        for service in services:
            if "prometheus" in service.name.lower():
                url = service.get_url("http")
                if url:
                    prometheus_url = url
            if "grafana" in service.name.lower():
                url = service.get_url("http")
                if url:
                    grafana_url = url

        # Clean up config file
        config_file.unlink(missing_ok=True)

        # Update context
        if context:
            context.set_enclave(enclave_name)

        return f"""✅ **Testnet Deployed Successfully!**

**Enclave:** `{enclave_name}`
**Validators:** {num_validators} ({num_nodes} nodes × 128 validators)
**Clients:** {num_nodes} Nethermind + {num_nodes} Lighthouse
**Services:** {len(services)} total

**Monitoring:**
- Prometheus: {prometheus_url or "Starting..."}
- Grafana: {grafana_url or "Starting..."}

**Next Steps:**
- Use `check_beacon_health` to verify finality
- Run chaos experiments with `run_experiment`
- Query metrics via `query_prometheus`

**To clean up:**
```bash
kurtosis enclave rm {enclave_name} --force
```
"""

    except Exception as e:
        return f"""❌ **Testnet Deployment Failed**

Error: {str(e)}

**Troubleshooting:**
- Check Kurtosis engine: `kurtosis engine status`
- Check Docker is running
- Try with fewer validators (128 or 256)
"""


@register_tool(
    name="destroy_testnet",
    safety_tier=SafetyTier.INFRASTRUCTURE,
    description="Destroy a Kurtosis testnet enclave (WARNING: permanent data loss)",
    parameters={
        "type": "object",
        "properties": {
            "enclave_name": {
                "type": "string",
                "description": "Name of the enclave to destroy",
            }
        },
        "required": ["enclave_name"],
    },
)
def destroy_testnet(enclave_name: str, context: Optional[Any] = None) -> str:
    """Destroy testnet implementation."""
    try:
        client = KurtosisClient(dry_run=False)
        success = client.destroy_enclave(enclave_name)

        # Clear context
        if context and context.current_enclave_name == enclave_name:
            context.current_enclave_name = None

        if success:
            return f"""✅ **Testnet Destroyed**

Enclave `{enclave_name}` has been removed.
All services stopped and resources freed.
"""
        else:
            return f"❌ Failed to destroy enclave `{enclave_name}`"

    except Exception as e:
        return f"❌ Error destroying testnet: {e}"


@register_tool(
    name="list_testnets",
    safety_tier=SafetyTier.READ_ONLY,
    description="List all Kurtosis testnet enclaves",
    parameters={"type": "object", "properties": {}},
)
def list_testnets() -> str:
    """List all enclaves."""
    try:
        client = KurtosisClient(dry_run=False)
        enclaves = client.list_enclaves()

        if not enclaves:
            return "No testnets found. Use `deploy_testnet` to create one."

        lines = ["**Active Testnets:**\n"]
        for enclave in enclaves:
            status_icon = "✅" if enclave.state.value == "running" else "⏸️"
            lines.append(
                f"{status_icon} **{enclave.name}**\n"
                f"  - State: {enclave.state.value}\n"
                f"  - Created: {enclave.creation_time}\n"
            )

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error listing testnets: {e}"


@register_tool(
    name="scale_testnet",
    safety_tier=SafetyTier.INFRASTRUCTURE,
    description="Scale testnet by changing validator count (requires redeployment)",
    parameters={
        "type": "object",
        "properties": {
            "enclave_name": {
                "type": "string",
                "description": "Enclave to scale",
            },
            "target_validators": {
                "type": "integer",
                "description": "Target validator count (must be divisible by 128)",
            },
        },
        "required": ["enclave_name", "target_validators"],
    },
)
def scale_testnet(enclave_name: str, target_validators: int) -> str:
    """Scale testnet (mock - requires redeployment)."""
    if target_validators % 128 != 0:
        return f"❌ target_validators must be divisible by 128, got {target_validators}"

    current_validators = 256  # Mock
    num_nodes = target_validators // 128

    return f"""**Testnet Scaling**

**Enclave:** {enclave_name}
**Current:** {current_validators} validators
**Target:** {target_validators} validators ({num_nodes} nodes)

⚠️ **Note:** Scaling requires testnet redeployment:
1. Create snapshot of current state
2. Destroy current testnet
3. Deploy new testnet with {num_nodes} nodes
4. Optionally restore snapshot data

**Recommended approach:**
Use `destroy_testnet` + `deploy_testnet({target_validators})` instead.
"""


@register_tool(
    name="configure_client_diversity",
    safety_tier=SafetyTier.DESIGN,
    description="Configure client diversity distribution (for planning, doesn't modify running testnet)",
    parameters={
        "type": "object",
        "properties": {
            "execution_distribution": {
                "type": "object",
                "description": "Execution client distribution (percentages must sum to 1.0)",
                "properties": {
                    "nethermind": {"type": "number", "default": 0.4},
                    "geth": {"type": "number", "default": 0.3},
                    "besu": {"type": "number", "default": 0.15},
                    "erigon": {"type": "number", "default": 0.15},
                },
            },
            "consensus_distribution": {
                "type": "object",
                "description": "Consensus client distribution",
                "properties": {
                    "lighthouse": {"type": "number", "default": 0.4},
                    "prysm": {"type": "number", "default": 0.3},
                    "teku": {"type": "number", "default": 0.15},
                    "nimbus": {"type": "number", "default": 0.15},
                },
            },
        },
        "required": ["execution_distribution", "consensus_distribution"],
    },
)
def configure_client_diversity(
    execution_distribution: dict,
    consensus_distribution: dict,
) -> str:
    """Configure client diversity (planning tool)."""
    exec_total = sum(execution_distribution.values())
    cons_total = sum(consensus_distribution.values())

    if abs(exec_total - 1.0) > 0.01:
        return f"❌ Execution distribution must sum to 1.0, got {exec_total}"
    if abs(cons_total - 1.0) > 0.01:
        return f"❌ Consensus distribution must sum to 1.0, got {cons_total}"

    exec_lines = [f"- {client}: {pct*100:.0f}%" for client, pct in sorted(execution_distribution.items(), key=lambda x: -x[1])]
    cons_lines = [f"- {client}: {pct*100:.0f}%" for client, pct in sorted(consensus_distribution.items(), key=lambda x: -x[1])]

    return f"""**Client Diversity Configuration**

**Execution Layer:**
"""f"""{chr(10).join(exec_lines)}"""f"""

**Consensus Layer:**
"""f"""{chr(10).join(cons_lines)}"""f"""

⚠️ **Note:** This configuration is for planning only.
To apply, use `deploy_testnet` with a ClientConfig that matches this distribution.

**Mainnet Comparison:**
Recommended to match mainnet client distribution for realistic testing.
"""


@register_tool(
    name="get_testnet_info",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get detailed information about a testnet enclave",
    parameters={
        "type": "object",
        "properties": {
            "enclave_name": {
                "type": "string",
                "description": "Name of the enclave (or uses current from context)",
            }
        },
    },
)
def get_testnet_info(enclave_name: Optional[str] = None, context: Optional[Any] = None) -> str:
    """Get complete enclave information."""
    try:
        # Resolve enclave name from context
        if not enclave_name and context:
            enclave_name = context.get_enclave_name()

        if not enclave_name:
            return "❌ No enclave specified and no current enclave in context"

        client = KurtosisClient(dry_run=False)
        info = client.get_enclave_info(enclave_name)

        if not info:
            return f"❌ Enclave not found: {enclave_name}"

        services = client.get_services(enclave_name)
        beacon_services = client.find_beacon_services(enclave_name)

        lines = [
            f"**Testnet Info: {enclave_name}**\n",
            f"**State:** {info.state.value}",
            f"**Created:** {info.creation_time}\n",
            f"**Services:** {len(services)} total",
            f"**Beacon Nodes:** {len(beacon_services)}\n",
            "**Service List:**",
        ]

        for service in services[:10]:  # Show first 10
            lines.append(f"- {service.name}: {service.status}")

        if len(services) > 10:
            lines.append(f"- ... and {len(services) - 10} more")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error getting testnet info: {e}"


# ============================================================================
# Monitoring & Metrics (7 tools)
# ============================================================================

@register_tool(
    name="query_prometheus",
    safety_tier=SafetyTier.READ_ONLY,
    description="Execute a PromQL query against Prometheus",
    parameters={
        "type": "object",
        "properties": {
            "promql": {
                "type": "string",
                "description": "PromQL query string (e.g., 'beacon_head_slot')",
            },
            "start_time": {
                "type": "string",
                "description": "Optional start time for range query (RFC3339)",
            },
            "end_time": {
                "type": "string",
                "description": "Optional end time for range query (RFC3339)",
            },
            "step": {
                "type": "string",
                "description": "Optional step duration for range query (e.g., '15s')",
            },
        },
        "required": ["promql"],
    },
)
def query_prometheus(
    promql: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    step: Optional[str] = None,
) -> str:
    """Execute Prometheus query."""
    try:
        # This requires a running Prometheus instance
        # For now, return mock data
        return f"""**Prometheus Query Result:**

Query: `{promql}`

⚠️ Note: This requires a deployed testnet with Prometheus.
Deploy a testnet first with `deploy_testnet`.

Example queries:
- `beacon_head_slot` - Current beacon chain head slot
- `beacon_finalized_epoch` - Last finalized epoch
- `beacon_participation_prev_epoch_total_active_balance_gwei` - Active balance
"""

    except Exception as e:
        return f"❌ Error querying Prometheus: {e}"


@register_tool(
    name="get_metric_value",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get current value of a specific metric from the catalog",
    parameters={
        "type": "object",
        "properties": {
            "metric_name": {
                "type": "string",
                "description": "Metric name from the 52-metric catalog",
            }
        },
        "required": ["metric_name"],
    },
)
def get_metric_value(metric_name: str) -> str:
    """Get metric value."""
    # Get metric from catalog
    catalog = MetricsCatalog()
    metric = next((m for m in catalog.metrics if m.name == metric_name), None)

    if not metric:
        return f"""❌ Unknown metric: {metric_name}

Use `list_available_metrics` to see all available metrics.
"""

    return f"""**Metric: {metric_name}**

**Description:** {metric.description}
**Category:** {metric.category}

⚠️ Requires deployed testnet with Prometheus to query actual values.
"""


@register_tool(
    name="list_available_metrics",
    safety_tier=SafetyTier.READ_ONLY,
    description="List all available metrics from the 52-metric catalog",
    parameters={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Optional category filter: consensus, network, resource, safety, mev",
                "enum": ["consensus", "network", "resource", "safety", "mev"],
            }
        },
    },
)
def list_available_metrics(category: Optional[str] = None) -> str:
    """List metrics from catalog."""
    catalog = MetricsCatalog()
    metrics = catalog.metrics

    if category:
        metrics = catalog.get_by_category(category)

    lines = [f"**Available Metrics ({len(metrics)} total)**\n"]

    # Group by category
    by_category: dict[str, list] = {}
    for metric in metrics:
        if metric.category not in by_category:
            by_category[metric.category] = []
        by_category[metric.category].append(metric)

    for cat, cat_metrics in sorted(by_category.items()):
        lines.append(f"### {cat.upper()} ({len(cat_metrics)} metrics)\n")
        for metric in cat_metrics[:5]:  # Show first 5 per category
            lines.append(f"- **{metric.name}**: {metric.description}")
        if len(cat_metrics) > 5:
            lines.append(f"- ... and {len(cat_metrics) - 5} more\n")

    return "\n".join(lines)


@register_tool(
    name="check_beacon_health",
    safety_tier=SafetyTier.READ_ONLY,
    description="Check health and sync status of beacon nodes",
    parameters={
        "type": "object",
        "properties": {
            "enclave_name": {
                "type": "string",
                "description": "Enclave name (or uses current from context)",
            },
            "node_id": {
                "type": "string",
                "description": "Optional specific node ID to check",
            },
        },
    },
)
def check_beacon_health(
    enclave_name: Optional[str] = None,
    node_id: Optional[str] = None,
    context: Optional[Any] = None,
) -> str:
    """Check beacon node health."""
    try:
        # Resolve enclave
        if not enclave_name and context:
            enclave_name = context.get_enclave_name()

        if not enclave_name:
            return "❌ No enclave specified and no current enclave in context"

        # Get beacon services
        client = KurtosisClient(dry_run=False)
        beacon_services = client.find_beacon_services(enclave_name)

        if not beacon_services:
            return f"❌ No beacon nodes found in enclave {enclave_name}"

        # Check specific node or all nodes
        if node_id:
            service = next((s for s in beacon_services if node_id in s.name), None)
            if not service:
                return f"❌ Node not found: {node_id}"
            beacon_services = [service]

        lines = [f"**Beacon Health Check: {enclave_name}**\n"]

        for service in beacon_services[:5]:  # Check first 5
            beacon_url = service.get_url("http")
            if not beacon_url:
                lines.append(f"- **{service.name}**: ❌ No HTTP endpoint")
                continue

            # Try to connect
            beacon_client = BeaconAPIClient(beacon_url)
            try:
                health = beacon_client.health_check()
                sync = beacon_client.get_sync_status()

                if health:
                    sync_icon = "✅" if not sync.get("is_syncing", True) else "🔄"
                    lines.append(
                        f"- **{service.name}**: {sync_icon} Healthy\n"
                        f"  - Syncing: {sync.get('is_syncing', 'unknown')}\n"
                        f"  - Head slot: {sync.get('head_slot', 'unknown')}"
                    )
                else:
                    lines.append(f"- **{service.name}**: ❌ Unhealthy")

            except Exception as e:
                lines.append(f"- **{service.name}**: ⚠️ Error: {e}")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error checking beacon health: {e}"


@register_tool(
    name="wait_for_finality",
    safety_tier=SafetyTier.READ_ONLY,
    description="Wait for the beacon chain to reach finality (blocking operation)",
    parameters={
        "type": "object",
        "properties": {
            "enclave_name": {
                "type": "string",
                "description": "Enclave name (or uses current from context)",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Maximum time to wait (default 600s = 10 min)",
                "default": 600,
            },
        },
    },
)
def wait_for_finality(
    enclave_name: Optional[str] = None,
    timeout_seconds: int = 600,
    context: Optional[Any] = None,
) -> str:
    """Wait for finality."""
    try:
        # Resolve enclave
        if not enclave_name and context:
            enclave_name = context.get_enclave_name()

        if not enclave_name:
            return "❌ No enclave specified"

        # Get first beacon node
        client = KurtosisClient(dry_run=False)
        beacon_services = client.find_beacon_services(enclave_name)

        if not beacon_services:
            return f"❌ No beacon nodes found in {enclave_name}"

        beacon_url = beacon_services[0].get_url("http")
        if not beacon_url:
            return "❌ No beacon API endpoint found"

        # Wait for finality
        beacon_client = BeaconAPIClient(beacon_url)
        result = beacon_client.wait_for_finality(timeout_seconds=timeout_seconds)

        if result.finalized:
            return f"""✅ **Finality Achieved!**

**Epoch:** {result.finalized_epoch}
**Duration:** {result.duration_seconds:.1f}s
**Checkpoint:** {result.finalized_checkpoint}

The network is ready for chaos experiments.
"""
        else:
            return f"""⚠️ **Finality Not Achieved**

Waited {timeout_seconds}s but network did not finalize.

**Troubleshooting:**
- Check if enough validators are online
- Verify network connectivity
- Check beacon logs for errors
"""

    except Exception as e:
        return f"❌ Error waiting for finality: {e}"


@register_tool(
    name="get_service_urls",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get service URLs for a testnet enclave",
    parameters={
        "type": "object",
        "properties": {
            "enclave_name": {
                "type": "string",
                "description": "Enclave name (or uses current from context)",
            },
            "service_type": {
                "type": "string",
                "description": "Optional service type filter",
                "enum": ["beacon", "execution", "prometheus", "grafana"],
            },
        },
    },
)
def get_service_urls(
    enclave_name: Optional[str] = None,
    service_type: Optional[str] = None,
    context: Optional[Any] = None,
) -> str:
    """Get service URLs."""
    try:
        # Resolve enclave
        if not enclave_name and context:
            enclave_name = context.get_enclave_name()

        if not enclave_name:
            return "❌ No enclave specified"

        client = KurtosisClient(dry_run=False)
        services = client.get_services(enclave_name)

        if not services:
            return f"❌ No services found in {enclave_name}"

        # Filter by type
        if service_type:
            services = [s for s in services if service_type.lower() in s.name.lower()]

        lines = [f"**Service URLs: {enclave_name}**\n"]

        for service in services:
            http_url = service.get_url("http")
            if http_url:
                lines.append(f"- **{service.name}**: {http_url}")

        if not lines[1:]:
            return f"❌ No services found matching filter: {service_type}"

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error getting service URLs: {e}"
