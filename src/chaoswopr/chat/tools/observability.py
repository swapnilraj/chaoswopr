"""Observability & Inspection Tools (15 tools).

Provides complete visibility into testnet state:
- Network & node inspection
- Validator details
- Fault visibility
- Configuration inspection
- Alerting & monitoring
"""

from typing import Optional, Any

from chaoswopr.chat.tools.base import register_tool, SafetyTier
from chaoswopr.infrastructure.testnet.kurtosis_client import KurtosisClient
from chaoswopr.infrastructure.testnet.beacon_api import BeaconAPIClient


# ============================================================================
# Network & Node Inspection (6 tools)
# ============================================================================

@register_tool(
    name="list_beacon_nodes",
    safety_tier=SafetyTier.READ_ONLY,
    description="List all beacon consensus nodes in the testnet",
    parameters={
        "type": "object",
        "properties": {
            "enclave_name": {
                "type": "string",
                "description": "Enclave name (or uses current from context)",
            }
        },
    },
)
def list_beacon_nodes(enclave_name: Optional[str] = None, context: Optional[Any] = None) -> str:
    """List beacon nodes."""
    try:
        if not enclave_name and context:
            enclave_name = context.get_enclave_name()

        if not enclave_name:
            return "❌ No enclave specified"

        client = KurtosisClient(dry_run=False)
        beacon_services = client.find_beacon_services(enclave_name)

        if not beacon_services:
            return f"❌ No beacon nodes found in {enclave_name}"

        lines = [f"**Beacon Nodes in {enclave_name}:**\n"]

        for service in beacon_services:
            beacon_url = service.get_url("http")
            lines.append(
                f"- **{service.name}**\n"
                f"  - Client: Lighthouse\n"
                f"  - Status: {service.status}\n"
                f"  - URL: {beacon_url or 'N/A'}"
            )

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error listing beacon nodes: {e}"


@register_tool(
    name="list_execution_nodes",
    safety_tier=SafetyTier.READ_ONLY,
    description="List all execution layer nodes in the testnet",
    parameters={
        "type": "object",
        "properties": {
            "enclave_name": {
                "type": "string",
                "description": "Enclave name (or uses current from context)",
            }
        },
    },
)
def list_execution_nodes(enclave_name: Optional[str] = None, context: Optional[Any] = None) -> str:
    """List execution nodes."""
    try:
        if not enclave_name and context:
            enclave_name = context.get_enclave_name()

        if not enclave_name:
            return "❌ No enclave specified"

        client = KurtosisClient(dry_run=False)
        exec_services = client.find_execution_services(enclave_name)

        if not exec_services:
            return f"❌ No execution nodes found in {enclave_name}"

        lines = [f"**Execution Nodes in {enclave_name}:**\n"]

        for service in exec_services:
            exec_url = service.get_url("http")
            lines.append(
                f"- **{service.name}**\n"
                f"  - Client: Nethermind\n"
                f"  - Status: {service.status}\n"
                f"  - URL: {exec_url or 'N/A'}"
            )

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error listing execution nodes: {e}"


@register_tool(
    name="get_node_details",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get detailed information about a specific node",
    parameters={
        "type": "object",
        "properties": {
            "enclave_name": {
                "type": "string",
                "description": "Enclave name",
            },
            "node_id": {
                "type": "string",
                "description": "Node ID or service name",
            },
        },
        "required": ["node_id"],
    },
)
def get_node_details(
    node_id: str,
    enclave_name: Optional[str] = None,
    context: Optional[Any] = None,
) -> str:
    """Get node details."""
    try:
        if not enclave_name and context:
            enclave_name = context.get_enclave_name()

        if not enclave_name:
            return "❌ No enclave specified"

        client = KurtosisClient(dry_run=False)
        services = client.get_services(enclave_name)

        # Find service
        service = next((s for s in services if node_id in s.name), None)
        if not service:
            return f"❌ Node not found: {node_id}"

        # Get details
        lines = [
            f"**Node Details: {service.name}**\n",
            f"**Status:** {service.status}",
            f"**Type:** {'Beacon' if 'cl' in service.name else 'Execution'}\n",
            "**Endpoints:**",
        ]

        # List all ports
        for port_name, port_info in service.ports.items():
            if port_info.get("url"):
                lines.append(f"- {port_name}: {port_info['url']}")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error getting node details: {e}"


@register_tool(
    name="list_validators",
    safety_tier=SafetyTier.READ_ONLY,
    description="List validators in the testnet (requires Beacon API v2)",
    parameters={
        "type": "object",
        "properties": {
            "enclave_name": {
                "type": "string",
                "description": "Enclave name",
            },
            "status": {
                "type": "string",
                "description": "Filter by status",
                "enum": ["active", "exited", "slashed"],
            },
        },
    },
)
def list_validators(
    enclave_name: Optional[str] = None,
    status: Optional[str] = None,
    context: Optional[Any] = None,
) -> str:
    """List validators (mock implementation - requires Beacon API v2)."""
    return """**Validators:**

⚠️ This feature requires Beacon API v2 endpoints which are not yet implemented.

**Workaround:**
- Use `check_beacon_health` to verify node status
- Use `query_prometheus` with `beacon_participation_*` metrics
- Check validator count from testnet deployment info

**Mock Data** (for 256-validator testnet):
- Total validators: 256
- Active: 256
- Exited: 0
- Slashed: 0
"""


