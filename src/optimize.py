"""Phase 2 — best build & best Pokemon per role.

For each Pokemon we brute-force its legal 3-item combos x a few stat-targeted emblem
templates (a maxed account: Lv40 items + gold emblems + X Attack), pick the build that
maximises the metric, then rank Pokemon within each role.

Metrics (per your call):
  * Offensive roles (Attacker/Speedster/All-Rounder): BURST and sustained DPS, reported
    separately.
  * Defenders/Supporters: SURVIVABILITY = effective HP (raw damage needed to drop them).

Modelled at Lv5 (pre-evolution): unite-db gives the base-move ratios (the pre-evo kit) and
item levels are account-wide, so a maxed account already has Lv40 items at Lv5. This is the
window where the data is fully faithful (Lv5/7 upgrade moves aren't in unite-db). Results are
"best by modelled combat metric" -- they ignore range, mobility, CC, and objective control.
"""
from __future__ import annotations

import csv
import itertools
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import damage
from abilities import auto_damage, base_moves, load_moves, move_damage
from builds import BULK_POOL, PHYSICAL_POOL, SPECIAL_POOL, load_data, make_build, tier_build

LEVEL = 5
TARGET_KEY = "cinderace"          # un-invested squishy reference
BURST_WINDOW_S = 2.0              # autos that land during the opening burst
DATA_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "data")
FIG_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "figures")

OFFENSIVE = {"Attacker", "Speedster", "All-Rounder"}
DEFENSIVE = {"Defender", "Supporter"}


def item_pool(dtype):
    return SPECIAL_POOL if dtype == "Special" else PHYSICAL_POOL


def emblem_templates(dtype):
    return ["max_sp_atk"] if dtype == "Special" else ["max_attack", "max_attack_speed"]


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def sustained_dps(attacker, defender, pmoves, level) -> float:
    """Auto-attack DPS + sum(move damage / cooldown) over the base (pre-evo) kit."""
    aps = damage.attacks_per_second(attacker.total.attack_speed)
    auto = auto_damage(attacker, defender, pmoves, defender.total.hp, x_attack=False)
    dps = auto * aps
    for mv in base_moves(pmoves).values():
        cd = float(mv.get("cooldown") or 0)
        if cd > 0:
            dps += move_damage(attacker, defender, mv, level) / cd
    return dps


def burst_damage(attacker, defender, pmoves, level) -> float:
    """All base moves once (with X Attack) + autos landing in the opening window."""
    total = sum(move_damage(attacker, defender, mv, level, x_attack=True)
                for mv in base_moves(pmoves).values())
    n_autos = max(1, int(BURST_WINDOW_S * damage.attacks_per_second(attacker.total.attack_speed)))
    for _ in range(n_autos):
        total += auto_damage(attacker, defender, pmoves, defender.total.hp, x_attack=True)
    return total


def survivability(build) -> dict:
    phys = damage.effective_hp(build.total.hp, build.total.defense)
    spec = damage.effective_hp(build.total.hp, build.total.sp_def)
    return {"ehp_phys": phys, "ehp_spec": spec, "ehp_avg": (phys + spec) / 2}


# --------------------------------------------------------------------------- #
# Optimisation
# --------------------------------------------------------------------------- #
def best_offensive_build(data, moves, key, target, metric: str) -> dict:
    dtype = data["pokemon"][key].get("damage_type")
    scorer = burst_damage if metric == "burst" else sustained_dps
    best = None
    for items in itertools.combinations(item_pool(dtype), 3):
        for emb in emblem_templates(dtype):
            atk = make_build(data, key, LEVEL, list(items), emb)
            score = scorer(atk, target, moves[key], LEVEL)
            if best is None or score > best["score"]:
                best = {"score": score, "items": list(items), "emblems": emb}
    return best


def rank_offensive(data, moves, target):
    rows = []
    for key, p in data["pokemon"].items():
        if key.startswith("_") or p.get("role") not in OFFENSIVE or key not in moves:
            continue
        if not base_moves(moves[key]):
            continue
        burst = best_offensive_build(data, moves, key, target, "burst")
        dps = best_offensive_build(data, moves, key, target, "dps")
        rows.append({
            "pokemon": p["display_name"], "role": p["role"], "dmg_type": p.get("damage_type"),
            "burst": round(burst["score"]), "burst_build": "+".join(burst["items"]) + " / " + burst["emblems"],
            "dps": round(dps["score"]), "dps_build": "+".join(dps["items"]) + " / " + dps["emblems"],
        })
    return rows


