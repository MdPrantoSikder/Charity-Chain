#!/usr/bin/env bash
set -euo pipefail

COUNT="${1:-10}"
BESU=~/besu/build/install/besu/bin/besu

mapfile -t ADDRS < <(ls -1 networkFiles/keys | sort)

if [[ ! -f networkFiles/genesis.json.orig ]]; then
  cp networkFiles/genesis.json networkFiles/genesis.json.orig
fi

{
  echo -n "["
  for ((i=0; i<COUNT; i++)); do
    sep=","
    if (( i == COUNT-1 )); then sep=""; fi
    echo -n "\"${ADDRS[$i]}\"${sep}"
  done
  echo "]"
} > toEncode.json

EXTRA=$("$BESU" rlp encode --type=QBFT_EXTRA_DATA --from=toEncode.json | tr -d '\n')

cp networkFiles/genesis.json.orig networkFiles/genesis.json
sed -i "s|\"extraData\"[[:space:]]*:[[:space:]]*\"[^\"]*\"|\"extraData\": \"${EXTRA}\"|" networkFiles/genesis.json

echo "Validator set now $COUNT nodes"
