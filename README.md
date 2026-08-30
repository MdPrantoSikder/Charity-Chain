# CharityChain: A Permissioned Blockchain Donation Platform with Performance-Based Consensus

This repository accompanies a final-year thesis in the Department of Computer Science and Engineering, University of Liberal Arts Bangladesh. It contains a charity donation platform built on a private Hyperledger Besu network, a consensus mechanism implemented within the Besu client, and the experimental infrastructure and data used to evaluate it.

**Consensus implementation:** https://github.com/MdPrantoSikder/besu/compare/main...cbbft

---

## 1. Contributions

This work makes three contributions.

**A consensus mechanism.** CB-BFT (Cluster-Based Byzantine Fault Tolerant) replaces the round-robin proposer selection used by Besu's QBFT and IBFT2 with selection based on measured validator performance. It is implemented as a Java module within the Besu source tree and activated by a single genesis configuration flag. The Byzantine fault tolerant state machine — three-phase commit, round change, block validation — is inherited unchanged from QBFT; only proposer selection differs.

**An evaluation testbed.** A controlled environment in which any consensus protocol implemented in Besu can be evaluated under identical conditions, with the consensus mechanism as the sole independent variable. Four protocols have been evaluated to date.

**An empirical evaluation.** 116 experimental runs across two experiments, with variance reported, and independent validation using Hyperledger Caliper.

---

## 2. CB-BFT

Round-robin proposer selection assigns each validator a turn irrespective of its state. When a validator has failed, its turn nonetheless arrives, and the network incurs a round-change timeout before proceeding. Under repeated failure this cost accumulates.

CB-BFT computes a score for each validator from three criteria derived from block headers — resource utilisation, latency, and proposal reputation — weighted by the CRITIC method. Validators are clustered adaptively by score, and proposers are drawn from the highest-performing 30 percent. Validators that cease to perform fall out of the selection pool.

Scoring uses 64-bit fixed-point arithmetic throughout (WAD scale, `Math.multiplyHigh` for 128-bit intermediate products, `BigInteger.sqrt` for square roots). Floating-point arithmetic was found to produce divergent scores across nodes and consequently to break consensus determinism.

The implementation comprises 661 lines across 9 files, of which 587 lines constitute the consensus module itself. The remainder is the wiring required to instantiate the selector and parse the activating flag.

---

## 3. Experimental design

The testbed is constructed so that any measured difference is attributable to the consensus mechanism. Control is structural rather than procedural: every protocol is deployed through the same scripts, from configuration files that differ only in their consensus section, so a biased comparison would require deliberate modification rather than oversight.

Five properties are held constant:

| Layer | Held identical | Confound eliminated |
|:---|:---|:---|
| Host | One machine, one Docker daemon | Hardware and operating system variation |
| Client | One Besu binary per arm | Transaction pool, EVM, and networking differences |
| Network | 15 identical containers, fixed addresses and resources | Topology and capacity variation |
| Parameters | One timing block, copied into each configuration | Block period, timeout, and epoch differences |
| Procedure | One deployment pipeline, one measurement script | Operator variation between runs |

### 3.1 Parameters

| Category | Parameter | Value |
|:---|:---|:---|
| Network | Validators | 15 |
| | Chain identifier | 1337 |
| | Block period | 2 s |
| | Round-change timeout | 4 s |
| | Epoch length | 30,000 |
| Workload | Offered load | 5 tx/s |
| | Measured window | 150 s |
| | Warm-up, discarded | 30 s |
| Fault injection | Method | `docker stop` on nodes 15, 14, 13 |
| | Timing | 75 s into run (45 s into measured window) |
| | Levels | 0, 1, 2, 3 failed validators |
| Repetition | Runs per condition | 5 |
| Independent variable | Consensus protocol | QBFT, IBFT2, Clique, CB-BFT |

Each run begins from a freshly generated network; no chain state, peer memory, or database persists between runs. Faults are injected during the measured window rather than before it, so that the measurement captures how each protocol responds to failure rather than its steady-state behaviour on a reduced validator set.

### 3.2 Protocol selection

| Protocol | Byzantine fault tolerant | Proposer selection | Role |
|:---|:---:|:---|:---|
| QBFT | Yes | Round-robin | Primary baseline |
| IBFT2 | Yes | Round-robin | Secondary baseline |
| CB-BFT | Yes | CRITIC-scored, top 30% | Proposed mechanism |
| Clique | No | In-turn signing | Non-BFT reference |

Performance comparison is meaningful only between protocols providing equivalent guarantees. QBFT, IBFT2, and CB-BFT are all Byzantine fault tolerant and are therefore compared directly. Clique is included as a reference point: it performs no inter-node agreement, so its invariance to validator failure reflects the absence of Byzantine fault tolerance rather than superior resilience.

Protocols implemented in other clients were excluded. Raft, for example, is available in GoQuorum but not in Besu; evaluating it would introduce a different transaction pool, execution environment, and networking stack, and any observed difference would confound consensus with implementation. This constraint also motivates the decision to implement CB-BFT within the Besu source rather than as an application-layer coordinator: only an in-client implementation can be compared under the stated conditions.

---

## 4. Results

### 4.1 Fault tolerance, identical validators

Mean block interval in seconds, five runs per condition:

| Failed validators | QBFT | IBFT2 | Clique | CB-BFT |
|:---:|:---:|:---:|:---:|:---:|
| 0 | 1.997 | 2.094 | 1.992 | 2.005 |
| 1 | 2.241 | 2.173 | 2.000 | 2.054 |
| 2 | 2.894 | 2.653 | 2.002 | 2.166 |
| 3 | 3.989 | 3.286 | 2.008 | 2.513 |

