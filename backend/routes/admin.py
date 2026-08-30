"""
routes/admin.py — validator monitoring from the live chain, plus user admin.

The validator endpoints used to read simulated rows from Postgres. They now
query the Besu network directly: the validator set comes from the chain, and
proposer activity is counted from recent block headers. Nothing here invents a
number — every value is something the chain already knows.
"""

from datetime import datetime, timezone
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from database import get_db
from models import User, AuditLog
from security import require_role
from blockchain_client import blockchain

router = APIRouter(prefix="/api", tags=["admin"])

CONSENSUS_NAME = "CB-BFT"
WINDOW = 30          # blocks of history, matching the selector's scoring window


def _require_chain():
    if not getattr(blockchain, "enabled", False):
        raise HTTPException(
            status_code=503,
            detail="Blockchain client is disabled — cannot read validator state"
        )


def _ensure_poa_middleware():
    """
    QBFT stores validator addresses and commit seals in extraData, so headers
    exceed the 32 bytes web3.py expects on a proof-of-work chain. The PoA
    middleware relaxes that check; without it every get_block call raises
    ExtraDataLengthError. Injected once, then cached.
    """
    w3 = blockchain.w3
    if getattr(w3, "_cbbft_poa_ready", False):
        return
    try:
        from web3.middleware import ExtraDataToPOAMiddleware      # web3 >= 7
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    except ImportError:
        from web3.middleware import geth_poa_middleware           # web3 6.x
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    w3._cbbft_poa_ready = True


def _recent_headers(limit: int = WINDOW):
    """The last `limit` block headers, newest last."""
    _ensure_poa_middleware()
    head = blockchain.w3.eth.block_number
    start = max(0, head - limit + 1)
    return [blockchain.w3.eth.get_block(n) for n in range(start, head + 1)]


def _validator_set():
    """
    Current validators, straight from the chain.

    qbft_getValidatorsByBlockNumber is the authoritative source. If the RPC
    namespace is not exposed, fall back to the proposers actually seen in the
    recent window, which is a subset but never a fabrication.
    """
    try:
        res = blockchain.w3.provider.make_request(
            "qbft_getValidatorsByBlockNumber", ["latest"]
        )
        vals = res.get("result")
        if vals:
            return [v.lower() for v in vals], "qbft_getValidatorsByBlockNumber"
    except Exception:
        pass

    seen = {(h.get("miner") or "").lower() for h in _recent_headers()}
    return sorted(v for v in seen if v), "recent block proposers"


# ══════════════════════════════════════════════════════════
#  VALIDATORS — read from the running chain
# ══════════════════════════════════════════════════════════

@router.get("/nodes")
async def get_nodes():
    """
    Every validator on the network, with the proposal activity CB-BFT scores on.

    `proposals` is how many of the last WINDOW blocks this validator proposed —
    the same signal the selector reads inside the node.
    """
    _require_chain()
    validators, source = _validator_set()
    headers = _recent_headers()

    counts = Counter((h.get("miner") or "").lower() for h in headers)
    window = len(headers)
    top = max(counts.values()) if counts else 0

    out = []
    for v in validators:
        proposals = counts.get(v, 0)
        out.append({
            "id":        v,
            "address":   v,
            "org":       "besu-validator",
            "proposals": proposals,
            "share":     round(proposals / window, 4) if window else 0.0,
            "status":    "active" if proposals > 0 else "idle",
            "is_leader": proposals > 0 and proposals == top,
        })

    out.sort(key=lambda d: (-d["proposals"], d["id"]))
    return out


@router.get("/nodes/{node_id}")
async def get_node(node_id: str):
    _require_chain()
    nodes = await get_nodes()
    for n in nodes:
        if n["id"].lower() == node_id.lower():
            return n
    raise HTTPException(status_code=404, detail="Validator not found on chain")


# ══════════════════════════════════════════════════════════
#  CONSENSUS STATE — derived from the chain
# ══════════════════════════════════════════════════════════

@router.get("/consensus/epoch")
async def get_epoch():
    """Chain progress. There is no separate epoch table any more."""
    _require_chain()
    headers = _recent_headers()
    intervals = [
        headers[i]["timestamp"] - headers[i - 1]["timestamp"]
        for i in range(1, len(headers))
    ]
    avg = round(sum(intervals) / len(intervals), 3) if intervals else None
    return {
        "chain_height":       blockchain.w3.eth.block_number,
        "window":             len(headers),
        "avg_block_interval": avg,
        "measured_at":        datetime.now(timezone.utc).isoformat(),
    }


