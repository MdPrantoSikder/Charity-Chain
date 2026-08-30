"""Extract CB-BFT trade-offs from the raw experiment output."""
import csv, glob, os, collections
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = "../results"
QBFT_C, CBBFT_C, INK = "#B0446A", "#1E7F63", "#1F2733"
FAULTS = [0, 1, 2, 3]

def proposers(path):
    out = []
    with open(path) as fh:
        for row in csv.DictReader(fh):
            p = (row.get("proposer") or "").strip().strip('"')
            if p.startswith("0x"):
                out.append(p)
    return out[30:]

def gini(counts):
    x = np.sort(np.array(counts, dtype=float))
    n = len(x)
    if n == 0 or x.sum() == 0:
        return 0.0
    idx = np.arange(1, n + 1)
    return float((2 * idx - n - 1).dot(x) / (n * x.sum()))

def per_run(arm, faults):
    """One Counter per repetition - addresses differ between runs, so never pool them."""
    out = []
    for d in sorted(glob.glob("%s/%s-15n-cmp%df-r*" % (RESULTS, arm, faults))):
        f = os.path.join(d, "blocks.csv")
        if os.path.exists(f):
            c = collections.Counter(proposers(f))
            if c:
                out.append(c)
    return out

def collect(arm, faults):
    runs = per_run(arm, faults)
    return runs[0] if runs else collections.Counter()

def carriers(t):
    v = sorted(t.values(), reverse=True)
    tot = sum(v)
    if tot == 0:
        return 0
    run = 0
    for i, x_ in enumerate(v, 1):
        run += x_
        if run >= 0.9 * tot:
            return i
    return len(v)

gq = [float(np.mean([gini(list(c.values())) for c in per_run("qbft", f)] or [0])) for f in FAULTS]
gc = [float(np.mean([gini(list(c.values())) for c in per_run("cbbft", f)] or [0])) for f in FAULTS]
cq = [float(np.mean([carriers(c) for c in per_run("qbft", f)] or [0])) for f in FAULTS]
cc = [float(np.mean([carriers(c) for c in per_run("cbbft", f)] or [0])) for f in FAULTS]
dist_q, dist_c = collect("qbft", 0), collect("cbbft", 0)

fig, ax = plt.subplots(1, 3, figsize=(15, 4.6))
fig.suptitle("CB-BFT trade-offs - proposal concentration is the cost of merit-weighted selection",
             fontsize=12.5, fontweight="bold", color=INK)

a = ax[0]
vq = sorted(dist_q.values(), reverse=True)
vc = sorted(dist_c.values(), reverse=True)
n = max(len(vq), len(vc), 1)
vq += [0] * (n - len(vq)); vc += [0] * (n - len(vc))
x = np.arange(n); w = 0.4
a.bar(x - w/2, vq, w, color=QBFT_C, label="QBFT")
a.bar(x + w/2, vc, w, color=CBBFT_C, label="CB-BFT")
a.set_xlabel("Validator (ranked by proposals)")
a.set_ylabel("Blocks proposed, one representative run")
a.set_title("(a) Proposal distribution, no faults", fontsize=11, fontweight="bold")
a.grid(axis="y", alpha=0.3); a.legend()

b = ax[1]
b.plot(FAULTS, gq, marker="o", lw=2, color=QBFT_C, label="QBFT")
b.plot(FAULTS, gc, marker="s", lw=2, color=CBBFT_C, label="CB-BFT")
b.set_xlabel("Degraded validators"); b.set_ylabel("Gini coefficient of proposals")
b.set_title("(b) Concentration cost", fontsize=11, fontweight="bold")
b.set_xticks(FAULTS); b.set_ylim(0, max(max(gc), max(gq), 0.1) * 1.3)
b.grid(alpha=0.3); b.legend()

c = ax[2]
x2 = np.arange(len(FAULTS))
c.bar(x2 - w/2, cq, w, color=QBFT_C, label="QBFT")
c.bar(x2 + w/2, cc, w, color=CBBFT_C, label="CB-BFT")
c.set_xticks(x2); c.set_xticklabels(FAULTS)
c.set_xlabel("Degraded validators")
c.set_ylabel("Validators producing 90% of blocks")
c.set_title("(c) Effective proposer set size", fontsize=11, fontweight="bold")
c.grid(axis="y", alpha=0.3); c.legend()

plt.tight_layout(rect=[0, 0, 1, 0.93])
plt.savefig("fig_tradeoffs.png", dpi=200, bbox_inches="tight")
plt.savefig("fig_tradeoffs.pdf", bbox_inches="tight")

with open("tradeoff_table.csv", "w", newline="") as fh:
    w2 = csv.writer(fh)
    w2.writerow(["faults","qbft_gini","cbbft_gini","qbft_validators_for_90pct","cbbft_validators_for_90pct"])
    for i, f in enumerate(FAULTS):
        w2.writerow([f, "%.3f" % gq[i], "%.3f" % gc[i], "%.1f" % cq[i], "%.1f" % cc[i]])

print("wrote fig_tradeoffs.png/.pdf and tradeoff_table.csv\n")
print("%-8s %-12s %-12s %-16s %s" % ("faults","QBFT Gini","CB-BFT Gini","QBFT 90% set","CB-BFT 90% set"))
for i, f in enumerate(FAULTS):
    print("%-8d %-12.3f %-12.3f %-16.1f %.1f" % (f, gq[i], gc[i], cq[i], cc[i]))
