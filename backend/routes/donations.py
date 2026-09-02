from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime, timezone
import hashlib
import json
import time

from database import get_db
from models import Donation, Case, Block, AuditLog, User
from security import get_current_user, require_role
from ipfs_client import pin_to_ipfs
from escrow_service import contract
from blockchain_client import blockchain

router = APIRouter(prefix="/api/donations", tags=["donations"])

# Consensus no longer runs in this process. CB-BFT is compiled into the Besu
# nodes (consensus/cbbft), so the proposer for the block carrying this
# transaction is chosen on-chain, by every validator independently.
CONSENSUS_NAME = "cbbft-besu"


def donation_response(d: Donation) -> dict:
    return {
        "id":             d.id,
        "donor_id":       d.donor_id,
        "case_id":        d.case_id,
        "amount":         d.amount,
        "status":         d.status,
        "tx_hash":        d.tx_hash,
        "block_id":       d.block_id,
        "leader_node":    d.leader_node,
        "validated_at":   d.validated_at.isoformat()  if d.validated_at  else None,
        "confirmed_at":   d.confirmed_at.isoformat()  if d.confirmed_at  else None,
        "released_at":    d.released_at.isoformat()   if d.released_at   else None,
        "funds_released": d.funds_released,
        "created_at":     d.created_at.isoformat()    if d.created_at    else None,
    }


class DonateRequest(BaseModel):
    case_id: str
    amount:  float


