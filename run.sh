#!/usr/bin/env bash
# CharityChain — full system startup (chain, database, contract, users, API)
set -uo pipefail
NODES=7
IMAGE="mdpranto0sikder/cbbft-besu:1.0"
RPC="http://localhost:8545"
DB_URL="postgresql+asyncpg://postgres:charitychain@localhost:5432/charitychain"
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "[1/7] Stopping anything already running"
pkill -f uvicorn 2>/dev/null || true
docker compose -p cbbft down >/dev/null 2>&1 || true
docker rm -f charitychain-db >/dev/null 2>&1 || true

echo "[2/7] Starting PostgreSQL"
docker run -d --name charitychain-db \
  -e POSTGRES_PASSWORD=charitychain -e POSTGRES_DB=charitychain \
  -p 5432:5432 postgres:16-alpine >/dev/null
sleep 8

echo "[3/7] Generating CB-BFT genesis for $NODES validators"
cd "$ROOT/wsl-setup"
sudo rm -rf networkFiles node*/data
docker run --rm -v "$PWD":/work -w /work --user root "$IMAGE" \
  operator generate-blockchain-config \
  --config-file=qbftConfigFile.json --to=networkFiles --private-key-file-name=key >/dev/null
sudo chown -R "$(id -u):$(id -g)" networkFiles 2>/dev/null || true
grep -q cbbftproposerselection networkFiles/genesis.json && echo "      CB-BFT enabled"

echo "[4/7] Starting $NODES validators"
./setup-nodes.sh "$NODES" >/dev/null
sed -i "s|charitychain/cbbft-besu:26.5.0|$IMAGE|g" docker-compose.yml
docker compose -p cbbft up -d >/dev/null
for i in $(seq 1 40); do
  r=$(curl -s --max-time 3 -X POST -H "Content-Type: application/json" \
    --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' "$RPC" \
    | grep -o '"result":"[^"]*"' || true)
  [ -n "$r" ] && { echo "      chain live: $r"; break; }
  sleep 3
done

echo "[5/7] Deploying CharityChain contract"
cd "$ROOT/blockchain"
npx hardhat run scripts/deploy.js --network localhost 2>&1 | grep -E "deployed|CONTRACT" || \
  echo "      deploy failed — donations will not work"

echo "[6/7] Starting API"
cd "$ROOT/backend"
export DATABASE_URL="$DB_URL"
export HARDHAT_RPC_URL="$RPC"
export HARDHAT_ENABLED="true"
export DEPLOYER_PRIVATE_KEY="0x8f2a55949038a9610f50fb23b5883af3b4ecb3c3bb792cbcefbd1542c692be63"
uvicorn main:app --host 0.0.0.0 --port 8000 >/tmp/api.log 2>&1 &
for i in $(seq 1 30); do
  curl -s --max-time 2 http://localhost:8000/ >/dev/null 2>&1 && break
  sleep 2
done

echo "[7/7] Creating default users"
python3 create_admin.py 2>&1 | tail -1

if [ -n "${CODESPACE_NAME:-}" ]; then
  gh codespace ports visibility 8000:public -c "$CODESPACE_NAME" >/dev/null 2>&1 \
    && echo "      port 8000 set to public"
fi

echo ""
echo "======================================================================"
echo "  CharityChain is running"
echo "    App    : http://localhost:8000/app/"
echo "    API    : http://localhost:8000/"
echo "    Chain  : $RPC   ($NODES CB-BFT validators)"
echo ""
echo "    a@a.com (admin)   / 12345678"
echo "    d@d.com (donor)   / 12345678"
echo "    n@n.com (needy)   / 12345678"
echo "    t@t.com (trustee) / 12345678"
echo ""
echo "  API log: tail -f /tmp/api.log      Stop: ./stop.sh"
echo "======================================================================"
