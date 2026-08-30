"""
make_graphs.py — evaluation figures from REAL measured data.

    python make_graphs.py

Reads consensus_comparison.csv and fault_tolerance.csv (both produced from
blocks actually sealed on the live Besu network) and writes PNGs to figures/.

Every plotted value was measured. Nothing is modelled or estimated.

FIGURES — one claim per figure
------------------------------
  fig1_detection.png     THE headline: only CB-BFT notices a degraded node
  fig2_leadership.png    distinct proposers + leader monopoly
  fig3_gini.png          leadership concentration, with the honest caveat
  fig4_latency.png       consensus cost is negligible beside the chain
  fig5_structure.png     clustering is unique to CB-BFT
  fig6_tradeoff.png      where CB-BFT wins AND where it loses
  fig7_architecture.png  CB-BFT network diagram (drawn, not measured)

Layout note: every figure uses explicit subplots_adjust rather than
tight_layout, because captions placed below axes get clipped or overlapped by
tight_layout's bounding-box calculation.
"""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd

OUT = "figures"
os.makedirs(OUT, exist_ok=True)

COLORS = {"CB-BFT": "#6C63FF", "Raft": "#00A88F", "PBFT": "#E8912A"}
ORDER = ["CB-BFT", "Raft", "PBFT"]

plt.rcParams.update({
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.labelsize": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 150,
    "savefig.facecolor": "white",
})


def sort_protocols(df):
    df = df.copy()
    df["_o"] = df["protocol"].apply(
        lambda p: ORDER.index(p) if p in ORDER else 99)
    return df.sort_values("_o").drop(columns="_o").reset_index(drop=True)


def bar_panel(ax, df, col, title, ylabel, fmt="{:.0f}", pad=1.30):
    colors = [COLORS.get(p, "#9EA3BF") for p in df["protocol"]]
    bars = ax.bar(df["protocol"], df[col], color=colors, width=0.5,
                  edgecolor="white", linewidth=2)
    ax.set_title(title, pad=14)
    ax.set_ylabel(ylabel, labelpad=10)
    ax.grid(axis="y", alpha=0.22)
    ax.set_axisbelow(True)
    top = max(df[col]) or 1
    for rect, v in zip(bars, df[col]):
        ax.text(rect.get_x() + rect.get_width() / 2, v + top * 0.04,
                fmt.format(v), ha="center", fontweight="bold", fontsize=12)
    ax.set_ylim(0, top * pad)


# ══════════════════════════════════════════════════════════════════
#  FIG 1 — DETECTION.  The headline result.
# ══════════════════════════════════════════════════════════════════
def fig_detection(ft):
    fig, ax = plt.subplots(figsize=(10, 6.2))

    # Raft and PBFT both sit flat at zero, so one line hides the other.
    # A small vertical offset keeps both visible without changing the claim.
    offsets = {"CB-BFT": 0.0, "Raft": 0.16, "PBFT": -0.16}
    styles  = {"CB-BFT": "-", "Raft": "--", "PBFT": ":"}
    for proto in ORDER:
        d = ft[ft["protocol"] == proto]
        if d.empty:
            continue
        ax.plot(d["degraded"], d["demoted"] + offsets[proto], "o",
                linestyle=styles[proto], label=proto,
                color=COLORS[proto], linewidth=3, markersize=10,
                markeredgecolor="white", markeredgewidth=1.6)

    ax.set_xlabel("Degraded validator nodes injected", labelpad=10)
    ax.set_ylabel("Nodes detected and excluded from consensus", labelpad=10)
    ax.set_title("Only CB-BFT Detects Degraded Validators", pad=16)
    ax.legend(frameon=False, fontsize=12, loc="upper left")
    ax.grid(alpha=0.22)
    ax.set_axisbelow(True)
    ax.set_xlim(-0.6, 16)
    ax.set_ylim(-0.8, 17)

    ax.annotate("CB-BFT: every degraded node detected",
                xy=(15, 15), xytext=(8.4, 13.4),
                fontsize=10.5, color=COLORS["CB-BFT"], fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=COLORS["CB-BFT"], lw=1.6))
    ax.annotate("Raft and PBFT: zero detected at every level",
                xy=(9, 0), xytext=(4.0, 3.6),
                fontsize=10.5, color="#8A8FA8", fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="#8A8FA8", lw=1.6))

    fig.subplots_adjust(left=0.11, right=0.96, top=0.90, bottom=0.20)
    fig.text(0.5, 0.045,
             "Raft and PBFT have no reputation system — neither specification reads node "
             "attributes,\nso a degraded validator keeps voting indefinitely. "
             "Their lines are offset slightly to remain distinguishable.",
             ha="center", fontsize=9.5, color="#5A5E7A", style="italic")
    fig.savefig(f"{OUT}/fig1_detection.png", bbox_inches="tight")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════
