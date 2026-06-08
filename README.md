# Pokémon Unite — Stat Investment vs. Time-to-Kill

Does maxing **held items** (Lv 40), **emblems** (gold rarity + color sets), and a **battle
item** (X Attack) let an opponent delete you faster *before your first evolution* —
regardless of which Pokémon they play? Enemy builds are **unobservable in-game** (no
inspect/scoreboard), so this proves the *mechanism* with a damage / time-to-kill model
built from current, validated stats and the game's verified damage formula.

## Headline finding

**Pre-evo (Lv 4) burst — base moves + auto-attacks — maxed vs. un-invested, in *actions to
kill* an un-invested squishy:**

| | un-invested | maxed + X Attack |
|---|------------:|-----------------:|
| Cinderace (Attacker)    | 22 | **11** |
| Zeraora (Speedster)     | 16 | **9**  |
| Buzzwole (All-Rounder)  | 14 | **8**  |
| Pikachu (Sp. Attacker)  | 19 | **14** |

**Across all 69 offensive Pokémon: mean 22.4 → 11.1 actions — a 47.9% reduction.** Maxed
items + emblems + X Attack **roughly halve** how fast you're deleted pre-evolution, and the
effect is **consistent regardless of Pokémon**. (Sanity check: the fastest maxed pre-evo
deletes the model surfaces are **Mega-Gyarados, Gyarados, Zacian, Urshifu** — the real
early-game bullies.)

**Which lever does the work:** moves carry a big flat/level base + a sub-1.0 stat ratio, so
investment is *diluted* on ability burst (~+20%) but *full* on auto-attacks (~+40–50%). So
pre-evo "delete" pressure comes from **level + ability choice** *and* — especially against
auto-attackers — **item/emblem investment**.

## Sources & verification

- **Stats + move scaling — [unite-db](https://unite-db.com) raw JSON** (`/pokemon.json`,
  `/stats.json`): the Mathcord-sourced data the site itself loads, for **all 94 Pokémon**
  (per-level stats; per-move `base + slider×(Lv−1) + ratio×stat`). Cached in `data/unite_db_*.json`.
  The unite-db *pages* are JS-rendered (unreadable to a fetcher) — the `/*.json` endpoints are raw.
- **Held/battle items + emblems — [Game8](https://game8.co/games/Pokemon-UNITE/)** (Lv40 item
  tables, emblem rarity + color sets), current to patch **v1.21.1.8 (2026-05-14)**.
- **Damage formula — reference engine** [`Stephen-Choi/pokemon-unite-damage-calculator`](https://github.com/Stephen-Choi/pokemon-unite-damage-calculator):
  mitigation `floor(atk × 600/(600+Def))` + attack-speed buckets, taken **verbatim**.
- **Validated:** unite-db's Pikachu Thunder Shock `0.75×SpAtk + 21×(Lv−1) + 390` reproduces
  the reference engine *exactly*; unite-db stats match Game8 (current Lv6 Def 80, not the stale
  65). `tests/` reproduce the formula, Blastoise 35%, attack-speed buckets, Muscle Band cap,
  and the move formula — **20 tests green**.

## Run

```bash
pip install -r requirements.txt
python -m pytest tests/ -q               # verify engine + move formulas (20 tests)
python src/analysis.py                   # Phase 1: hits-to-kill chart (autos)
python src/abilities.py                  # roster-wide pre-evo burst (moves + autos)
python src/optimize.py                   # Phase 2: best build & Pokemon per role (+ data/phase2_offense.csv)

# Refresh data from unite-db (re-cache + regenerate the derived files):
python src/fetch_unitedb.py              # -> data/unite_db_pokemon.json
python src/parse_unitedb_moves.py        # -> data/moves.json   (roster move ratios)
python src/build_pokemon_from_unitedb.py # -> data/pokemon.json (94 mons, per-level stats)
```

## Layout

```
data/
  unite_db_pokemon.json / unite_db_stats.json   raw unite-db snapshot (source of truth)
  pokemon.json / moves.json                      generated: 94-mon stats + move ratios
  helditems.json / battleitems.json / emblems.json   Game8: items + emblems
src/
  stats.py       Stats algebra
  damage.py      verified engine (mitigation, attack-speed, basic, move, TTK/DPS, EHP)
  builds.py      build assembly (items + emblem templates + investment tiers)
  abilities.py   move / burst-combo modelling (roster-wide)
  analysis.py    Phase 1 charts
  fetch_unitedb.py · parse_unitedb_moves.py · build_pokemon_from_unitedb.py   data pipeline
tests/    engine + move-formula verification
figures/  exported charts
```

## Status

- **Phase 1 — mechanism proof:** ✅ engine + headline chart (`src/analysis.py`).
- **Phase 1b — abilities + X Attack, roster-wide:** ✅ real move ratios for 94 mons (`src/abilities.py`).
- **Phase 2 — best build & Pokémon per role:** ✅ `src/optimize.py` — brute-forces item triples ×
  emblem templates per mon; ranks offense by Burst & DPS, tanks/supports by effective HP (Lv5 pre-evo).
- **Phase 3 — personal match log:** planned.

## Caveats / to refine

- unite-db's static endpoint lists the **pre-evo kit** (passive + basic + 2 base moves + Unite
  move); the **Lv5/7 upgrade moves aren't there**. Fine for the pre-evo question; post-evo burst
  would need them.
- **Melee boosted (every-3rd) basics** aren't in unite-db (only the reference engine has them);
  not yet modelled roster-wide.
- Crit base multiplier assumed 2.0 (+Scope Lens); X Attack move multiplier uses the 1.10 midpoint
  of the documented 1.05–1.15 range.
