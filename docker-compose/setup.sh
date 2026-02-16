#!/bin/bash
# Setup script for Docker Compose Ethereum testnet
#
# This script:
# 1. Generates JWT secrets for EL-CL authentication
# 2. Creates a simple genesis configuration
# 3. Generates validator keys
# 4. Creates Prometheus config
# 5. Starts the testnet with NET_ADMIN capability

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$SCRIPT_DIR/config"

echo "========================================="
echo "  Ethereum Testnet Setup"
echo "  with NET_ADMIN for Chaos Injection"
echo "========================================="
echo

# Create config directory
mkdir -p "$CONFIG_DIR"

# Step 1: Generate JWT secrets
echo "[1/5] Generating JWT secrets..."
if [ ! -f "$CONFIG_DIR/jwt.hex" ]; then
    openssl rand -hex 32 | tr -d "\n" > "$CONFIG_DIR/jwt.hex"
    echo "✓ JWT secret generated"
else
    echo "✓ JWT secret already exists"
fi

# Step 2: Create simple genesis.json
echo "[2/5] Creating genesis configuration..."
cat > "$CONFIG_DIR/genesis.json" << 'EOF'
{
  "config": {
    "chainId": 32382,
    "homesteadBlock": 0,
    "eip150Block": 0,
    "eip155Block": 0,
    "eip158Block": 0,
    "byzantiumBlock": 0,
    "constantinopleBlock": 0,
    "petersburgBlock": 0,
    "istanbulBlock": 0,
    "berlinBlock": 0,
    "londonBlock": 0,
    "mergeForkBlock": 0,
    "shanghaiTime": 0,
    "terminalTotalDifficulty": 0,
    "terminalTotalDifficultyPassed": true
  },
  "nonce": "0x0",
  "timestamp": "0x0",
  "extraData": "0x",
  "gasLimit": "0x47b760",
  "difficulty": "0x1",
  "mixHash": "0x0000000000000000000000000000000000000000000000000000000000000000",
  "coinbase": "0x0000000000000000000000000000000000000000",
  "alloc": {
    "0x123463a4B065722E99115D6c222f267d9cABb524": {
      "balance": "0x200000000000000000000000000000000000000000000000000000000000000"
    }
  },
  "number": "0x0",
  "gasUsed": "0x0",
  "parentHash": "0x0000000000000000000000000000000000000000000000000000000000000000"
}
EOF
echo "✓ Genesis configuration created"

# Step 3: Create minimal Beacon chain config
echo "[3/5] Creating Beacon chain configuration..."
cat > "$CONFIG_DIR/config.yaml" << 'EOF'
PRESET_BASE: 'mainnet'
CONFIG_NAME: 'chaoswopr-testnet'

# Genesis
MIN_GENESIS_TIME: 0
GENESIS_DELAY: 0

# Altair
ALTAIR_FORK_EPOCH: 0

# Bellatrix (Merge)
BELLATRIX_FORK_EPOCH: 0
TERMINAL_TOTAL_DIFFICULTY: 0

# Capella (Shanghai)
CAPELLA_FORK_EPOCH: 0

# Deneb
DENEB_FORK_EPOCH: 0

# Time parameters (faster for testing)
SECONDS_PER_SLOT: 12
SLOTS_PER_EPOCH: 32
MIN_VALIDATOR_WITHDRAWABILITY_DELAY: 256
SHARD_COMMITTEE_PERIOD: 256

# Deposit contract (not used for testing)
DEPOSIT_CHAIN_ID: 32382
DEPOSIT_NETWORK_ID: 32382
DEPOSIT_CONTRACT_ADDRESS: 0x4242424242424242424242424242424242424242

# Eth1
ETH1_FOLLOW_DISTANCE: 1
EOF
echo "✓ Beacon chain config created"

# Step 4: Create Prometheus config
echo "[4/5] Creating Prometheus configuration..."
mkdir -p "$CONFIG_DIR"
cat > "$CONFIG_DIR/prometheus.yml" << 'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'nethermind-el-1'
    static_configs:
      - targets: ['el-1:8545']

  - job_name: 'nethermind-el-2'
    static_configs:
      - targets: ['el-2:8545']

  - job_name: 'prysm-cl-1'
    static_configs:
      - targets: ['cl-1:8080']

  - job_name: 'prysm-cl-2'
    static_configs:
      - targets: ['cl-2:8080']
EOF
echo "✓ Prometheus config created"

# Step 5: Copy JWT to volume mount locations (will be done by docker-compose)
echo "[5/5] Setup complete!"
echo

# Create docker-compose override for JWT mounting
cat > "$SCRIPT_DIR/docker-compose.override.yml" << EOF
version: '3.8'

services:
  el-1:
    volumes:
      - $CONFIG_DIR/jwt.hex:/nethermind/data/jwt.hex:ro

  el-2:
    volumes:
      - $CONFIG_DIR/jwt.hex:/nethermind/data/jwt.hex:ro
EOF

echo "========================================="
echo "  Setup Complete!"
echo "========================================="
echo
echo "Next steps:"
echo "  1. Start the testnet:"
echo "     cd $SCRIPT_DIR && docker-compose up -d"
echo
echo "  2. Check status:"
echo "     docker-compose ps"
echo
echo "  3. View logs:"
echo "     docker-compose logs -f"
echo
echo "  4. Test chaos injection:"
echo "     docker exec el-1-nethermind tc qdisc add dev eth0 root netem delay 100ms"
echo
echo "  5. Stop testnet:"
echo "     docker-compose down"
echo
echo "Endpoints:"
echo "  - EL-1 RPC:  http://localhost:8545"
echo "  - EL-2 RPC:  http://localhost:8645"
echo "  - CL-1 API:  http://localhost:4000"
echo "  - CL-2 API:  http://localhost:4100"
echo "  - Prometheus: http://localhost:9090"
echo
