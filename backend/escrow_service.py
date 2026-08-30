"""
smart_contract.py — Simulated Hyperledger Fabric Chaincode

This module replicates chaincode behavior in Python.
In a production Hyperledger Fabric network this would be
deployed as Go or Node.js chaincode on each peer node.

Responsibilities (matching sequence diagram):
  - Lock Funds (Escrow)       → holds donation until consensus confirms
  - Store Block Hash          → writes confirmed block to ledger
  - Store Block → CID         → links IPFS CID to block
  - Release Funds (Milestones)→ releases funds in stages to needy
  - Notify Tx + Proof         → returns proof of execution
"""

import hashlib
import json
import hmac
import os
from datetime import datetime, timezone
from typing import Optional
from enum import Enum


# ── Contract Configuration ─────────────────────────────────────
CONTRACT_SECRET = os.getenv("JWT_SECRET", "charitychain_contract_secret").encode()

# Milestone release percentages
# Funds are released in 3 stages as case progresses
MILESTONES = {
    1: 0.30,   # 30% released when case first confirmed
    2: 0.40,   # 40% released at midpoint verification
    3: 0.30,   # 30% released at final completion
}


class EscrowStatus(str, Enum):
    LOCKED    = "locked"
    PARTIAL   = "partial_released"
    RELEASED  = "fully_released"
    REFUNDED  = "refunded"
    REJECTED  = "rejected"


# ── Escrow State ───────────────────────────────────────────────
# In real Hyperledger Fabric this would be stored in the
# world state (CouchDB/LevelDB). We store it in memory
# per request and persist via PostgreSQL.

class EscrowRecord:
    def __init__(
        self,
        donation_id: str,
        donor_id:    str,
        case_id:     str,
        amount:      float,
    ):
        self.donation_id     = donation_id
        self.donor_id        = donor_id
        self.case_id         = case_id
        self.amount          = amount
        self.locked_amount   = amount
        self.released_amount = 0.0
        self.status          = EscrowStatus.LOCKED
        self.milestone       = 0
        self.created_at      = datetime.now(timezone.utc).isoformat()
        self.updated_at      = self.created_at
        self.proof_hash      = self._generate_proof()

    def _generate_proof(self) -> str:
        """
        Generate a cryptographic proof of the escrow lock.
        This is what gets stored on the ledger as evidence.
        """
        payload = json.dumps({
            "donation_id": self.donation_id,
            "donor_id":    self.donor_id,
            "case_id":     self.case_id,
            "amount":      self.amount,
            "created_at":  self.created_at,
        }, sort_keys=True).encode()

        return hmac.new(CONTRACT_SECRET, payload, hashlib.sha256).hexdigest()

    def to_dict(self) -> dict:
        return {
            "donation_id":     self.donation_id,
            "donor_id":        self.donor_id,
            "case_id":         self.case_id,
            "amount":          self.amount,
            "locked_amount":   self.locked_amount,
            "released_amount": self.released_amount,
            "status":          self.status,
            "milestone":       self.milestone,
            "proof_hash":      self.proof_hash,
            "created_at":      self.created_at,
            "updated_at":      self.updated_at,
        }