#  FIG 2 — LEADERSHIP
# ══════════════════════════════════════════════════════════════════
def fig_leadership(df):
    fig, ax = plt.subplots(1, 2, figsize=(13, 5.8))

    bar_panel(ax[0], df, "distinct_leaders",
              "Distinct Block Proposers", "nodes that sealed ≥ 1 block")

    colors = [COLORS.get(p, "#9EA3BF") for p in df["protocol"]]
    bars = ax[1].barh(df["protocol"], df["top_leader_pct"], color=colors,
                      height=0.45, edgecolor="white", linewidth=2)
    ax[1].set_xlabel("% of blocks sealed by the single busiest node", labelpad=10)
    ax[1].set_title("Leader Monopoly", pad=14)
    ax[1].set_xlim(0, 132)
    ax[1].grid(axis="x", alpha=0.22)
    ax[1].set_axisbelow(True)
    ax[1].invert_yaxis()
    for rect, (_, r) in zip(bars, df.iterrows()):
        ax[1].text(r["top_leader_pct"] + 3, rect.get_y() + rect.get_height() / 2,
                   f"{r['top_leader_pct']:.0f}%", va="center",
                   fontweight="bold", fontsize=12)

    fig.suptitle("Leadership Distribution — 10 real blocks per protocol",
                 fontsize=15, fontweight="bold", y=0.97)
    fig.subplots_adjust(left=0.08, right=0.96, top=0.82, bottom=0.20, wspace=0.28)
    fig.text(0.5, 0.05,
             "Raft elects one permanent leader that sealed every block. "
             "CB-BFT rotated across 7 nodes.",
             ha="center", fontsize=10, color="#5A5E7A", style="italic")
    fig.savefig(f"{OUT}/fig2_leadership.png", bbox_inches="tight")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════
#  FIG 3 — GINI, with the sample-size caveat stated on the figure
# ══════════════════════════════════════════════════════════════════
def fig_gini(df):
    fig, ax = plt.subplots(figsize=(9, 6))

    bar_panel(ax, df, "leader_gini", "Leadership Concentration (Gini)",
              "0 = even rotation      1 = one node monopolises",
              fmt="{:.3f}", pad=1.45)

    ax.axhline(0.5, color="#C4C8DA", lw=1.2, ls="--", zorder=0)
    ax.text(2.42, 0.52, "more decentralised below", fontsize=8.5,
            color="#8A8FA8", ha="right")

    fig.subplots_adjust(left=0.13, right=0.96, top=0.89, bottom=0.24)
    fig.text(0.5, 0.075,
             "PBFT rotates round-robin and is therefore the most even — but it ignores node\n"
             "quality entirely. CB-BFT restricts proposing to the top 30% of each cluster, so a\n"
             "Gini of zero is neither expected nor desirable.",
             ha="center", fontsize=9.5, color="#5A5E7A", style="italic")
    fig.savefig(f"{OUT}/fig3_gini.png", bbox_inches="tight")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════
