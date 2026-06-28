"""Build assembly: turn (Pokemon, level, held items, emblem page) into total stats.

A `Build` carries the resolved total `Stats` plus the combat flags the damage
engine needs (Muscle Band on/off, crit multiplier from Scope Lens, etc.).
Item flats use the Lv40 column from data/helditems.json. Emblem pages are
modelled with stat-targeted templates (see EMBLEM_TEMPLATES).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import damage
import emblems
from stats import Stats, base_stats, from_mapping

DATA_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "data")


def load_data() -> dict:
    """Load the three data files the build assembler needs: per-Pokemon stats, held
    items (Lv40 column + passives), and emblem color-set bonuses."""
    def _load(name):
        with open(os.path.join(DATA_DIR, name), encoding="utf-8") as fh:
            return json.load(fh)
    return {
        "pokemon": _load("pokemon.json"),
        "items": _load("helditems.json"),
        "emblems": _load("emblems.json"),
    }


# --------------------------------------------------------------------------- #
# Emblem-page templates  ->  (flat Stats, core-percent Stats)
# A maxed page = 6 gold emblems of the target color (color bonus) + their flats;
# the irrelevant tradeoff stat is chosen so it doesn't touch what we measure.
# --------------------------------------------------------------------------- #
def emblem_page(template: str | None, rarity: str = "gold") -> tuple[Stats, Stats]:
    """Return (flat, core-percent) for a template — a REAL optimised 10-emblem page from
    unite-db's 762 emblems (emblems.optimal_page), tradeoffs and color bonuses included."""
    if template in (None, "none"):
        return Stats(), Stats()
    if template not in emblems.TEMPLATE_TARGET:
        raise ValueError(f"unknown emblem template: {template!r}")
    return emblems.optimal_page(emblems.TEMPLATE_TARGET[template], rarity)


# --------------------------------------------------------------------------- #
# Item pools & named investment tiers
# --------------------------------------------------------------------------- #
PHYSICAL_POOL = ["muscle_band", "scope_lens", "attack_weight", "razor_claw", "float_stone",
                 "weakness_policy", "rapid_fire_scarf", "drain_crown"]
SPECIAL_POOL = ["wise_glasses", "choice_specs", "sp_atk_specs", "shell_bell", "energy_amplifier"]
BULK_POOL = ["assault_vest", "focus_band", "buddy_barrier", "rocky_helmet",
             "resonant_guard", "score_shield", "aeos_cookie"]

# A classic max physical-attacker loadout vs. nothing equipped.
INVESTMENT_TIERS = {
    "uninvested": dict(items=[], emblems="none"),
    "maxed_attacker": dict(items=["muscle_band", "scope_lens", "float_stone"], emblems="max_attack"),
    "maxed_special": dict(items=["wise_glasses", "choice_specs", "sp_atk_specs"], emblems="max_sp_atk"),
}


@dataclass
class Build:
    pokemon: str
    level: int
    items: list[str]
    emblems: str
    total: Stats
    muscle_band: bool = False
    crit_multiplier: float = damage.DEFAULT_CRIT_MULTIPLIER
    move_flat: float = 0.0      # flat bonus to each move hit (e.g. Choice Specs +60)

    @property
    def crit_rate(self) -> float:
        return self.total.crit / 100.0


def make_build(data: dict, pokemon: str, level: int,
               items: list[str] | None = None, emblems: str = "none",
               rarity: str = "gold") -> Build:
    items = items or []
    pdata = data["pokemon"][pokemon]
    flat = base_stats(pdata, level)
    item_pct = Stats()
    muscle_band = False
    crit_multiplier = damage.DEFAULT_CRIT_MULTIPLIER
    move_flat = 0.0

    for key in items:
        item = data["items"][key]
        flat = flat + from_mapping(item.get("stats_lv40", {}))
        passive = item.get("passive", {})
        ptype = passive.get("type")
        if ptype == "pct_remaining_hp":
            muscle_band = True
        elif ptype == "crit_damage":
            crit_multiplier += passive.get("crit_damage_pct", 0) / 100.0
        elif ptype == "pct_stat":  # e.g. Wise Glasses +7% Sp.Atk
            setattr(item_pct, passive["stat"], getattr(item_pct, passive["stat"]) + passive.get("pct", 0))
        elif ptype == "move_flat":  # e.g. Choice Specs +60 per move hit
            move_flat += passive.get("amount", 0)

    emb_flat, emb_pct = emblem_page(emblems, rarity)
    flat = flat + emb_flat
    total = flat.apply_core_pct(emb_pct + item_pct)
    return Build(pokemon, level, list(items), emblems, total, muscle_band, crit_multiplier, move_flat)


def tier_build(data: dict, pokemon: str, level: int, tier: str) -> Build:
    """Build a Pokemon at one of the named INVESTMENT_TIERS (uninvested / maxed_attacker /
    maxed_special) — a shortcut for the canonical loadouts used across the analyses."""
    spec = INVESTMENT_TIERS[tier]
    return make_build(data, pokemon, level, spec["items"], spec["emblems"])


# --------------------------------------------------------------------------- #
# Combat between two builds
# --------------------------------------------------------------------------- #
def hits_between(attacker: Build, defender: Build) -> int:
    """Basic attacks for `attacker` to knock out `defender` (carries crit/Muscle Band flags)."""
    return damage.hits_to_ko(
        attacker.total.attack, defender.total.hp, defender.total.defense,
        crit_rate=attacker.crit_rate, crit_multiplier=attacker.crit_multiplier,
        muscle_band=attacker.muscle_band,
    )


def ttko_between(attacker: Build, defender: Build) -> float:
    """Seconds for `attacker` to knock out `defender` via basic attacks (attack-speed aware)."""
    return damage.time_to_ko(
        attacker.total.attack, defender.total.hp, defender.total.defense,
        attack_speed=attacker.total.attack_speed,
        crit_rate=attacker.crit_rate, crit_multiplier=attacker.crit_multiplier,
        muscle_band=attacker.muscle_band,
    )


if __name__ == "__main__":
    data = load_data()
    lvl = 3  # pre first evolution
    target = tier_build(data, "pikachu", lvl, "uninvested")   # a squishy with nothing equipped
    bare = tier_build(data, "pikachu", lvl, "uninvested")
    maxed = tier_build(data, "pikachu", lvl, "maxed_attacker")

    print(f"Pikachu mirror @ Lv{lvl}  (target: un-invested, HP {target.total.hp:.0f}, Def {target.total.defense:.0f})")
    for name, atk in [("un-invested attacker", bare), ("MAXED attacker", maxed)]:
        h = hits_between(atk, target)
        t = ttko_between(atk, target)
        print(f"  {name:22s} Atk {atk.total.attack:6.1f} | {h:2d} hits | {t:4.2f}s")
