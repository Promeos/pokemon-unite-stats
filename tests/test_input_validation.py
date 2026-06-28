"""Enforce that every INPUT feeding a score is proven (see src/validate_inputs.py).

One test per input category so a regression points at exactly which source drifted:
attack/stats, cooldowns, held items, emblems, X Attack. These complement test_validation.py
(which checks the move-damage *formula* vs Game8) by checking the *inputs* the formula consumes.
"""
import validate_inputs as vi


def _fail_msg(result):
    return f"{result['name']} not proven:\n  " + "\n  ".join(result["lines"])


def test_attack_and_stats_traceable():
    r = vi.check_attack_stats()
    assert r["ok"], _fail_msg(r)


def test_cooldowns_traceable():
    r = vi.check_cooldowns()
    assert r["ok"], _fail_msg(r)


def test_held_items_traceable():
    r = vi.check_held_items()
    assert r["ok"], _fail_msg(r)


def test_emblems_traceable():
    r = vi.check_emblems()
    assert r["ok"], _fail_msg(r)


def test_battle_item_traceable():
    r = vi.check_battle_item()
    assert r["ok"], _fail_msg(r)


def test_all_input_categories_proven():
    results = vi.run_all()
    failed = [r["name"] for r in results if not r["ok"]]
    assert not failed, f"unproven input categories: {failed}"
