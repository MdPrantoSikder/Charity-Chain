"""
recompute_nodes.py — rescore every validator node with CB-BFT, right now.

The dashboard reads F_score and pool straight from the database. Those columns
still hold values written by the old ABPC engine, so the UI keeps showing the
old picture until something recomputes them. Run this once after the engine
swap; after that, every donation keeps them current.

    python recompute_nodes.py
"""

import asyncio
from sqlalchemy import select

from database import async_session
from models import ValidatorNode
from cbbft_engine import NodeAttributes, run_l1_to_l5


async def main() -> None:
    async with async_session() as db:
        rows = (await db.execute(select(ValidatorNode))).scalars().all()
        if not rows:
            print("No validator nodes found. Run seed_data.py first.")
            return

        nodes = [NodeAttributes.from_db(r) for r in rows]
        print(f"Loaded {len(nodes)} nodes")
        print(f"BEFORE  pools: { {p: sum(1 for n in nodes if n.pool == p) for p in set(n.pool for n in nodes)} }")
        print(f"BEFORE  F_score range: {min(n.F_score for n in nodes):.4f} .. {max(n.F_score for n in nodes):.4f}")

        pools, scores = run_l1_to_l5(nodes)

        by_id = {n.id: n for n in nodes}
        for r in rows:
            n = by_id.get(r.id)
            if n:
                r.F_score = n.F_score
                r.pool = n.pool
                r.is_leader = n.is_leader
        await db.commit()

        print(f"AFTER   pools: { {p: len(v) for p, v in pools.items()} }")
        print(f"AFTER   F_score range: {min(scores.values()):.4f} .. {max(scores.values()):.4f}")
        print("Committed. Refresh the admin dashboard.")


if __name__ == "__main__":
    asyncio.run(main())