@router.get("/consensus/info")
async def consensus_info():
    """
    Which consensus is live and how concentrated proposals currently are.

    CB-BFT selects from the top 30% of the leading cluster, so a small effective
    proposer set is the expected behaviour rather than a fault.
    """
    _require_chain()
    validators, source = _validator_set()
    headers = _recent_headers()
    counts = Counter((h.get("miner") or "").lower() for h in headers)

    n = len(validators)
    active = sum(1 for v in validators if counts.get(v, 0) > 0)

    return {
        "protocol":            CONSENSUS_NAME,
        "implementation":      "consensus/cbbft inside Hyperledger Besu",
        "validator_source":    source,
        "total_validators":    n,
        "proposing_in_window": active,
        "window":              len(headers),
        "chain_height":        blockchain.w3.eth.block_number,
        "chain_id":            blockchain.w3.eth.chain_id,
        "f_byzantine":         (n - 1) // 3 if n else 0,
        "proposal_counts":     dict(counts.most_common()),
    }


# ══════════════════════════════════════════════════════════
#  USERS
# ══════════════════════════════════════════════════════════

def _user_dict(u: User) -> dict:
    return {
        "id":             u.id,
        "full_name":      u.full_name,
        "email":          u.email,
        "role":           u.role,
        "kyc_status":     u.kyc_status,
        "wallet_balance": u.wallet_balance,
        "created_at":     u.created_at.isoformat() if u.created_at else None,
    }


@router.get("/admin/users")
async def get_users(
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_role("admin", "trustee"))
):
    result = await db.execute(select(User).order_by(User.created_at))
    return [_user_dict(u) for u in result.scalars().all()]


@router.get("/admin/trustees/pending")
async def get_pending_trustees(
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_role("admin"))
):
    result = await db.execute(
        select(User).where(User.role == "trustee", User.kyc_status == "pending")
    )
    return [_user_dict(u) for u in result.scalars().all()]


@router.post("/admin/trustees/{user_id}/approve")
async def approve_trustee(
    user_id:      str,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_role("admin"))
):
    result = await db.execute(
        select(User).where(User.id == user_id, User.role == "trustee")
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Trustee not found")

    user.kyc_status = "verified"
    db.add(AuditLog(
        event_type  = "trustee_approved",
        description = f"Trustee {user.full_name} approved by {current_user.full_name}",
        actor_id    = current_user.id,
    ))
    await db.commit()
    return {"message": f"Trustee {user.full_name} approved successfully"}


@router.post("/admin/trustees/{user_id}/reject")
async def reject_trustee(
    user_id:      str,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_role("admin"))
):
    result = await db.execute(
        select(User).where(User.id == user_id, User.role == "trustee")
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Trustee not found")

    user.kyc_status = "rejected"
    db.add(AuditLog(
        event_type  = "trustee_rejected",
        description = f"Trustee {user.full_name} rejected by {current_user.full_name}",
        actor_id    = current_user.id,
    ))
    await db.commit()
    return {"message": f"Trustee {user.full_name} rejected"}


# ══════════════════════════════════════════════════════════
#  WALLET TOP UP (admin override)
# ══════════════════════════════════════════════════════════

class AdminTopUpRequest(BaseModel):
    amount: float = Field(..., gt=0)


@router.post("/admin/topup/{user_id}")
async def admin_topup(
    user_id:      str,
    req:          AdminTopUpRequest,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_role("admin"))
):
    # lock the row: without it two concurrent top-ups can both read the old
    # balance and one write is lost
    result = await db.execute(
        select(User).where(User.id == user_id).with_for_update()
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.wallet_balance = (user.wallet_balance or 0) + req.amount
    db.add(AuditLog(
        event_type  = "admin_topup",
        description = (f"Admin {current_user.full_name} topped up "
                       f"{user.full_name} by BDT {req.amount}"),
        actor_id    = current_user.id,
        meta        = {"target_user": user.id, "amount": req.amount},
    ))
    await db.commit()
    await db.refresh(user)

    return {
        "message":        f"Topped up {user.full_name} by BDT {req.amount}",
        "user_id":        user.id,
        "wallet_balance": user.wallet_balance,
    }