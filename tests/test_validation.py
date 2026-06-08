"""Cross-source validation: our computed move damage must match Game8's published totals.

Guards against bad ratios / unit errors in the unite-db parse. See src/validate.py for the
reference cases (Cinderace Ember/Pyro Ball/Low Sweep/Flame Charge, Buzzwole Smack Down).
"""
from validate import validation_rows


def test_move_damage_matches_game8_within_2pct():
    rows = validation_rows()
    assert rows, "no validation cases ran"
    for name, level, computed, game8, err, note in rows:
        assert err < 2.0, f"{name} @Lv{level}: computed {computed:.0f} vs Game8 {game8} ({err:.1f}%)"


def test_pyro_ball_is_exact():
    # The headline check: Cinderace Pyro Ball @ Lv7 == Game8's 1774 to the integer.
    row = next(r for r in validation_rows() if "Pyro Ball" in r[0])
    assert round(row[2]) == 1774
