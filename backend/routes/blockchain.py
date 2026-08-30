"""
routes/blockchain.py — the application's hash-linked donation records.

These are not the chain's own blocks. Ordering and authorship are decided by
CB-BFT inside the Besu nodes; each row here records one donation, links it to
the previous record, and carries the transaction hashes that anchor it on the
chain.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_db
from models import Block, AuditLog

router = APIRouter(tags=["blockchain"])


def block_response(b: Block) -> dict:
    return {
        "id":          b.id,
        "index":       b.index,
        "tx_data":     b.tx_data,
        # the Besu validator that proposed the block carrying this donation,
        # selected by CB-BFT inside the node
        "leader_node": b.leader_node,
        "quorum":      b.quorum,
        "block_hash":  b.block_hash,
        "prev_hash":   b.prev_hash,
        "ipfs_cid":    b.ipfs_cid,
        "consensus":   b.consensus,
        "onchain_ms":  b.onchain_ms,
        "total_ms":    b.total_ms,
        "timestamp":   b.timestamp.isoformat() if b.timestamp else None,
    }


@router.get("/api/chain")
async def get_chain(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Block).order_by(Block.index))
    return [block_response(b) for b in result.scalars().all()]


@router.get("/api/chain/{block_id}")
async def get_block(block_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Block).where(Block.id == block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    return block_response(block)


@router.get("/api/transparency/audit")
async def get_audit_log(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.timestamp.desc())
    )
    return [
        {
            "id":          l.id,
            "event_type":  l.event_type,
            "description": l.description,
            "tx_hash":     l.tx_hash,
            "actor_id":    l.actor_id,
            "meta":        l.meta,
            "timestamp":   l.timestamp.isoformat() if l.timestamp else None,
        }
        for l in result.scalars().all()
    ]


@router.get("/api/transparency/consensus-logs")
async def get_consensus_logs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.event_type == "donation_confirmed")
        .order_by(AuditLog.timestamp.desc())
    )
    return [
        {
            "id":          l.id,
            "event_type":  l.event_type,
            "description": l.description,
            "tx_id":       l.tx_hash,
            "meta":        l.meta or {},
            "timestamp":   l.timestamp.isoformat() if l.timestamp else None,
        }
        for l in result.scalars().all()
    ]