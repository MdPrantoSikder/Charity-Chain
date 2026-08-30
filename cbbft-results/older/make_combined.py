"""Combined CB-BFT vs QBFT figure across both experiments."""
import csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

QBFT_C, CBBFT_C, INK = "#B0446A", "#1E7F63", "#1F2733"
FAULTS = [0, 1, 2, 3]

def load(p):
    return list(csv.DictReader(open(p)))

def stat(rows, arm, field):
    m, s = [], []
    for f in FAULTS:
        v = [float(r[field]) for r in rows if r["arm"] == arm and int(r["faults"]) == f]
        m.append(np.mean(v) if v else np.nan)
        s.append(np.std(v, ddof=1) if len(v) > 1 else 0.0)
    return np.array(m), np.array(s)

homo = load("cbbft_results.csv")
tier = load("cbbft_results_tiered.csv")

hq, hqs = stat(homo, "qbft", "block_interval_s")
hc, hcs = stat(homo, "cbbft", "block_interval_s")
tq, tqs = stat(tier, "qbft", "block_interval_s")
tc, tcs = stat(tier, "cbbft", "block_interval_s")
hqt, _  = stat(homo, "qbft", "transactions")
hct, _  = stat(homo, "cbbft", "transactions")
tqt, _  = stat(tier, "qbft", "transactions")
tct, _  = stat(tier, "cbbft", "transactions")

adv_h = (hq - hc) / hq * 100.0
adv_t = (tq - tc) / tq * 100.0

fig, ax = plt.subplots(2, 2, figsize=(13, 9.5))
fig.suptitle(
    "CB-BFT vs QBFT - 15 validators, 5 tx/s, 150 s per run\n"
    "Experiment 1: identical containers   |   Experiment 2: three CPU tiers "
    "(2.00 / 0.75 / 0.30 cores)",
    fontsize=12.5, fontweight="bold", color=INK)

a = ax[0][0]
a.errorbar(FAULTS, hq, yerr=hqs, marker="o", capsize=4, lw=2, color=QBFT_C, label="QBFT")
a.errorbar(FAULTS, hc, yerr=hcs, marker="s", capsize=4, lw=2, color=CBBFT_C, label="CB-BFT")
a.axhline(2.0, ls="--", lw=1, color="#8A94A3")
a.set_title("(a) Experiment 1 - identical containers", fontsize=11, fontweight="bold")
a.set_xlabel("Degraded validators"); a.set_ylabel("Mean block interval (s)")
a.set_xticks(FAULTS); a.set_ylim(1.8, 4.6); a.grid(alpha=0.3); a.legend()

b = ax[0][1]
b.errorbar(FAULTS, tq, yerr=tqs, marker="o", capsize=4, lw=2, color=QBFT_C, label="QBFT")
b.errorbar(FAULTS, tc, yerr=tcs, marker="s", capsize=4, lw=2, color=CBBFT_C, label="CB-BFT")
b.axhline(2.0, ls="--", lw=1, color="#8A94A3")
b.set_title("(b) Experiment 2 - heterogeneous CPU tiers", fontsize=11, fontweight="bold")
b.set_xlabel("Degraded validators"); b.set_ylabel("Mean block interval (s)")
b.set_xticks(FAULTS); b.set_ylim(1.8, 4.6); b.grid(alpha=0.3); b.legend()

c = ax[1][0]
w = 0.35; x = np.arange(len(FAULTS))
c.bar(x - w/2, adv_h, w, color="#2A6DA8", label="identical")
c.bar(x + w/2, adv_t, w, color="#7FB2D9", label="tiered")
for i, (u, v) in enumerate(zip(adv_h, adv_t)):
    c.text(i - w/2, max(u,0) + 0.9, "%.1f" % u, ha="center", fontsize=9, fontweight="bold")
    c.text(i + w/2, max(v,0) + 0.9, "%.1f" % v, ha="center", fontsize=9, fontweight="bold")
c.set_xticks(x); c.set_xticklabels(FAULTS)
c.set_xlabel("Degraded validators")
c.set_ylabel("CB-BFT block interval advantage (%)")
c.set_title("(c) The advantage replicates across both setups", fontsize=11, fontweight="bold")
c.set_ylim(min(0, min(adv_h.min(), adv_t.min()) * 1.6), 44)
c.grid(axis="y", alpha=0.3); c.legend()

d = ax[1][1]
d.plot(FAULTS, hqt/150.0, marker="o", lw=2, color=QBFT_C, label="QBFT, identical")
d.plot(FAULTS, tqt/150.0, marker="o", lw=2, ls="--", color=QBFT_C, alpha=0.6, label="QBFT, tiered")
d.plot(FAULTS, hct/150.0, marker="s", lw=2, color=CBBFT_C, label="CB-BFT, identical")
d.plot(FAULTS, tct/150.0, marker="s", lw=2, ls="--", color=CBBFT_C, alpha=0.6, label="CB-BFT, tiered")
d.axhline(5.0, ls=":", lw=1, color="#8A94A3")
d.text(0.05, 4.93, "offered load 5 tx/s", fontsize=8.5, color="#6B7688")
d.set_xlabel("Degraded validators"); d.set_ylabel("Confirmed throughput (tx/s)")
d.set_title("(d) QBFT sheds load; CB-BFT does not", fontsize=11, fontweight="bold")
d.set_xticks(FAULTS); d.grid(alpha=0.3); d.legend(fontsize=8.5)

plt.tight_layout(rect=[0, 0, 1, 0.93])
plt.savefig("fig_combined.png", dpi=200, bbox_inches="tight")
plt.savefig("fig_combined.pdf", bbox_inches="tight")

with open("combined_table.csv", "w", newline="") as fh:
    w2 = csv.writer(fh)
    w2.writerow(["faults","homo_qbft_mean","homo_qbft_sd","homo_cbbft_mean","homo_cbbft_sd",
                 "homo_advantage_pct","tier_qbft_mean","tier_qbft_sd","tier_cbbft_mean",
                 "tier_cbbft_sd","tier_advantage_pct"])
    for i, f in enumerate(FAULTS):
        w2.writerow([f, "%.3f" % hq[i], "%.3f" % hqs[i], "%.3f" % hc[i], "%.3f" % hcs[i],
                     "%.1f" % adv_h[i], "%.3f" % tq[i], "%.3f" % tqs[i], "%.3f" % tc[i],
                     "%.3f" % tcs[i], "%.1f" % adv_t[i]])

print("wrote fig_combined.png/.pdf and combined_table.csv\n")
for i, f in enumerate(FAULTS):
    print("faults %d  identical %4.1f%%   tiered %4.1f%%" % (f, adv_h[i], adv_t[i]))
