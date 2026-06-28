"""#5 — Does the model agree with the meta? Correlate each mon's modeled rating against
unite-db's community tier (tier field, already cached). If the model is capturing something
real, higher-tier mons should have higher modeled ratings.

Model rating = within-role percentile of the role's metric (offense: best of Burst/DPS;
tanks/supports: effective HP). We report Spearman rho overall and per role, and chart the
mean model rating per tier.
"""
from __future__ import annotations

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from abilities import load_moves
from builds import load_data, tier_build
from optimize import FIG_DIR, LEVEL, TARGET_KEY, rank_defensive, rank_offensive

DATA_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "data")
TIER_NUM = {"S": 7, "A+": 6, "A": 5, "B+": 4, "B": 3, "C": 2, "D": 1, "F": 0}
TIER_ORDER = ["F", "D", "C", "B", "B+", "A", "A+", "S"]


def spearman(xs, ys):
    """Spearman rank correlation of two equal-length sequences (0 if either has no variance).
    Self-contained so the project needs no scipy dependency."""
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for pos, i in enumerate(order):
            r[i] = pos
        return r
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sx = sum((a - mx) ** 2 for a in rx) ** 0.5
    sy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (sx * sy) if sx and sy else 0.0


def _pct(vals):
    """Convert values to within-list percentiles 0-100 (smallest -> 0, largest -> 100)."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    out = [50.0] * len(vals)
    for pos, i in enumerate(order):
        out[i] = pos / (len(vals) - 1) * 100 if len(vals) > 1 else 50.0
    return out


def model_ratings():
    """Return list of (pokemon, role, rating 0-100, tier_letter)."""
    data = load_data()
    moves = load_moves()
    target = tier_build(data, TARGET_KEY, LEVEL, "uninvested")
    raw = json.load(open(os.path.join(DATA_DIR, "unite_db_pokemon.json"), encoding="utf-8"))
    tier = {p["name"]: str(p.get("tier")) for p in raw}

    rows = []
    off = rank_offensive(data, moves, target)
    by_role = {}
    for r in off:
        by_role.setdefault(r["role"], []).append(r)
    for role, rr in by_role.items():
        bp, dp = _pct([x["burst"] for x in rr]), _pct([x["dps"] for x in rr])
        for i, x in enumerate(rr):
            rows.append((x["pokemon"], role, max(bp[i], dp[i]), tier.get(x["pokemon"])))

    deff = rank_defensive(data)
    by_role_d = {}
    for r in deff:
        by_role_d.setdefault(r["role"], []).append(r)
    for role, rr in by_role_d.items():
        ep = _pct([x["ehp_avg"] for x in rr])
        for i, x in enumerate(rr):
            rows.append((x["pokemon"], role, ep[i], tier.get(x["pokemon"])))
    return rows


def main():
    rows = model_ratings()
    valid = [(n, role, rating, TIER_NUM[t]) for n, role, rating, t in rows if t in TIER_NUM]
    rho = spearman([r[2] for r in valid], [r[3] for r in valid])
    print(f"Model rating vs unite-db community tier:  Spearman rho = {rho:+.2f}  (n={len(valid)})")
    for role in ("Attacker", "Speedster", "All-Rounder", "Defender", "Supporter"):
        rr = [r for r in valid if r[1] == role]
        if len(rr) > 3:
            print(f"  {role:12}: rho = {spearman([r[2] for r in rr], [r[3] for r in rr]):+.2f}  (n={len(rr)})")

    # chart: mean model rating per tier (should trend up if model agrees with meta)
    means = []
    for t in TIER_ORDER:
        vals = [r[2] for r in rows if r[3] == t]
        means.append(sum(vals) / len(vals) if vals else None)
    fig, ax = plt.subplots(figsize=(9, 5))
    xs = [t for t, m in zip(TIER_ORDER, means) if m is not None]
    ys = [m for m in means if m is not None]
    ax.bar(xs, ys, color="#4c72b0")
    for x, y in zip(xs, ys):
        ax.text(x, y + 1, f"{y:.0f}", ha="center", fontsize=9)
    ax.set_xlabel("unite-db community tier (worst -> best)")
    ax.set_ylabel("mean modeled rating (within-role percentile)")
    ax.set_title(f"Does the model agree with the meta?  Spearman rho = {rho:+.2f}  (higher tier -> higher rating)")
    ax.set_ylim(0, 100)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    p = os.path.join(FIG_DIR, "meta_validation.png")
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"\nSaved: {p}")


if __name__ == "__main__":
    main()
