"""
cbbft_engine.py — CB-BFT consensus for the CharityChain application.

Replaces the earlier abpc/ package. Exposes the SAME four entry points, so
routes/donations.py only needs its import lines changed:

    NodeAttributes      node record loaded from the ValidatorNode table
    run_l1_to_l5()      CRITIC scoring + adaptive clustering  -> (pools, scores)
    run_l6_to_l8()      leader election + 2/3 vote            -> (ok, leader, votes, reason)
    run_l9()            EWMA reputation update + JSD drift    -> (scores, jsd, recluster)

WHAT CHANGED vs ABPC
--------------------
  scoring    hand-rolled entropy/variance (entropy term was always ~0)
             -> CRITIC (Diakoulaki et al. 1995): objective weights from the data
  clustering fixed thresholds labelled "spectral clustering"
             -> adaptive gap clustering, T = mu_g + 0.5 * sigma_g
  leader     argmax of a fake "VRF" seeded with time.time() (unverifiable)
             -> deterministic top-30% pool, seeded on (epoch, tx_hash)
  voting     a node could never vote no (score floor made it unreachable)
             -> dissent is reachable; quorum is genuinely exercised
  reputation additive +0.02/-0.05, saturates at 1.0 and stops discriminating
             -> EWMA decay, recent behaviour dominates

THE FOUR CRITIC CRITERIA
------------------------
    CPU         benefit -- processing power
    Latency     COST    -- lower is better
    Reputation  benefit -- historical behaviour
    Throughput  benefit -- transactions processed per round

These are the ONLY scored attributes and the only ones the node record carries.
uptime, bandwidth and stake were removed: nothing scored them, and columns no
code reads invite the question "which of these actually matter?".

Run migrate_criteria.py once to add cpu/throughput and drop the other three.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

# ── tunables ─────────────────────────────────────────────────────────
GAP_COEFF        = 0.5     # clustering threshold T = mu_g + GAP_COEFF * sigma_g
MIN_CLUSTERS     = 4       # BFT needs |L| >= 4 to tolerate f >= 1
MIN_CLUSTER_SIZE = 3       # every cluster must be able to supply a backup leader
POOL_FRACTION    = 0.30    # leader candidate pool per cluster
MIN_POOL         = 3
LAMBDA_REWARD    = 0.9     # EWMA on a correct vote
LAMBDA_PUNISH    = 0.8     # punishment lands harder than reward
TRUST_NEUTRAL    = 0.5
TRUST_DEMOTE     = 0.3     # below this -> Probation (recovery room)
JSD_THRESHOLD    = 0.15    # drift above this triggers a recluster

# CB-BFT forms CLUSTERS by score gaps -- there is no Elite/Standard/Observer
# hierarchy (that was ABPC). Clusters are numbered best-first. Probation is a
# membership STATUS from the Recovery Room, not a cluster.
CLUSTER_PREFIX = "Cluster-"

PROTOCOL = "CB-BFT"
LAST_ROUND = {}          # per-round metrics, read by consensus.py / benchmark.py


# ── node record ──────────────────────────────────────────────────────
@dataclass
class NodeAttributes:
    id:         str
    org:        str

    # ── the four CRITIC criteria -- the only scored attributes ───────
    cpu:        float = 0.7     # benefit -- processing power
    latency:    float = 0.2     # COST    -- lower is better
    reputation: float = 0.5     # benefit -- trust / behaviour
    throughput: float = 0.6     # benefit -- tx processed per round

    F_score:    float = 0.0
    pool:       str   = "Cluster-1"
    is_leader:  bool  = False
    status:     str   = "active"
    history:    list  = field(default_factory=list)

    def criteria(self) -> List[float]:
        """
        The four CRITIC criteria, in fixed order:
            [CPU, Latency, Reputation, Throughput]

        Latency is a COST criterion (lower is better) -- see COST_CRITERIA.
        No fallbacks: these are real columns. Substituting bandwidth or stake
        would mean CRITIC scores attributes the thesis does not claim.
        """
        return [self.cpu, self.latency, self.reputation, self.throughput]

    def to_dict(self) -> dict:
        return {
            "id": self.id, "org": self.org,
            "cpu":        round(self.cpu, 4),
            "latency":    round(self.latency, 4),
            "reputation": round(self.reputation, 4),
            "throughput": round(self.throughput, 4),
            "F_score":    round(self.F_score, 4),
            "pool": self.pool, "is_leader": self.is_leader, "status": self.status,
        }

    @classmethod
    def from_db(cls, db_node) -> "NodeAttributes":
        return cls(
            id=db_node.id, org=db_node.org,
            cpu=db_node.cpu, latency=db_node.latency,
            reputation=db_node.reputation, throughput=db_node.throughput,
            F_score=db_node.F_score, pool=db_node.pool,
            is_leader=db_node.is_leader, status=db_node.status,
            history=db_node.history or [],
        )


COST_CRITERIA = {1}          # index of latency


# ── Phase 1: CRITIC ──────────────────────────────────────────────────
def _normalize(X: np.ndarray) -> np.ndarray:
    Xn = np.zeros_like(X, dtype=float)
    for j in range(X.shape[1]):
        col = X[:, j]
        lo, hi = col.min(), col.max()
        if hi - lo == 0:
            Xn[:, j] = 1.0
            continue
        Xn[:, j] = (hi - col) / (hi - lo) if j in COST_CRITERIA else (col - lo) / (hi - lo)
    return Xn


def critic_weights(X: np.ndarray) -> np.ndarray:
    """C_j = sigma_j * sum_k (1 - r_jk);  w_j = C_j / sum C."""
    Xn = _normalize(X)
    sigma = Xn.std(axis=0)
    m = Xn.shape[1]
    R = np.eye(m)
    for j in range(m):
        for k in range(m):
            if j != k:
                R[j, k] = 0.0 if sigma[j] == 0 or sigma[k] == 0 else \
                    np.corrcoef(Xn[:, j], Xn[:, k])[0, 1]
    R = np.nan_to_num(R)
    C = sigma * (1.0 - R).sum(axis=1)
    return np.full(m, 1.0 / m) if C.sum() == 0 else C / C.sum()


# ── Phase 2: adaptive clustering ─────────────────────────────────────
def _cluster_once(ordered: List[NodeAttributes], coeff: float) -> List[List[NodeAttributes]]:
    if len(ordered) < 2:
        return [list(ordered)]
    gaps = [ordered[k + 1].F_score - ordered[k].F_score for k in range(len(ordered) - 1)]
    T = float(np.mean(gaps) + coeff * np.std(gaps))
    out, cur = [], [ordered[0]]
    for k, g in enumerate(gaps):
        if g <= T:
            cur.append(ordered[k + 1])
        else:
            out.append(cur)
            cur = [ordered[k + 1]]
    out.append(cur)
    return out


def _adaptive_cluster(nodes: List[NodeAttributes]) -> List[List[NodeAttributes]]:
    ordered = sorted(nodes, key=lambda n: n.F_score)
    clusters = _cluster_once(ordered, GAP_COEFF)
    for coeff in (GAP_COEFF, 0.25, 0.0, -0.25, -0.5):
        clusters = _cluster_once(ordered, coeff)
        if len(clusters) >= MIN_CLUSTERS:
            break
    if len(clusters) < MIN_CLUSTERS and len(ordered) >= MIN_CLUSTERS:
        k = min(MIN_CLUSTERS, len(ordered))
        clusters = [list(c) for c in np.array_split(np.array(ordered, dtype=object), k)]
    # merge undersized clusters: a singleton has no backup leader
    while len(clusters) > MIN_CLUSTERS:
        sizes = [len(c) for c in clusters]
        if min(sizes) >= MIN_CLUSTER_SIZE:
            break
        i = sizes.index(min(sizes))
        j = i + 1 if i == 0 else i - 1
        merged = sorted(clusters[i] + clusters[j], key=lambda n: n.F_score)
        clusters = [c for x, c in enumerate(clusters) if x not in (i, j)]
        clusters.insert(min(i, j), merged)

    # If merging cannot fix an undersized cluster without breaking the count
    # floor, fall back to equal rank groups. A cluster of one has no backup
    # leader and cannot supply a meaningful intra-cluster quorum.
    if len(ordered) >= MIN_CLUSTERS * MIN_CLUSTER_SIZE and \
       any(len(c) < MIN_CLUSTER_SIZE for c in clusters):
        clusters = [list(c) for c in
                    np.array_split(np.array(ordered, dtype=object), MIN_CLUSTERS)]
    return clusters


def run_l1_to_l5(
    nodes: List[NodeAttributes]
) -> Tuple[Dict[str, List[str]], Dict[str, float]]:
    """CRITIC scoring + adaptive clustering. Returns (pools, final_scores)."""
    active = [n for n in nodes if n.status != "blocked"]
    if not active:
        return {}, {}

    X = np.array([n.criteria() for n in active], dtype=float)
    w = critic_weights(X)
    Xn = _normalize(X)
    for i, n in enumerate(active):
        n.F_score = round(float(Xn[i] @ w), 4)

    clusters = _adaptive_cluster(active)
    clusters.sort(key=lambda c: -np.mean([n.F_score for n in c]))   # best first

    pools: Dict[str, List[str]] = {}
    for idx, cl in enumerate(clusters):
        label = f"{CLUSTER_PREFIX}{idx + 1}"
        for n in cl:
            n.pool = label
            # Recovery Room is a status, not a cluster
            n.status = "probation" if n.reputation < TRUST_DEMOTE else "active"
        pools[label] = [n.id for n in cl]

    return pools, {n.id: n.F_score for n in active}


# ── Phase 3-4: leader election and voting ────────────────────────────
def _seed(epoch: int, tx_hash: str, ids: List[str]) -> int:
    payload = f"{epoch}:{tx_hash}:{'|'.join(sorted(ids))}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def elect_leader(candidates: List[NodeAttributes], epoch: int,
                 tx_hash: str) -> Optional[NodeAttributes]:
    """
    Top-30% pool (min 3), shuffled deterministically. Every node derives the
    same order from public inputs, so the choice is verifiable -- unlike the
    old VRF, which mixed in time.time() and could not be reproduced.
    """
    if not candidates:
        return None
    ranked = sorted(candidates, key=lambda n: n.F_score, reverse=True)
    k = min(len(ranked), max(MIN_POOL, math.ceil(POOL_FRACTION * len(ranked))))
    pool = ranked[:k]
    rng = random.Random(_seed(epoch, tx_hash, [n.id for n in pool]))
    rng.shuffle(pool)
    for n in candidates:
        n.is_leader = False
    pool[0].is_leader = True
    return pool[0]


def bft_vote(voters: List[NodeAttributes], tx_hash: str) -> Tuple[bool, Dict[str, bool]]:
    """2f+1 of n, f = (n-1)//3. Dissent is genuinely reachable here."""
    votes: Dict[str, bool] = {}
    for n in voters:
        # a node rejects if it is untrusted or offline -- no score floor blocks this
        votes[n.id] = (n.status == "active") and (n.reputation >= TRUST_DEMOTE)
    approvals = sum(1 for v in votes.values() if v)
    need = (2 * len(voters)) // 3 + 1 if voters else 1
    return approvals >= need, votes


