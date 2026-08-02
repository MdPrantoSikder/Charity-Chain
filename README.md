# CharityChain

A blockchain-based charity donation platform with a custom permissioned consensus mechanism, built as the applied system for undergraduate thesis + capstone research on attribute-based node clustering.

> **Status:** Active development · Final-year thesis project (CSE, University of Liberal Arts Bangladesh.)

---

## What it is

CharityChain lets donors give to verified organizations with every donation recorded as a real on-chain transaction, so the money trail is auditable end-to-end. It runs on a private, permissioned chain governed by **CB-BFT** — a Cluster-Based Byzantine Fault Tolerant consensus mechanism designed for this project.

The research question underneath it: *can a reputation-and-attribute-aware clustering scheme select block-sealing leaders more fairly and efficiently than flat leader-election, without sacrificing Byzantine fault tolerance?*

## Consensus: CB-BFT

The consensus layer is the core research contribution. Nodes are scored, clustered, and one representative per cluster is chosen to propose blocks under a BFT commit rule.

- **CRITIC scoring** across four measured attributes: CPU, Latency (cost-inverted), Trust, and Throughput. Weights are derived objectively from the data via the CRITIC method rather than set by hand.
- **Adaptive gap clustering** — nodes are grouped using a data-driven threshold (`T = μ + 0.5σ`) instead of a fixed cluster count.
- **Representative leader selection** — the top-scoring node in each cluster acts as the cluster's representative proposer; peer nodes monitor and can object.
- **Challenge window before commit** — silence is consent; `f + 1` valid objections drop the proposed block.
- **EWMA trust decay** so reputation reflects recent behavior, not just history.
- **Recovery Room** onboarding path for newly joined nodes before they earn full participation.
- Signed messages and peer-measured attributes to resist self-reported metric forgery.

Consensus is benchmarked against a real baseline (**Raft**) on latency, throughput, scalability, fault tolerance, resource utilization, and message overhead.

## Architecture

```
Donor / Org UI  ──►  API layer  ──►  CB-BFT consensus  ──►  Permissioned chain
                         │
                         └──►  SSLCommerz (BDT payments, sandbox)
```

- **Payments:** SSLCommerz gateway (initiate / success / fail / cancel + server-side validation). Currency is **BDT**.
- **Chain:** multi-node permissioned network, nodes run as Docker containers.
- **Ledger records:** donation transactions, organization registrations, disbursements.

## Tech stack

| Layer        | Tools                                             |
|--------------|---------------------------------------------------|
| Backend      | Python, FastAPI                                    |
| Consensus    | Custom CB-BFT (Python), benchmarked vs Raft       |
| Data         | PostgreSQL                                         |
| Payments     | SSLCommerz (sandbox)                               |
| Infra        | Docker, multi-node deployment                      |
| Frontend     | React (Bootstrap)                                  |

## Getting started

```bash
# 1. Clone
git clone https://github.com/<your-username>/charitychain.git
cd charitychain.

# 2. Configure environment,
cp .env.example .env
#   then fill in your own SSLCommerz sandbox credentials and DB settings

# 3. Bring up the stack
docker compose up --build.
```

> **Never commit your real `.env`.** It is gitignored by default. Only `.env.example` (with placeholder values) belongs in the repo.

## Repository layout

```
charitychain/
├── node/              # chain core: Block, Chain, TxPool, node runtime
├── consensus/         # CB-BFT: CRITIC scoring, clustering, leader selection, commit
├── api/               # FastAPI app, routes, SSLCommerz integration
├── benchmarks/        # CB-BFT vs Raft comparison harness + results
├── frontend/          # React (Bootstrap) donor/org UI
├── docker/            # Dockerfiles + compose for the multi-node network
├── docs/              # thesis notes, architecture, evaluation writeup
├── .env.example
├── .gitignore
└── README.md
```

## Research context

Developed as the unified thesis + capstone project (CSE 4098B), University of Liberal Arts Bangladesh, Dhaka. The consensus design evolved from an earlier attribute-based scheme (ABPC) into the current CB-BFT formulation.

## License

See [LICENSE](LICENSE).

## Authors

CharityChain capstone group — University of Liberal Arts Bangladesh.
Supervised by Nafees Mansoor, PhD.
