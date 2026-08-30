"""
raft_engine.py — Raft as a drop-in replacement for cbbft_engine.

Exposes the SAME four entry points, so swapping consensus is one env var:

    NodeAttributes, run_l1_to_l5, run_l6_to_l8, run_l9

WHAT RAFT ACTUALLY DOES (Ongaro & Ousterhout, 2014)
---------------------------------------------------
  * ONE stable leader. It only changes when the current leader fails --
    there is no scoring, no reputation, no attribute-based selection.
  * The leader appends entries to all followers; followers ACKNOWLEDGE.
    They do NOT independently validate the entry -- they replicate what the
    leader sends. This is why a lying leader is simply believed.
  * Commit requires a SIMPLE MAJORITY (n/2 + 1), not 2f+1.
  * Byzantine tolerance: ZERO. Raft assumes crash faults only.

Because Raft has no notion of node attributes, run_l1_to_l5 does no scoring --
every node sits in one flat replica set. That is not a simplification, it is
what Raft is. Reporting it that way is the honest comparison.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from cbbft_engine import NodeAttributes          # identical node record

PROTOCOL = "Raft"
LAST_ROUND: Dict[str, float] = {}                # metrics for the benchmark


def run_l1_to_l5(nodes: List[NodeAttributes]) -> Tuple[Dict[str, List[str]],
                                                       Dict[str, float]]:
    """Raft has no scoring or clustering -- one flat replica set."""
    active = [n for n in nodes if n.status != "blocked"]
    for n in active:
        n.F_score = 1.0            # Raft does not rank nodes
        n.pool = "Replica-Set"
    return ({"Replica-Set": [n.id for n in active]},
            {n.id: n.F_score for n in active})


def elect_leader(candidates: List[NodeAttributes], epoch: int,
                 tx_hash: str) -> Optional[NodeAttributes]:
    """One stable leader: the first node, rotating only on failure (by epoch)."""
    if not candidates:
        return None
    ranked = sorted(candidates, key=lambda n: n.id)
    leader = ranked[0]                     # stable -- no rotation per block
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

    # Followers ACK without validating -- Raft's defining property.
    votes = {r.id: (r.status != "blocked") for r in replicas}
    acks = sum(1 for v in votes.values() if v)
    need = n // 2 + 1

    LAST_ROUND.update({
        "protocol": PROTOCOL,
        "messages": 2 * (n - 1),           # AppendEntries + ACK per follower
        "rounds": 2,
        "voters": n,
        "quorum": need,
        "f_byzantine": 0,
    })

    if acks < need:
        return False, leader, votes, f"Majority not reached ({acks}/{need})"
    return True, leader, votes, "Committed"


def run_l9(nodes: List[NodeAttributes], participants: List[str],
           confirmed: bool, baseline_scores: List[float]
           ) -> Tuple[Dict[str, float], float, bool]:
    """Raft keeps no reputation. Scores stay flat; there is nothing to drift."""
    return ({n.id: n.reputation for n in nodes}, 0.0, False)