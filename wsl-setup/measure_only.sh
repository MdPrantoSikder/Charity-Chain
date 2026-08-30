#!/usr/bin/env bash
# Measures the ALREADY-RUNNING network. Does not touch docker-compose or genesis.
set -uo pipefail
PROTOCOL="${1:-ibft2}"; DURATION="${2:-150}"; LABEL="${3:-r1}"; TPS="${4:-5}"
RPC="http://localhost:8545"; WARMUP=30
OUT="results/${PROTOCOL}-15n-${LABEL}"
rpc() { curl -s --max-time 10 -X POST -H "Content-Type: application/json" \
  --data "{\"jsonrpc\":\"2.0\",\"method\":\"$1\",\"params\":$2,\"id\":1}" "$RPC"; }
mkdir -p "$OUT"
cp networkFiles/genesis.json "$OUT/genesis.json" 2>/dev/null || true
B=$(rpc eth_blockNumber "[]" | jq -r .result)
if [ "$B" = "null" ] || [ -z "$B" ]; then echo "RPC not ready - start the network first"; exit 1; fi
echo "=== $PROTOCOL | ${DURATION}s | ${TPS} tx/s ==="
echo "warmup ${WARMUP}s"; sleep "$WARMUP"
START_BLOCK=$(( $(rpc eth_blockNumber "[]" | jq -r .result) )); START_TS=$(date +%s)
echo "start block $START_BLOCK"
./venv/bin/python load.py "$TPS" "$DURATION" > "$OUT/load.log" 2>&1 &
LOAD_PID=$!; sleep "$DURATION"; wait $LOAD_PID 2>/dev/null || true
END_BLOCK=$(( $(rpc eth_blockNumber "[]" | jq -r .result) )); END_TS=$(date +%s)
echo "end block $END_BLOCK"
echo "block,timestamp,proposer,txcount,gasused" > "$OUT/blocks.csv"
for ((b=START_BLOCK; b<=END_BLOCK; b++)); do
  hex=$(printf "0x%x" "$b")
  rpc eth_getBlockByNumber "[\"$hex\",false]" \
    | jq -r '.result | [(.number|ltrimstr("0x")), (.timestamp|ltrimstr("0x")), .miner, (.transactions|length), (.gasUsed|ltrimstr("0x"))] | @csv' >> "$OUT/blocks.csv"
done
BLOCKS=$((END_BLOCK - START_BLOCK)); ELAPSED=$((END_TS - START_TS))
TXS=$(tail -n +2 "$OUT/blocks.csv" | cut -d, -f4 | tr -d '"' | paste -sd+ | bc)
PROPOSERS=$(tail -n +2 "$OUT/blocks.csv" | cut -d, -f3 | sort -u | wc -l)
{ echo "protocol,$PROTOCOL"; echo "nodes,15"; echo "blocks,$BLOCKS"; echo "elapsed_s,$ELAPSED"
  echo "block_interval_s,$(echo "scale=3; $ELAPSED/$BLOCKS" | bc)"
  echo "distinct_proposers,$PROPOSERS"; echo "transactions,$TXS"; } > "$OUT/summary.csv"
echo; cat "$OUT/summary.csv"
