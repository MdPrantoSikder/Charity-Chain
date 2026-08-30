from sqlalchemy import Column, String, Float, Boolean, Integer, DateTime, Text, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from database import Base


def now_utc():
    return datetime.now(timezone.utc)


def new_id():
    return str(uuid.uuid4())[:8].upper()


class User(Base):
    __tablename__ = "users"

    id             = Column(String, primary_key=True, default=new_id)
    full_name      = Column(String, nullable=False)
    email          = Column(String, unique=True, nullable=False, index=True)
    hashed_pw      = Column(String, nullable=False)
    role           = Column(Enum("donor","needy","trustee","admin","validator", name="user_role"), nullable=False)
    kyc_status     = Column(String, default="pending")
    wallet         = Column(String, nullable=True)
    wallet_balance = Column(Float,  default=10000.0)
    created_at     = Column(DateTime(timezone=True), default=now_utc)

    cases     = relationship("Case",     back_populates="needy",  foreign_keys="Case.needy_id")
    donations = relationship("Donation", back_populates="donor",  foreign_keys="Donation.donor_id")


class Case(Base):
    __tablename__ = "cases"

    id             = Column(String, primary_key=True, default=new_id)
    needy_id       = Column(String, ForeignKey("users.id"), nullable=False)
    title          = Column(String, nullable=False)
    category       = Column(String, nullable=False)
    description    = Column(Text,   nullable=True)
    location       = Column(String, nullable=True)
    amount_needed  = Column(Float,  nullable=False)
    amount_funded  = Column(Float,  default=0.0)
    status         = Column(String, default="pending")
    ipfs_cid       = Column(String, nullable=True)
    trustee_notes  = Column(Text,   nullable=True)
    approved_at    = Column(DateTime(timezone=True), nullable=True)
    created_at     = Column(DateTime(timezone=True), default=now_utc)

    needy     = relationship("User",     back_populates="cases",     foreign_keys=[needy_id])
    donations = relationship("Donation", back_populates="case",      foreign_keys="Donation.case_id")


class Donation(Base):
    __tablename__ = "donations"

    id             = Column(String, primary_key=True, default=new_id)
    donor_id       = Column(String, ForeignKey("users.id"), nullable=False)
    case_id        = Column(String, ForeignKey("cases.id"), nullable=False)
    amount         = Column(Float,  nullable=False)
    status         = Column(String, default="pending")
    tx_hash        = Column(String, nullable=True)
    block_id       = Column(String, ForeignKey("blocks.id"), nullable=True)

    # The Besu validator that proposed the block carrying this donation.
    # CB-BFT selects it inside the node; nothing here decides it.
    leader_node    = Column(String, nullable=True)

    validated_at   = Column(DateTime(timezone=True), nullable=True)
    confirmed_at   = Column(DateTime(timezone=True), nullable=True)
    released_at    = Column(DateTime(timezone=True), nullable=True)
    funds_released = Column(Boolean, default=False)
    created_at     = Column(DateTime(timezone=True), default=now_utc)

    donor = relationship("User", back_populates="donations", foreign_keys=[donor_id])
    case  = relationship("Case", back_populates="donations", foreign_keys=[case_id])
    block = relationship("Block", back_populates="donations", foreign_keys=[block_id])


class Block(Base):
    """
    Application-layer audit record for a donation, hash-linked to its
    predecessor and anchored on the chain.

    This is not the blockchain's own block. Ordering and authorship are decided
    by CB-BFT inside the Besu nodes; this row records the donation, links it to
    the previous record, and stores the transaction hashes that anchor it.
    """
    __tablename__ = "blocks"

    id           = Column(String,  primary_key=True, default=new_id)
    index        = Column(Integer, nullable=False)
    tx_data      = Column(JSONB,   nullable=True)
    leader_node  = Column(String,  nullable=True)
    quorum       = Column(Boolean, default=False)
    block_hash   = Column(String,  nullable=False)
    prev_hash    = Column(String,  nullable=True)
    ipfs_cid     = Column(String,  nullable=True)
    timestamp    = Column(DateTime(timezone=True), default=now_utc)

    # ── Provenance and measured timings ──────────────────────────────────
    # Consensus runs inside the Besu nodes, so there is nothing left for this
    # process to time. What remains is the chain round-trip and the total
    # pipeline, both wall-clock and recorded live as the donation is handled.
    consensus    = Column(String, default="cbbft-besu", index=True)
    onchain_ms   = Column(Float,  default=0.0)   # Besu transaction round-trip
    total_ms     = Column(Float,  default=0.0)   # whole donation pipeline

    donations = relationship("Donation", back_populates="block", foreign_keys="Donation.block_id")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id          = Column(String, primary_key=True, default=new_id)
    event_type  = Column(String, nullable=False)
    description = Column(Text,   nullable=True)
    tx_hash     = Column(String, nullable=True)
    actor_id    = Column(String, nullable=True)
    meta        = Column(JSONB,  nullable=True)
    timestamp   = Column(DateTime(timezone=True), default=now_utc)


class CaseDocument(Base):
    __tablename__ = "case_documents"

    id           = Column(String,  primary_key=True, default=new_id)
    case_id      = Column(String,  ForeignKey("cases.id"), nullable=False)
    filename     = Column(String,  nullable=False)
    content_type = Column(String,  nullable=True)
    file_data    = Column(Text,    nullable=True)  # base64 encoded
    ipfs_cid     = Column(String,  nullable=True)
    uploaded_at  = Column(DateTime(timezone=True), default=now_utc)