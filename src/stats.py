"""Stat algebra: combine a Pokemon's base stats with held items and emblems.

Model (sources documented in README / plan):
    total_core = (base + sum(item flats) + sum(emblem flats)) * (1 + color_set_pct)
    attack_speed and crit are additive percent-points (NOT scaled by color_set_pct).

Everything is kept in native units:
    hp, attack, defense, sp_atk, sp_def : raw stat points
    attack_speed                        : percent points (feeds the attack-speed buckets)
    crit                                : percent crit rate
"""
from __future__ import annotations

from dataclasses import dataclass

CORE = ("hp", "attack", "defense", "sp_atk", "sp_def")
ADDITIVE = ("attack_speed", "crit")
ALL = CORE + ADDITIVE


@dataclass
class Stats:
    hp: float = 0.0
    attack: float = 0.0
    defense: float = 0.0
    sp_atk: float = 0.0
    sp_def: float = 0.0
    attack_speed: float = 0.0  # percent points (sum of base + item + red-emblem bonuses)
    crit: float = 0.0          # percent crit rate

    def __add__(self, other: "Stats") -> "Stats":
        return Stats(**{k: getattr(self, k) + getattr(other, k) for k in ALL})

    def apply_core_pct(self, pct: "Stats") -> "Stats":
        """Multiply the 5 core stats by (1 + pct/100). attack_speed/crit pass through."""
        out = {k: getattr(self, k) * (1.0 + getattr(pct, k) / 100.0) for k in CORE}
        out.update({k: getattr(self, k) for k in ADDITIVE})
        return Stats(**out)

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in ALL}


def from_mapping(m: dict) -> Stats:
    """Build a Stats from a {stat: value} dict, ignoring unknown keys, defaulting missing to 0."""
    return Stats(**{k: float(m.get(k, 0.0)) for k in ALL})


def base_stats(pokemon_data: dict, level: int) -> Stats:
    """Base stats for a Pokemon at a given level, from a loaded pokemon-data dict."""
    return from_mapping(pokemon_data["stats_by_level"][str(level)])
