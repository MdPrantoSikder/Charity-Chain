// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * CharityChain.sol
 *
 * Private permissioned charity donation contract.
 * Deployed on Hardhat local private network.
 *
 * 3 core functions:
 *   1. lockFunds()        — escrow donation before ABPC consensus
 *   2. storeBlockHash()   — record confirmed block on-chain after consensus
 *   3. releaseMilestone() — release funds in 3 stages (30% / 40% / 30%)
 *
 * Only the contract owner (your FastAPI backend wallet) can call these.
 * This matches your Python smart_contract.py simulation exactly.
 */

contract CharityChain is Ownable, ReentrancyGuard {

    // ── Enums ────────────────────────────────────────────────

    enum EscrowStatus {
        Locked,
        PartialReleased,
        FullyReleased,
        Refunded,
        Rejected
    }

    // ── Structs ──────────────────────────────────────────────

    struct Escrow {
        string  donationId;
        string  donorId;
        string  caseId;
        uint256 amount;
        uint256 releasedAmount;
        uint8   milestone;
        EscrowStatus status;
        uint256 createdAt;
    }

    struct BlockRecord {
        uint256 blockIndex;
        bytes32 blockHash;
        bytes32 prevHash;
        string  leaderNode;
        string  donationId;
        uint256 timestamp;
        bool    exists;
    }

    // ── Storage ──────────────────────────────────────────────

    mapping(string => Escrow) public escrows;
    mapping(uint256 => BlockRecord) public blockRecords;
    uint256 public totalBlocks;
    uint256[4] public milestonePercents = [0, 3000, 4000, 3000];

    // ── Events ───────────────────────────────────────────────

    event FundsLocked(
        string indexed donationId,
        string donorId,
        string caseId,
        uint256 amount,
        uint256 timestamp
    );

    event BlockStored(
        uint256 indexed blockIndex,
        bytes32 blockHash,
        string  leaderNode,
        uint256 timestamp
    );

    event MilestoneReleased(
        string indexed donationId,
        uint8   milestone,
        uint256 releaseAmount,
        uint256 timestamp
    );

    event FundsRefunded(
        string indexed donationId,
        uint256 amount,
        string  reason,
        uint256 timestamp
    );

    // ── Constructor ──────────────────────────────────────────

    constructor() Ownable(msg.sender) {}

    // ── Function 1: Lock Funds ───────────────────────────────

    function lockFunds(
        string memory donationId,
        string memory donorId,
        string memory caseId
    ) external onlyOwner nonReentrant {
        require(
            bytes(escrows[donationId].donationId).length == 0,
            "Escrow already exists for this donation"
        );

        escrows[donationId] = Escrow({
            donationId:     donationId,
            donorId:        donorId,
            caseId:         caseId,
            amount:         1,
            releasedAmount: 0,
            milestone:      0,
            status:         EscrowStatus.Locked,
            createdAt:      block.timestamp
        });

        emit FundsLocked(donationId, donorId, caseId, 1, block.timestamp);
    }

    // ── Function 2: Store Block Hash ─────────────────────────

    function storeBlockHash(
        uint256       blockIndex,
        bytes32       blockHash,
        bytes32       prevHash,
        string memory leaderNode,
        string memory donationId
    ) external onlyOwner {
        require(
            !blockRecords[blockIndex].exists,
            "Block index already recorded"
        );

        blockRecords[blockIndex] = BlockRecord({
            blockIndex: blockIndex,
            blockHash:  blockHash,
            prevHash:   prevHash,
            leaderNode: leaderNode,
            donationId: donationId,
            timestamp:  block.timestamp,
            exists:     true
        });

        totalBlocks += 1;

        emit BlockStored(blockIndex, blockHash, leaderNode, block.timestamp);
    }

    // ── Function 3: Release Milestone ────────────────────────

    function releaseMilestone(
        string memory donationId,
        uint8         milestone
    ) external onlyOwner nonReentrant {
        require(milestone >= 1 && milestone <= 3, "Invalid milestone");

        Escrow storage escrow = escrows[donationId];
        require(bytes(escrow.donationId).length > 0, "Escrow not found");
        require(escrow.status != EscrowStatus.FullyReleased, "Already fully released");
        require(escrow.status != EscrowStatus.Refunded, "Escrow was refunded");
        require(escrow.status != EscrowStatus.Rejected, "Escrow was rejected");
        require(milestone > escrow.milestone, "Milestone already released");

        uint256 releaseAmount = (escrow.amount * milestonePercents[milestone]) / 10000;

        escrow.releasedAmount += releaseAmount;
        escrow.milestone       = milestone;
        escrow.status = (milestone == 3)
            ? EscrowStatus.FullyReleased
            : EscrowStatus.PartialReleased;

        emit MilestoneReleased(donationId, milestone, releaseAmount, block.timestamp);
    }

    // ── Function 4: Refund ───────────────────────────────────

    function refundEscrow(
        string memory donationId,
        string memory reason
    ) external onlyOwner {
        Escrow storage escrow = escrows[donationId];
        require(bytes(escrow.donationId).length > 0, "Escrow not found");
        require(escrow.status == EscrowStatus.Locked, "Can only refund locked escrow");

        escrow.status = EscrowStatus.Refunded;

        emit FundsRefunded(donationId, escrow.amount, reason, block.timestamp);
    }

    // ── View functions ────────────────────────────────────────

    function getEscrow(string memory donationId)
        external view returns (Escrow memory)
    {
        return escrows[donationId];
    }

    function getBlock(uint256 blockIndex)
        external view returns (BlockRecord memory)
    {
        return blockRecords[blockIndex];
    }

    function verifyBlockHash(uint256 blockIndex, bytes32 expectedHash)
        external view returns (bool)
    {
        return blockRecords[blockIndex].exists &&
               blockRecords[blockIndex].blockHash == expectedHash;
    }
}