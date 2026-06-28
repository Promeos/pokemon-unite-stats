"""Prove every INPUT that feeds a per-role *score* traces to an authoritative source.

`validate.py` checks the move-damage *formula* vs Game8. This module complements it by proving
the *inputs* that assemble a score — each Pokemon's attack (and the rest of its stats), move
cooldowns, held items, emblems, and the X Attack battle item — are exactly the values in the
sources the project cites, and that the engine actually applies them.

Two kinds of proof, kept distinct on purpose:

  * PROVENANCE (strong, automatic, 100% coverage): the derived data files are exactly
    reproducible from the cached *raw* unite-db JSON. So every per-level stat in pokemon.json
    and every cooldown in moves.json equals its raw source value — not a hand-edited copy.
  * CROSS-CHECK / SNAPSHOT: a transcribed snapshot of authoritative Game8 values (patch
    v1.21.1.8) the model must match, each item tagged with its Game8 archive id, plus behavior
    assertions that make_build / the damage engine actually fold the value into the output.

Honest scope: provenance proves "the model uses exactly the cited source data." The one true
*external* cross-check of magnitudes is `validate.py` (computed move totals vs Game8, <0.4%).
Held-item / emblem / X-Attack numbers are locked to a patch snapshot with archive ids; re-run
the data pipeline to refresh them from source.
"""
from __future__ import annotations

import json
import os

import damage
import emblems
from abilities import auto_damage, form_damage, load_moves, move_form
from builds import (BULK_POOL, PHYSICAL_POOL, SPECIAL_POOL, load_data, make_build)
from stats import base_stats

DATA_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "data")