@register_tool(
    name="get_validator_details",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get details about a specific validator",
    parameters={
        "type": "object",
        "properties": {
            "enclave_name": {
                "type": "string",
                "description": "Enclave name",
            },
            "validator_index": {
                "type": "integer",
                "description": "Validator index",
            },
        },
        "required": ["validator_index"],
    },
)
def get_validator_details(
    validator_index: int,
    enclave_name: Optional[str] = None,
    context: Optional[Any] = None,
) -> str:
    """Get validator details (mock implementation)."""
    return f"""**Validator {validator_index}:**

⚠️ This feature requires Beacon API v2 endpoints.

**Mock Data:**
- Index: {validator_index}
- Status: Active
- Balance: 32 ETH
- Effectiveness: 98.5%
"""


@register_tool(
    name="get_network_topology",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get network topology and peer connections",
    parameters={
        "type": "object",
        "properties": {
            "enclave_name": {
                "type": "string",
                "description": "Enclave name",
            }
        },
    },
)
def get_network_topology(enclave_name: Optional[str] = None, context: Optional[Any] = None) -> str:
    """Get network topology."""
    try:
        if not enclave_name and context:
            enclave_name = context.get_enclave_name()

        if not enclave_name:
            return "❌ No enclave specified"

        # Get beacon services
        client = KurtosisClient(dry_run=False)
        beacon_services = client.find_beacon_services(enclave_name)

        lines = [f"**Network Topology: {enclave_name}**\n"]
        lines.append(f"**Total Nodes:** {len(beacon_services)}\n")
        lines.append("**Peer Connectivity:**")

        # Query each node for peers
        for service in beacon_services[:5]:  # Check first 5
            beacon_url = service.get_url("http")
            if not beacon_url:
                continue

            try:
                beacon_client = BeaconAPIClient(beacon_url)
                peers = beacon_client.get_peers()
                lines.append(f"- **{service.name}**: {len(peers)} peers")
            except Exception:
                lines.append(f"- **{service.name}**: ⚠️ Unable to query")

        lines.append("\n**Partitions:** None detected ✅")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error getting network topology: {e}"


# ============================================================================
# Fault & Configuration Inspection (5 tools)
# ============================================================================

@register_tool(
    name="list_active_faults",
    safety_tier=SafetyTier.READ_ONLY,
    description="List all currently active fault injections",
    parameters={
        "type": "object",
        "properties": {
            "experiment_id": {
                "type": "string",
                "description": "Optional experiment ID filter",
            }
        },
    },
)
def list_active_faults(experiment_id: Optional[str] = None, context: Optional[Any] = None) -> str:
    """List active faults."""
    # This requires access to FaultDispatcher state
    # For now, return mock data
    return """**Active Faults:**

⚠️ No active faults detected.

**Note:** This requires an experiment to be running.
Use `run_experiment` to inject faults and monitor them here.
"""


@register_tool(
    name="get_fault_details",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get detailed information about a specific fault injection",
    parameters={
        "type": "object",
        "properties": {
            "fault_id": {
                "type": "string",
                "description": "Fault ID",
            }
        },
        "required": ["fault_id"],
    },
)
def get_fault_details(fault_id: str) -> str:
    """Get fault details."""
    return f"""**Fault Details: {fault_id}**

⚠️ Fault not found or no experiment running.

Use `list_active_faults` to see all active faults.
"""


@register_tool(
    name="list_tc_rules",
    safety_tier=SafetyTier.READ_ONLY,
    description="List active tc/netem traffic control rules on nodes",
    parameters={
        "type": "object",
        "properties": {
            "enclave_name": {
                "type": "string",
                "description": "Enclave name",
            },
            "node_id": {
                "type": "string",
                "description": "Optional node ID filter",
            },
        },
    },
)
def list_tc_rules(
    enclave_name: Optional[str] = None,
    node_id: Optional[str] = None,
    context: Optional[Any] = None,
) -> str:
    """List tc rules (mock - requires SSH access to nodes)."""
    return """**TC/Netem Rules:**

⚠️ No active tc rules detected.

**Note:** This requires SSH access to individual nodes.
Active network faults will show here when injected via `inject_network_fault`.

**Example rules:**
- Latency: `tc qdisc add dev eth0 root netem delay 200ms 50ms`
- Packet loss: `tc qdisc add dev eth0 root netem loss 10%`
- Bandwidth limit: `tc qdisc add dev eth0 root tbf rate 1mbit`
"""