# ── Smart Contract Class ───────────────────────────────────────
class CharitySmartContract:
    """
    Simulates Hyperledger Fabric chaincode.

    In a real Fabric network:
      - This class would be the chaincode
      - Each method would be a transaction function
      - State would be stored in the peer's world state DB
      - Every call would be endorsed by multiple peers

    In our simulation:
      - Methods are called directly from routes/donations.py
      - State is passed back and stored in PostgreSQL
      - Proof hashes are stored on the Block record
    """

    # ── Chaincode Function 1: Lock Funds ──────────────────────
    def lock_funds(
        self,
        donation_id: str,
        donor_id:    str,
        case_id:     str,
        amount:      float,
    ) -> EscrowRecord:
        """
        Called BEFORE ABPC consensus runs.
        Locks the donation amount in escrow.
        No funds move until consensus confirms.

        Sequence diagram: Lock Funds (Escrow) step.
        """
        if amount <= 0:
            raise ValueError("Cannot lock zero or negative amount")

        escrow = EscrowRecord(
            donation_id = donation_id,
            donor_id    = donor_id,
            case_id     = case_id,
            amount      = amount,
        )

        return escrow

    # ── Chaincode Function 2: Store Block Hash ────────────────
    def store_block_hash(
        self,
        block_index: int,
        block_hash:  str,
        tx_data:     dict,
        prev_hash:   str,
        leader_node: str,
        timestamp:   str,
    ) -> dict:
        """
        Called AFTER ABPC consensus confirms.
        Records the block hash on the ledger.
        This is the immutability guarantee.

        Sequence diagram: Store Block Hash → Ledger step.
        """
        # Generate ledger entry — this is what gets written
        ledger_entry = {
            "block_index": block_index,
            "block_hash":  block_hash,
            "prev_hash":   prev_hash,
            "leader_node": leader_node,
            "tx_data":     tx_data,
            "timestamp":   timestamp,
            "ledger_id":   self._ledger_id(block_hash),
        }

        # Generate a contract execution proof
        proof = self._generate_execution_proof(ledger_entry)
        ledger_entry["contract_proof"] = proof

        return ledger_entry

    # ── Chaincode Function 3: Store Block → CID ───────────────
    def store_block_cid(
        self,
        block_hash: str,
        ipfs_cid:   str,
    ) -> dict:
        """
        Links the IPFS CID to the confirmed block.
        Ensures document is retrievable from the hash.

        Sequence diagram: Store Block → CID step.
        """
        return {
            "block_hash": block_hash,
            "ipfs_cid":   ipfs_cid,
            "linked_at":  datetime.now(timezone.utc).isoformat(),
            "ipfs_url":   f"https://ipfs.io/ipfs/{ipfs_cid}",
        }

    # ── Chaincode Function 4: Release Funds (Milestones) ──────
    def release_milestone(
        self,
        escrow:      EscrowRecord,
        milestone:   int,          # 1, 2, or 3
        verifier_id: str,          # trustee or admin who verified
    ) -> dict:
        """
        Releases a percentage of locked funds based on milestone.
        Called by trustee after verifying case progress.

        Milestone 1 → 30% released (initial confirmation)
        Milestone 2 → 40% released (midpoint verification)
        Milestone 3 → 30% released (completion)

        Sequence diagram: Release Funds (Milestones) step.
        """
        if milestone not in MILESTONES:
            raise ValueError(f"Invalid milestone: {milestone}. Must be 1, 2, or 3")

        if escrow.milestone >= milestone:
            raise ValueError(f"Milestone {milestone} already released")

        if escrow.status == EscrowStatus.RELEASED:
            raise ValueError("Funds already fully released")

        if escrow.status == EscrowStatus.REJECTED:
            raise ValueError("Cannot release funds from rejected escrow")

        # Calculate release amount
        release_pct    = MILESTONES[milestone]
        release_amount = round(escrow.amount * release_pct, 2)

        # Update escrow state
        escrow.released_amount += release_amount
        escrow.locked_amount   -= release_amount
        escrow.milestone        = milestone
        escrow.updated_at       = datetime.now(timezone.utc).isoformat()

        # Update status
        if escrow.released_amount >= escrow.amount:
            escrow.status = EscrowStatus.RELEASED
        else:
            escrow.status = EscrowStatus.PARTIAL

        # Generate release proof
        release_proof = self._generate_release_proof(
            escrow, milestone, release_amount, verifier_id
        )

        return {
            "donation_id":     escrow.donation_id,
            "case_id":         escrow.case_id,
            "milestone":       milestone,
            "release_pct":     release_pct * 100,
            "release_amount":  release_amount,
            "released_total":  escrow.released_amount,
            "locked_remaining": escrow.locked_amount,
            "escrow_status":   escrow.status,
            "verifier_id":     verifier_id,
            "release_proof":   release_proof,
            "released_at":     escrow.updated_at,
        }

    # ── Chaincode Function 5: Notify Tx + Proof ───────────────
    def generate_tx_proof(
        self,
        donation_id:    str,
        block_hash:     str,
        escrow:         EscrowRecord,
        ledger_entry:   dict,
        ipfs_link:      dict,
    ) -> dict:
        """
        Generates the final transaction proof sent to donor and needy.
        This is the "receipt" of the entire operation.

        Sequence diagram: Notify Tx + Proof step.
        """
        proof_payload = {
            "donation_id":    donation_id,
            "block_hash":     block_hash,
            "escrow_proof":   escrow.proof_hash,
            "contract_proof": ledger_entry.get("contract_proof"),
            "ipfs_cid":       ipfs_link.get("ipfs_cid"),
            "ipfs_url":       ipfs_link.get("ipfs_url"),
            "amount":         escrow.amount,
            "status":         escrow.status,
            "milestone":      escrow.milestone,
            "timestamp":      datetime.now(timezone.utc).isoformat(),
        }

        # Final proof hash — combines all proofs into one
        final_hash = hashlib.sha256(
            json.dumps(proof_payload, sort_keys=True).encode()
        ).hexdigest()

        return {
            **proof_payload,
            "tx_proof": final_hash,
            "verified": True,
        }

    # ── Chaincode Function 6: Refund ──────────────────────────
    def refund_escrow(
        self,
        escrow:    EscrowRecord,
        reason:    str,
    ) -> dict:
        """
        Called when ABPC consensus fails.
        Refunds the locked amount back to donor.

        Sequence diagram: implied when consensus fails.
        """
        escrow.status     = EscrowStatus.REFUNDED
        escrow.updated_at = datetime.now(timezone.utc).isoformat()

        return {
            "donation_id":    escrow.donation_id,
            "refund_amount":  escrow.amount,
            "reason":         reason,
            "refunded_at":    escrow.updated_at,
            "refund_proof":   self._generate_execution_proof({
                "action":    "refund",
                "donation":  escrow.donation_id,
                "amount":    escrow.amount,
                "reason":    reason,
            }),
        }

    # ── Internal Helpers ──────────────────────────────────────
    def _ledger_id(self, block_hash: str) -> str:
        """Generate a short ledger entry ID from block hash."""
        return "LDG_" + block_hash[:12].upper()

    def _generate_execution_proof(self, data: dict) -> str:
        payload = json.dumps(data, sort_keys=True).encode()
        return hmac.new(CONTRACT_SECRET, payload, hashlib.sha256).hexdigest()

    def _generate_release_proof(
        self,
        escrow:        EscrowRecord,
        milestone:     int,
        release_amount: float,
        verifier_id:   str,
    ) -> str:
        payload = json.dumps({
            "donation_id":    escrow.donation_id,
            "milestone":      milestone,
            "release_amount": release_amount,
            "verifier_id":    verifier_id,
            "timestamp":      escrow.updated_at,
        }, sort_keys=True).encode()
        return hmac.new(CONTRACT_SECRET, payload, hashlib.sha256).hexdigest()


# ── Singleton instance — import this everywhere ────────────────
contract = CharitySmartContract()