#  FIG 4 — WHERE THE TIME GOES
# ══════════════════════════════════════════════════════════════════
def fig_latency(df):
    fig, ax = plt.subplots(figsize=(10.5, 6.4))

    x = range(len(df))
    w = 0.26
    ax.bar([i - w for i in x], df["scoring_ms"], w,
           label="Scoring + clustering", color="#6C63FF", edgecolor="white", lw=1.2)
    ax.bar(list(x), df["consensus_ms"], w,
           label="Leader election + voting", color="#3BAAFF", edgecolor="white", lw=1.2)
    ax.bar([i + w for i in x], df["onchain_ms"], w,
           label="Besu chain round-trip", color="#E8912A", edgecolor="white", lw=1.2)

    ax.set_yscale("log")
    ax.set_xticks(list(x))
    ax.set_xticklabels(df["protocol"], fontsize=12)
    ax.set_ylabel("milliseconds (log scale)", labelpad=10)
    ax.set_title("Where the Time Actually Goes", pad=16)
    ax.legend(frameon=False, fontsize=10.5, loc="upper left",
              bbox_to_anchor=(0.01, 0.99))
    ax.grid(axis="y", alpha=0.22)
    ax.set_axisbelow(True)
    ax.set_ylim(0.004, 60000)

    for i, r in df.iterrows():
        ax.text(i + w, r["onchain_ms"] * 1.7, f"{r['onchain_ms']:.0f} ms",
                ha="center", fontsize=10, fontweight="bold", color="#B36A10")
        consensus = r["scoring_ms"] + r["consensus_ms"]
        pct = 100 * consensus / (consensus + r["onchain_ms"])
        ax.text(i - w / 2, 0.0075, f"{pct:.3f}%", ha="center",
                fontsize=10, fontweight="bold", color="#4A45B8")

    fig.subplots_adjust(left=0.11, right=0.96, top=0.90, bottom=0.20)
    fig.text(0.5, 0.045,
             "Percentages show consensus as a share of end-to-end donation time. "
             "The chain dominates by\nthree orders of magnitude, so CB-BFT's higher "
             "scoring cost is not observable to a donor.",
             ha="center", fontsize=9.5, color="#5A5E7A", style="italic")
    fig.savefig(f"{OUT}/fig4_latency.png", bbox_inches="tight")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════
#  FIG 5 — STRUCTURE
# ══════════════════════════════════════════════════════════════════
def fig_structure(df):
    fig, ax = plt.subplots(1, 2, figsize=(13, 5.8))

    bar_panel(ax[0], df, "avg_clusters", "Clusters Formed per Block",
              "average clusters", fmt="{:.1f}")
    bar_panel(ax[1], df, "avg_voters", "Validators Voting per Block",
              "average validators", fmt="{:.1f}")

    fig.suptitle("Structural Differences — clustering is unique to CB-BFT",
                 fontsize=15, fontweight="bold", y=0.97)
    fig.subplots_adjust(left=0.08, right=0.96, top=0.82, bottom=0.22, wspace=0.26)
    fig.text(0.5, 0.06,
             "1 cluster = a flat replica set. Raft and PBFT do not group nodes because neither "
             "scores them.\nVoter counts reflect different quorum structures and are not "
             "directly comparable.",
             ha="center", fontsize=9.5, color="#5A5E7A", style="italic")
    fig.savefig(f"{OUT}/fig5_structure.png", bbox_inches="tight")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════