def best_bulk_build(data, key) -> dict:
    best = None
    for items in itertools.combinations(BULK_POOL, 3):
        s = survivability(make_build(data, key, LEVEL, list(items), "max_bulk"))
        if best is None or s["ehp_avg"] > best["surv"]["ehp_avg"]:
            best = {"items": list(items), "surv": s}
    return best


def rank_defensive(data):
    rows = []
    for key, p in data["pokemon"].items():
        if key.startswith("_") or p.get("role") not in DEFENSIVE:
            continue
        b = best_bulk_build(data, key)
        s = b["surv"]
        rows.append({"pokemon": p["display_name"], "role": p["role"],
                     "ehp_phys": round(s["ehp_phys"]), "ehp_spec": round(s["ehp_spec"]),
                     "ehp_avg": round(s["ehp_avg"]), "build": "+".join(b["items"])})
    return rows


def _table(rows, cols, widths):
    print("  " + "".join(f"{c:<{w}}" for c, w in zip(cols, widths)))
    for r in rows:
        print("  " + "".join(f"{str(r[c]):<{w}}" for c, w in zip(cols, widths)))


def _barh(ax, rows, val_key, color):
    rows = rows[::-1]  # highest at top
    ax.barh([r["pokemon"] for r in rows], [r[val_key] for r in rows], color=color)
    ax.tick_params(labelsize=8)
    vmax = max((r[val_key] for r in rows), default=1)
    for i, r in enumerate(rows):
        ax.text(r[val_key] + vmax * 0.01, i, f"{r[val_key]:,}", va="center", fontsize=7)
    ax.margins(x=0.18)


def make_charts(off, deff):
    os.makedirs(FIG_DIR, exist_ok=True)
    roles = ["Attacker", "Speedster", "All-Rounder"]
    paths = []
    for metric, color, fname, title in [
        ("burst", "#d62728", "phase2_burst.png", "pre-evo BURST damage"),
        ("dps", "#1f77b4", "phase2_dps.png", "sustained DPS"),
    ]:
        fig, axes = plt.subplots(1, 3, figsize=(14, 4))
        for ax, role in zip(axes, roles):
            rr = sorted((r for r in off if r["role"] == role), key=lambda r: -r[metric])[:6]
            _barh(ax, rr, metric, color)
            ax.set_title(role, fontsize=10)
        fig.suptitle(f"Phase 2 — top {title} by role (Lv5 pre-evo, optimal maxed build)", fontsize=12)
        fig.tight_layout()
        p = os.path.join(FIG_DIR, fname)
        fig.savefig(p, dpi=130)
        plt.close(fig)
        paths.append(p)

    fig, ax = plt.subplots(figsize=(8, 5))
    _barh(ax, sorted(deff, key=lambda r: -r["ehp_avg"])[:10], "ehp_avg", "#2ca02c")
    ax.set_title("Phase 2 — Defender/Supporter survivability (effective HP, best bulk build)", fontsize=11)
    fig.tight_layout()
    p = os.path.join(FIG_DIR, "phase2_survivability.png")
    fig.savefig(p, dpi=130)
    plt.close(fig)
    paths.append(p)
    return paths


EMBLEM_NAMES = {"max_attack": "Attack emblems", "max_attack_speed": "Atk-Speed emblems",
                "max_sp_atk": "Sp.Atk emblems", "max_bulk": "Bulk emblems", "none": "no emblems"}
ROLE_COLORS = {"Attacker": "#d62728", "Speedster": "#9467bd", "All-Rounder": "#ff7f0e",
               "Defender": "#1f77b4", "Supporter": "#2ca02c"}


def _pretty_items(items_str, data):
    return " + ".join(data["items"][k]["display_name"] for k in items_str.split("+"))


def _pretty_build(build_str, data):
    items_part, emb = build_str.split(" / ")
    return f"{_pretty_items(items_part, data)}  ·  {EMBLEM_NAMES.get(emb, emb)}"