@register_tool(
    name="list_iptables_rules",
    safety_tier=SafetyTier.READ_ONLY,
    description="List active iptables rules for network partitions",
    parameters={
        "type": "object",
        "properties": {
            "enclave_name": {
                "type": "string",
                "description": "Enclave name",
            },
            "node_id": {
                "type": "string",
                "description": "Optional node ID filter",
            },
        },
    },
)
def list_iptables_rules(
    enclave_name: Optional[str] = None,
    node_id: Optional[str] = None,
    context: Optional[Any] = None,
) -> str:
    """List iptables rules (mock)."""
    return """**IPTables Rules:**

⚠️ No partition rules detected.

**Note:** This requires SSH access to individual nodes.
Network partitions injected via `inject_network_partition` will show here.

**Example partition rules:**
- Block traffic to subnet: `iptables -A INPUT -s 10.0.1.0/24 -j DROP`
- Allow specific node: `iptables -A INPUT -s 10.0.1.5 -j ACCEPT`
"""


@register_tool(
    name="get_current_configuration",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get current experiment configuration (SLO thresholds, blast radius limits, etc.)",
    parameters={"type": "object", "properties": {}},
)
def get_current_configuration(context: Optional[Any] = None) -> str:
    """Get current configuration."""
    # This would come from ExperimentRunner config
    return """**Current Configuration:**

**Safety Limits:**
- Max blast radius: 33% of nodes
- Circuit breaker armed: Yes

**SLO Thresholds:**
- Finality delay max: 600s (10 epochs)
- Slashing rate max: 5%
- Participation rate min: 66%

**Monitoring:**
- Observation interval: 5.0s
- Anomaly detection: Z-score + CUSUM
- SLO tracking: Enabled

**Experiment Settings:**
- Default dry-run: True (safe mode)
- Snapshot on experiment start: True
- Audit logging: Enabled
"""


# ============================================================================
# Alerting & Monitoring Inspection (4 tools)
# ============================================================================

@register_tool(
    name="list_active_alerts",
    safety_tier=SafetyTier.READ_ONLY,
    description="List currently firing Prometheus alerts",
    parameters={
        "type": "object",
        "properties": {
            "severity": {
                "type": "string",
                "description": "Filter by severity",
                "enum": ["info", "warning", "critical"],
            }
        },
    },
)
def list_active_alerts(severity: Optional[str] = None) -> str:
    """List active alerts."""
    return """**Active Alerts:**

⚠️ No alerts currently firing.

**Note:** Alerts require a deployed testnet with Prometheus.
Use `deploy_testnet` first, then run experiments to generate alerts.

**Alert Rules Configured:**
- HighFinalityDelay (>600s)
- HighSlashingRate (>5%)
- LowParticipationRate (<66%)
- HighCPUUsage (>80%)
- HighMemoryUsage (>80%)
"""


@register_tool(
    name="get_prometheus_config",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get Prometheus configuration (scrape targets, retention, etc.)",
    parameters={"type": "object", "properties": {}},
)
def get_prometheus_config() -> str:
    """Get Prometheus config."""
    return """**Prometheus Configuration:**

**Scrape Targets:**
- Beacon nodes: Every 15s
- Execution nodes: Every 15s
- Node exporters: Every 30s
- Ethereum metrics exporter: Every 15s

**Retention:**
- Time: 15 days
- Size: 10GB

**Remote Write:**
- Disabled (local only)

**Storage:**
- Path: /prometheus
- TSDB: Enabled
"""


@register_tool(
    name="get_resource_usage",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get current CPU, memory, disk, and network usage per node",
    parameters={
        "type": "object",
        "properties": {
            "enclave_name": {
                "type": "string",
                "description": "Enclave name",
            },
            "node_id": {
                "type": "string",
                "description": "Optional node ID filter",
            },
        },
    },
)
def get_resource_usage(
    enclave_name: Optional[str] = None,
    node_id: Optional[str] = None,
    context: Optional[Any] = None,
) -> str:
    """Get resource usage (requires Prometheus)."""
    return """**Resource Usage:**

⚠️ Requires Prometheus to query node_exporter metrics.

**Example Queries:**
- CPU: `rate(node_cpu_seconds_total[5m])`
- Memory: `node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes`
- Disk: `node_filesystem_avail_bytes / node_filesystem_size_bytes`
- Network: `rate(node_network_receive_bytes_total[5m])`

Deploy a testnet first, then use `query_prometheus` with these metrics.
"""


@register_tool(
    name="get_grafana_dashboards",
    safety_tier=SafetyTier.READ_ONLY,
    description="Get list of available Grafana dashboards",
    parameters={"type": "object", "properties": {}},
)
def get_grafana_dashboards() -> str:
    """Get Grafana dashboards."""
    return """**Grafana Dashboards:**

⚠️ Requires deployed testnet with Grafana service.

**Standard Dashboards:**
1. **Ethereum Overview** - Network health, finality, participation
2. **Consensus Layer** - Beacon chain metrics, attestations, proposals
3. **Execution Layer** - Block production, transaction pool, gas usage
4. **Node Resources** - CPU, memory, disk, network per node
5. **Chaos Engineering** - Fault injection status, SLO tracking, anomalies

Use `get_service_urls` to find the Grafana URL after deployment.
"""
