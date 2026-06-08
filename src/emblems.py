"""Real emblem-page optimizer over unite-db's 762 emblems (data/unite_db_emblems.json).

Each emblem has up to two colors, a grade (A/B/C = gold/silver/bronze), and a `stats` list
of real +/- changes (e.g. gold Bulbasaur = +3 Sp.Atk / -50 HP). A page is 10 emblems; each
counts toward BOTH its colors' set bonuses. We pick the 10 that best serve a target stat
(prioritising the target color so the color bonus is reached), sum their stats INCLUDING the
tradeoffs, and add the real color-set bonuses. This replaces the old single-color template.
"""
from __future__ import annotations

import json
import os
from collections import Counter

from stats import Stats

DATA_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "data")
GRADE = {"gold": "A", "silver": "B", "bronze": "C"}
TARGET_COLOR = {"attack": "Brown", "sp_atk": "Green", "defense": "Blue", "sp_def": "Purple", "hp": "White"}
STAT_KEY = {"attack": "attack", "sp_atk": "sp_attack", "defense": "defense", "sp_def": "sp_defense", "hp": "hp"}

_EMBLEMS = None
_COLOR_BONUS = None
_CACHE = {}


def _emblems():
    global _EMBLEMS
    if _EMBLEMS is None:
        _EMBLEMS = json.load(open(os.path.join(DATA_DIR, "unite_db_emblems.json"), encoding="utf-8"))
    return _EMBLEMS


def _color_bonus_table():
    global _COLOR_BONUS
    if _COLOR_BONUS is None:
        _COLOR_BONUS = json.load(open(os.path.join(DATA_DIR, "emblems.json"), encoding="utf-8"))["color_set_bonuses"]
    return _COLOR_BONUS


def colors_of(e):
    return [c for c in (e.get("color1"), e.get("color2")) if c]


def _estats(e):
    d = {}
    for s in e.get("stats", []) or []:
        for k, v in s.items():
            d[k] = d.get(k, 0) + v
    return d


def _flat_of(e) -> Stats:
    s = _estats(e)
    return Stats(hp=s.get("hp", 0), attack=s.get("attack", 0), defense=s.get("defense", 0),
                 sp_atk=s.get("sp_attack", 0), sp_def=s.get("sp_defense", 0), crit=s.get("crit", 0))


def _color_bonuses(page) -> tuple[Stats, Stats]:
    table = _color_bonus_table()
    counts = Counter()
    for e in page:
        for c in colors_of(e):
            counts[c.lower()] += 1
    flat, pct = Stats(), Stats()
    blank = Stats()
    for color, n in counts.items():
        spec = table.get(color)
        if not spec:
            continue
        val = 0
        for thr, v in sorted((int(t), v) for t, v in spec["tiers"].items()):
            if n >= thr:
                val = v
        stat = spec["stat"]
        if not val or not hasattr(blank, stat):       # skip move_speed / cdr-on-Stats / hindrance / etc.
            continue
        target = pct if spec["kind"] == "pct" else flat
        setattr(target, stat, getattr(target, stat) + val)
    return flat, pct


def optimal_page(target: str, rarity: str = "gold") -> tuple[Stats, Stats]:
    """Return (flat Stats, core-percent Stats) for the best 10-emblem page for `target`."""
    cache_key = (target, rarity)
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    pool = [e for e in _emblems() if e.get("grade") == GRADE[rarity]]

    if target == "attack_speed":            # 7 Red (for the +8% AS bonus) + 3 Brown (Attack)
        reds = sorted((e for e in pool if "Red" in colors_of(e)),
                      key=lambda e: _estats(e).get("attack", 0), reverse=True)
        browns = sorted((e for e in pool if "Brown" in colors_of(e)),
                        key=lambda e: _estats(e).get("attack", 0), reverse=True)
        page = reds[:7] + browns[:3]
    elif target == "bulk":                  # maximise an HP-equivalent bulk score
        page = sorted(pool, key=lambda e: _estats(e).get("hp", 0)
                      + 10 * (_estats(e).get("defense", 0) + _estats(e).get("sp_defense", 0)),
                      reverse=True)[:10]
    else:                                   # prioritise the target color, then the stat
        tcolor, skey = TARGET_COLOR[target], STAT_KEY[target]
        page = sorted(pool, key=lambda e: (tcolor in colors_of(e), _estats(e).get(skey, 0)),
                      reverse=True)[:10]

    flat = Stats()
    for e in page:
        flat = flat + _flat_of(e)
    cflat, pct = _color_bonuses(page)
    result = (flat + cflat, pct)
    _CACHE[cache_key] = result
    return result


def describe(target: str, rarity: str = "gold") -> dict:
    """Human-readable summary of the optimal page (for inspection)."""
    flat, pct = optimal_page(target, rarity)
    pool = [e for e in _emblems() if e.get("grade") == GRADE[rarity]]
    # recompute page colors for display
    if target == "attack_speed":
        reds = sorted((e for e in pool if "Red" in colors_of(e)), key=lambda e: _estats(e).get("attack", 0), reverse=True)
        browns = sorted((e for e in pool if "Brown" in colors_of(e)), key=lambda e: _estats(e).get("attack", 0), reverse=True)
        page = reds[:7] + browns[:3]
    elif target == "bulk":
        page = sorted(pool, key=lambda e: _estats(e).get("hp", 0) + 10 * (_estats(e).get("defense", 0) + _estats(e).get("sp_defense", 0)), reverse=True)[:10]
    else:
        tcolor, skey = TARGET_COLOR[target], STAT_KEY[target]
        page = sorted(pool, key=lambda e: (tcolor in colors_of(e), _estats(e).get(skey, 0)), reverse=True)[:10]
    cc = Counter(c for e in page for c in colors_of(e))
    return {"flat": flat.as_dict(), "pct": pct.as_dict(), "colors": dict(cc)}


if __name__ == "__main__":
    for t in ("attack", "sp_atk", "bulk", "attack_speed"):
        d = describe(t)
        nz = {k: round(v, 1) for k, v in d["flat"].items() if round(v, 1)}
        nzp = {k: v for k, v in d["pct"].items() if v}
        print(f"{t:13} flat={nz}  pct={nzp}  colors={d['colors']}")
