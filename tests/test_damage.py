"""Verify the engine against the documented, primary sources.

References:
  * Mitigation formula + the floor: reference engine damagecalculator/damage_calculator.go
  * Blastoise worked example (324 Def -> 35% reduction, 200 dmg -> ~130 through):
    GameRant "How Defense & Special Defense Works"
  * Attack-speed buckets + delay: reference engine attack/model.go test cases
    (0 AS -> 60 frames; 52 -> 40; >272.51 -> 16)
  * Muscle Band passive: 3% remaining HP true damage, capped 360
"""
import math

import damage as d


# --------------------------- mitigation --------------------------- #
def test_blastoise_reduction_is_35_percent():
    # GameRant: Blastoise with 324 Defense reduces incoming damage by ~35%.
    reduction = 1.0 - d.mitigation_multiplier(324)
    assert abs(reduction - 0.35) < 0.01


def test_blastoise_200_damage_floored():
    # 200 * 600/924 = 129.87 -> engine floors to 129 (article rounds to 130).
    assert d.mitigated_damage(200, 324) == 129


def test_zero_defense_is_full_damage():
    assert d.mitigation_multiplier(0) == 1.0
    assert d.mitigated_damage(250, 0) == 250


def test_mitigation_matches_reference_formula():
    # Spot-check the exact verbatim formula at a few points.
    for atk, dfn in [(300, 100), (450, 250), (134, 35)]:
        assert d.mitigated_damage(atk, dfn) == math.floor(atk * 600 / (600 + dfn))


# --------------------------- effective HP --------------------------- #
def test_effective_hp_inverts_mitigation():
    # Damage needed to drop hp behind defense, then re-mitigated, should equal hp.
    hp, dfn = 3292, 35
    ehp = d.effective_hp(hp, dfn)
    assert abs(ehp * d.mitigation_multiplier(dfn) - hp) < 1e-6


# --------------------------- attack speed --------------------------- #
def test_attack_speed_buckets_reference_points():
    assert d.frame_delay_for_attack_speed(0) == 60      # base
    assert d.frame_delay_for_attack_speed(52) == 40     # 51.29 < 52 <= 68.05
    assert d.frame_delay_for_attack_speed(400) == 16    # above top threshold


def test_attack_interval_and_rate():
    assert abs(d.attack_interval_seconds(0) - 1.0) < 0.005      # 60 frames ~ 1.0 s
    assert abs(d.attacks_per_second(0) - 1.0) < 0.005
    assert abs(d.attacks_per_second(400) - 3.75) < 0.01         # 16 frames -> 3.75/s


# --------------------------- basic hit / muscle band --------------------------- #
def test_basic_hit_no_items_equals_mitigated():
    assert d.basic_hit_damage(290, 240) == d.mitigated_damage(290, 240)


def test_muscle_band_caps_at_360():
    # 3% of 20000 HP = 600, capped to 360, then reduced by the target's Defense.
    base = d.mitigated_damage(290, 240)
    cap_bonus = math.floor(360 * d.mitigation_multiplier(240))
    hit = d.basic_hit_damage(290, 240, target_current_hp=20000, muscle_band=True)
    assert hit == base + cap_bonus


def test_muscle_band_uncapped_below_threshold():
    # 3% of 5000 = 150 (< 360 cap), then reduced by the target's Defense.
    base = d.mitigated_damage(290, 240)
    bonus = math.floor(150 * d.mitigation_multiplier(240))
    hit = d.basic_hit_damage(290, 240, target_current_hp=5000, muscle_band=True)
    assert hit == base + bonus


def test_crit_expected_value():
    # 50% crit at 2x => expected 1.5x the mitigated hit.
    base = 290 * d.mitigation_multiplier(240)
    hit = d.basic_hit_damage(290, 240, crit_rate=0.5, crit_multiplier=2.0)
    assert hit == math.floor(base * 1.5)


# --------------------------- hits / time to KO --------------------------- #
def test_hits_to_ko_basic_case():
    # No defense: ceil(hp / attack).
    assert d.hits_to_ko(100, 1000, 0) == 10
    assert d.hits_to_ko(150, 1000, 0) == 7   # 150*6=900, 7th knocks out


def test_muscle_band_reduces_hits_to_ko():
    plain = d.hits_to_ko(150, 4000, 50)
    with_mb = d.hits_to_ko(150, 4000, 50, muscle_band=True)
    assert with_mb <= plain


def test_time_to_ko_uses_intervals():
    # 10 hits at 0 AS (1.0 s interval) -> 9 intervals -> ~9.0 s.
    assert abs(d.time_to_ko(100, 1000, 0, attack_speed=0.0) - 9.0) < 0.05
