"""
export_results.py — compare consensus protocols from REAL recorded blocks.

    python export_results.py

Reads what the running system actually produced: blocks sealed on the live Besu
network, the leader each protocol elected, the clusters it formed, how long each
phase took, and whether the block reached the chain.

WHAT IS MEASURED
----------------
  blocks sealed      real rows in the blocks table
  distinct leaders   counted from blocks.leader_node
  leadership Gini    0 = perfectly even rotation, 1 = one node monopolises
  clusters formed    from blocks.pools_formed
  validators voting  from blocks.votes
  scoring / consensus / on-chain latency   wall-clock, recorded per block
  on-chain rate      real transaction hash present

WHAT IS NOT MEASURED — do not claim it
---------------------------------------
Message counts and Byzantine fault tolerance. The validators are database rows
inside one process, so no messages cross a network and no faults are injected.
Those belong in a theoretical analysis section citing each protocol's published
complexity (Ongaro & Ousterhout 2014 for Raft; Castro & Liskov 1999 for PBFT),
not in a measured results table.
"""

import asyncio
import csv
from collections import defaultdict

from sqlalchemy import select

from database import AsyncSessionLocal
from models import Block, AuditLog

# Blocks at or below this index predate the timing instrumentation.
MIN_INDEX = 40


def gini(counts, population):
    """Leadership concentration, zero-padded to the full validator population."""
    c = sorted(list(counts) + [0] * max(0, population - len(counts)))
    k, total = len(c), sum(c)
    if total == 0 or k == 0:
        return 0.0
    return round((2 * sum((i + 1) * v for i, v in enumerate(c))) / (k * total)
                 - (k + 1) / k, 4)


def avg(xs):
    return round(sum(xs) / len(xs), 3) if xs else 0.0


async def main() -> None:
    async with AsyncSessionLocal() as db:
        blocks = (await db.execute(
            select(Block).where(Block.index > MIN_INDEX).order_by(Block.index)
        )).scalars().all()
        logs = (await db.execute(select(AuditLog).where(
            AuditLog.event_type == "donation_confirmed"))).scalars().all()

    if not blocks:
        print(f"No blocks with index > {MIN_INDEX}. Make some donations first.")
        return

    onchain_by_hash = {l.tx_hash: (l.meta or {}).get("on_chain", False)
                       for l in logs}

    groups = defaultdict(list)
    for b in blocks:
        groups[b.consensus or "unknown"].append(b)

    rows = []
    for proto, bs in groups.items():
        leaders = defaultdict(int)
        clusters, voters, onchain = [], [], 0
        t_score, t_cons, t_chain, t_total = [], [], [], []

        for b in bs:
            if b.leader_node:
                leaders[b.leader_node] += 1
            if b.pools_formed:
                clusters.append(len(b.pools_formed))
            if b.votes:
                voters.append(len(b.votes))
            if onchain_by_hash.get(b.block_hash):
                onchain += 1
            if b.total_ms:
                t_score.append(b.scoring_ms or 0)
                t_cons.append(b.consensus_ms or 0)
                t_chain.append(b.onchain_ms or 0)
                t_total.append(b.total_ms or 0)

        population = len({n for b in bs for n in (b.votes or {})}) or len(leaders)

        rows.append({
            "protocol":         proto,
            "blocks":           len(bs),
            "distinct_leaders": len(leaders),
            "leader_gini":      gini(leaders.values(), population),
            "avg_clusters":     avg(clusters),
            "avg_voters":       avg(voters),
            "scoring_ms":       avg(t_score),
            "consensus_ms":     avg(t_cons),
            "onchain_ms":       avg(t_chain),
            "total_ms":         avg(t_total),
            "on_chain":         onchain,
            "on_chain_pct":     round(100 * onchain / len(bs), 1),
            "top_leader":       max(leaders, key=leaders.get) if leaders else "—",
            "top_leader_pct":   round(100 * max(leaders.values()) / len(bs), 1) if leaders else 0,
        })

    rows.sort(key=lambda r: r["protocol"] != "CB-BFT")   # CB-BFT first

    hdr = (f"{'protocol':<10}{'blocks':>7}{'leaders':>8}{'gini':>8}"
           f"{'clusters':>9}{'voters':>7}{'score ms':>10}{'cons ms':>9}"
           f"{'chain ms':>10}{'on-chain':>10}")
    print("\n" + "=" * len(hdr))
    print("MEASURED FROM REAL BLOCKS ON THE LIVE BESU NETWORK")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['protocol']:<10}{r['blocks']:>7}{r['distinct_leaders']:>8}"
              f"{r['leader_gini']:>8}{r['avg_clusters']:>9}{r['avg_voters']:>7}"
              f"{r['scoring_ms']:>10}{r['consensus_ms']:>9}{r['onchain_ms']:>10}"
              f"{str(r['on_chain']) + '/' + str(r['blocks']):>10}")
    print("=" * len(hdr))

    print("\nHow to read this")
    print("  leaders   — distinct nodes that sealed at least one block")
    print("  gini      — 0 rotates evenly, 1 one node monopolises leadership")
    print("  clusters  — groups formed by scoring (1 = flat replica set)")
    print("  voters    — validators participating per block")
    print("  score ms  — CRITIC scoring + adaptive clustering")
    print("  cons ms   — leader election + voting")
    print("  chain ms  — Besu round-trip (should be similar for all protocols,")
    print("              since the chain's work does not change)")

    for r in rows:
        print(f"\n  {r['protocol']}: busiest leader {r['top_leader']} "
              f"sealed {r['top_leader_pct']}% of blocks")

    with open("consensus_comparison.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("\nSaved: consensus_comparison.csv")

    if len(rows) < 3:
        have = ", ".join(r["protocol"] for r in rows)
        print(f"\nOnly {have} recorded. For the full comparison, set")
        print("CONSENSUS=raft in .env, restart, donate again, then CONSENSUS=pbft.")


if __name__ == "__main__":
    asyncio.run(main())