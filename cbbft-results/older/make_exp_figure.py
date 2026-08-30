"""Standalone per-experiment figure. Usage:
   python3 make_exp_figure.py 1   -> homogeneous (cbbft_results.csv)
   python3 make_exp_figure.py 2   -> tiered (cbbft_results_tiered.csv)
"""
import csv, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

QBFT_C, CBBFT_C, INK = "#B0446A", "#1E7F63", "#1F2733"
FAULTS = [0, 1, 2, 3]

exp = sys.argv[1] if len(sys.argv) > 1 else "2"
if exp == "1":
    src, out = "cbbft_results.csv", "fig_exp1_homogeneous"
    title = ("Experiment 1 \u2014 homogeneous validators (CB-BFT vs QBFT)\n"
             "15 identical containers, 5 tx/s, 150 s per run")
else:
    src, out = "cbbft_results_tiered.csv", "fig_exp2_tiered"
    title = ("Experiment 2 \u2014 tiered validators (CB-BFT vs QBFT)\n"
             "15 nodes in three CPU tiers (5\u00d72.00, 5\u00d70.75, "
             "5\u00d70.30 cores), 5 tx/s, 150 s per run")

rows = list(csv.DictReader(open(src)))

def stat(arm, field):
    m, s, n = [], [], []
    for f in FAULTS:
        v = [float(r[field]) for r in rows
             if r["arm"] == arm and int(r["faults"]) == f]
        m.append(np.mean(v))
        s.append(np.std(v, ddof=1) if len(v) > 1 else 0.0)
        n.append(len(v))
    return np.array(m), np.array(s), n

qi, qis, nrep = stat("qbft", "block_interval_s")
ci, cis, _ = stat("cbbft", "block_interval_s")
qb, qbs, _ = stat("qbft", "blocks")
cb, cbs, _ = stat("cbbft", "blocks")
qt, _, _ = stat("qbft", "transactions")
ct, _, _ = stat("cbbft", "transactions")
adv = (qi - ci) / qi * 100.0

fig, ax = plt.subplots(2, 2, figsize=(12.5, 9.5))
fig.suptitle(title, fontsize=12.5, fontweight="bold", color=INK)

a = ax[0][0]
a.errorbar(FAULTS, qi, yerr=qis, marker="o", capsize=4, lw=2,
           color=QBFT_C, label="QBFT")
a.errorbar(FAULTS, ci, yerr=cis, marker="s", capsize=4, lw=2,
           color=CBBFT_C, label="CB-BFT")
a.axhline(2.0, ls="--", lw=1, color="#8A94A3")
a.set_title("(a) Mean block interval", fontsize=11, fontweight="bold")
a.set_xlabel("Degraded validators"); a.set_ylabel("Mean block interval (s)")
a.set_xticks(FAULTS); a.grid(alpha=0.3); a.legend()

b = ax[0][1]
b.errorbar(FAULTS, qb, yerr=qbs, marker="o", capsize=4, lw=2,
           color=QBFT_C, label="QBFT")
b.errorbar(FAULTS, cb, yerr=cbs, marker="s", capsize=4, lw=2,
           color=CBBFT_C, label="CB-BFT")
b.set_title("(b) Blocks produced in 150 s", fontsize=11, fontweight="bold")
b.set_xlabel("Degraded validators"); b.set_ylabel("Blocks")
b.set_xticks(FAULTS); b.grid(alpha=0.3); b.legend()

c = ax[1][0]
c.plot(FAULTS, qt / 150.0, marker="o", lw=2, color=QBFT_C, label="QBFT")
c.plot(FAULTS, ct / 150.0, marker="s", lw=2, color=CBBFT_C, label="CB-BFT")
c.axhline(5.0, ls=":", lw=1, color="#8A94A3")
c.set_title("(c) Confirmed throughput", fontsize=11, fontweight="bold")
c.set_xlabel("Degraded validators")
c.set_ylabel("Confirmed throughput (tx/s)")
c.set_xticks(FAULTS); c.grid(alpha=0.3); c.legend()

d = ax[1][1]
x = np.arange(len(FAULTS))
colors = ["#9AA6B5" if v < 0 else "#2A6DA8" for v in adv]
d.bar(x, adv, 0.55, color=colors)
for i, v in enumerate(adv):
    off = 0.9 if v >= 0 else -2.4
    d.text(i, v + off, "%.1f%%" % v, ha="center",
           fontsize=10, fontweight="bold")
d.axhline(0, lw=1, color=INK)
d.set_xticks(x); d.set_xticklabels(FAULTS)
d.set_title("(d) CB-BFT block-interval advantage",
            fontsize=11, fontweight="bold")
d.set_xlabel("Degraded validators")
d.set_ylabel("Advantage over QBFT (%)")
d.set_ylim(min(-6, adv.min() * 1.6), max(adv.max() * 1.2, 10))
d.grid(axis="y", alpha=0.3)
d.text(0.02, 0.97, "n = %d reps at 0 faults, %d reps at 1\u20133 faults"
       % (nrep[0], nrep[1]),
       transform=d.transAxes, fontsize=8.5, va="top", color="#6B7688")

plt.tight_layout(rect=[0, 0, 1, 0.92])
plt.savefig(out + ".png", dpi=200, bbox_inches="tight")
plt.savefig(out + ".pdf", bbox_inches="tight")
print("wrote", out + ".png/.pdf")
for i, f in enumerate(FAULTS):
    print("faults %d  qbft %.3f  cbbft %.3f  adv %+.1f%%"
          % (f, qi[i], ci[i], adv[i]))
