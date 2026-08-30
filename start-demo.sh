#!/usr/bin/env bash
# CharityChain demo: 7-validator CB-BFT network + database + API
set -e
NODES=7
IMAGE="mdpranto0sikder/cbbft-besu:1.0"
cd "$(dirname "$0")/wsl-setup"

echo "[1/5] Starting PostgreSQL"
docker rm -f charitychain-db 2>/dev/null || true
docker run -d --name charitychain-db \
  -e POSTGRES_PASSWORD=charitychain \
  -e POSTGRES_DB=charitychain \
  -p 5432:5432 postgres:16-alpine
sleep 8

echo "[2/5] Generating CB-BFT genesis for $NODES validators"
sudo rm -rf networkFiles node*/data
docker run --rm -v "$PWD":/work -w /work --user root "$IMAGE" \
  operator generate-blockchain-config \
  --config-file=qbftConfigFile.json --to=networkFiles --private-key-file-name=key
sudo chown -R "$(id -u):$(id -g)" networkFiles 2>/dev/null || true
grep -q cbbftproposerselection networkFiles/genesis.json && echo "  CB-BFT enabled"

echo "[3/5] Laying out validators"
./setup-nodes.sh "$NODES"
sed -i "s|charitychain/cbbft-besu:26.5.0|$IMAGE|g" docker-compose.yml

echo "[4/5] Starting the network"
docker compose -p cbbft up -d
for i in $(seq 1 40); do
  r=$(curl -s --max-time 3 -X POST -H "Content-Type: application/json" \
    --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
    http://localhost:8545 | grep -o '"result":"[^"]*"' || true)
  [ -n "$r" ] && { echo "  chain live: $r"; break; }
  sleep 3
done

echo "[5/5] Starting the API"
cd ../backend
export DATABASE_URL="postgresql+asyncpg://postgres:charitychain@localhost:5432/charitychain"
export HARDHAT_RPC_URL="http://127.0.0.1:8545"
export HARDHAT_ENABLED="true"
uvicorn main:app --host 0.0.0.0 --port 8000
