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

import damage
from abilities import auto_damage, base_moves, load_moves, move_damage
from builds import PHYSICAL_POOL, SPECIAL_POOL, load_data, make_build, tier_build

LEVEL = 5
TARGET_KEY = "cinderace"          # un-invested squishy reference
BURST_WINDOW_S = 2.0              # autos that land during the opening burst
BULK_ITEMS = ["assault_vest"]     # only defensive item we have data for (flagged)
DATA_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "data")

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


def rank_defensive(data):
    rows = []
    for key, p in data["pokemon"].items():
        if key.startswith("_") or p.get("role") not in DEFENSIVE:
            continue
        build = make_build(data, key, LEVEL, list(BULK_ITEMS), "max_bulk")
        s = survivability(build)
        rows.append({"pokemon": p["display_name"], "role": p["role"],
                     "ehp_phys": round(s["ehp_phys"]), "ehp_spec": round(s["ehp_spec"]),
                     "ehp_avg": round(s["ehp_avg"])})
    return rows


def _table(rows, cols, widths):
    print("  " + "".join(f"{c:<{w}}" for c, w in zip(cols, widths)))
    for r in rows:
        print("  " + "".join(f"{str(r[c]):<{w}}" for c, w in zip(cols, widths)))


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
    print("### Defender/Supporter — top by SURVIVABILITY (effective HP, bulk build)")
    _table(sorted(deff, key=lambda r: -r["ehp_avg"])[:10],
           ["pokemon", "role", "ehp_phys", "ehp_spec", "ehp_avg"], [14, 12, 10, 10, 9])

    out = os.path.join(DATA_DIR, "phase2_offense.csv")
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(off[0].keys()))
        w.writeheader()
        w.writerows(off)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