def _load(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# 1. Base stats / ATTACK — provenance + Game8 cross-check
# --------------------------------------------------------------------------- #
# Values unite-db publishes and the project asserts match Game8's current tables.
GAME8_STAT_CASES = [   # (pokemon, level, stat, expected)
    ("pikachu", 6, "defense", 80),
    ("pikachu", 15, "attack", 290),
    ("cinderace", 5, "attack", 174),
]


def check_attack_stats():
    """pokemon.json (every mon's attack + all per-level stats) is reproducible from the cached
    raw unite-db stats.json, and the documented Game8 spot-values match."""
    import build_pokemon_from_unitedb as bp
    disk = _load("pokemon.json")
    reproducible = bp.build() == disk
    mons = [k for k in disk if not k.startswith("_")]
    levels = sum(len(disk[k]["stats_by_level"]) for k in mons)

    cross = []
    for mon, lvl, stat, exp in GAME8_STAT_CASES:
        got = base_stats(disk[mon], lvl).as_dict()[stat]
        cross.append((f"{mon} Lv{lvl} {stat}", got, exp, got == exp))

    ok = reproducible and all(c[-1] for c in cross)
    lines = [f"pokemon.json reproducible from raw unite-db stats.json: {reproducible}",
             f"  coverage: {len(mons)} Pokemon x per-level stats = {levels} stat rows proven == source"]
    for name, got, exp, good in cross:
        lines.append(f"  cross-check {name}: model={got} Game8={exp} {'OK' if good else 'MISMATCH'}")
    return {"name": "Base stats / Attack", "ok": ok, "lines": lines}


# --------------------------------------------------------------------------- #
# 2. Move cooldowns — provenance + spot-check
# --------------------------------------------------------------------------- #
COOLDOWN_CASES = [   # (pokemon, slot, form-name, expected cooldown s)
    ("cinderace", "ember", "base", 6.0),
    ("cinderace", "ember", "Pyro Ball", 4.5),
    ("cinderace", "low_sweep", "Flame Charge", 5.0),
]


def check_cooldowns():
    """moves.json (every damaging slot's base/upgrade/enhanced cooldown) is reproducible from
    the cached raw unite-db pokemon.json, and named cooldowns match."""
    import parse_unitedb_moves as pm
    disk = load_moves()
    reproducible = pm.build() == disk
    mons = [k for k in disk if not k.startswith("_")]
    cds = 0
    for k in mons:
        for m in disk[k].get("moves", {}).values():
            cds += 1 + len(m["upgrades"]) + sum(1 for u in m["upgrades"] if u["enhanced"])

    spot = []
    for mon, slot, form_name, exp in COOLDOWN_CASES:
        m = disk[mon]["moves"][slot]
        if form_name == "base":
            got = m["base"]["cooldown"]
        else:
            got = next(u["cooldown"] for u in m["upgrades"] if u["name"] == form_name)
        spot.append((f"{mon}/{form_name}", got, exp, got == exp))

    ok = reproducible and all(s[-1] for s in spot)
    lines = [f"moves.json reproducible from raw unite-db pokemon.json: {reproducible}",
             f"  coverage: {cds} cooldowns (base+upgrade+enhanced) across {len(mons)} Pokemon proven == source"]
    for name, got, exp, good in spot:
        lines.append(f"  cooldown {name}: model={got}s source={exp}s {'OK' if good else 'MISMATCH'}")
    return {"name": "Move cooldowns", "ok": ok, "lines": lines}


# --------------------------------------------------------------------------- #
# 3. Held items — Game8 snapshot (Lv40) + provenance ids + applied-in-build
# --------------------------------------------------------------------------- #
# Lv40 column transcribed from each item's Game8 page (archive ids live in helditems.json),
# patch v1.21.1.8. {stat: value} are the flats; passive_* are the modelled passive essentials.
GAME8_ITEM_LV40 = {
    "muscle_band":   {"attack": 17.5, "attack_speed": 8.7},
    "scope_lens":    {"crit": 7.0},                       # pure crit, NO flat attack
    "attack_weight": {"attack": 21},
    "razor_claw":    {"attack": 17.5, "crit": 2.3},
    "float_stone":   {"attack": 28},
    "weakness_policy": {"hp": 235, "attack": 17.5},
    "rapid_fire_scarf": {"attack": 14, "attack_speed": 10.5},
    "drain_crown":   {"hp": 140, "attack": 21},
    "wise_glasses":  {"sp_atk": 44},
    "choice_specs":  {"sp_atk": 44},
    "sp_atk_specs":  {"sp_atk": 28},
    "shell_bell":    {"sp_atk": 28, "cdr": 5.2},
    "energy_amplifier": {"cdr": 5.2},
    "assault_vest":  {"hp": 315, "sp_def": 59.5},
    "focus_band":    {"defense": 35, "sp_def": 35},
    "buddy_barrier": {"hp": 525},
    "rocky_helmet":  {"hp": 315, "defense": 59.5},
    "resonant_guard": {"hp": 525},
    "score_shield":  {"hp": 525},
    "aeos_cookie":   {"hp": 280},
}


def check_held_items():
    """Every optimizer-pool item (a) is sourced (has a Game8 archive id), (b) matches the Game8
    Lv40 snapshot, and (c) is actually folded into make_build's totals/flags."""
    items = _load("helditems.json")
    pool = sorted(set(PHYSICAL_POOL + SPECIAL_POOL + BULK_POOL))
    data = load_data()
    lines, ok = [], True

    # (a) provenance + (b) snapshot
    bad_vals, missing_id = [], []
    for k in pool:
        it = items.get(k, {})
        if not it.get("game8_archive"):
            missing_id.append(k)
        exp = GAME8_ITEM_LV40.get(k, {})
        got = it.get("stats_lv40", {})
        # exact match on the snapshot keys; no other core flats sneaking in
        if any(round(got.get(s, 0), 3) != round(v, 3) for s, v in exp.items()) or \
           set(got) - set(exp) - {"move_speed"}:
            bad_vals.append((k, got, exp))
    ok = ok and not bad_vals and not missing_id
    lines.append(f"pool items: {len(pool)} (phys {len(PHYSICAL_POOL)} / spec {len(SPECIAL_POOL)} / bulk {len(BULK_POOL)})")
    lines.append(f"  all carry a Game8 archive id: {not missing_id}" + (f"  MISSING {missing_id}" if missing_id else ""))
    lines.append(f"  all match Game8 Lv40 snapshot (v1.21.1.8): {not bad_vals}")
    for k, got, exp in bad_vals:
        lines.append(f"    MISMATCH {k}: file={got} expected={exp}")

    # (c) applied-in-build behavior
    base = base_stats(data["pokemon"]["cinderace"], 5)
    b_float = make_build(data, "cinderace", 5, ["float_stone"], "none")
    b_mb = make_build(data, "cinderace", 5, ["muscle_band"], "none")
    b_scope = make_build(data, "cinderace", 5, ["scope_lens"], "none")
    b_wise = make_build(data, "pikachu", 5, ["wise_glasses"], "none")
    base_pika = base_stats(data["pokemon"]["pikachu"], 5)
    checks = [
        ("Float Stone +28 flat attack applied", round(b_float.total.attack - base.attack, 1) == 28.0),
        ("Muscle Band sets pct-remaining-HP flag", b_mb.muscle_band is True),
        ("Scope Lens raises crit multiplier +0.14", round(b_scope.crit_multiplier - damage.DEFAULT_CRIT_MULTIPLIER, 2) == 0.14),
        # Wise Glasses = +44 flat Sp.Atk AND +7% passive -> total = (base + 44) * 1.07
        ("Wise Glasses applies +44 flat & +7% Sp.Atk", round(b_wise.total.sp_atk, 2) == round((base_pika.sp_atk + 44) * 1.07, 2)),
        ("Choice Specs sets +60 move_flat", make_build(data, "pikachu", 5, ["choice_specs"], "none").move_flat == 60),
    ]
    for name, good in checks:
        ok = ok and good
        lines.append(f"  behavior: {name}: {'OK' if good else 'FAIL'}")
    return {"name": "Held items (Lv40)", "ok": ok, "lines": lines}


# --------------------------------------------------------------------------- #
# 4. Emblems — raw set, color-bonus table, deterministic & faithful aggregation
# --------------------------------------------------------------------------- #
def check_emblems():
    """The 762-emblem raw set is intact, the color-set bonus table matches Game8, pages are
    deterministic, and a page's stats are exactly the sum of its named emblems + color bonus."""
    raw = _load("unite_db_emblems.json")
    table = _load("emblems.json")["color_set_bonuses"]
    lines, ok = [], True

    from collections import Counter
    grades = Counter(e.get("grade") for e in raw)
    n_ok = len(raw) == 762 and grades.get("A") == 258 and grades.get("B") == 252 and grades.get("C") == 252
    ok = ok and n_ok
    lines.append(f"raw emblems: {len(raw)} (A/B/C = {grades.get('A')}/{grades.get('B')}/{grades.get('C')}) {'OK' if n_ok else 'CHECK'}")

    # color-bonus caps (Game8): Brown/Green/White cap +4%, Blue/Purple +8%, Red +8 AS
    cap_ok = (table["brown"]["tiers"]["6"] == 4 and table["blue"]["tiers"]["6"] == 8
              and table["red"]["tiers"]["7"] == 8)
    ok = ok and cap_ok
    lines.append(f"color-set bonus caps (brown +4% / blue +8% / red +8 AS): {'OK' if cap_ok else 'CHECK'}")

    # deterministic
    det = emblems.optimal_page("attack", "gold") == emblems.optimal_page("attack", "gold")
    ok = ok and det
    lines.append(f"optimal_page deterministic: {det}")

    # faithful aggregation: recompute the attack page's flat directly from raw fields and the
    # color table, INDEPENDENT of emblems._flat_of / _color_bonuses.
    page = emblems._select_page("attack", "gold")
    rf = {"hp": 0.0, "attack": 0.0, "defense": 0.0, "sp_atk": 0.0, "sp_def": 0.0, "crit": 0.0, "cdr": 0.0}
    keymap = {"hp": "hp", "attack": "attack", "defense": "defense", "sp_attack": "sp_atk",
              "sp_defense": "sp_def", "crit": "crit", "cdr": "cdr"}
    counts = Counter()
    for e in page:
        for s in e.get("stats", []) or []:
            for rk, rv in s.items():
                if rk in keymap:
                    rf[keymap[rk]] += rv
        for c in (e.get("color1"), e.get("color2")):
            if c:
                counts[c.lower()] += 1
    # add color-set pct as a multiplicative bump on the core stat (matches stats.apply_core_pct)
    recomputed_pct = {}
    for color, n in counts.items():
        spec = table.get(color)
        if not spec or spec["kind"] != "pct":
            continue
        val = 0
        for thr, v in sorted((int(t), v) for t, v in spec["tiers"].items()):
            if n >= thr:
                val = v
        if val and spec["stat"] in rf:
            recomputed_pct[spec["stat"]] = recomputed_pct.get(spec["stat"], 0) + val
    flat, pct = emblems.optimal_page("attack", "gold")
    flat_match = all(round(getattr(flat, k), 2) == round(rf[k], 2) for k in rf)
    pct_match = all(round(getattr(pct, s), 2) == round(recomputed_pct.get(s, 0), 2)
                    for s in ("hp", "attack", "sp_atk", "defense", "sp_def"))
    brown_capped = round(getattr(pct, "attack"), 2) == 4.0
    ok = ok and flat_match and pct_match and brown_capped
    lines.append(f"attack-page flats == sum of named emblems' raw stats: {flat_match}")
    lines.append(f"attack-page color bonus == recomputed from table: {pct_match}")
    lines.append(f"6+ Brown reaches the capped +4% Attack bonus: {brown_capped}")
    return {"name": "Emblems (762-set)", "ok": ok, "lines": lines}


# --------------------------------------------------------------------------- #
# 5. Battle item (X Attack) — engine constants tied to source + applied
# --------------------------------------------------------------------------- #
def check_battle_item():
    """The X Attack multipliers in the pure engine equal the values in battleitems.json (Game8),
    and turning X Attack on actually multiplies basic and move output."""
    bi = _load("battleitems.json")["x_attack"]
    lines, ok = [], True

    basic_ok = damage.X_ATTACK_BASIC_MULT == bi["basic_damage_mult"]
    lo, hi = bi["move_damage_mult_range"]
    mid = round((lo + hi) / 2, 10)
    move_ok = round(damage.X_ATTACK_MOVE_MULT, 10) == mid
    ok = ok and basic_ok and move_ok
    lines.append(f"engine X_ATTACK_BASIC_MULT {damage.X_ATTACK_BASIC_MULT} == battleitems.json {bi['basic_damage_mult']}: {basic_ok}")
    lines.append(f"engine X_ATTACK_MOVE_MULT {damage.X_ATTACK_MOVE_MULT} == midpoint{tuple([lo, hi])}={mid}: {move_ok}")

    # behavior: X Attack on > off, for both a basic and a move
    data = load_data()
    moves = load_moves()
    atk = make_build(data, "cinderace", 5, ["muscle_band", "scope_lens", "float_stone"], "max_attack")
    tgt = make_build(data, "cinderace", 5, [], "none")
    form = move_form(moves["cinderace"]["moves"]["ember"], 5)
    move_on = form_damage(atk, tgt, form, 5, x_attack=True)
    move_off = form_damage(atk, tgt, form, 5, x_attack=False)
    auto_on = auto_damage(atk, tgt, moves["cinderace"], tgt.total.hp, x_attack=True)
    auto_off = auto_damage(atk, tgt, moves["cinderace"], tgt.total.hp, x_attack=False)
    basic_applies = round(auto_on / auto_off, 2) == 1.2 if auto_off else False
    move_applies = move_on > move_off
    ok = ok and basic_applies and move_applies
    lines.append(f"behavior: X Attack basic x1.2 applied ({auto_off:.0f}->{auto_on:.0f}): {basic_applies}")
    lines.append(f"behavior: X Attack move multiplier applied ({move_off:.0f}->{move_on:.0f}): {move_applies}")
    return {"name": "Battle item (X Attack)", "ok": ok, "lines": lines}


CHECKS = [check_attack_stats, check_cooldowns, check_held_items, check_emblems, check_battle_item]


def run_all():
    return [c() for c in CHECKS]


def main():
    print("Input provenance & validation — proving each score input traces to its source\n")
    results = run_all()
    for r in results:
        print(f"[{'PASS' if r['ok'] else 'FAIL'}] {r['name']}")
        for ln in r["lines"]:
            print(f"    {ln}")
        print()
    n_ok = sum(r["ok"] for r in results)
    verdict = "ALL INPUTS PROVEN" if n_ok == len(results) else "SOME CHECKS FAILED"
    print("-" * 70)
    print(f"{n_ok}/{len(results)} input categories proven  ->  {verdict}")


if __name__ == "__main__":
    main()
