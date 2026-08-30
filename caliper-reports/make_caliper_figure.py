"""Caliper ERC-20 benchmark results across three consensus protocols."""
import csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

QC, IC, CC, INK = "#B0446A", "#BA7517", "#1E7F63", "#1F2733"
ORDER = ["qbft", "ibft2", "cbbft"]
LABEL = {"qbft": "QBFT", "ibft2": "IBFT2", "cbbft": "CB-BFT"}
COL = {"qbft": QC, "ibft2": IC, "cbbft": CC}

rows = list(csv.DictReader(open("caliper_summary.csv")))


def vals(p, f):
    return [float(r[f]) for r in rows if r["protocol"] == p]


fig, ax = plt.subplots(1, 3, figsize=(15, 5.2))
fig.suptitle(
    "Hyperledger Caliper \u2014 ERC-20 transfer benchmark\n"
    "15 validators, 5 tx/s offered, 150 s per run, 3 runs per protocol",
    fontsize=12.5, fontweight="bold", color=INK)

x = np.arange(len(ORDER))

a = ax[0]
means = [np.mean(vals(p, "avg_latency_s")) for p in ORDER]
a.bar(x, means, 0.55, color=[COL[p] for p in ORDER], zorder=2)
for i, p in enumerate(ORDER):
    for v in vals(p, "avg_latency_s"):
        a.plot(i, v, "o", color=INK, ms=5, alpha=0.7, zorder=3)
    a.text(i, means[i] + 0.07, "%.2f s" % means[i], ha="center",
           fontsize=10.5, fontweight="bold")
a.set_xticks(x); a.set_xticklabels([LABEL[p] for p in ORDER])
a.set_ylabel("Average latency (s)")
a.set_title("(a) Average transaction latency", fontsize=11, fontweight="bold")
a.set_ylim(0, 1.95); a.grid(axis="y", alpha=0.3, zorder=0)
a.text(0.03, 0.955, "dots = individual runs", transform=a.transAxes,
       fontsize=8.5, va="top", color="#6B7688")

b = ax[1]
for i, p in enumerate(ORDER):
    v = vals(p, "max_latency_s")
    b.plot([i] * len(v), v, "o", color=COL[p], ms=10, zorder=3)
    b.plot([i - 0.2, i + 0.2], [np.mean(v)] * 2, "-", color=INK, lw=2, zorder=4)
b.annotate("outlier", xy=(2, 6.76), xytext=(1.55, 7.3),
           fontsize=9, color="#6B7688",
           arrowprops=dict(arrowstyle="->", color="#6B7688", lw=1))
b.set_xticks(x); b.set_xticklabels([LABEL[p] for p in ORDER])
b.set_xlim(-0.5, 2.5); b.set_ylim(1.5, 8.0)
b.set_ylabel("Max latency (s)")
b.set_title("(b) Worst-case latency, each run shown",
            fontsize=11, fontweight="bold")
b.grid(axis="y", alpha=0.3, zorder=0)
b.text(0.03, 0.955, "bar = mean of 3 runs", transform=b.transAxes,
       fontsize=8.5, va="top", color="#6B7688")

c = ax[2]
tp = [np.mean(vals(p, "throughput_tps")) for p in ORDER]
c.bar(x, tp, 0.55, color=[COL[p] for p in ORDER], zorder=2)
c.axhline(5.0, ls=":", lw=1.2, color="#8A94A3", zorder=1)
for i in range(len(ORDER)):
    c.text(i, tp[i] + 0.1, "%.1f" % tp[i], ha="center",
           fontsize=10.5, fontweight="bold")
c.set_xticks(x); c.set_xticklabels([LABEL[p] for p in ORDER])
c.set_ylabel("Throughput (tx/s)")
c.set_title("(c) Throughput \u2014 751/751 succeeded, all runs",
            fontsize=11, fontweight="bold")
c.set_ylim(0, 6.2); c.grid(axis="y", alpha=0.3, zorder=0)
c.text(0.03, 0.955, "offered load 5 tx/s", transform=c.transAxes,
       fontsize=8.5, va="top", color="#6B7688")

plt.tight_layout(rect=[0, 0, 1, 0.88])
plt.savefig("fig_caliper.png", dpi=200, bbox_inches="tight")
plt.savefig("fig_caliper.pdf", bbox_inches="tight")
print("wrote fig_caliper.png/.pdf")
