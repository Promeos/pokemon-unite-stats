"""Abilities + burst-combo modelling using unite-db move ratios (validated).

Per-component move damage = base + slider*(level-1) + ratio*stat, mitigated by the
target's Def (Atk moves) or Sp.Def (SpAtk moves); multi-hit moves sum their components.
Data: data/moves.json (roster-wide, parsed from unite-db; see parse_unitedb_moves.py).
A "pre-evo burst" uses a mon's BASE (non-Unite) moves -- its kit before first evolution.

Validated: Pikachu Thunder Shock 0.75*SpAtk + 21*(Lv-1) + 390 reproduces the reference
engine exactly, so these ratios are trustworthy for every listed move.
"""
from __future__ import annotations

import json
import os

import damage
from builds import Build, load_data, tier_build

MOVES_PATH = os.path.join(os.path.dirname(__file__), os.pardir, "data", "moves.json")
OFFENSIVE_ROLES = {"Attacker", "Speedster", "All-Rounder"}


def load_moves() -> dict:
    with open(MOVES_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _stat_mit(attacker: Build, defender: Build, dmg_type: str):
    if dmg_type == "SpAtk":
        return attacker.total.sp_atk, defender.total.sp_def
    return attacker.total.attack, defender.total.defense


def move_damage(attacker: Build, defender: Build, move: dict, level: int, x_attack: bool = False) -> float:
    mult = damage.X_ATTACK_MOVE_MULT if x_attack else 1.0
    total = 0.0
    for c in move["components"]:
        stat, mit = _stat_mit(attacker, defender, c["dmg_type"])
        total += damage.move_damage(stat, level, c["ratio"], c["slider"], c["base"], mit, mult=mult)
    return total


def auto_damage(attacker: Build, defender: Build, pmoves: dict, current_hp: float, x_attack: bool = False) -> float:
    b = pmoves.get("basic") or {"dmg_type": "Atk", "ratio": 1.0}
    stat, mit = _stat_mit(attacker, defender, b["dmg_type"])
    dmg = damage.basic_hit_damage(
        stat, mit, target_current_hp=current_hp, basic_multiplier=b.get("ratio", 1.0),
        crit_rate=attacker.crit_rate, crit_multiplier=attacker.crit_multiplier,
        muscle_band=attacker.muscle_band,
    )
    return dmg * (damage.X_ATTACK_BASIC_MULT if x_attack else 1.0)


def base_moves(pmoves: dict) -> dict:
    return {k: m for k, m in pmoves.get("moves", {}).items() if not m.get("is_unite")}


def burst_combo(attacker: Build, defender: Build, pmoves: dict, level: int,
                x_attack: bool = True, max_autos: int = 60) -> dict:
    """Cast the mon's base (pre-evo) moves once each, then auto until the target dies."""
    hp = defender.total.hp
    log = []
    for mv in base_moves(pmoves).values():
        d = move_damage(attacker, defender, mv, level, x_attack)
        hp -= d
        log.append((mv["display_name"], round(d)))
        if hp <= 0:
            break
    autos = 0
    while hp > 0 and autos < max_autos:
        autos += 1
        d = auto_damage(attacker, defender, pmoves, hp, x_attack)
        hp -= d
        log.append(("auto", round(d)))
    return dict(actions=len(log), autos=autos, killed=hp <= 0, log=log)


def maxed_tier_for(data: dict, key: str) -> str:
    return "maxed_special" if data["pokemon"][key].get("damage_type") == "Special" else "maxed_attacker"


def _fmt(log):
    return " -> ".join(f"{n}:{d}" for n, d in log)


def main():
    data = load_data()
    moves = load_moves()
    level = 4               # solidly pre-evolution (both base moves available)
    target_key = "cinderace"  # un-invested squishy reference

    # --- showcase a few real pre-evo bursts ---
    print(f"Pre-evo burst @ Lv{level} vs un-invested {target_key.title()} "
          f"(maxed = role items+emblems + X Attack):\n")
    target = tier_build(data, target_key, level, "uninvested")
    show = ["cinderace", "zeraora", "buzzwole", "pikachu"]
    for k in show:
        if k not in moves or k not in data["pokemon"]:
            continue
        bare = tier_build(data, k, level, "uninvested")
        maxed = tier_build(data, k, level, maxed_tier_for(data, k))
        rb = burst_combo(bare, target, moves[k], level, x_attack=False)
        rm = burst_combo(maxed, target, moves[k], level, x_attack=True)
        print(f"{data['pokemon'][k]['display_name']:11} ({data['pokemon'][k]['role']}):")
        print(f"   un-invested: {rb['actions']} actions  | {_fmt(rb['log'])}")
        print(f"   MAXED+XAtk : {rm['actions']} actions  | {_fmt(rm['log'])}\n")

    # --- roster-wide: does maxing cut pre-evo burst actions, regardless of mon? ---
    rows = []
    for k, p in data["pokemon"].items():
        if k.startswith("_") or p.get("role") not in OFFENSIVE_ROLES or k not in moves:
            continue
        if not base_moves(moves[k]):
            continue
        bare = tier_build(data, k, level, "uninvested")
        maxed = tier_build(data, k, level, maxed_tier_for(data, k))
        a0 = burst_combo(bare, target, moves[k], level, x_attack=False)["actions"]
        a1 = burst_combo(maxed, target, moves[k], level, x_attack=True)["actions"]
        rows.append((k, a0, a1))

    import statistics
    saved = [(a0 - a1) / a0 * 100 for _, a0, a1 in rows if a0]
    print("=" * 64)
    print(f"Roster pre-evo burst (Lv{level}, {len(rows)} offensive mons vs un-invested squishy):")
    print(f"  mean actions un-invested: {statistics.mean(a0 for _,a0,_ in rows):.1f}"
          f"  ->  MAXED: {statistics.mean(a1 for _,_,a1 in rows):.1f}")
    print(f"  mean reduction in actions-to-kill: {statistics.mean(saved):.1f}%")
    fastest = sorted(rows, key=lambda r: r[2])[:5]
    print("  fastest MAXED pre-evo deletes:", ", ".join(f"{data['pokemon'][k]['display_name']}({a1})" for k, _, a1 in fastest))


if __name__ == "__main__":
    main()
