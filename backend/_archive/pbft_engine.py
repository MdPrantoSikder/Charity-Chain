"""
pbft_engine.py — PBFT as a drop-in replacement for cbbft_engine.

Exposes the SAME four entry points as cbbft_engine and raft_engine.

WHAT PBFT ACTUALLY DOES (Castro & Liskov, 1999)
-----------------------------------------------
  * Round-robin primary. No scoring, no reputation, no clustering.
  * Three phases: pre-prepare (primary -> all), prepare (all -> all),
    commit (all -> all). Message complexity is O(n^2).
  * Every replica INDEPENDENTLY validates -- so a lying primary is caught.
  * Commit requires 2f+1 of n, tolerating f = (n-1)//3 Byzantine nodes.

PBFT is the strong safety baseline: it tolerates the same fault class as
CB-BFT. The comparison is therefore about COST, not about who is safe.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from cbbft_engine import NodeAttributes, TRUST_DEMOTE

PROTOCOL = "PBFT"
LAST_ROUND: Dict[str, float] = {}


def run_l1_to_l5(nodes: List[NodeAttributes]) -> Tuple[Dict[str, List[str]],
                                                       Dict[str, float]]:
    """PBFT has no scoring or clustering -- one flat replica set."""
    active = [n for n in nodes if n.status != "blocked"]
    for n in active:
        n.F_score = 1.0
        n.pool = "Replica-Set"
    return ({"Replica-Set": [n.id for n in active]},
            {n.id: n.F_score for n in active})


def elect_leader(candidates: List[NodeAttributes], epoch: int,
                 tx_hash: str) -> Optional[NodeAttributes]:
    """Round-robin primary -- rotation by epoch, no attributes involved."""
    if not candidates:
        return None
    ranked = sorted(candidates, key=lambda n: n.id)
    leader = ranked[epoch % len(ranked)]
    for n in candidates:
        n.is_leader = False
    leader.is_leader = True
    return leader


def run_l6_to_l8(pools: Dict[str, List[NodeAttributes]],
                 all_nodes: List[NodeAttributes],
                 tx_hash: str,
                 epoch: int = 1) -> Tuple[bool, Optional[NodeAttributes],
                                          Dict[str, bool], str]:
    replicas = pools.get("Replica-Set") or next(iter(pools.values()), [])
    if not replicas:
        return False, None, {}, "No replicas available"

    leader = elect_leader(replicas, epoch, tx_hash)
    n = len(replicas)

    # Every replica validates independently -- dissent is reachable.
    votes = {r.id: (r.status == "active" and r.reputation >= TRUST_DEMOTE)
             for r in replicas}
    approvals = sum(1 for v in votes.values() if v)
    need = (2 * n) // 3 + 1

    LAST_ROUND.update({
        "protocol": PROTOCOL,
        "messages": (n - 1) + 2 * n * (n - 1),    # pre-prepare + prepare + commit
        "rounds": 3,
        "voters": n,
        "quorum": need,
        "f_byzantine": (n - 1) // 3,
    })

    if approvals < need:
        return False, leader, votes, f"Quorum not reached ({approvals}/{need})"
    return True, leader, votes, "Committed"


def run_l9(nodes: List[NodeAttributes], participants: List[str],
           confirmed: bool, baseline_scores: List[float]
           ) -> Tuple[Dict[str, float], float, bool]:
    """PBFT keeps no reputation state."""
    return ({n.id: n.reputation for n in nodes}, 0.0, False)