"""Abilities + burst-combo modelling using unite-db move ratios (validated vs Game8).

Each move slot has a base form (Lv1-3), Lv5/7 upgrade options, and Lv11/13 enhanced forms.
`move_form` picks the right form for a Pokemon level (best upgrade once unlocked). Per
component: damage = (base + slider*(level-1) + ratio*stat) * hits, mitigated by Def/Sp.Def
(after penetration); execute components add true damage as a % of the target's HP.

So this models the FULL kit at any level, not just pre-evo. Data: data/moves.json (parsed
from unite-db; see parse_unitedb_moves.py).
"""
from __future__ import annotations

import json
import math
import os

import damage
from builds import Build, load_data, tier_build

MOVES_PATH = os.path.join(os.path.dirname(__file__), os.pardir, "data", "moves.json")
OFFENSIVE_ROLES = {"Attacker", "Speedster", "All-Rounder"}


def load_moves() -> dict:
    """Load data/moves.json (the parsed full move kit keyed by Pokemon)."""
    with open(MOVES_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _stat_mit(attacker: Build, defender: Build, dmg_type: str):
    """(attacker offensive stat, defender mitigating defense) for a component's damage type:
    Sp.Atk vs Sp.Def for 'SpAtk', else Attack vs Defense."""
    if dmg_type == "SpAtk":
        return attacker.total.sp_atk, defender.total.sp_def
    return attacker.total.attack, defender.total.defense


def move_form(slot: dict, level: int) -> dict:
    """The active form {name, cooldown, components, execute} of a move slot at `level`:
    base pre-upgrade, then the highest-damage unlocked upgrade (enhanced once unlocked)."""
    avail = [u for u in slot["upgrades"] if level >= u["min_level"]]
    if not avail:
        return {"name": slot["display_name"], **slot["base"]}

    def form_of(u):
        if u["enhanced"] and level >= u["enh_level"]:
            f = u["enhanced"]
            return {"name": u["name"] + "+", "cooldown": f["cooldown"],
                    "components": f["components"], "execute": f["execute"]}
        return {"name": u["name"], "cooldown": u["cooldown"],
                "components": u["components"], "execute": u["execute"]}

    def nominal(f):  # pick the better upgrade with a stand-in stat
        return sum((c["base"] + c["slider"] * (level - 1) + c["ratio"] * 1200) * c["hits"]
                   for c in f["components"])

    return max((form_of(u) for u in avail), key=nominal)


def execute_damage(execs, max_hp, current_hp) -> float:
    """True-damage execute total: each component is a % of the target's missing, current, or
    max HP (e.g. a 'deals 8% of missing HP' finisher). Ignores defense (true damage)."""
    total = 0.0
    for e in execs:
        if e["of"] == "missing":
            total += e["pct"] * max(0.0, max_hp - current_hp)
        elif e["of"] in ("remaining", "current"):
            total += e["pct"] * current_hp
        elif e["of"] == "max":
            total += e["pct"] * max_hp
    return total


def form_damage(attacker, defender, form, level, x_attack=False, current_hp=None) -> float:
    """Total damage of one cast of `form` (sums components × hits, + execute true damage)."""
    mult = damage.X_ATTACK_MOVE_MULT if x_attack else 1.0
    pen = attacker.total.penetration
    total = 0.0
    for c in form["components"]:
        stat, mit = _stat_mit(attacker, defender, c["dmg_type"])
        total += damage.move_damage(stat, level, c["ratio"], c["slider"], c["base"], mit,
                                    mult=mult, penetration=pen) * c["hits"]
    if attacker.move_flat and form["components"]:        # Choice Specs flat, once
        _, mit = _stat_mit(attacker, defender, form["components"][0]["dmg_type"])
        total += math.floor(attacker.move_flat * mult * damage.mitigation_multiplier(mit, pen))
    if current_hp is not None and form["execute"]:
        total += execute_damage(form["execute"], defender.total.hp, current_hp)
    return total


def auto_damage(attacker, defender, pmoves, current_hp, x_attack=False) -> float:
    """One basic attack's damage, using the Pokemon's basic-attack stat/ratio (Atk or Sp.Atk),
    including crit, Muscle Band, penetration, and the optional X Attack basic multiplier."""
    b = pmoves.get("basic") or {"dmg_type": "Atk", "ratio": 1.0}
    stat, mit = _stat_mit(attacker, defender, b["dmg_type"])
    dmg = damage.basic_hit_damage(
        stat, mit, target_current_hp=current_hp, basic_multiplier=b.get("ratio", 1.0),
        crit_rate=attacker.crit_rate, crit_multiplier=attacker.crit_multiplier,
        muscle_band=attacker.muscle_band, penetration=attacker.total.penetration,
    )
    return dmg * (damage.X_ATTACK_BASIC_MULT if x_attack else 1.0)


def damaging_slots(pmoves, include_unite=False) -> dict:
    """The move slots that deal damage (any form has components), optionally including the
    Unite move. Skips pure-utility moves so the burst/DPS loops only see damage abilities."""
    out = {}
    for k, m in pmoves.get("moves", {}).items():
        if m["is_unite"] and not include_unite:
            continue
        if m["base"]["components"] or any(u["components"] for u in m["upgrades"]):
            out[k] = m
    return out


MOVE_CAST_S = 0.8   # nominal animation/cast time per move (approx)


def burst_combo(attacker, defender, pmoves, level, x_attack=True, include_unite=False, max_autos=60):
    """Cast each kit move once (best form for the level), then auto until the target dies.
    Returns actions, autos, and an approximate seconds-to-KO (move casts + auto intervals)."""
    hp = defender.total.hp
    log = []
    moves_cast = 0
    for slot in damaging_slots(pmoves, include_unite).values():
        form = move_form(slot, level)
        d = form_damage(attacker, defender, form, level, x_attack, current_hp=hp)
        hp -= d
        moves_cast += 1
        log.append((form["name"], round(d)))
        if hp <= 0:
            break
    autos = 0
    while hp > 0 and autos < max_autos:
        autos += 1
        d = auto_damage(attacker, defender, pmoves, hp, x_attack)
        hp -= d
        log.append(("auto", round(d)))
    seconds = moves_cast * MOVE_CAST_S + autos * damage.attack_interval_seconds(attacker.total.attack_speed)
    return dict(actions=len(log), autos=autos, knocked_out=hp <= 0, seconds=round(seconds, 1), log=log)


def maxed_tier_for(data, key):
    """The matching maxed INVESTMENT_TIER for a Pokemon — special vs physical by damage_type."""
    return "maxed_special" if data["pokemon"][key].get("damage_type") == "Special" else "maxed_attacker"


def _fmt(log):
    return " -> ".join(f"{n}:{d}" for n, d in log)


def main():
    data = load_data()
    moves = load_moves()
    target_key = "cinderace"

    for level, label in [(4, "PRE-evo"), (9, "POST-evo (upgrades online)")]:
        target = tier_build(data, target_key, level, "uninvested")
        print(f"\n===== Burst @ Lv{level} ({label}) vs un-invested {target_key.title()} "
              f"(HP {target.total.hp:.0f}) =====")
        for k in ("cinderace", "buzzwole", "pikachu"):
            bare = tier_build(data, k, level, "uninvested")
            maxed = tier_build(data, k, level, maxed_tier_for(data, k))
            rb = burst_combo(bare, target, moves[k], level, x_attack=False)
            rm = burst_combo(maxed, target, moves[k], level, x_attack=True)
            print(f"{data['pokemon'][k]['display_name']:11}: un-invested {rb['actions']:2d} | "
                  f"MAXED {rm['actions']:2d}   ({_fmt(rm['log'][:3])} ...)")


if __name__ == "__main__":
    main()