def run_l6_to_l8(
    pools: Dict[str, List[NodeAttributes]],
    all_nodes: List[NodeAttributes],
    tx_hash: str,
    epoch: int = 1
) -> Tuple[bool, Optional[NodeAttributes], Dict[str, bool], str]:
    """Leader election -> intra-cluster vote -> inter-cluster confirmation."""
    def _rank(name: str) -> int:
        try:
            return int(name.split("-")[-1])
        except ValueError:
            return 999
    ordered = sorted((k for k, v in pools.items() if v), key=_rank)
    if not ordered:
        return False, None, {}, "No eligible clusters"

    # The proposing cluster ROTATES. Always proposing from Cluster-1 confines
    # leadership to that cluster's top-30% pool -- 3 nodes out of 30 -- and
    # reduces the other clusters to passive voters, which defeats the point of
    # cluster representation.
    home = pools[ordered[epoch % len(ordered)]]
    leader = elect_leader(home, epoch, tx_hash)
    if leader is None:
        return False, None, {}, "No leader elected - no eligible nodes"

    quorum, votes = bft_vote(home, tx_hash)
    if not quorum:
        return False, leader, votes, "Intra-cluster quorum failed"

    # inter-cluster: 2/3 of cluster leaders must confirm
    confirms = 0
    leaders = 0
    for name in ordered:
        members = pools.get(name, [])
        if not members:
            continue
        leaders += 1
        ok, _ = bft_vote(members, tx_hash)
        confirms += int(ok)
    need = (2 * leaders) // 3 + 1
    if confirms < need:
        return False, leader, votes, \
            f"Inter-cluster confirmation failed ({confirms}/{need})"

    LAST_ROUND.update({
        "protocol": PROTOCOL,
        "messages": (len(all_nodes) - leaders) + (leaders - 1) + 2 * leaders * (leaders - 1),
        "rounds": 4,
        "voters": leaders,
        "quorum": need,
        "f_byzantine": (leaders - 1) // 3,
    })
    return True, leader, votes, "Confirmed"


