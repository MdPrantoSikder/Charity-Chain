const { ethers } = require("hardhat");
const { expect } = require("chai");

describe("CharityChain", function () {
  let contract;
  let owner;

  // Deploy a fresh contract before each test
  beforeEach(async function () {
    [owner] = await ethers.getSigners();
    const CharityChain = await ethers.getContractFactory("CharityChain");
    contract = await CharityChain.deploy();
    await contract.waitForDeployment();
  });

  // ── Test 1: Lock Funds ──────────────────────────────────
  it("should lock funds and create escrow", async function () {
    await contract.lockFunds("DON001", "DONOR001", "CASE001");

    const escrow = await contract.getEscrow("DON001");
    expect(escrow.donationId).to.equal("DON001");
    expect(escrow.status).to.equal(0); // 0 = Locked
    expect(escrow.milestone).to.equal(0);
    console.log("  lockFunds passed");
  });

  // ── Test 2: Cannot lock same donation twice ─────────────
  it("should reject duplicate donation lock", async function () {
    await contract.lockFunds("DON001", "DONOR001", "CASE001");
    await expect(
      contract.lockFunds("DON001", "DONOR001", "CASE001")
    ).to.be.revertedWith("Escrow already exists for this donation");
    console.log("  duplicate lock rejected correctly");
  });

  // ── Test 3: Store block hash ────────────────────────────
  it("should store block hash on-chain", async function () {
    const blockHash = ethers.keccak256(ethers.toUtf8Bytes("block_data_1"));
    const prevHash  = ethers.keccak256(ethers.toUtf8Bytes("genesis"));

    await contract.storeBlockHash(1, blockHash, prevHash, "BankA_1", "DON001");

    const record = await contract.getBlock(1);
    expect(record.exists).to.equal(true);
    expect(record.blockHash).to.equal(blockHash);
    expect(record.leaderNode).to.equal("BankA_1");
    console.log("  storeBlockHash passed — block #1 recorded");
  });

  // ── Test 4: Verify block hash ───────────────────────────
  it("should verify block hash correctly", async function () {
    const blockHash = ethers.keccak256(ethers.toUtf8Bytes("block_data_1"));
    const prevHash  = ethers.keccak256(ethers.toUtf8Bytes("genesis"));

    await contract.storeBlockHash(1, blockHash, prevHash, "BankA_1", "DON001");

    const valid   = await contract.verifyBlockHash(1, blockHash);
    const invalid = await contract.verifyBlockHash(1, ethers.keccak256(ethers.toUtf8Bytes("wrong")));

    expect(valid).to.equal(true);
    expect(invalid).to.equal(false);
    console.log("  verifyBlockHash passed");
  });

  // ── Test 5: Release milestone 1 (30%) ──────────────────
  it("should release milestone 1", async function () {
    await contract.lockFunds("DON001", "DONOR001", "CASE001");
    await contract.releaseMilestone("DON001", 1);

    const escrow = await contract.getEscrow("DON001");
    expect(escrow.milestone).to.equal(1);
    expect(escrow.status).to.equal(1); // 1 = PartialReleased
    console.log("  milestone 1 (30%) released");
  });

  // ── Test 6: Release all 3 milestones ───────────────────
  it("should release all milestones and mark fully released", async function () {
    await contract.lockFunds("DON001", "DONOR001", "CASE001");
    await contract.releaseMilestone("DON001", 1);
    await contract.releaseMilestone("DON001", 2);
    await contract.releaseMilestone("DON001", 3);

    const escrow = await contract.getEscrow("DON001");
    expect(escrow.milestone).to.equal(3);
    expect(escrow.status).to.equal(2); // 2 = FullyReleased
    console.log("  all 3 milestones released, status = FullyReleased");
  });

  // ── Test 7: Refund escrow ───────────────────────────────
  it("should refund escrow when consensus fails", async function () {
    await contract.lockFunds("DON001", "DONOR001", "CASE001");
    await contract.refundEscrow("DON001", "BFT quorum failed");

    const escrow = await contract.getEscrow("DON001");
    expect(escrow.status).to.equal(3); // 3 = Refunded
    console.log("  refundEscrow passed");
  });

  // ── Test 8: Only owner can call ─────────────────────────
  it("should reject calls from non-owner", async function () {
    const [, attacker] = await ethers.getSigners();
    await expect(
      contract.connect(attacker).lockFunds("DON001", "DONOR001", "CASE001")
    ).to.be.revertedWithCustomError(contract, "OwnableUnauthorizedAccount");
    console.log("  non-owner rejected correctly");
  });
});