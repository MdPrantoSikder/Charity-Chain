"""
benchmark.py — run the SAME workload through each consensus and record it.

    python benchmark.py

This is the experiment. Identical nodes, identical donations, identical escrow
rules. The only thing that changes between runs is which consensus module is
loaded. Whatever difference appears in the table is caused by the algorithm.

Nodes are built here from a FIXED SEED rather than read from the database, so
every protocol faces the identical population and re-running reproduces the
numbers exactly -- which is what you need when the table goes in a paper.
"""

from __future__ import annotations

import importlib
import json
import os
import random
import statistics
import sys
import time
import types
from typing import Dict, List

ROUNDS  = 30          # donations per protocol
N_NODES = 30


def make_db_rows(n: int, seed: int = 7) -> List[types.SimpleNamespace]:
    """
    Identical node population for every protocol.

    Carries exactly the four CRITIC criteria -- cpu, latency, reputation,
    throughput -- matching the validator_nodes table after migrate_criteria.py.
    """
    rng = random.Random(seed)
    orgs = ["BankA", "BankB", "BankC", "NGO_A", "NGO_B", "NGO_C", "Hosp_A", "Hosp_B"]
    return [types.SimpleNamespace(
        id=f"N{i:02d}", org=orgs[i % 8],
        cpu=round(rng.uniform(0.30, 1.00), 4),
        latency=round(rng.uniform(0.05, 0.50), 4),      # cost criterion
        reputation=round(rng.uniform(0.40, 1.00), 4),
        throughput=round(rng.uniform(0.20, 1.00), 4),
        F_score=0.0, pool="", is_leader=False,
        status="active", history=[]) for i in range(n)]


def run_one(protocol: str) -> Dict:
    """Run ROUNDS consensus rounds under one protocol and record the metrics."""
    os.environ["CONSENSUS"] = protocol
    for m in ("consensus", "cbbft_engine", "raft_engine", "pbft_engine"):
        sys.modules.pop(m, None)
    c = importlib.import_module("consensus")

    rows  = make_db_rows(N_NODES)
    nodes = [c.NodeAttributes.from_db(r) for r in rows]

    latencies, msgs, ok_rounds, fails = [], [], 0, 0
    leaders_seen: Dict[str, int] = {}

    for h in range(1, ROUNDS + 1):
        baseline = [n.F_score for n in nodes]
        t0 = time.perf_counter()

        pools_dict, _ = c.run_l1_to_l5(nodes)
        node_map    = {n.id: n for n in nodes}
        pools_nodes = {p: [node_map[i] for i in ids if i in node_map]
                       for p, ids in pools_dict.items()}
        confirmed, leader, votes, reason = c.run_l6_to_l8(
            pools_nodes, nodes, f"tx_{h}", h)
        c.run_l9(nodes, list(votes.keys()), confirmed, baseline)

        dt = (time.perf_counter() - t0) * 1000.0
        if confirmed:
            ok_rounds += 1
            latencies.append(dt)
            msgs.append(c.LAST_ROUND.get("messages", 0))
            if leader:
                leaders_seen[leader.id] = leaders_seen.get(leader.id, 0) + 1
        else:
            fails += 1

    # Gini over how often each node led.
    # 0 = leadership rotates perfectly evenly, 1 = one node monopolises it.
    counts = sorted(leaders_seen.get(n.id, 0) for n in nodes)
    k, total = len(counts), sum(counts)
    if total == 0:
        gini = 0.0
    else:
        gini = round(
            (2 * sum((i + 1) * v for i, v in enumerate(counts))) / (k * total)
            - (k + 1) / k, 4)

    return {
        "protocol":         c.ACTIVE,
        "committed":        ok_rounds,
        "failed":           fails,
        "msgs_per_round":   round(statistics.mean(msgs), 1) if msgs else 0,
        "latency_ms":       round(statistics.mean(latencies), 3) if latencies else 0,
        "f_byzantine":      c.LAST_ROUND.get("f_byzantine", 0),
        "distinct_leaders": len(leaders_seen),
        "leader_gini":      gini,
    }


if __name__ == "__main__":
    print(f"Same system, same {N_NODES} nodes, same {ROUNDS} donations.")
    print("Only the consensus module changes.\n")

    results = [run_one(p) for p in ("cbbft", "raft", "pbft")]

    hdr = (f"{'protocol':<10}{'committed':>11}{'failed':>8}{'msgs/round':>12}"
           f"{'latency ms':>12}{'f_byz':>7}{'leaders':>9}{'gini':>8}")
    print("=" * len(hdr)); print(hdr); print("=" * len(hdr))
    for r in results:
        print(f"{r['protocol']:<10}{r['committed']:>11}{r['failed']:>8}"
              f"{r['msgs_per_round']:>12}{r['latency_ms']:>12}"
              f"{r['f_byzantine']:>7}{r['distinct_leaders']:>9}{r['leader_gini']:>8}")

    with open("benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved: benchmark_results.json")
    print("\n'leaders' = distinct nodes that led at least once (fairness).")
    print("'gini'    = 0 means leadership rotates evenly, 1 means one node monopolises.")
    print("\nCB-BFT restricts proposing to the top 30% of each cluster, so its Gini")
    print("is expected to sit between Raft (one permanent leader) and PBFT")
    print("(quality-blind round-robin) -- not at zero.")