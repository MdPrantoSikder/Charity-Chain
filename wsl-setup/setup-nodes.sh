#!/usr/bin/env bash
set -euo pipefail

COUNT="${1:-10}"
IMAGE="charitychain/cbbft-besu:26.5.0"
BASE_RPC=8545
SUBNET="172.28.0"
IP_OFFSET=10

mapfile -t ADDRS < <(ls -1 networkFiles/keys | sort)
if (( ${#ADDRS[@]} < COUNT )); then
  echo "Only ${#ADDRS[@]} keys available, need $COUNT" >&2
  exit 1
fi

sudo rm -rf node*/ static-nodes.json docker-compose.yml

for ((i=0; i<COUNT; i++)); do
  n=$((i+1))
  mkdir -p "node$n/data"
  cp "networkFiles/keys/${ADDRS[$i]}/key"     "node$n/data/key"
  cp "networkFiles/keys/${ADDRS[$i]}/key.pub" "node$n/data/key.pub"
done

{
  echo "["
  for ((i=0; i<COUNT; i++)); do
    n=$((i+1))
    ip="${SUBNET}.$((IP_OFFSET + i))"
    pub=$(tr -d '\n' < "node$n/data/key.pub" | sed 's/^0x//')
    sep=","
    if (( i == COUNT-1 )); then sep=""; fi
    echo "  \"enode://${pub}@${ip}:30303\"${sep}"
  done
  echo "]"
} > static-nodes.json

for ((i=0; i<COUNT; i++)); do
  cp static-nodes.json "node$((i+1))/data/static-nodes.json"
done

chmod -R 777 node*/data

# ── Heterogeneous validator tiers ──────────────────────────────────
# All fifteen containers were previously identical, so CB-BFT had no real
# difference to score: proposal counts drifted apart by chance and the feedback
# loop amplified it. CPU limits create genuine heterogeneity - a constrained
# node is measurably slower to build and seal a block, which shows up in the
# latency criterion as a larger timestamp delta.
#
# The tiers model a consortium of unequal participants: well-resourced banks,
# mid-sized hospitals, and small NGOs on modest infrastructure.
#   tier A - first third  - 2.00 CPU, 512m heap
#   tier B - second third - 0.75 CPU, 384m heap
#   tier C - final third  - 0.30 CPU, 256m heap
# Node 1 is always tier A: it serves RPC for every experiment, and throttling
# it would make the measurement harness the bottleneck rather than consensus.
tier_of() {
  local idx=$1 total=$2
  local third=$(( (total + 2) / 3 ))
  if (( idx == 0 )) || (( idx < third )); then echo A
  elif (( idx < 2*third )); then echo B
  else echo C; fi
}
tier_cpus() { case "$1" in A) echo 2.0 ;; B) echo 0.75 ;; C) echo 0.30 ;; esac; }
tier_heap() { case "$1" in A) echo 512m ;; B) echo 384m ;; C) echo 256m ;; esac; }
tier_mem()  { case "$1" in A) echo 900m ;; B) echo 800m ;; C) echo 700m ;; esac; }

exec > docker-compose.yml
echo "services:"
for ((i=0; i<COUNT; i++)); do
  n=$((i+1))
  rpc=$((BASE_RPC + i))
  ip="${SUBNET}.$((IP_OFFSET + i))"
  tier=$(tier_of "$i" "$COUNT")
  echo "  node${n}:"
  echo "    image: ${IMAGE}"
  echo "    container_name: cbbft-node${n}"
  echo "    environment:"
  echo "      BESU_OPTS: \"-Xmx$(tier_heap "$tier")\""
  echo "    command:"
  echo "      - --genesis-file=/opt/besu/genesis.json"
  echo "      - --data-path=/opt/besu/data"
  echo "      - --node-private-key-file=/opt/besu/data/key"
  echo "      - --p2p-host=${ip}"
  echo "      - --p2p-port=30303"
  echo "      - --rpc-http-enabled"
  echo "      - --rpc-http-host=0.0.0.0"
  echo "      - --rpc-http-port=8545"
  if [ "$n" = "1" ]; then
    echo "      - --rpc-ws-enabled"
    echo "      - --rpc-ws-host=0.0.0.0"
    echo "      - --rpc-ws-port=8546"
    echo "      - --rpc-ws-api=ETH,NET,WEB3"
  fi
  echo "      - --rpc-http-api=ETH,NET,WEB3,ADMIN,TXPOOL,QBFT,IBFT"
  echo "      - --host-allowlist=*"
  echo "      - --rpc-http-cors-origins=*"
  echo "      - --min-gas-price=0"
  echo "    volumes:"
  echo "      - ./networkFiles/genesis.json:/opt/besu/genesis.json:ro"
  echo "      - ./node${n}/data:/opt/besu/data"
  echo "    ports:"
  echo "      - \"${rpc}:8545\""
  if [ "$n" = "1" ]; then
    echo "      - \"8600:8546\""
  fi
  echo "    cpus: $(tier_cpus "$tier")"
  echo "    mem_limit: $(tier_mem "$tier")"
  echo "    labels:"
  echo "      cbbft.tier: \"${tier}\""
  echo "    networks:"
  echo "      cbbft:"
  echo "        ipv4_address: ${ip}"
done
echo ""
echo "networks:"
echo "  cbbft:"
echo "    name: cbbft-net"
echo "    ipam:"
echo "      config:"
echo "        - subnet: ${SUBNET}.0/24"
