"""Does the best Defender / Supporter change with level?  (Lv5 chart basis vs Lv15 full build)

`optimize.py` ranks Defenders/Supporters at Lv5, the level chosen for the OFFENSIVE study
because pre-evo move data is the faithful window. But survivability is pure stats (no
moves) and is available at every level — and tanks come online late, after their final
evolution and stat spikes. So Lv5 arguably under-rates them.

This re-ranks the two defensive roles by the SAME survivability metric optimize.py uses for
best_per_role.png (best 3 of BULK_POOL + max_bulk gold emblems + shields up,
optimize.survivability) at Lv15, and visualises how far each Pokemon moves between the two
levels. Reuses optimize.survivability / optimize.shield_pct verbatim, so the only changed
variable is the level. Writes data/defensive_ranking.csv + figures/defensive_ranking.png.
"""
from __future__ import annotations

import csv
import itertools
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from builds import BULK_POOL, load_data, make_build
from optimize import shield_pct, survivability

DATA_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "data")
FIG_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "figures")

LV_BASE, LV_FULL = 5, 15          # current-chart level vs full-build level
ROLES = ("Defender", "Supporter")
RISE_COLOR, FALL_COLOR, FLAT_COLOR = "#2ca02c", "#d62728", "#bbbbbb"
BIG_MOVE = 3                      # |rank change| that counts as a notable mover


def best_bulk_value(data: dict, key: str, level: int) -> float:
    """Best-3-of-BULK_POOL effective HP (avg phys/spec) + shields up, at a given level —
    exactly optimize.best_bulk_build's objective, but with the level parameterised."""
    best = 0.0
    for items in itertools.combinations(BULK_POOL, 3):
        b = make_build(data, key, level, list(items), "max_bulk")
        val = survivability(b)["ehp_avg"] + shield_pct(data, items) * b.total.hp
        best = max(best, val)
    return best


def rank(data: dict, level: int, role: str) -> list[tuple[str, int]]:
    """(display_name, value) for every Pokemon of `role`, best-first, at `level`."""
    rows = [(p["display_name"], round(best_bulk_value(data, key, level)))
            for key, p in data["pokemon"].items()
            if not key.startswith("_") and p.get("role") == role]
    rows.sort(key=lambda r: -r[1])
    return rows


def merged_rows(data: dict) -> list[dict]:
    """One row per defensive Pokemon: value + rank at both levels, and the rank change."""
    out = []
    for role in ROLES:
        r_base, r_full = rank(data, LV_BASE, role), rank(data, LV_FULL, role)
        rank_base = {n: i + 1 for i, (n, _) in enumerate(r_base)}
        val_base = dict(r_base)
        for i, (name, val_full) in enumerate(r_full):
            out.append({
                "role": role, "pokemon": name,
                f"ehp_lv{LV_BASE}": val_base[name], f"rank_lv{LV_BASE}": rank_base[name],
                f"ehp_lv{LV_FULL}": val_full, f"rank_lv{LV_FULL}": i + 1,
                "rank_change": rank_base[name] - (i + 1),   # +ve = rose at Lv15
            })
    return out


def _slope_panel(ax, r_base, r_full, title: str) -> None:
    rank_base = {n: i + 1 for i, (n, _) in enumerate(r_base)}
    rank_full = {n: i + 1 for i, (n, _) in enumerate(r_full)}
    val_full = dict(r_full)
    n = len(r_base)
    for name in rank_base:
        yb, yf = rank_base[name], rank_full[name]
        move = yb - yf  # +ve = climbed
        color = RISE_COLOR if move >= BIG_MOVE else FALL_COLOR if move <= -BIG_MOVE else FLAT_COLOR
        lw, z = (2.4, 3) if abs(move) >= BIG_MOVE else (1.1, 1)
        ax.plot([0, 1], [yb, yf], "-o", color=color, lw=lw, ms=5, zorder=z)
        ax.text(-0.03, yb, f"{yb}. {name}", ha="right", va="center", fontsize=8)
        bold = "bold" if abs(move) >= BIG_MOVE else "normal"
        ax.text(1.03, yf, f"{name}  ({val_full[name]:,})", ha="left", va="center",
                fontsize=8, fontweight=bold)
    ax.set_xlim(-0.62, 1.78)
    ax.set_ylim(n + 0.6, 0.4)  # invert so rank 1 is on top
    ax.set_xticks([0, 1])
    ax.set_xticklabels([f"Lv{LV_BASE}\n(chart basis)", f"Lv{LV_FULL}\n(full build)"], fontsize=9)
    ax.set_yticks([])
    ax.set_title(title, fontsize=11)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)


def make_chart(data: dict) -> str:
    os.makedirs(FIG_DIR, exist_ok=True)
    fig, axes = plt.subplots(1, len(ROLES), figsize=(14, 7.6))
    for ax, role in zip(axes, ROLES):
        _slope_panel(ax, rank(data, LV_BASE, role), rank(data, LV_FULL, role),
                     f"{role}s — survivability rank")
    handles = [Line2D([], [], color=RISE_COLOR, marker="o", label=f"climbs ≥{BIG_MOVE}"),
               Line2D([], [], color=FALL_COLOR, marker="o", label=f"falls ≥{BIG_MOVE}"),
               Line2D([], [], color=FLAT_COLOR, marker="o", label="±small")]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=9, frameon=False)
    fig.suptitle("Best Defender / Supporter flips by level — survivability (best bulk build + shields)\n"
                 "same metric as best_per_role.png; only the level changes (Lv5 pre-evo → Lv15 full build)",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    path = os.path.join(FIG_DIR, "defensive_ranking.png")
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


def main() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure:
        reconfigure(encoding="utf-8")
    data = load_data()

    print(f"Best-by-survivability per defensive role — Lv{LV_BASE} (best_per_role.png basis) "
          f"vs Lv{LV_FULL} (full build)\n")
    for role in ROLES:
        r_base, r_full = rank(data, LV_BASE, role), rank(data, LV_FULL, role)
        rank_base = {n: i + 1 for i, (n, _) in enumerate(r_base)}
        print(f"### {role}:  best @ Lv{LV_BASE} = {r_base[0][0]}   ->   best @ Lv{LV_FULL} = {r_full[0][0]}")
        for i, (name, val) in enumerate(r_full[:5]):
            moved = rank_base[name] - (i + 1)
            tag = f"  (was #{rank_base[name]} @ Lv{LV_BASE}, {'+' if moved >= 0 else ''}{moved})" if moved else "  (unchanged)"
            print(f"   Lv{LV_FULL} #{i + 1}: {name:<14} {val:>7,}{tag}")
        print()

    rows = merged_rows(data)
    out = os.path.join(DATA_DIR, "defensive_ranking.csv")
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    chart = make_chart(data)
    print(f"Saved: {out}\n       {chart}")


if __name__ == "__main__":
    main()
