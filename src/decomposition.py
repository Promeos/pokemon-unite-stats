"""#2 — Which lever actually drives the pre-evo burst, and does emblem rarity matter?

Isolates each investment lever by building the burst up one step at a time
(base -> +items -> +emblems -> +X Attack), averaged across the offensive roster, and sweeps
emblem rarity (none -> bronze -> silver -> gold). Answers the original question.
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import damage
from abilities import (OFFENSIVE_ROLES, auto_damage, damaging_slots, form_damage,
                       load_moves, maxed_tier_for, move_form)
from builds import INVESTMENT_TIERS, load_data, make_build, tier_build

FIG_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "figures")
LEVEL = 4
TARGET_KEY = "cinderace"


def burst(attacker, defender, pmoves, level, x_attack):
    total = sum(form_damage(attacker, defender, move_form(s, level), level, x_attack=x_attack)
                for s in damaging_slots(pmoves).values())
    aps = damage.attacks_per_second(attacker.total.attack_speed)
    for _ in range(max(1, int(2.0 * aps))):
        total += auto_damage(attacker, defender, pmoves, defender.total.hp, x_attack)
    return total


def offensive_mons(data, moves):
    return [k for k, p in data["pokemon"].items()
            if not k.startswith("_") and p.get("role") in OFFENSIVE_ROLES
            and k in moves and damaging_slots(moves[k])]


def main():
    data = load_data()
    moves = load_moves()
    target = tier_build(data, TARGET_KEY, LEVEL, "uninvested")
    mons = offensive_mons(data, moves)
    n = len(mons)

    # ---- lever decomposition (averaged) ----
    acc = {"base": 0.0, "items": 0.0, "emblems": 0.0, "xatk": 0.0}
    for k in mons:
        spec = INVESTMENT_TIERS[maxed_tier_for(data, k)]
        b0 = burst(make_build(data, k, LEVEL), target, moves[k], LEVEL, False)
        bi = burst(make_build(data, k, LEVEL, spec["items"]), target, moves[k], LEVEL, False)
        be = burst(make_build(data, k, LEVEL, spec["items"], spec["emblems"], "gold"), target, moves[k], LEVEL, False)
        bx = burst(make_build(data, k, LEVEL, spec["items"], spec["emblems"], "gold"), target, moves[k], LEVEL, True)
        acc["base"] += b0; acc["items"] += bi - b0; acc["emblems"] += be - bi; acc["xatk"] += bx - be
    for key in acc:
        acc[key] /= n
    total = sum(acc.values())
    inv = total - acc["base"]
    print(f"Avg pre-evo burst decomposition (Lv{LEVEL}, {n} offensive mons):")
    for key in ("base", "items", "emblems", "xatk"):
        print(f"  {key:8}: {acc[key]:7.0f}  ({acc[key] / total * 100:4.1f}% of total)")
    print(f"  -> of the INVESTMENT gain ({inv:.0f} = +{inv/acc['base']*100:.0f}% over base): "
          f"items {acc['items']/inv*100:.0f}%, emblems {acc['emblems']/inv*100:.0f}%, X Attack {acc['xatk']/inv*100:.0f}%")

    # ---- emblem rarity sweep (items on, X Attack off) ----
    rar = {}
    for rarity in ("none", "bronze", "silver", "gold"):
        s = 0.0
        for k in mons:
            spec = INVESTMENT_TIERS[maxed_tier_for(data, k)]
            emb = "none" if rarity == "none" else spec["emblems"]
            s += burst(make_build(data, k, LEVEL, spec["items"], emb,
                                  rarity if rarity != "none" else "gold"), target, moves[k], LEVEL, False)
        rar[rarity] = s / n
    print("\nEmblem rarity sweep (items on, X Attack off):")
    for r in ("none", "bronze", "silver", "gold"):
        print(f"  {r:7}: {rar[r]:7.0f}  (+{(rar[r]/rar['none']-1)*100:.1f}% vs no emblems)")

    # ---- charts ----
    os.makedirs(FIG_DIR, exist_ok=True)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.6))
    segs = [("base", "#999999"), ("items", "#d62728"), ("emblems", "#ff7f0e"), ("xatk", "#9467bd")]
    left = 0.0
    for name, color in segs:
        ax1.barh(["avg burst"], [acc[name]], left=left, color=color,
                 label=f"{name} ({acc[name]/total*100:.0f}%)")
        if acc[name] > total * 0.04:
            ax1.text(left + acc[name] / 2, 0, f"{acc[name]:.0f}", ha="center", va="center", color="white", fontsize=9)
        left += acc[name]
    ax1.set_title(f"Where pre-evo burst comes from (Lv{LEVEL} avg, {n} mons)")
    ax1.set_xlabel("burst damage")
    ax1.legend(fontsize=8, loc="lower right")
    ax1.set_yticks([])

    rs = ["none", "bronze", "silver", "gold"]
    ax2.plot(rs, [rar[r] for r in rs], "o-", color="#ff7f0e")
    for r in rs:
        ax2.text(r, rar[r], f" {rar[r]:.0f}", va="bottom", fontsize=8)
    ax2.set_title("Emblem rarity sweep (items on)")
    ax2.set_ylabel("avg burst damage")
    ax2.grid(alpha=0.3)
    fig.suptitle("Lever decomposition — items dominate, emblems/rarity are a small edge", fontsize=12)
    fig.tight_layout()
    p = os.path.join(FIG_DIR, "lever_decomposition.png")
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print(f"\nSaved: {p}")


if __name__ == "__main__":
    main()
