"""Core Pokemon Unite damage engine.

Formulas are sourced from the open-source reference engine
`Stephen-Choi/pokemon-unite-damage-calculator` (math derived from unite-db + the
Unite Mathcord), corroborated by GameRant's worked example and the unite-dmg.com
calculator. See README for full citations.

VERIFIED against reference code:
  * Mitigation:  finalDamage = floor(attackDamage * 600 / (600 + Def))
                 (damagecalculator/damage_calculator.go)
  * Attack speed -> frame-delay buckets, delay_ms = frames/4 * 66.67
                 (attack/model.go)
  * Muscle Band passive: 3% of target's REMAINING HP, capped at 360/hit, basic
    attacks only. Per Game8 (current, tested) this bonus IS reduced by the
    target's Defense, so we mitigate it. (The reference engine modelled it as a
    separate damage type; we follow Game8's explicit description.)
"""
from __future__ import annotations

import math

MITIGATION_CONSTANT = 600.0


# --------------------------------------------------------------------------- #
# Mitigation (verified verbatim)
# --------------------------------------------------------------------------- #
def mitigation_multiplier(defense: float) -> float:
    """Fraction of pre-mitigation damage that gets through `defense` (Def or Sp.Def)."""
    return MITIGATION_CONSTANT / (MITIGATION_CONSTANT + defense)


def mitigated_damage(attack_damage: float, defense: float) -> int:
    """Single-hit post-mitigation damage, floored (matches the reference engine)."""
    return math.floor(attack_damage * mitigation_multiplier(defense))


def effective_hp(hp: float, defense: float) -> float:
    """Pre-mitigation damage needed to deplete `hp` sitting behind `defense`.

    Inverse of mitigation: raw = hp / (600/(600+def)) = hp * (1 + def/600).
    Used as the survivability metric for Defenders / Supporters.
    """
    return hp * (1.0 + defense / MITIGATION_CONSTANT)


# --------------------------------------------------------------------------- #
# Attack speed (buckets verbatim from reference engine attack/model.go)
# --------------------------------------------------------------------------- #
ATTACK_SPEED_BUCKETS = {
    0.0: 60, 8.1: 56, 16.42: 52, 26.11: 48, 37.56: 44, 51.29: 40,
    68.05: 36, 89.04: 32, 115.99: 28, 151.81: 24, 202.04: 20, 272.51: 16,
}
_AS_KEYS = sorted(ATTACK_SPEED_BUCKETS)          # ascending thresholds
_MS_PER_FRAME = 66.67 / 4.0                       # 4 frames == 66.67 ms  (~60 fps)
_MIN_FRAME_DELAY = 16


def frame_delay_for_attack_speed(attack_speed: float) -> int:
    """Frames between basic attacks for an attack-speed stat value (step function)."""
    for idx, key in enumerate(_AS_KEYS):
        if attack_speed <= key:
            return ATTACK_SPEED_BUCKETS[_AS_KEYS[max(0, idx - 1)]]
    return _MIN_FRAME_DELAY  # above the top threshold -> fastest


def attack_interval_seconds(attack_speed: float) -> float:
    return frame_delay_for_attack_speed(attack_speed) * _MS_PER_FRAME / 1000.0


def attacks_per_second(attack_speed: float) -> float:
    return 1.0 / attack_interval_seconds(attack_speed)


# --------------------------------------------------------------------------- #
# Basic-attack damage (crit folded as expected value, Muscle Band passive)
# --------------------------------------------------------------------------- #
DEFAULT_CRIT_MULTIPLIER = 2.0      # a crit deals 2x; Scope Lens raises this
MUSCLE_BAND_PCT = 0.03             # 3% of target remaining HP at Lv40 (Game8-confirmed)
MUSCLE_BAND_CAP = 360.0            # per-hit cap (true damage)


