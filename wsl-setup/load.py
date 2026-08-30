#!/usr/bin/env python3
"""Constant-rate transaction load for the CB-BFT experiments.

    ./venv/bin/python load.py <tps> <duration_seconds>

Uses the standard Besu dev account, which is the alloc address in
qbftConfigFile.json. That key is public and published in Besu's own
docs - fine for a disposable local chain, never for anything else.
"""
import sys
import time
from web3 import Web3

RPC = "http://localhost:8545"
KEY = "0x8f2a55949038a9610f50fb23b5883af3b4ecb3c3bb792cbcefbd1542c692be63"

tps = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
duration = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0

w3 = Web3(Web3.HTTPProvider(RPC))
acct = w3.eth.account.from_key(KEY)
chain_id = w3.eth.chain_id
nonce = w3.eth.get_transaction_count(acct.address)

interval = 1.0 / tps
deadline = time.time() + duration
sent = 0
failed = 0

while time.time() < deadline:
    tx = {
        "to": acct.address,
        "value": 0,
        "gas": 21000,
        "gasPrice": 0,
        "nonce": nonce,
        "chainId": chain_id,
    }
    try:
        signed = acct.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None)
        if raw is None:
            raw = signed.rawTransaction
        w3.eth.send_raw_transaction(raw)
        nonce += 1
        sent += 1
    except Exception as exc:
        failed += 1
        if failed <= 3:
            print(f"tx failed: {exc}", file=sys.stderr)
    time.sleep(interval)

print(f"sent={sent} failed={failed}")