# ── Phase 5: reputation update + JSD ─────────────────────────────────
def _jsd(p: List[float], q: List[float]) -> float:
    """Jensen-Shannon divergence between two score distributions."""
    if not p or not q:
        return 0.0
    # a first run has no baseline yet (all scores zero) -- no drift to report
    if max(q) == 0 and min(q) == 0:
        return 0.0
    bins = np.linspace(0, 1, 11)
    hp, _ = np.histogram(np.clip(p, 0, 1), bins=bins)
    hq, _ = np.histogram(np.clip(q, 0, 1), bins=bins)
    hp = hp / hp.sum() if hp.sum() else hp + 1e-12
    hq = hq / hq.sum() if hq.sum() else hq + 1e-12
    hp, hq = hp + 1e-12, hq + 1e-12
    m = 0.5 * (hp + hq)
    kl = lambda a, b: float(np.sum(a * np.log2(a / b)))
    return round(math.sqrt(max(0.0, 0.5 * kl(hp, m) + 0.5 * kl(hq, m))), 4)


def run_l9(
    nodes: List[NodeAttributes],
    participants: List[str],
    confirmed: bool,
    baseline_scores: List[float]
) -> Tuple[Dict[str, float], float, bool]:
    """
    EWMA reputation update, then JSD drift check.

    EWMA rather than addition: additive trust saturates at 1.0 for every honest
    node, variance goes to zero, and CRITIC then gives reputation ~0 weight --
    the reputation system silently stops mattering.
    """
    took_part = set(participants)
    updated: Dict[str, float] = {}
    for n in nodes:
        if n.id in took_part:
            target = 1.0 if confirmed else 0.0
            lam = LAMBDA_REWARD if confirmed else LAMBDA_PUNISH
            n.reputation = round(lam * n.reputation + (1 - lam) * target, 4)
        else:
            # inactivity drifts toward neutral: nobody parks a high score
            n.reputation = round(
                n.reputation + (TRUST_NEUTRAL - n.reputation) * (1 - LAMBDA_REWARD), 4)

        n.status = "probation" if n.reputation < TRUST_DEMOTE else "active"
        n.history = (n.history or [])[-9:] + [n.reputation]
        updated[n.id] = n.reputation

    jsd = _jsd([n.F_score for n in nodes], baseline_scores)
    return updated, jsd, jsd > JSD_THRESHOLD