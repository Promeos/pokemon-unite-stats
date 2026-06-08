"""Validate our computed move damage against Game8's published move totals.

Game8 lists each move's damage at default build (no items), tested vs a 0-defense dummy —
so its numbers are pre-mitigation, directly comparable to our raw formula output. We compute
the move's MAIN damage (excluding the separate burn DoT and Game8's occasional crit doubling)
and diff it against Game8's reported "initial hit".

This turns "validated on 1 move" into a cross-roster cross-source check.
"""
from __future__ import annotations

from abilities import load_moves, move_form
from builds import load_data
from stats import base_stats

# (pokemon, move-slot, Pokemon level, Game8 main/initial damage, note). Values transcribed
# from Game8's individual move pages (see data/*archive ids). move_form() picks the
# best-unlocked form, so at Lv7 the Ember slot resolves to Pyro Ball, etc.
CASES = [
    ("cinderace", "ember", 1, 310, "Ember (base)"),
    ("cinderace", "low_sweep", 1, 148, "Low Sweep (base)"),
    ("cinderace", "ember", 7, 1774, "-> Pyro Ball"),
    ("cinderace", "low_sweep", 8, 260, "-> Flame Charge"),
    ("buzzwole", "mega_punch", 7, 1158, "-> Smack Down (punch+slam)"),
]


def raw_main_damage(form, level, stats) -> float:
    """Pre-mitigation damage of a move's MAIN components (base>0 or slider>0), excluding
    pure %-Atk burn DoTs and execute."""
    total = 0.0
    for c in form["components"]:
        if c["base"] == 0 and c["slider"] == 0:   # pure-ratio DoT (burn) — Game8 lists separately
            continue
        stat = stats.sp_atk if c["dmg_type"] == "SpAtk" else stats.attack
        total += (c["base"] + c["slider"] * (level - 1) + c["ratio"] * stat) * c["hits"]
    return total


def validation_rows(data=None, moves=None):
    data = data or load_data()
    moves = moves or load_moves()
    rows = []
    for mon, slot_key, level, game8, note in CASES:
        form = move_form(moves[mon]["moves"][slot_key], level)
        comp = raw_main_damage(form, level, base_stats(data["pokemon"][mon], level))
        rows.append((f"{mon}/{form['name']}", level, comp, game8, abs(comp - game8) / game8 * 100, note))
    return rows


def main():
    print(f"{'Pokemon/move':28} {'Lv':>3} {'computed':>9} {'Game8':>7} {'err':>6}")
    print("-" * 60)
    worst = 0.0
    for name, level, comp, game8, err, note in validation_rows():
        worst = max(worst, err)
        print(f"{name:28} {level:>3} {comp:>9.0f} {game8:>7} {err:>5.1f}% {'OK' if err < 2 else '!!'}  {note}")
    print("-" * 60)
    print(f"worst error: {worst:.1f}%  ->  "
          f"{'PASS: main move damage matches Game8 across the sample' if worst < 2 else 'CHECK'}")
    print("\nNote: reference engine cross-check (Pikachu Thunder Shock) is in tests/test_abilities.py.")
    print("Known minor gap: burn DoT ratios on a couple moves differ ~2x (secondary component).")


if __name__ == "__main__":
    main()
