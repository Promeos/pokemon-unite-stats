# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A data study testing whether maxed **held items** (Lv40) + **emblems** + **X Attack** let an
opponent kill faster, *regardless of Pokémon*. Enemy builds are unobservable in-game, so it's a
**model**: a damage/time-to-kill engine fed by current unite-db data for all 94 mons, modeling
the **full move kit** (base + Lv5/7 upgrades + Lv11/13 enhanced + multi-hit + execute). See
`README.md` and the plan at `C:\Users\chris\.claude\plans\steady-waddling-scone.md`.

## Commands

```bash
pip install -r requirements.txt
python -m pytest tests/ -q     # 22 tests (run after ANY change to damage.py / parsing)
python src/validate.py         # #1 cross-check computed move damage vs Game8 totals
python src/optimize.py         # Phase 2 per-role optimizer -> charts + data/phase2_offense.csv
python src/decomposition.py    # #2 lever decomposition (items vs emblems vs X Attack) + rarity
python src/meta_validation.py  # #5 model rating vs unite-db community tier
python src/abilities.py        # pre/post-evo burst combos

# Data pipeline (re-cache from unite-db, regenerate derived files):
python src/fetch_unitedb.py ; python src/parse_unitedb_moves.py ; python src/build_pokemon_from_unitedb.py
```
`build_pokemon_from_unitedb.py` needs `data/unite_db_stats.json` (`fetch_unitedb.fetch_json("stats")`).
Imports resolve via `conftest.py` (puts `src/` on `sys.path`); Pyright "unresolved import" warnings
are expected.

## Architecture

raw unite-db JSON → `parse_unitedb_moves.py` / `build_pokemon_from_unitedb.py` → `data/moves.json`
+ `data/pokemon.json` → `stats.py` (Stats algebra) → `builds.py` (Build = total Stats + flags) →
`damage.py` (mitigation, attack-speed, basic, move, TTK/DPS, EHP) → `abilities.py` (full-kit combat) /
`optimize.py` / `decomposition.py` / `meta_validation.py` / `analysis.py`. Engine is pure + tested.

- **`damage.py`** — verified core. `floor(atk × 600/(600+max(0,Def−pen)))`; attack-speed buckets;
  `move_damage = floor((base + slider*(Lv-1) + ratio*stat) × mit)`; `effective_cooldown` (CDR, 30% cap).
- **`stats.py`** — `Stats`: 5 core stats scaled by emblem % (`apply_core_pct`); `attack_speed`, `crit`,
  `penetration`, `cdr` are additive.
- **`builds.py`** — `make_build()` folds item Lv40 flats + item % passives + emblem page into total
  stats; flags `muscle_band`, `crit_multiplier`, `move_flat`. `maxed_tier_for` picks physical vs special
  by `damage_type`. Pools: `PHYSICAL_POOL` (8), `SPECIAL_POOL` (5), `BULK_POOL` (7).
- **`emblems.py`** — `optimal_page(target, rarity)` picks the best 10 of unite-db's 762 emblems for a
  target stat (real colors / grades A,B,C / stat tradeoffs + color-set bonuses); replaces the old template.
- **`abilities.py`** — `move_form(slot, level)` picks base/upgrade/enhanced by level; `form_damage` sums
  components × hits + execute true-damage + penetration; `burst_combo` returns actions + seconds.

## Data sources & non-obvious gotchas

- **unite-db raw JSON is the source.** `unite-db.com/pokemon.json` (moves incl. `upgrades` &
  `enhanced_*` fields, `ratio/base/slider/dmg_type`, `add1..5`, hit counts in `(Nx)` labels, execute in
  add `true_desc`), `/stats.json` (per-level stats incl. penetration/cdr), and `/emblems.json` (762
  emblems: up to 2 colors, grade A/B/C = gold/silver/bronze, stat tradeoffs). The unite-db *web pages
  are JS-rendered and unreadable*; the `/*.json` endpoints are raw. There is no `/moves.json` (404).
- **Move fields:** `ratio` is a PERCENT (75 → 0.75×); `slider` is the per-level term; `base` flat;
  `dmg_type` ∈ {Atk, SpAtk} picks the stat AND the mitigating defense. `parse_unitedb_moves.py` converts.
- **VALIDATION = Game8, not the reference engine.** The reference engine (`Stephen-Choi/...`) is **stale on
  rebalanced moves** (Electro Ball 0.66 vs unite-db's current 0.84). `validate.py` shows computed move
  damage matches Game8 within 0.4% (Pyro Ball exactly 1774); `tests/test_validation.py` enforces it.
- **Items/emblems from Game8.** Items cap Lv40 and Lv30→40 is non-linear — read real tables, never
  extrapolate. Muscle Band %HP bonus IS reduced by Defense (3% remaining, cap 360).
- **Off-stat investment does nothing:** a Sp.Atk build gives +0% to Attack autos; `make_build` routes by stat.
- **Known omissions (documented in README):** melee boosted 3rd hits, crit-damage scaling, CC; shields
  counted "up" (situational); a couple burn-DoT ratios differ ~2×.
- **The headline guardrail:** modeled combat power weakly predicts the meta tier (Spearman +0.06,
  `meta_validation.py`). The per-role tables are "hardest-hitting", not a tier list.

## Regenerating / adding data

Re-run the pipeline to refresh from unite-db. Edit `data/helditems.json` / `emblems.json` /
`battleitems.json` for Game8 item/emblem numbers; keep the schema (`stats.from_mapping` ignores unknown
keys, defaults missing to 0).
