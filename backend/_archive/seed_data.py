"""
seed_data.py — create the 30 validator nodes.

    python seed_data.py

Each node carries exactly the four CRITIC criteria:

    cpu         benefit -- processing power
    latency     COST    -- lower is better
    reputation  benefit -- historical behaviour
    throughput  benefit -- transactions processed per round

F_score, pool and is_leader are NOT seeded. They are CONSENSUS OUTPUT. The old
version wrote F_score=0.93, pool="Elite", is_leader=True straight into the
database -- fabricated consensus results that existed before any consensus had
run. They are computed by run_l1_to_l5, or by running recompute_nodes.py.

HONESTY NOTE for the thesis: these values are SIMULATED, not measured from real
hardware. They are seeded here and drifted by scheduler.py. Say so in the
limitations section.
"""

import asyncio
from sqlalchemy import select
from database import AsyncSessionLocal, engine, Base
from models import ValidatorNode, EpochState

CRITERIA = ("cpu", "latency", "reputation", "throughput")

SEED_NODES = [

    # ── BankA (4 nodes) ──
    {"id":"BankA_1", "org":"BankA", "cpu":0.89, "latency":0.09, "reputation":0.94, "throughput":0.91, "status":"active"},
    {"id":"BankA_2", "org":"BankA", "cpu":0.95, "latency":0.11, "reputation":0.91, "throughput":0.93, "status":"active"},
    {"id":"BankA_3", "org":"BankA", "cpu":0.85, "latency":0.13, "reputation":0.89, "throughput":0.87, "status":"active"},
    {"id":"BankA_4", "org":"BankA", "cpu":0.76, "latency":0.15, "reputation":0.86, "throughput":0.79, "status":"active"},

    # ── BankB (4 nodes) ──
    {"id":"BankB_1", "org":"BankB", "cpu":0.86, "latency":0.14, "reputation":0.88, "throughput":0.92, "status":"active"},
    {"id":"BankB_2", "org":"BankB", "cpu":0.72, "latency":0.17, "reputation":0.85, "throughput":0.71, "status":"active"},
    {"id":"BankB_3", "org":"BankB", "cpu":0.70, "latency":0.19, "reputation":0.82, "throughput":0.79, "status":"active"},
    {"id":"BankB_4", "org":"BankB", "cpu":0.79, "latency":0.21, "reputation":0.79, "throughput":0.70, "status":"active"},

    # ── BankC (3 nodes) ──
    {"id":"BankC_1", "org":"BankC", "cpu":0.91, "latency":0.18, "reputation":0.84, "throughput":0.98, "status":"active"},
    {"id":"BankC_2", "org":"BankC", "cpu":0.80, "latency":0.22, "reputation":0.80, "throughput":0.82, "status":"active"},
    {"id":"BankC_3", "org":"BankC", "cpu":0.66, "latency":0.25, "reputation":0.76, "throughput":0.59, "status":"active"},

    # ── NGO_A (4 nodes) ──
    {"id":"NGO_A_1", "org":"NGO_A", "cpu":0.71, "latency":0.28, "reputation":0.73, "throughput":0.62, "status":"active"},
    {"id":"NGO_A_2", "org":"NGO_A", "cpu":0.61, "latency":0.31, "reputation":0.70, "throughput":0.58, "status":"active"},
    {"id":"NGO_A_3", "org":"NGO_A", "cpu":0.55, "latency":0.33, "reputation":0.67, "throughput":0.58, "status":"active"},
    {"id":"NGO_A_4", "org":"NGO_A", "cpu":0.60, "latency":0.36, "reputation":0.64, "throughput":0.68, "status":"active"},

    # ── NGO_B (4 nodes) ──
    {"id":"NGO_B_1", "org":"NGO_B", "cpu":0.71, "latency":0.26, "reputation":0.75, "throughput":0.75, "status":"active"},
    {"id":"NGO_B_2", "org":"NGO_B", "cpu":0.65, "latency":0.33, "reputation":0.68, "throughput":0.69, "status":"active"},
    {"id":"NGO_B_3", "org":"NGO_B", "cpu":0.61, "latency":0.36, "reputation":0.65, "throughput":0.57, "status":"active"},
    {"id":"NGO_B_4", "org":"NGO_B", "cpu":0.69, "latency":0.39, "reputation":0.62, "throughput":0.77, "status":"active"},

    # ── NGO_C (3 nodes) ──
    {"id":"NGO_C_1", "org":"NGO_C", "cpu":0.75, "latency":0.29, "reputation":0.71, "throughput":0.78, "status":"active"},
    {"id":"NGO_C_2", "org":"NGO_C", "cpu":0.59, "latency":0.34, "reputation":0.66, "throughput":0.56, "status":"active"},
    {"id":"NGO_C_3", "org":"NGO_C", "cpu":0.54, "latency":0.39, "reputation":0.61, "throughput":0.48, "status":"active"},

    # ── Hosp_A (3 nodes) ──
    {"id":"Hosp_A_1", "org":"Hosp_A", "cpu":0.64, "latency":0.40, "reputation":0.61, "throughput":0.61, "status":"active"},
    {"id":"Hosp_A_2", "org":"Hosp_A", "cpu":0.63, "latency":0.43, "reputation":0.58, "throughput":0.59, "status":"active"},
    {"id":"Hosp_A_3", "org":"Hosp_A", "cpu":0.62, "latency":0.46, "reputation":0.55, "throughput":0.67, "status":"active"},

    # ── Hosp_B (3 nodes) ──
    {"id":"Hosp_B_1", "org":"Hosp_B", "cpu":0.50, "latency":0.38, "reputation":0.63, "throughput":0.48, "status":"active"},
    {"id":"Hosp_B_2", "org":"Hosp_B", "cpu":0.65, "latency":0.42, "reputation":0.59, "throughput":0.62, "status":"active"},
    {"id":"Hosp_B_3", "org":"Hosp_B", "cpu":0.64, "latency":0.45, "reputation":0.56, "throughput":0.59, "status":"active"},

    # ── Govt_A (2 nodes) ──
    {"id":"Govt_A_1", "org":"Govt_A", "cpu":0.75, "latency":0.15, "reputation":0.87, "throughput":0.81, "status":"active"},
    {"id":"Govt_A_2", "org":"Govt_A", "cpu":0.86, "latency":0.19, "reputation":0.83, "throughput":0.80, "status":"active"},
]


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        seeded, refreshed = 0, 0

        for node_data in SEED_NODES:
            result = await db.execute(
                select(ValidatorNode).where(ValidatorNode.id == node_data["id"])
            )
            existing = result.scalar_one_or_none()
            if not existing:
                db.add(ValidatorNode(**node_data))
                print(f"  ✅ Seeded: {node_data['id']}")
                seeded += 1
            else:
                for key in CRITERIA:
                    setattr(existing, key, node_data[key])
                refreshed += 1

        result = await db.execute(select(EpochState).where(EpochState.id == 1))
        if not result.scalar_one_or_none():
            db.add(EpochState(id=1, epoch_number=1, jsd_score=0.0))
            print("  ✅ Seeded initial epoch state")

        await db.commit()
        print(f"\n🎉 Seed complete — {seeded} new, {refreshed} refreshed")
        print(f"📊 Total nodes: {len(SEED_NODES)}  across 9 organisations")
        print("   F_score / pool / is_leader are computed, not seeded.")
        print("   Run recompute_nodes.py to populate them now.")


if __name__ == "__main__":
    asyncio.run(seed())