@router.post("/donate")
async def donate(
    req:          DonateRequest,
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_role("donor"))
):
    # ── Validate case ────────────────────────────────────────────────
    result = await db.execute(select(Case).where(Case.id == req.case_id))
    case   = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.status != "approved":
        raise HTTPException(status_code=400, detail="Case is not approved for donations")
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    # ── Cap at the remaining need ────────────────────────────────────
    # A case cannot receive more than its goal. Once fully funded it is
    # closed and no further donations are accepted.
    remaining = (case.amount_needed or 0) - (case.amount_funded or 0)
    if remaining <= 0:
        raise HTTPException(
            status_code=400,
            detail="This case is fully funded and no longer accepting donations")
    if req.amount > remaining:
        raise HTTPException(
            status_code=400,
            detail=f"Only ${remaining:,.2f} is still needed for this case")

    t_start = time.perf_counter()

    # ── Lock the donor row ───────────────────────────────────────────
    # The balance is read here but not deducted until the commit at the end.
    # Without SELECT ... FOR UPDATE two concurrent donations would both pass
    # this check before either wrote, and the donor could overdraw.
    locked = await db.execute(
        select(User).where(User.id == current_user.id).with_for_update()
    )
    donor = locked.scalar_one()

    if donor.wallet_balance < req.amount:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient balance. Your balance is BDT {donor.wallet_balance:.2f}"
        )

    # ── Provisional donation record ──────────────────────────────────
    donation = Donation(
        donor_id = current_user.id,
        case_id  = req.case_id,
        amount   = req.amount,
        status   = "pending",
    )
    db.add(donation)
    await db.flush()

    # ── Escrow: application-layer hold ───────────────────────────────
    escrow = contract.lock_funds(
        donation_id = donation.id,
        donor_id    = current_user.id,
        case_id     = req.case_id,
        amount      = req.amount,
    )

    # ── Escrow: on-chain record ──────────────────────────────────────
    # This transaction enters the Besu transaction pool. CB-BFT selects the
    # proposer; the block is sealed once two thirds of validators commit.
    _t = time.perf_counter()
    chain_lock = blockchain.lock_funds(
        donation_id = donation.id,
        donor_id    = current_user.id,
        case_id     = req.case_id,
    )
    onchain_ms = (time.perf_counter() - _t) * 1000

    # ── Transaction data and hash ────────────────────────────────────
    tx_data = {
        "donation_id":  donation.id,
        "donor_id":     current_user.id,
        "donor_name":   current_user.full_name,
        "case_id":      req.case_id,
        "amount":       req.amount,
        "escrow_proof": escrow.proof_hash,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
    }
    tx_hash = hashlib.sha256(
        json.dumps(tx_data, sort_keys=True).encode()
    ).hexdigest()

    now = datetime.now(timezone.utc)

    # ── Previous block, for the hash link ────────────────────────────
    prev_result = await db.execute(
        select(Block).order_by(Block.index.desc())
    )
    prev_block  = prev_result.scalars().first()
    prev_hash   = prev_block.block_hash if prev_block else "0" * 64
    next_index  = (prev_block.index + 1) if prev_block else 1

    block_content = json.dumps({
        "index":     next_index,
        "tx_data":   tx_data,
        "prev_hash": prev_hash,
        "timestamp": now.isoformat(),
    }, sort_keys=True)
    block_hash = hashlib.sha256(block_content.encode()).hexdigest()

    ipfs_cid = await pin_to_ipfs(block_content, f"block_{next_index}")

    # ── Anchor the hash on chain ─────────────────────────────────────
    ledger_entry = contract.store_block_hash(
        block_index = next_index,
        block_hash  = block_hash,
        tx_data     = tx_data,
        prev_hash   = prev_hash,
        leader_node = CONSENSUS_NAME,
        timestamp   = now.isoformat(),
    )

    _t = time.perf_counter()
    chain_block = blockchain.store_block_hash(
        block_index = next_index,
        block_hash  = block_hash,
        prev_hash   = prev_hash,
        leader_node = CONSENSUS_NAME,
        donation_id = donation.id,
    )
    onchain_ms += (time.perf_counter() - _t) * 1000

    # The validator that proposed the Besu block carrying this transaction was
    # chosen by CB-BFT inside the node. Record it when the client exposes it.
    chain_proposer = chain_block.get("proposer") or chain_block.get("miner")
    chain_number   = chain_block.get("block_number")

    ipfs_link = contract.store_block_cid(block_hash, ipfs_cid)

    # ── Release milestone 1 (30%) ────────────────────────────────────
    milestone_result = contract.release_milestone(
        escrow      = escrow,
        milestone   = 1,
        verifier_id = "system",
    )

    _t = time.perf_counter()
    chain_milestone = blockchain.release_milestone(
        donation_id = donation.id,
        milestone   = 1,
    )
    onchain_ms += (time.perf_counter() - _t) * 1000

    tx_proof = contract.generate_tx_proof(
        donation_id  = donation.id,
        block_hash   = block_hash,
        escrow       = escrow,
        ledger_entry = ledger_entry,
        ipfs_link    = ipfs_link,
    )

    # ── Application block record ─────────────────────────────────────
    # A tamper-evident audit chain over donations, anchored on Besu. The
    # authoritative ordering is the chain's own, produced by CB-BFT.
    block = Block(
        index        = next_index,
        tx_data      = tx_data,
        leader_node  = chain_proposer,
        quorum       = bool(chain_block.get("on_chain", False)),
        block_hash   = block_hash,
        prev_hash    = prev_hash,
        ipfs_cid     = ipfs_cid,
        timestamp    = now,
        consensus    = CONSENSUS_NAME,
        onchain_ms   = round(onchain_ms, 4),
        total_ms     = round((time.perf_counter() - t_start) * 1000, 4),
    )
    db.add(block)
    await db.flush()

    # ── Confirm the donation ─────────────────────────────────────────
    donation.status         = "confirmed"
    donation.tx_hash        = tx_hash
    donation.block_id       = block.id
    donation.leader_node    = chain_proposer
    donation.validated_at   = now
    donation.confirmed_at   = now
    donation.released_at    = now
    donation.funds_released = True

    # Deduct from the locked row, not from current_user.
    donor.wallet_balance -= req.amount
    case.amount_funded    = (case.amount_funded or 0) + req.amount
    if case.amount_funded >= (case.amount_needed or 0):
        case.status = "completed"

    db.add(AuditLog(
        event_type  = "donation_confirmed",
        description = (
            f"BDT {req.amount} donated to case {req.case_id} "
            f"— block #{next_index} — sealed by {CONSENSUS_NAME}"
        ),
        tx_hash  = block_hash,
        actor_id = current_user.id,
        meta     = {
            "block_id":           block.id,
            "consensus":          CONSENSUS_NAME,
            "amount":             req.amount,
            "onchain_ms":         round(onchain_ms, 4),
            "escrow_proof":       escrow.proof_hash,
            "contract_proof":     ledger_entry.get("contract_proof"),
            "tx_proof":           tx_proof.get("tx_proof"),
            "milestone":          milestone_result.get("milestone"),
            "released_amount":    milestone_result.get("release_amount"),
            "chain_lock_tx":      chain_lock.get("tx_hash"),
            "chain_block_tx":     chain_block.get("tx_hash"),
            "chain_milestone_tx": chain_milestone.get("tx_hash"),
            "chain_block_number": chain_number,
            "chain_proposer":     chain_proposer,
            "on_chain":           chain_block.get("on_chain", False),
        },
    ))

    # ── Single atomic commit ─────────────────────────────────────────
    await db.commit()

    return {
        "donation_id":     donation.id,
        "consensus":       CONSENSUS_NAME,
        "tx_hash":         tx_hash,
        "block_hash":      block_hash,
        "block_index":     next_index,
        "confirmed":       True,
        "wallet_balance":  donor.wallet_balance,
        "escrow_proof":    escrow.proof_hash,
        "ledger_id":       ledger_entry.get("ledger_id"),
        "contract_proof":  ledger_entry.get("contract_proof"),
        "tx_proof":        tx_proof.get("tx_proof"),
        "milestone":       milestone_result.get("milestone"),
        "released_amount": milestone_result.get("release_amount"),
        "escrow_status":   escrow.status,
        "ipfs_cid":        ipfs_cid,
        "ipfs_url":        ipfs_link.get("ipfs_url"),
        "onchain_ms":      round(onchain_ms, 4),
        "chain_lock_tx":      chain_lock.get("tx_hash"),
        "chain_block_tx":     chain_block.get("tx_hash"),
        "chain_milestone_tx": chain_milestone.get("tx_hash"),
        "chain_block_number": chain_number,
        "chain_proposer":     chain_proposer,
        "on_chain":           chain_block.get("on_chain", False),
    }


@router.get("/my")
async def my_donations(
    db:           AsyncSession = Depends(get_db),
    current_user: User         = Depends(require_role("donor"))
):
    result = await db.execute(
        select(Donation).where(Donation.donor_id == current_user.id)
    )
    return [donation_response(d) for d in result.scalars().all()]


@router.get("/track/{donation_id}")
async def track_donation(
    donation_id: str,
    db:          AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Donation, User, Case)
        .join(User, Donation.donor_id == User.id)
        .join(Case, Donation.case_id  == Case.id)
        .where(Donation.id == donation_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Donation not found")

    d, u, c = row

    block_hash = None
    if d.block_id:
        br  = await db.execute(select(Block).where(Block.id == d.block_id))
        blk = br.scalar_one_or_none()
        block_hash = blk.block_hash if blk else None

    return {
        **donation_response(d),
        "donor_name":     u.full_name,
        "case_title":     c.title,
        "block_hash":     block_hash,
        "wallet_balance": u.wallet_balance,
    }