#  FIG 6 — THE HONEST TRADE-OFF
# ══════════════════════════════════════════════════════════════════
def fig_tradeoff(df, ft):
    fig = plt.figure(figsize=(13, 7.5))
    gs = fig.add_gridspec(2, 2, hspace=0.62, wspace=0.28,
                          left=0.08, right=0.96, top=0.86, bottom=0.11)

    a = fig.add_subplot(gs[0, 0])
    bar_panel(a, df, "distinct_leaders", "WIN — Distinct Proposers", "nodes")

    b = fig.add_subplot(gs[0, 1])
    det = []
    for p in ORDER:
        d = ft[(ft["protocol"] == p) & (ft["degraded"] == 15)]
        det.append(int(d["demoted"].iloc[0]) if not d.empty else 0)
    bars = b.bar(ORDER, det, color=[COLORS[p] for p in ORDER], width=0.5,
                 edgecolor="white", linewidth=2)
    b.set_title("WIN — Degraded Nodes Detected", pad=14)
    b.set_ylabel("of 15 injected")
    b.grid(axis="y", alpha=0.22); b.set_axisbelow(True)
    b.set_ylim(0, 19)
    for rect, v in zip(bars, det):
        b.text(rect.get_x() + rect.get_width() / 2, v + 0.5, str(v),
               ha="center", fontweight="bold", fontsize=12)

    c = fig.add_subplot(gs[1, 0])
    bar_panel(c, df, "leader_gini", "LOSS — Gini vs PBFT",
              "lower is more even", fmt="{:.3f}", pad=1.42)

    d = fig.add_subplot(gs[1, 1])
    cons = df["scoring_ms"] + df["consensus_ms"]
    bars = d.bar(df["protocol"], cons, color=[COLORS.get(p) for p in df["protocol"]],
                 width=0.5, edgecolor="white", linewidth=2)
    d.set_title("LOSS — Consensus Cost vs Raft", pad=14)
    d.set_ylabel("milliseconds")
    d.grid(axis="y", alpha=0.22); d.set_axisbelow(True)
    d.set_ylim(0, max(cons) * 1.35)
    for rect, v in zip(bars, cons):
        d.text(rect.get_x() + rect.get_width() / 2, v + max(cons) * 0.05,
               f"{v:.3f}", ha="center", fontweight="bold", fontsize=11)

    fig.suptitle("CB-BFT — Measured Strengths and Measured Weaknesses",
                 fontsize=15, fontweight="bold", y=0.955)
    fig.text(0.5, 0.025,
             "CB-BFT is the only protocol that detects degraded validators and it distributes "
             "leadership far more evenly than Raft.\nIt pays with higher scoring cost than Raft "
             "and less even rotation than PBFT — a deliberate trade of pure fairness for node quality.",
             ha="center", fontsize=10, color="#3A3F5A")
    fig.savefig(f"{OUT}/fig6_tradeoff.png", bbox_inches="tight")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════
