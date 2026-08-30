"""Generate CB-BFT vs QBFT result figures from cbbft_results.csv."""
import csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

QBFT_C = "#B0446A"
CBBFT_C = "#1E7F63"
INK = "#1F2733"

rows = list(csv.DictReader(open("cbbft_results.csv")))
FAULTS = [0, 1, 2, 3]


def stat(arm, field):
    m, s = [], []
    for f in FAULTS:
        v = [float(r[field]) for r in rows if r["arm"] == arm and int(r["faults"]) == f]
        m.append(np.mean(v))
        s.append(np.std(v, ddof=1))
    return np.array(m), np.array(s)


qi, qis = stat("qbft", "block_interval_s")
ci, cis = stat("cbbft", "block_interval_s")
qb, qbs = stat("qbft", "blocks")
cb, cbs = stat("cbbft", "blocks")
qt, qts = stat("qbft", "transactions")
ct, cts = stat("cbbft", "transactions")

qtps, qtpss = qt / 150.0, qts / 150.0
ctps, ctpss = ct / 150.0, cts / 150.0
adv = (qi - ci) / qi * 100.0

fig, ax = plt.subplots(2, 2, figsize=(12, 9))
fig.suptitle(
    "CB-BFT vs QBFT - 15 validators, 5 tx/s offered load, 150 s per run, 5 repetitions",
    fontsize=13, fontweight="bold", color=INK)

a = ax[0][0]
a.errorbar(FAULTS, qi, yerr=qis, marker="o", capsize=4, lw=2, color=QBFT_C, label="QBFT")
a.errorbar(FAULTS, ci, yerr=cis, marker="s", capsize=4, lw=2, color=CBBFT_C, label="CB-BFT")
a.axhline(2.0, ls="--", lw=1, color="#8A94A3")
a.text(1.6, 2.06, "configured block period 2.0 s", fontsize=8.5, color="#6B7688")
a.set_xlabel("Degraded validators")
a.set_ylabel("Mean block interval (s)")
a.set_title("(a) Block interval degradation", fontsize=11, fontweight="bold")
a.set_xticks(FAULTS)
a.grid(alpha=0.3)
a.legend()

w = 0.35
x = np.arange(len(FAULTS))

b = ax[0][1]
b.bar(x - w / 2, qtps, w, yerr=qtpss, capsize=4, color=QBFT_C, label="QBFT")
b.bar(x + w / 2, ctps, w, yerr=ctpss, capsize=4, color=CBBFT_C, label="CB-BFT")
b.axhline(5.0, ls="--", lw=1, color="#8A94A3")
b.text(-0.4, 5.05, "offered load 5 tx/s", fontsize=8.5, color="#6B7688")
b.set_xticks(x)
b.set_xticklabels(FAULTS)
b.set_xlabel("Degraded validators")
b.set_ylabel("Confirmed throughput (tx/s)")
b.set_title("(b) Transaction throughput", fontsize=11, fontweight="bold")
b.grid(axis="y", alpha=0.3)
b.legend()

c = ax[1][0]
c.bar(x - w / 2, qb, w, yerr=qbs, capsize=4, color=QBFT_C, label="QBFT")
c.bar(x + w / 2, cb, w, yerr=cbs, capsize=4, color=CBBFT_C, label="CB-BFT")
c.set_xticks(x)
c.set_xticklabels(FAULTS)
c.set_xlabel("Degraded validators")
c.set_ylabel("Blocks produced in 150 s")
c.set_title("(c) Block production", fontsize=11, fontweight="bold")
c.grid(axis="y", alpha=0.3)
c.legend()

d = ax[1][1]
d.bar(FAULTS, adv, 0.5, color=CBBFT_C)
for f, v in zip(FAULTS, adv):
    d.text(f, max(v, 0) + 0.8, "%.1f%%" % v, ha="center", fontsize=10,
           fontweight="bold", color=INK)
d.set_xlabel("Degraded validators")
d.set_ylabel("CB-BFT block interval advantage (%)")
d.set_title("(d) Advantage grows with fault count", fontsize=11, fontweight="bold")
d.set_xticks(FAULTS)
d.set_ylim(min(0, min(adv) * 1.5), max(adv) * 1.25)
d.grid(axis="y", alpha=0.3)

plt.tight_layout(rect=[0, 0, 1, 0.96])
plt.savefig("fig_results.png", dpi=200, bbox_inches="tight")
plt.savefig("fig_results.pdf", bbox_inches="tight")
print("wrote fig_results.png / .pdf")

with open("summary_table.csv", "w", newline="") as fh:
    w2 = csv.writer(fh)
    w2.writerow(["faults", "qbft_interval_mean", "qbft_interval_sd",
                 "cbbft_interval_mean", "cbbft_interval_sd", "advantage_pct",
                 "qbft_tps_mean", "cbbft_tps_mean",
                 "qbft_blocks_mean", "cbbft_blocks_mean"])
    for i, f in enumerate(FAULTS):
        w2.writerow([f, "%.3f" % qi[i], "%.3f" % qis[i], "%.3f" % ci[i], "%.3f" % cis[i],
                     "%.1f" % adv[i], "%.2f" % qtps[i], "%.2f" % ctps[i],
                     "%.1f" % qb[i], "%.1f" % cb[i]])

print("\n%-8s %-24s %-24s %s" % ("faults", "QBFT interval (s)", "CB-BFT interval (s)", "advantage"))
for i, f in enumerate(FAULTS):
    print("%-8d %.3f +/- %-16.3f %.3f +/- %-16.3f %.1f%%"
          % (f, qi[i], qis[i], ci[i], cis[i], adv[i]))
