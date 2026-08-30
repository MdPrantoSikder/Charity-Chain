"""
fault_experiment.py — measure how each protocol responds to degraded nodes.

    python fault_experiment.py

This is the experiment a BFT defence needs. The comparison so far covers
fairness and cost; this covers FAULT TOLERANCE -- what actually happens when
validator nodes go bad.

METHOD
------
Degrade N validator nodes (reputation driven below the 0.30 demotion
threshold), then run a real consensus round under each protocol and record:

  validators still voting     does the protocol exclude the bad nodes?
  nodes demoted               does it detect degradation at all?
  consensus still commits     does the network survive?
  clusters formed             does the structure adapt?

Restores every node afterwards, so your database is left as it was.

WHY THE PROTOCOLS DIFFER -- and it is not a handicap
-----------------------------------------------------
CB-BFT scores nodes on four criteria and demotes any node whose reputation
falls below 0.30, excluding it from voting. Raft and PBFT have NO reputation
system at all -- they cannot read node attributes, so a degraded validator
keeps voting indefinitely. That is genuine protocol behaviour, taken from
their specifications, not a limitation imposed for this comparison.
"""

import asyncio
import csv
import importlib
import os
import sys

from sqlalchemy import select

from database import AsyncSessionLocal
from models import ValidatorNode

# How many nodes to degrade at each step
STEPS = [0, 3, 6, 9, 12, 15]
DEGRADED_REPUTATION = 0.15   # below TRUST_DEMOTE (0.30)


def load_engine(protocol: str):
    """Load one consensus module through the same switch the app uses."""
    os.environ["CONSENSUS"] = protocol
    for m in ("consensus", "cbbft_engine", "raft_engine", "pbft_engine"):
        sys.modules.pop(m, None)
    return importlib.import_module("consensus")


async def snapshot(db):
    """Read the real validator set from the database."""
    rows = (await db.execute(
        select(ValidatorNode).order_by(ValidatorNode.id))).scalars().all()
    return [{
        "id": r.id, "org": r.org, "cpu": r.cpu, "latency": r.latency,
        "reputation": r.reputation, "throughput": r.throughput,
        "F_score": r.F_score, "pool": r.pool, "is_leader": r.is_leader,
        "status": r.status, "history": r.history or [],
    } for r in rows]


class Row:
    """Mimics a ValidatorNode row so NodeAttributes.from_db can read it."""
    def __init__(self, d):
        self.__dict__.update(d)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        original = await snapshot(db)

    if not original:
        print("No validator nodes. Run seed_data.py first.")
        return

    print(f"Loaded {len(original)} validators from the database\n")
    results = []

    for protocol in ("cbbft", "raft", "pbft"):
        c = load_engine(protocol)

        for n_bad in STEPS:
            # fresh copy each step -- degradation must not accumulate
            data = [dict(d) for d in original]
            for d in data[:n_bad]:
                d["reputation"] = DEGRADED_REPUTATION
                d["cpu"] = 0.05
                d["throughput"] = 0.05
                d["latency"] = 0.48

            nodes = [c.NodeAttributes.from_db(Row(d)) for d in data]

            pools, _ = c.run_l1_to_l5(nodes)
            node_map = {n.id: n for n in nodes}
            pools_nodes = {p: [node_map[i] for i in ids if i in node_map]
                           for p, ids in pools.items()}
            confirmed, leader, votes, reason = c.run_l6_to_l8(
                pools_nodes, nodes, f"fault_{n_bad}", 1)

            demoted = sum(1 for n in nodes if n.status == "probation")
            approvals = sum(1 for v in votes.values() if v)

            results.append({
                "protocol":     c.ACTIVE,
                "degraded":     n_bad,
                "degraded_pct": round(100 * n_bad / len(nodes), 1),
                "demoted":      demoted,
                "voters":       len(votes),
                "approvals":    approvals,
                "clusters":     len(pools),
                "committed":    confirmed,
                "reason":       reason if not confirmed else "",
            })

    # ── report ───────────────────────────────────────────────────
    hdr = (f"{'protocol':<9}{'degraded':>10}{'demoted':>9}{'voters':>8}"
           f"{'approvals':>11}{'clusters':>10}{'committed':>11}")
    print("=" * len(hdr))
    print("FAULT TOLERANCE — response to degraded validator nodes")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    last = None
    for r in results:
        if last and r["protocol"] != last:
            print("-" * len(hdr))
        print(f"{r['protocol']:<9}{r['degraded']:>10}{r['demoted']:>9}"
              f"{r['voters']:>8}{r['approvals']:>11}{r['clusters']:>10}"
              f"{('yes' if r['committed'] else 'NO'):>11}")
        last = r["protocol"]
    print("=" * len(hdr))

    print("\nReading the result")
    print("  demoted — nodes the protocol excluded from consensus.")
    print("            CB-BFT detects and demotes; Raft and PBFT cannot,")
    print("            because neither reads node attributes at all.")
    print("  committed — whether the block still reached quorum.")

    with open("fault_tolerance.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    print("\nSaved: fault_tolerance.csv")
    print("Database untouched — the experiment ran on in-memory copies.")


if __name__ == "__main__":
    asyncio.run(main())