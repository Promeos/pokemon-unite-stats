# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A data study testing whether maxed **held items** (Lv40) + **emblems** (gold + color sets) +
**X Attack** let an opponent kill faster **before first evolution**, *regardless of Pokémon*.
Enemy builds are unobservable in-game, so it's a **model**: a verified damage/time-to-kill
engine fed by current, validated unite-db data for all 94 mons. See `README.md` and the
approved plan at `C:\Users\chris\.claude\plans\steady-waddling-scone.md`.

## Commands

```bash
pip install -r requirements.txt
python -m pytest tests/ -q     # verify engine + move formulas (run after ANY change to damage.py)
python -m pytest tests/test_damage.py::test_blastoise_reduction_is_35_percent -q   # single test
python src/analysis.py         # Phase 1: hits-to-kill chart (autos) -> figures/
python src/abilities.py        # roster-wide pre-evo burst (moves + autos)

# Data pipeline (re-cache from unite-db, regenerate the derived files):
python src/fetch_unitedb.py              # -> data/unite_db_pokemon.json
python src/parse_unitedb_moves.py        # -> data/moves.json   (roster move ratios)
python src/build_pokemon_from_unitedb.py # -> data/pokemon.json (94 mons; needs unite_db_stats.json)
```
`build_pokemon_from_unitedb.py` needs `data/unite_db_stats.json` — fetch it with
`fetch_unitedb.fetch_json("stats")`. Imports work via `conftest.py` (puts `src/` on `sys.path`);
Pyright flags `import damage` etc. as unresolved — expected, they resolve at runtime.

## Architecture (the pipeline)

raw unite-db JSON → generated `data/pokemon.json` + `data/moves.json` → `stats.py` (Stats
algebra) → `builds.py` (Build = total Stats + flags) → `damage.py` (mitigation, attack-speed,
basic, move, TTK/DPS, EHP) → `abilities.py` (burst combos) / `analysis.py` (charts). The engine
is pure and unit-tested; everything else is data.

- **`damage.py`** — verified core. `mitigated_damage = floor(atk × 600/(600+Def))`, the
  attack-speed buckets, and `move_damage = floor((base + slider*(Lv-1) + ratio*stat) × 600/(600+Def))`
  are all matched verbatim to the reference engine. Don't change without re-checking the tests.
- **`stats.py`** — `Stats` dataclass. 5 **core** stats scaled by emblem % via `apply_core_pct`;
  `attack_speed`/`crit` are additive percent-points (never scaled).
- **`builds.py`** — `make_build()` folds item Lv40 flats + item % passives (Wise Glasses) + emblem
  template into total stats; sets flags (`muscle_band`, `crit_multiplier`, `move_flat` from Choice
  Specs). `INVESTMENT_TIERS` + `maxed_tier_for()` pick physical vs special builds by `damage_type`.
- **`abilities.py`** — move damage by component (Atk→Def, SpAtk→SpDef), `burst_combo` (base moves
  then autos until dead), roster pre-evo analysis.

## Data sources & non-obvious gotchas

- **Stats + move ratios = unite-db raw JSON.** `unite-db.com/pokemon.json` (moves:
  `ratio,base,slider,dmg_type`) and `/stats.json` (per-level stats) — the Mathcord data its site
  uses. unite-db's *web pages are JS-rendered and unreadable* to a fetcher; the **`/*.json`
  endpoints are raw and readable.** Validated: Thunder Shock `0.75*SpAtk+21*(Lv-1)+390` == reference
  engine; stats == Game8.
- **Move fields:** `ratio` is a PERCENT (75 → 0.75×), `slider` is the per-level term, `base` is flat,
  `dmg_type` ∈ {Atk, SpAtk} picks the stat AND the mitigating defense. `add1..add4_*` are extra
  damage components — sum them. `parse_unitedb_moves.py` already converts ratio→fraction.
- **unite-db lists only the pre-evo kit:** passive + basic + 2 base moves + Unite move. The
  **Lv5/7 upgrade moves are NOT in the static endpoint** (there is no `moves.json` — it 404s).
- **Items/emblems still come from Game8** (unite-db doesn't expose Lv40 item tables cleanly).
  Held items cap at Lv40 and **Lv30→40 is non-linear** — read the real Game8 table, never extrapolate.
- **Muscle Band's %HP bonus IS reduced by Defense** (Game8; 3% remaining HP, cap 360) — in
  `basic_hit_damage`.
- **Off-stat investment does nothing:** a Sp.Atk build gives +0% to Attack-based autos and
  vice-versa; `make_build` routes bonuses by stat, `maxed_tier_for` picks the build by `damage_type`.

## Regenerating / adding data

Re-run the data pipeline (above) to refresh from unite-db. To adjust items/emblems, edit
`data/helditems.json` / `data/emblems.json` / `data/battleitems.json` (Game8 numbers); keep the
schema — `stats.from_mapping` ignores unknown keys and defaults missing ones to 0.
