import asyncio
from sqlalchemy import update
from database import AsyncSessionLocal
from models import ValidatorNode, EpochState

RESET_NODES = [
    {"id":"BankA_1", "reputation":0.94, "uptime":0.96, "latency":0.09, "bandwidth":0.92, "stake":0.90, "F_score":0.93, "pool":"Elite",     "is_leader":True,  "status":"active", "history":[]},
    {"id":"BankA_2", "reputation":0.91, "uptime":0.93, "latency":0.11, "bandwidth":0.89, "stake":0.85, "F_score":0.90, "pool":"Elite",     "is_leader":False, "status":"active", "history":[]},
    {"id":"BankA_3", "reputation":0.89, "uptime":0.91, "latency":0.13, "bandwidth":0.87, "stake":0.83, "F_score":0.88, "pool":"Elite",     "is_leader":False, "status":"active", "history":[]},
    {"id":"BankA_4", "reputation":0.86, "uptime":0.88, "latency":0.15, "bandwidth":0.84, "stake":0.80, "F_score":0.85, "pool":"Elite",     "is_leader":False, "status":"active", "history":[]},
    {"id":"BankB_1", "reputation":0.88, "uptime":0.90, "latency":0.14, "bandwidth":0.85, "stake":0.80, "F_score":0.86, "pool":"Elite",     "is_leader":False, "status":"active", "history":[]},
    {"id":"BankB_2", "reputation":0.85, "uptime":0.87, "latency":0.17, "bandwidth":0.82, "stake":0.77, "F_score":0.82, "pool":"Standard",  "is_leader":False, "status":"active", "history":[]},
    {"id":"BankB_3", "reputation":0.82, "uptime":0.84, "latency":0.19, "bandwidth":0.80, "stake":0.74, "F_score":0.79, "pool":"Standard",  "is_leader":False, "status":"active", "history":[]},
    {"id":"BankB_4", "reputation":0.79, "uptime":0.81, "latency":0.21, "bandwidth":0.77, "stake":0.71, "F_score":0.76, "pool":"Standard",  "is_leader":False, "status":"active", "history":[]},
    {"id":"BankC_1", "reputation":0.84, "uptime":0.86, "latency":0.18, "bandwidth":0.83, "stake":0.78, "F_score":0.81, "pool":"Standard",  "is_leader":False, "status":"active", "history":[]},
    {"id":"BankC_2", "reputation":0.80, "uptime":0.82, "latency":0.22, "bandwidth":0.79, "stake":0.74, "F_score":0.77, "pool":"Standard",  "is_leader":False, "status":"active", "history":[]},
    {"id":"BankC_3", "reputation":0.76, "uptime":0.78, "latency":0.25, "bandwidth":0.75, "stake":0.70, "F_score":0.73, "pool":"Standard",  "is_leader":False, "status":"active", "history":[]},
    {"id":"NGO_A_1", "reputation":0.73, "uptime":0.77, "latency":0.28, "bandwidth":0.72, "stake":0.64, "F_score":0.71, "pool":"Standard",  "is_leader":False, "status":"active", "history":[]},
    {"id":"NGO_A_2", "reputation":0.70, "uptime":0.75, "latency":0.31, "bandwidth":0.69, "stake":0.60, "F_score":0.68, "pool":"Standard",  "is_leader":False, "status":"active", "history":[]},
    {"id":"NGO_A_3", "reputation":0.67, "uptime":0.72, "latency":0.33, "bandwidth":0.66, "stake":0.57, "F_score":0.64, "pool":"Observer",  "is_leader":False, "status":"active", "history":[]},
    {"id":"NGO_A_4", "reputation":0.64, "uptime":0.69, "latency":0.36, "bandwidth":0.63, "stake":0.54, "F_score":0.61, "pool":"Observer",  "is_leader":False, "status":"active", "history":[]},
    {"id":"NGO_B_1", "reputation":0.75, "uptime":0.79, "latency":0.26, "bandwidth":0.73, "stake":0.66, "F_score":0.73, "pool":"Observer",  "is_leader":False, "status":"active", "history":[]},
    {"id":"NGO_B_2", "reputation":0.68, "uptime":0.73, "latency":0.33, "bandwidth":0.67, "stake":0.59, "F_score":0.64, "pool":"Observer",  "is_leader":False, "status":"watch",  "history":[]},
    {"id":"NGO_B_3", "reputation":0.65, "uptime":0.70, "latency":0.36, "bandwidth":0.64, "stake":0.56, "F_score":0.61, "pool":"Observer",  "is_leader":False, "status":"watch",  "history":[]},
    {"id":"NGO_B_4", "reputation":0.62, "uptime":0.67, "latency":0.39, "bandwidth":0.61, "stake":0.53, "F_score":0.57, "pool":"Observer",  "is_leader":False, "status":"watch",  "history":[]},
    {"id":"NGO_C_1", "reputation":0.71, "uptime":0.75, "latency":0.29, "bandwidth":0.70, "stake":0.62, "F_score":0.69, "pool":"Observer",  "is_leader":False, "status":"active", "history":[]},
    {"id":"NGO_C_2", "reputation":0.66, "uptime":0.70, "latency":0.34, "bandwidth":0.65, "stake":0.57, "F_score":0.63, "pool":"Observer",  "is_leader":False, "status":"active", "history":[]},
    {"id":"NGO_C_3", "reputation":0.61, "uptime":0.65, "latency":0.39, "bandwidth":0.60, "stake":0.52, "F_score":0.57, "pool":"Observer",  "is_leader":False, "status":"watch",  "history":[]},
    {"id":"Hosp_A_1","reputation":0.61, "uptime":0.66, "latency":0.40, "bandwidth":0.61, "stake":0.57, "F_score":0.55, "pool":"Probation", "is_leader":False, "status":"watch",  "history":[]},
    {"id":"Hosp_A_2","reputation":0.58, "uptime":0.63, "latency":0.43, "bandwidth":0.58, "stake":0.54, "F_score":0.50, "pool":"Probation", "is_leader":False, "status":"inactive","history":[]},
    {"id":"Hosp_A_3","reputation":0.55, "uptime":0.60, "latency":0.46, "bandwidth":0.55, "stake":0.51, "F_score":0.46, "pool":"Probation", "is_leader":False, "status":"inactive","history":[]},
    {"id":"Hosp_B_1","reputation":0.63, "uptime":0.67, "latency":0.38, "bandwidth":0.62, "stake":0.58, "F_score":0.57, "pool":"Probation", "is_leader":False, "status":"watch",  "history":[]},
    {"id":"Hosp_B_2","reputation":0.59, "uptime":0.64, "latency":0.42, "bandwidth":0.59, "stake":0.55, "F_score":0.52, "pool":"Probation", "is_leader":False, "status":"watch",  "history":[]},
    {"id":"Hosp_B_3","reputation":0.56, "uptime":0.61, "latency":0.45, "bandwidth":0.56, "stake":0.52, "F_score":0.48, "pool":"Probation", "is_leader":False, "status":"inactive","history":[]},
    {"id":"Govt_A_1","reputation":0.87, "uptime":0.89, "latency":0.15, "bandwidth":0.86, "stake":0.82, "F_score":0.84, "pool":"Elite",     "is_leader":False, "status":"active", "history":[]},
    {"id":"Govt_A_2","reputation":0.83, "uptime":0.85, "latency":0.19, "bandwidth":0.82, "stake":0.78, "F_score":0.80, "pool":"Standard",  "is_leader":False, "status":"active", "history":[]},
]

async def reset():
    async with AsyncSessionLocal() as db:
        for node in RESET_NODES:
            await db.execute(
                update(ValidatorNode)
                .where(ValidatorNode.id == node["id"])
                .values(**node)
            )

        # Reset epoch
        await db.execute(
            update(EpochState)
            .where(EpochState.id == 1)
            .values(epoch_number=1, jsd_score=0.0, last_recluster=None)
        )

        await db.commit()
        print(f"✅ Reset {len(RESET_NODES)} nodes to original scores")
        print("✅ Epoch reset to 1")

asyncio.run(reset())