def basic_hit_damage(
    attack: float,
    target_defense: float,
    target_current_hp: float | None = None,
    crit_rate: float = 0.0,
    crit_multiplier: float = DEFAULT_CRIT_MULTIPLIER,
    muscle_band: bool = False,
    basic_multiplier: float = 1.0,
) -> float:
    """Expected damage of one basic attack.

    `attack` is the attacker's Attack stat (== Game8 'Attack Damage' column, which is
    the pre-mitigation basic value). Crit is folded in as an expected value. Muscle
    Band adds min(3% * current HP, 360) as TRUE damage (not reduced by Defense).
    """
    pre = attack * basic_multiplier
    base = pre * mitigation_multiplier(target_defense)
    crit_rate = max(0.0, min(crit_rate, 1.0))
    base *= 1.0 + crit_rate * (crit_multiplier - 1.0)   # expected-value crit
    base = math.floor(base)
    bonus = 0.0
    if muscle_band and target_current_hp is not None:
        raw_bonus = min(MUSCLE_BAND_PCT * target_current_hp, MUSCLE_BAND_CAP)
        bonus = math.floor(raw_bonus * mitigation_multiplier(target_defense))
    return base + bonus


# --------------------------------------------------------------------------- #
# Move (ability) damage  +  X Attack battle item
# --------------------------------------------------------------------------- #
X_ATTACK_BASIC_MULT = 1.2      # X Attack: x1.2 basic-attack damage for 8 s
X_ATTACK_MOVE_MULT = 1.10      # X Attack: ~x1.05-1.15 move damage (midpoint)


def move_damage(stat_value, level, ratio, per_level, base,
                target_mitigation, flat_bonus=0.0, mult=1.0):
    """One move hit. raw = ratio*stat + per_level*(level-1) + base (+ item flat),
    then reduced by the target's relevant defense (Def or Sp.Def). Floored.

    Formula shape taken verbatim from the reference engine's per-move Go files.
    """
    raw = (ratio * stat_value + per_level * (level - 1) + base + flat_bonus) * mult
    return math.floor(raw * mitigation_multiplier(target_mitigation))


def execute_damage(current_hp, pct, cap):
    """Execute / %-current-HP component (e.g. Electro Ball). True damage, capped."""
    return math.floor(min(pct * current_hp, cap))


# --------------------------------------------------------------------------- #
# Time / hits to kill, DPS
# --------------------------------------------------------------------------- #
def hits_to_kill(
    attack: float,
    target_hp: float,
    target_defense: float,
    crit_rate: float = 0.0,
    crit_multiplier: float = DEFAULT_CRIT_MULTIPLIER,
    muscle_band: bool = False,
    basic_multiplier: float = 1.0,
    max_hits: int = 100_000,
) -> int:
    """Number of basic attacks to drop a target. Simulated hit-by-hit because the
    Muscle Band passive depends on the target's *current* HP."""
    hp = target_hp
    for n in range(1, max_hits + 1):
        hp -= basic_hit_damage(
            attack, target_defense, target_current_hp=hp,
            crit_rate=crit_rate, crit_multiplier=crit_multiplier,
            muscle_band=muscle_band, basic_multiplier=basic_multiplier,
        )
        if hp <= 0:
            return n
    return max_hits


def time_to_kill(
    attack: float,
    target_hp: float,
    target_defense: float,
    attack_speed: float = 0.0,
    **kwargs,
) -> float:
    """Seconds to kill via basic attacks. First hit lands at t=0, so n hits span
    (n-1) attack intervals."""
    n = hits_to_kill(attack, target_hp, target_defense, **kwargs)
    return (n - 1) * attack_interval_seconds(attack_speed)


def dps(
    attack: float,
    target_defense: float,
    attack_speed: float = 0.0,
    crit_rate: float = 0.0,
    crit_multiplier: float = DEFAULT_CRIT_MULTIPLIER,
    basic_multiplier: float = 1.0,
) -> float:
    """Sustained basic-attack DPS vs a target of given Defense.

    Excludes Muscle Band's %-current-HP bonus (target-dependent, not a steady-state
    quantity); pass it through hits_to_kill / time_to_kill when modelling a specific
    target instead.
    """
    per_hit = basic_hit_damage(
        attack, target_defense, target_current_hp=None,
        crit_rate=crit_rate, crit_multiplier=crit_multiplier,
        basic_multiplier=basic_multiplier,
    )
    return per_hit * attacks_per_second(attack_speed)