Among Byzantine fault tolerant protocols, CB-BFT exhibits the least degradation under failure:

| Failed validators | Improvement over QBFT | Improvement over IBFT2 |
|:---:|:---:|:---:|
| 0 | not significant | not significant |
| 1 | 8.3% | 5.4% |
| 2 | 25.1% | 18.4% |
| 3 | 37.0% | 23.5% |

Confirmed throughput exhibits the same pattern. At three failed validators QBFT confirmed 4.14 tx/s of the 5 tx/s offered, whereas CB-BFT sustained 4.73 tx/s.

### 4.2 Replication under heterogeneous validators

A second experiment assigned validators unequal computing capacity in three tiers (2.00, 0.75, and 0.30 CPU cores), with all other parameters unchanged. The improvement over QBFT replicated at 7.2%, 16.0%, and 30.7% at one, two, and three failures — reduced in magnitude but identical in pattern, indicating that the effect is not an artifact of uniform hardware.

### 4.3 Independent validation

The protocols were additionally benchmarked with Hyperledger Caliper using an ERC-20 transfer workload, three runs per protocol, with 751 of 751 transactions confirmed in every run:

| Protocol | Mean latency | Throughput | Success rate |
|:---|:---:|:---:|:---:|
| QBFT | 1.48 s | 5.0 tx/s | 100% |
| IBFT2 | 1.33 s | 5.0 tx/s | 100% |
| CB-BFT | 1.22 s | 5.0 tx/s | 100% |

The ordering obtained through client-side measurement on a contract-call workload agrees with that obtained through chain-side measurement on a transfer workload, providing independent corroboration of the instrumented results.

---

## 5. Trade-offs and negative results

**No benefit in a healthy network.** At zero faults the Byzantine fault tolerant protocols are statistically indistinguishable. The scoring mechanism introduces complexity that yields no return until validators fail.

**Proposal concentration.** CB-BFT routed approximately 97% of proposals through 4 of 15 validators, against the even rotation of QBFT and IBFT2. Improved fault tolerance is obtained at the cost of proposer diversity, and the concentration arises in part from a feedback effect in the reputation criterion.

**Capability selection was not demonstrated.** Under heterogeneous hardware, tier A received 49% of proposals against 26% and 25% for tiers B and C — approximately equal despite substantially different processing capacity. All tiers sealed blocks within the two-second block period, leaving the latency criterion with negligible variance to discriminate on. The supported claim is therefore that CB-BFT excludes non-performing validators, not that it preferentially selects more capable ones. Detecting capability differences would likely require a heavier transaction load or a shorter block period; this is left to future work.

**Increased timing variance at low fault counts.** Under heterogeneous hardware, CB-BFT exhibited a standard deviation of 0.144 s at zero faults against QBFT's 0.063 s.

---

## 6. Limitations

Client versions differ between arms. QBFT and CB-BFT were evaluated on the CB-BFT fork (26.8-develop); IBFT2 and Clique were evaluated on upstream Besu 25.10.0, as the fork does not parse their genesis `extraData` formats. The primary QBFT–CB-BFT comparison is unaffected, both arms deriving from the same binary and differing by one genesis flag.

Clique was additionally evaluated without the Shanghai fork, whose withdrawals field its block producer does not populate.

Injected faults are crash faults, effected by container termination. Byzantine behaviour — equivocation, invalid state signing — was not tested.

The study used 15 validators on a single host. Results may not extend to larger or geographically distributed deployments.

Caliper measurements were taken on a healthy network; no faults were injected during those runs.

---

## 7. The platform

CharityChain records donations on the chain from contribution through escrow to disbursement. Donors contribute to verified cases and track funds to their destination; recipients submit cases with supporting documentation; trustees review and approve disbursement; administrators monitor validator state, consensus health, and proposal distribution. A public explorer exposes all transactions and blocks without authentication.

---

## 8. Repository structure

```
backend/            FastAPI application: blockchain client, escrow, authentication, routes
frontend/           Web interface: donor, trustee, administrator, explorer
blockchain/         Solidity contracts and Hardhat configuration
cbbft-consensus/    CB-BFT proposer selector and staged patches against Besu
wsl-setup/          Docker Compose and network setup for the 15-node testbed
cbbft-results/      Experimental data, figures, and analysis scripts
caliper-reports/    Caliper configuration, workload, reports, and summary figure
```

---

## 9. Reproduction

Requirements: Docker, WSL2 or Linux, approximately 14 GB of memory for 15 validators, and a Besu image.

```bash
# 1. Generate the network from a protocol's configuration.
#    The genesis must be generated by the same binary that runs the nodes:
#    extraData formats differ between consensus families and are not interchangeable.
besu operator generate-blockchain-config \
  --config-file=qbftConfigFile.json \
  --to=networkFiles \
  --private-key-file-name=key

# 2. Lay out the validators and start the network.
./setup-nodes.sh 15
docker compose -p cbbft up -d

# 3. Measure: 30 s warm-up, then 150 s at 5 tx/s.
./measure_only.sh qbft 150 r1 5
```

Each run writes `summary.csv` (block interval, blocks produced, confirmed transactions, distinct proposers) and `blocks.csv` (per-block number, timestamp, proposer, transaction count, gas consumed) to `results/<protocol>-15n-<label>/`. Evaluating a different protocol requires substituting the configuration file; no other change is necessary.

---

Implemented with Hyperledger Besu, Java 21, Solidity, FastAPI, PostgreSQL, Docker, Hyperledger Caliper, and Python.
