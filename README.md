# CharityChain

**A transparent charity donation platform on a private Hyperledger Besu blockchain, with a novel Byzantine fault tolerant consensus mechanism.**

[![Besu](https://img.shields.io/badge/Hyperledger-Besu-blue)](https://besu.hyperledger.org/)
[![Consensus](https://img.shields.io/badge/consensus-CB--BFT-green)](https://github.com/MdPrantoSikder/besu/compare/main...cbbft)
[![License](https://img.shields.io/badge/license-Apache--2.0-lightgrey)](LICENSE)

---

## Overview

CharityChain records donations on a permissioned blockchain so that every transfer is traceable from donor to recipient. The platform runs on a 15-validator Hyperledger Besu network with escrow-based disbursement, role-based access for donors, trustees, and administrators, and a public transaction explorer.

Alongside the application, this project contributes **CB-BFT (Cluster-Based Byzantine Fault Tolerant)** — a consensus mechanism implemented inside the Besu client that selects block proposers by measured validator performance rather than fixed rotation — and an **evaluation testbed** in which any Besu-supported consensus protocol can be compared under identical conditions.

> ### CB-BFT consensus implementation
> **[View the changes against upstream Hyperledger Besu →](https://github.com/MdPrantoSikder/besu/compare/main...cbbft)**
>
> A new consensus module in the Besu source tree, integrated with the client's controller and genesis configuration, and activated by a single flag.

---

## Contributions

| # | Contribution | Where |
|---|---|---|
| 1 | CB-BFT consensus implemented inside the Besu client (Java) | [Besu fork](https://github.com/MdPrantoSikder/besu/compare/main...cbbft) |
| 2 | Controlled testbed for comparing consensus protocols | [`wsl-setup/`](wsl-setup/) |
| 3 | Empirical evaluation across four protocols and two experiments | [`cbbft-results/`](cbbft-results/) |
| 4 | Independent validation with Hyperledger Caliper | [`caliper-reports/`](caliper-reports/) |
| 5 | Donation platform built on the resulting chain | [`backend/`](backend/), [`frontend/`](frontend/) |

---

## How CB-BFT works

Standard BFT protocols in Besu (QBFT, IBFT2) rotate the block proposer in fixed order. When a validator fails, its turn still arrives, and the network waits out a round-change timeout before moving on — a cost paid on every cycle.

CB-BFT replaces that rotation with performance-based selection:

1. **Score** each validator on three CRITIC-weighted criteria derived from block headers — resource utilisation, latency, and proposal reputation.
2. **Cluster** validators adaptively by score.
3. **Select** proposers from the top 30%, excluding validators that are not performing.

The BFT state machine — three-phase commit, round changes, block validation — is inherited unchanged from QBFT. Only proposer selection differs, activated by a single genesis flag (`cbbftproposerselection`). CB-BFT and QBFT therefore run from the same binary, which is what makes the comparison below exact rather than approximate.

Scoring uses 64-bit fixed-point arithmetic throughout. Floating point was found to produce divergent scores across nodes and consequently to break consensus determinism — a constraint that shapes the entire implementation.

---

## Evaluation testbed

The design goal is a fair comparison: **the consensus protocol is the only independent variable.** Every protocol is deployed through the same scripts, from configuration files that differ in a single section, so unfairness is prevented by construction rather than by care.

| Category | Parameter | Value (identical for every protocol) |
|:---|:---|:---|
| **Hardware** | Host | Single machine, Docker on WSL2 |
| **Software** | Client | Hyperledger Besu |
| **Network** | Validators | 15 |
| | Chain ID | 1337 |
| | Block period | 2 s |
| | Round-change timeout | 4 s |
| | Epoch length | 30,000 |
| **Workload** | Offered load | 5 tx/s |
| | Measured window | 150 s |
| | Warm-up (discarded) | 30 s |
| **Faults** | Method | `docker stop` on nodes 15, 14, 13 |
| | Timing | 75 s into run (45 s into measured window) |
| | Levels | 0, 1, 2, 3 failed validators |
| **Repetition** | Runs per condition | 5 |
| **→ Varies** | **Consensus protocol** | **QBFT / IBFT2 / Clique / CB-BFT** |

Every run begins from a freshly generated network, so no chain state, peer memory, or database carries over. Faults are injected *during* the measured window rather than before it, so the measurement captures how each protocol responds to failure rather than its steady-state behaviour on a reduced validator set.

### Protocols compared

| Protocol | Byzantine fault tolerant | Proposer selection | Role in this study |
|:---|:---:|:---|:---|
| **QBFT** | Yes | Round-robin | Primary baseline |
| **IBFT2** | Yes | Round-robin | Secondary baseline |
| **CB-BFT** | Yes | CRITIC-scored, top 30% | This work |
| **Clique** | No | In-turn signing | Non-BFT reference point |

Clique performs no inter-node agreement, so validator failure does not slow it down. Its flat response reflects the **absence of Byzantine fault tolerance**, not superior resilience, and it is reported as a reference floor rather than a competitor.

Protocols implemented in other clients — Raft in GoQuorum, for example — were excluded deliberately: a different client brings a different transaction pool, EVM, and networking stack, so any measured difference would confound consensus with implementation. **This constraint also motivates implementing CB-BFT inside Besu rather than as an application-layer coordinator: only an in-client implementation can be evaluated under the stated conditions.**

---

## Results

### Fault tolerance

Mean block interval in seconds, 15 identical validators, 5 runs per condition:

| Failed validators | QBFT | IBFT2 | Clique* | **CB-BFT** |
|:---:|:---:|:---:|:---:|:---:|
| 0 | 1.997 | 2.094 | 1.992 | **2.005** |
| 1 | 2.241 | 2.173 | 2.000 | **2.054** |
| 2 | 2.894 | 2.653 | 2.002 | **2.166** |
| 3 | 3.989 | 3.286 | 2.008 | **2.513** |

<sub>*Clique is not Byzantine fault tolerant and is shown for reference only.</sub>

**CB-BFT improvement over BFT baselines:**

| Failed validators | over QBFT | over IBFT2 |
|:---:|:---:|:---:|
| 0 | not significant | not significant |
| 1 | **8.3%** | **5.4%** |
| 2 | **25.1%** | **18.4%** |
| 3 | **37.0%** | **23.5%** |

At three failed validators, QBFT confirmed only 4.14 tx/s of the offered 5 tx/s while CB-BFT sustained 4.73 tx/s — the difference an application actually experiences.

### Replication under heterogeneous hardware

A second experiment assigned validators unequal CPU (three tiers: 2.00 / 0.75 / 0.30 cores). The improvement over QBFT replicated: **7.2% / 16.0% / 30.7%** at one, two, and three faults — smaller in magnitude, identical in pattern, confirming the effect is not an artifact of uniform hardware.

### Independent benchmark

Benchmarked with **Hyperledger Caliper** on an ERC-20 transfer workload, 3 runs per protocol, 751/751 transactions confirmed in every run:

| Protocol | Mean latency | Throughput | Success |
|:---|:---:|:---:|:---:|
| QBFT | 1.48 s | 5.0 tx/s | 100% |
| IBFT2 | 1.33 s | 5.0 tx/s | 100% |
| **CB-BFT** | **1.22 s** | 5.0 tx/s | 100% |

Client-side measurement on a contract-call workload reproduces the ordering obtained by chain-side measurement on a transfer workload — independent corroboration of the instrumented results.

---

## Trade-offs

Reported in full, because they bound what the results claim:

| Trade-off | Evidence |
|:---|:---|
| **No benefit in a healthy network** | At zero faults all BFT protocols are statistically indistinguishable; the scoring adds complexity that only pays off under failure. |
| **Proposal concentration** | CB-BFT routed ~97% of proposals through 4 of 15 nodes, against round-robin's even rotation. Fault tolerance is gained at the cost of proposer diversity. |
| **No capability ranking** | Under heterogeneous CPU, tier A received 49% of proposals against 26% and 25% for tiers B and C. All tiers sealed within the 2 s block period, leaving the latency criterion nothing to rank on. **CB-BFT excludes failed validators; it was not shown to select the most capable ones.** |
| **Higher timing variance at low fault counts** | Standard deviation 0.144 s against QBFT's 0.063 s at zero faults under heterogeneous hardware. |

---

## Repository layout

```
backend/            FastAPI application — blockchain client, escrow, auth, routes.
frontend/           Web interface — donor, trustee, admin, explorer.
blockchain/         Solidity contracts and Hardhat configuration.
cbbft-consensus/    CB-BFT proposer selector and staged patches against Besu.
wsl-setup/          Docker Compose and network setup for the 15-node testbed.
cbbft-results/      Experiment data, figures, and analysis scripts.
caliper-reports/    Caliper configuration, workload, HTML reports, summary figure.
```

---

## Reproducing an experiment

**Requirements:** Docker, WSL2 or Linux, ~14 GB RAM for 15 validators, a Besu image.

```bash
# 1. Generate the network from a protocol's configuration.
#    The genesis MUST be generated by the same binary that will run the nodes:
#    extraData formats differ per consensus family and are not cross-compatible.
besu operator generate-blockchain-config \
  --config-file=qbftConfigFile.json \
  --to=networkFiles \
  --private-key-file-name=key

# 2. Lay out 15 nodes and start the network.
./setup-nodes.sh 15
docker compose -p cbbft up -d

# 3. Measure: 30 s warm-up, then 150 s at 5 tx/s.
./measure_only.sh qbft 150 r1 5
```

Each run writes `summary.csv` (block interval, blocks, transactions, distinct proposers) and `blocks.csv` (per-block number, timestamp, proposer, transaction count, gas used) to `results/<protocol>-15n-<label>/`.

To evaluate a different protocol, swap the configuration file. Nothing else changes.

---

## Limitations

- **Client versions differ across arms.** QBFT and CB-BFT ran on the CB-BFT fork (26.8-develop); IBFT2 and Clique ran on upstream Besu 25.10.0, since the fork does not parse their genesis extraData formats. The primary QBFT-versus-CB-BFT comparison is unaffected: same binary, one genesis flag.
- **Clique additionally ran without the Shanghai fork**, as its block producer does not populate the withdrawals field that fork requires.
- **Faults are crash faults** (`docker stop`), not Byzantine behaviour. No validator was made to equivocate or sign invalid state.
- **Scale.** 15 validators on a single host; results may not extend to larger or geographically distributed deployments.
- **Caliper runs measured a healthy network only** — no fault injection.

---

## Technology

`Hyperledger Besu` · `Java 21` · `Solidity` · `FastAPI` · `PostgreSQL` · `Docker` · `Hyperledger Caliper` · `Python`

---

<sub>Final-year capstone project — Department of Computer Science and Engineering, University of Liberal Arts Bangladesh.</sub>
