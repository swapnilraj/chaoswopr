# Docker Compose Ethereum Testnet with NET_ADMIN

This directory contains a Docker Compose setup for a 4-node Ethereum testnet with NET_ADMIN capability enabled for chaos injection testing.

## Why Docker Compose?

Kurtosis doesn't support the `capabilities` parameter in ServiceConfig, making it impossible to add NET_ADMIN at container creation time. Docker Compose directly supports `cap_add: [NET_ADMIN]`, providing a working alternative for chaos injection testing.

## Architecture

- **2 Nethermind** (Execution Layer) nodes
- **2 Prysm** (Consensus Layer) nodes
- **2 Validators**
- **Prometheus** for monitoring
- All containers have **NET_ADMIN** capability for tc/netem fault injection

## Quick Start

```bash
# 1. Setup and generate configs
./setup.sh

# 2. Start the testnet
docker-compose up -d

# 3. Check status
docker-compose ps

# 4. Test chaos injection
python3 ../scripts/test_docker_compose.py
```

## Endpoints

- **EL-1 RPC**: http://localhost:8545
- **EL-2 RPC**: http://localhost:8645
- **CL-1 Beacon API**: http://localhost:4000
- **CL-2 Beacon API**: http://localhost:4100
- **Prometheus**: http://localhost:9090

## Manual Chaos Injection

With NET_ADMIN enabled, you can inject faults directly:

```bash
# Packet loss (20%)
docker exec el-1-nethermind tc qdisc add dev eth0 root netem loss 20%

# Network latency (100ms)
docker exec el-1-nethermind tc qdisc add dev eth0 root netem delay 100ms

# Bandwidth throttling (1 Mbit/s)
docker exec el-1-nethermind tc qdisc add dev eth0 root tbf rate 1mbit burst 32kbit latency 400ms

# Remove faults
docker exec el-1-nethermind tc qdisc del dev eth0 root
```

## Using chaoswopr Library

```python
from chaoswopr.chaos.network_faults import NetworkFault, FaultType, NetworkFaultInjector

# Create fault
fault = NetworkFault(
    fault_type=FaultType.PACKET_LOSS,
    target_service="el-1-nethermind",
    loss_percentage=20.0,
)

# Inject
injector = NetworkFaultInjector(dry_run=False)
injector.inject_fault(fault)

# Cleanup
injector.remove_fault(fault.id)
```

## Stopping

```bash
# Stop containers (keep data)
docker-compose stop

# Stop and remove containers (keep data volumes)
docker-compose down

# Remove everything including data
docker-compose down -v
```

## Troubleshooting

### Containers not starting

Check logs:
```bash
docker-compose logs -f
```

### NET_ADMIN not working

Verify capability:
```bash
docker inspect el-1-nethermind | grep CapAdd
# Should show: "CapAdd": ["NET_ADMIN"]
```

### tc command not found

Install iproute2:
```bash
docker exec el-1-nethermind apt-get update
docker exec el-1-nethermind apt-get install -y iproute2
```

## Differences from Kurtosis

| Feature | Kurtosis | Docker Compose |
|---------|----------|----------------|
| NET_ADMIN support | ❌ No | ✅ Yes |
| Setup complexity | Low | Medium |
| Genesis generation | Automated | Manual |
| Client diversity | Built-in | Manual config |
| Best for | Production testing | Chaos injection testing |

## Next Steps

After verifying chaos injection works:
1. Test Track F (Node Agents) with Beacon API endpoints
2. Test Track G (Observer) with Prometheus endpoint
3. Consider migrating to Kubernetes + chaos-mesh for production