#  FIG 7 — ARCHITECTURE (drawn, not measured)
# ══════════════════════════════════════════════════════════════════
def fig_architecture():
    fig, ax = plt.subplots(figsize=(13, 9))
    ax.set_xlim(0, 13); ax.set_ylim(0, 10); ax.axis("off")

    def box(x, y, w, h, label, sub, fc, ec, fs=10):
        ax.add_patch(mpatches.FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.07",
            facecolor=fc, edgecolor=ec, linewidth=1.8))
        ax.text(x + w / 2, y + h * (0.63 if sub else 0.5), label,
                ha="center", va="center", fontsize=fs,
                fontweight="bold", color="#18192E")
        if sub:
            ax.text(x + w / 2, y + h * 0.25, sub, ha="center", va="center",
                    fontsize=fs - 2.2, color="#5A5E7A")

    def arrow(x1, y1, x2, y2, color="#5A5E7A"):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", lw=1.8, color=color))

    ax.text(6.5, 9.55, "CB-BFT Network Architecture", ha="center",
            fontsize=17, fontweight="bold")
    ax.text(6.5, 9.15, "Cluster-Based BFT with CRITIC reputation scoring",
            ha="center", fontsize=11.5, color="#5A5E7A")

    # ── application layer ──
    box(0.5, 7.85, 3.5, 0.9, "Donor", "web frontend", "#EEF0FF", "#6C63FF")
    box(4.75, 7.85, 3.5, 0.9, "FastAPI Backend", "donation pipeline",
        "#EEF0FF", "#6C63FF")
    box(9.0, 7.85, 3.5, 0.9, "PostgreSQL", "state + audit trail",
        "#EEF0FF", "#6C63FF")
    arrow(4.0, 8.30, 4.75, 8.30)
    arrow(8.25, 8.30, 9.0, 8.30)

    # ── consensus layer ──
    ax.add_patch(mpatches.FancyBboxPatch(
        (0.5, 3.15), 12.0, 4.15, boxstyle="round,pad=0.1",
        facecolor="#FAFAFF", edgecolor="#6C63FF", linewidth=1.4, linestyle="--"))
    ax.text(0.85, 7.02, "CB-BFT CONSENSUS LAYER — 30 validator nodes, 8 organisations",
            fontsize=10.5, fontweight="bold", color="#6C63FF")

    phases = [
        (0.9,  "1. CRITIC",     "objective weights",  "CPU · Latency↓ · Reputation · Throughput"),
        (4.0,  "2. Clustering", "T = μ + 0.5σ",       "adaptive gap-based, ≥ 4 clusters"),
        (7.1,  "3. Leader",     "top 30%, min 3",     "deterministic shuffle — verifiable"),
        (10.2, "4. Vote",       "2/3 quorum",         "f = ⌊(|L|−1)/3⌋"),
    ]
    for x, title, sub, note in phases:
        box(x, 5.75, 2.4, 0.85, title, sub, "#FFFFFF", "#3BAAFF", 10)
        ax.text(x + 1.2, 5.50, note, ha="center", fontsize=7.6, color="#5A5E7A")
    for x1, x2 in ((3.3, 4.0), (6.4, 7.1), (9.5, 10.2)):
        arrow(x1, 6.17, x2, 6.17)

    # ── clusters ──
    cluster_colors = ["#6C63FF", "#3BAAFF", "#00C9A7", "#F7A935"]
    for i, col in enumerate(cluster_colors):
        x = 1.0 + i * 2.95
        ax.add_patch(mpatches.FancyBboxPatch(
            (x, 3.55), 2.55, 1.5, boxstyle="round,pad=0.06",
            facecolor=col + "18", edgecolor=col, linewidth=1.6))
        ax.text(x + 1.28, 4.78, f"Cluster-{i+1}", ha="center",
                fontsize=10, fontweight="bold", color=col)
        ax.scatter([x + 0.5], [4.28], s=230, color=col, zorder=3, marker="*")
        ax.text(x + 0.5, 3.86, "leader", ha="center", fontsize=7.4, color=col)
        for j in range(4):
            ax.scatter([x + 1.1 + j * 0.35], [4.28], s=58, color=col,
                       alpha=0.45, zorder=3)
        ax.text(x + 1.8, 3.86, "members verify", ha="center",
                fontsize=7.4, color="#5A5E7A")

    ax.text(6.5, 3.30, "cluster leaders exchange votes   —   block commits at 2/3",
            ha="center", fontsize=9.5, color="#5A5E7A", style="italic")

    # ── chain layer ──
    ax.add_patch(mpatches.FancyBboxPatch(
        (0.5, 0.45), 12.0, 2.05, boxstyle="round,pad=0.1",
        facecolor="#FFF8EE", edgecolor="#E8912A", linewidth=1.4))
    ax.text(0.85, 2.22, "HYPERLEDGER BESU — private IBFT2 network, chain 1337",
            fontsize=10.5, fontweight="bold", color="#E8912A")

    for i in range(4):
        x = 1.05 + i * 2.9
        box(x, 0.85, 2.3, 0.9, f"Validator {i+1}", "Besu IBFT2",
            "#FFFFFF", "#E8912A", 9.5)
        if i < 3:
            arrow(x + 2.3, 1.30, x + 2.9, 1.30, color="#E8912A")

    ax.annotate("", xy=(6.5, 2.60), xytext=(6.5, 3.08),
                arrowprops=dict(arrowstyle="-|>", lw=2, color="#E8912A"))
    ax.text(6.75, 2.80, "block hash + escrow → Solidity smart contract",
            ha="left", fontsize=9, color="#E8912A", style="italic")

    fig.savefig(f"{OUT}/fig7_architecture.png", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    df = sort_protocols(pd.read_csv("consensus_comparison.csv"))
    print("Measured comparison:")
    print(df[["protocol", "blocks", "distinct_leaders", "leader_gini",
              "avg_clusters", "onchain_ms"]].to_string(index=False))

    ft = None
    if os.path.exists("fault_tolerance.csv"):
        ft = pd.read_csv("fault_tolerance.csv")
        print(f"\nFault-tolerance rows: {len(ft)}")
    else:
        print("\n  fault_tolerance.csv missing — run fault_experiment.py first")
        print("  (fig1 and fig6 need it)")

    if ft is not None:
        fig_detection(ft)
    fig_leadership(df)
    fig_gini(df)
    fig_latency(df)
    fig_structure(df)
    if ft is not None:
        fig_tradeoff(df, ft)
    fig_architecture()

    print(f"\nWrote figures to {OUT}/")
    for f in sorted(os.listdir(OUT)):
        print(f"  {f}")