def best_per_role(off, deff, data):
    rows = []
    for role in ("Attacker", "Speedster", "All-Rounder"):
        rr = [r for r in off if r["role"] == role]
        if not rr:
            continue
        b = max(rr, key=lambda r: r["burst"])
        d = max(rr, key=lambda r: r["dps"])
        rows.append({"role": role, "metric": "Burst", "pokemon": b["pokemon"],
                     "score": f"{b['burst']:,}", "build": _pretty_build(b["burst_build"], data)})
        rows.append({"role": role, "metric": "DPS", "pokemon": d["pokemon"],
                     "score": f"{d['dps']:,}", "build": _pretty_build(d["dps_build"], data)})
    for role in ("Defender", "Supporter"):
        rr = [r for r in deff if r["role"] == role]
        if rr:
            t = max(rr, key=lambda r: r["ehp_avg"])
            rows.append({"role": role, "metric": "Eff. HP", "pokemon": t["pokemon"],
                         "score": f"{t['ehp_avg']:,}", "build": f"{_pretty_items(t['build'], data)}  ·  Bulk emblems"})
    return rows


def make_summary_chart(rows):
    os.makedirs(FIG_DIR, exist_ok=True)
    cols = ["Role", "Best by", "Pokémon", "Score", "Optimal build"]
    widths = [0.13, 0.09, 0.15, 0.08, 0.55]
    cells = [[r["role"], r["metric"], r["pokemon"], r["score"], r["build"]] for r in rows]
    fig, ax = plt.subplots(figsize=(13, 0.46 * (len(rows) + 1) + 0.6))
    ax.axis("off")
    tbl = ax.table(cellText=cells, colLabels=cols, colWidths=widths, cellLoc="left",
                   bbox=[0, 0, 1, 1])
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    for j in range(len(cols)):
        h = tbl[0, j]
        h.set_facecolor("#222222")
        h.set_text_props(color="white", fontweight="bold")
    for i, r in enumerate(rows, start=1):
        base = ROLE_COLORS[r["role"]]
        for j in range(len(cols)):
            c = tbl[i, j]
            c.set_edgecolor("white")
            if j == 0:
                c.set_facecolor(base + "dd")
                c.set_text_props(color="white", fontweight="bold")
            else:
                c.set_facecolor(base + "16")
        tbl[i, 2].set_text_props(fontweight="bold")
    ax.set_title("Best Pokémon & build per role — Lv5 pre-evo, maxed account "
                 "(Lv40 items + gold emblems + X Attack)", fontsize=12, pad=14)
    fig.tight_layout()
    p = os.path.join(FIG_DIR, "best_per_role.png")
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return p


def main():
    data = load_data()
    moves = load_moves()
    target = tier_build(data, TARGET_KEY, LEVEL, "uninvested")
    print(f"Phase 2 — best build & Pokemon per role @ Lv{LEVEL} (pre-evo), "
          f"vs un-invested {TARGET_KEY.title()} (HP {target.total.hp:.0f}/Def {target.total.defense:.0f})")
    print("Maxed account = Lv40 items + gold emblems + X Attack. 'Best by modelled combat metric.'\n")

    off = rank_offensive(data, moves, target)
    for role in ("Attacker", "Speedster", "All-Rounder"):
        rr = [r for r in off if r["role"] == role]
        print(f"### {role} — top by BURST")
        _table(sorted(rr, key=lambda r: -r["burst"])[:8],
               ["pokemon", "burst", "burst_build"], [14, 8, 40])
        print(f"### {role} — top by DPS")
        _table(sorted(rr, key=lambda r: -r["dps"])[:8],
               ["pokemon", "dps", "dps_build"], [14, 8, 40])
        print()

    deff = rank_defensive(data)
    print("### Defender/Supporter — top by SURVIVABILITY (effective HP, best bulk build)")
    _table(sorted(deff, key=lambda r: -r["ehp_avg"])[:10],
           ["pokemon", "role", "ehp_avg", "build"], [14, 11, 9, 46])

    out = os.path.join(DATA_DIR, "phase2_offense.csv")
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(off[0].keys()))
        w.writeheader()
        w.writerows(off)
    print(f"\nSaved: {out}")
    for p in make_charts(off, deff) + [make_summary_chart(best_per_role(off, deff, data))]:
        print(f"       {p}")


if __name__ == "__main__":
    main()
