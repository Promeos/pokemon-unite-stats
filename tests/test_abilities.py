"""Verify move formulas reproduce the reference engine's per-move Go code exactly.

Pikachu (pokemon/pikachu/*.go):
  Thunderbolt  (unupgraded): 0.50*SpAtk + 12*(Lv-1) + 500
  Electro Ball (unupgraded): 0.66*SpAtk + 25*(Lv-1) + 530
  Boosted basic:             0.38*SpAtk + 10*(Lv-1) + 200
"""
import math

import damage as d


def test_thunderbolt_raw_matches_reference():
    # Lv6, SpAtk 246, no mitigation -> raw, floored.
    raw = d.move_damage(246, 6, 0.50, 12, 500, target_mitigation=0)
    assert raw == math.floor(0.50 * 246 + 12 * 5 + 500)   # 683


def test_electro_ball_raw_matches_reference():
    raw = d.move_damage(246, 6, 0.66, 25, 530, target_mitigation=0)
    assert raw == math.floor(0.66 * 246 + 25 * 5 + 530)   # 817


def test_boosted_basic_raw_matches_reference():
    raw = d.move_damage(246, 6, 0.38, 10, 200, target_mitigation=0)
    assert raw == math.floor(0.38 * 246 + 10 * 5 + 200)   # 343


def test_move_is_mitigated_by_defense():
    raw = d.move_damage(246, 6, 0.50, 12, 500, target_mitigation=0)
    mit = d.move_damage(246, 6, 0.50, 12, 500, target_mitigation=61)
    assert mit == math.floor(raw * d.mitigation_multiplier(61))


def test_move_flat_and_xattack_multiplier():
    base = d.move_damage(300, 8, 0.5, 12, 500, target_mitigation=0)
    with_flat = d.move_damage(300, 8, 0.5, 12, 500, target_mitigation=0, flat_bonus=60)
    assert with_flat == base + 60
    xatk = d.move_damage(300, 8, 0.5, 12, 500, target_mitigation=0, mult=1.10)
    assert xatk == math.floor((0.5 * 300 + 12 * 7 + 500) * 1.10)


def test_execute_caps():
    assert d.execute_damage(10000, 0.05, 1200) == 500       # 5% of 10000
    assert d.execute_damage(40000, 0.05, 1200) == 1200      # capped
