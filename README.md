# Pokémon Unite — Stat Investment vs. Time-to-Kill

**Does maxing your account — Lv 40 held items, gold emblems, X Attack — let you delete people
*before they evolve*, regardless of which Pokémon you play?** Enemy builds are unobservable
in-game (no inspect, no scoreboard), so this answers it with a **model**: a damage /
time-to-kill engine built from *current, validated* stats and the game's verified damage
formula, then run across the entire 94-Pokémon roster.

**Short answer: yes — maxed investment roughly *halves* how fast you're deleted pre-evolution,
and it holds regardless of Pokémon.**

## TL;DR

- 📉 **~48% faster kills.** Across 69 offensive Pokémon at Lv 4 (pre-evo), a maxed build deletes
  an un-invested squishy in **22.4 → 11.1 actions** on average.
- 🧪 **Validated data.** Move ratios and per-level stats come from [unite-db](https://unite-db.com)'s
  raw JSON (the Mathcord-sourced data its own site uses), cross-checked *exactly* against an
  open-source reference engine and Game8. **20 tests green.**
- 🏆 **Per-role optimizer.** Brute-forces every item build per mon to find the best Pokémon +
  build for each role (below).

## 🏆 Best Pokémon & build per role

The optimizer searches every legal 3-item combo × emblem template per Pokémon (a maxed account)
and ranks within each role — offense by **burst** and **sustained DPS**, tanks/supports by
**effective HP**:

![Best Pokémon and build per role](figures/best_per_role.png)

<details>
<summary>Per-role detail charts (burst · DPS · survivability)</summary>

![Top burst by role](figures/phase2_burst.png)
![Top DPS by role](figures/phase2_dps.png)
![Survivability](figures/phase2_survivability.png)

</details>

> "Best by **modeled combat metric**" — it doesn't credit range, mobility, CC, or objective
> control. Modeled at Lv 5 (pre-evo), the window where unite-db's base-move data is exact.

## 📉 Headline finding — investment ~halves pre-evo time-to-kill

A **maxed attacker vs. an un-invested squishy**, basic attacks only, pre-evolution:

| @ Lv 3 | un-invested | maxed | reduction |
|--------|------------:|------:|----------:|
| Cinderace | 24 hits / 23.0 s | 13 hits / 11.2 s | **46% / 51%** |
| Zeraora   | 18 hits / 17.0 s | 11 hits /  9.3 s | **39% / 45%** |
| Pikachu   | 24 hits / 23.0 s | 13 hits / 11.2 s | **46% / 51%** |

![Hits to kill, maxed vs un-invested](figures/phase1_hits_to_kill.png)

Fold in abilities (real move ratios) and the fastest maxed pre-evo deletes the model surfaces are
**Mega-Gyarados, Gyarados, Zacian, Urshifu** — exactly the early-game bullies people complain about.

## 🔬 What actually drives the "deleted in a few hits"

Moves carry a big flat/level base + a sub-1.0 stat ratio, so investment is **diluted on abilities
but full on auto-attacks**:

| damage source | un-invested → maxed |
|---|---|
| abilities | **+18–22%** |
| auto-attacks | **+40–50%** |
| off-stat (e.g. Attack on a Sp.Atk build) | **+0%** |

So pre-evo "delete" pressure is **level + ability choice** *plus* — especially against
auto-attackers — **item/emblem investment**.

## Sources & verification

- **Stats + move scaling — [unite-db](https://unite-db.com) raw JSON** (`/pokemon.json`,
  `/stats.json`): the Mathcord-sourced data the site itself loads, for all 94 Pokémon (per-level
  stats; per-move `base + slider×(Lv−1) + ratio×stat`). unite-db's *pages* are JS-rendered
  (unreadable to a fetcher) — the `/*.json` endpoints are raw. Cached in `data/unite_db_*.json`.
- **Held/battle items + emblems — [Game8](https://game8.co/games/Pokemon-UNITE/)** (Lv40 item
  tables, emblem rarity + color sets), current to patch **v1.21.1.8 (2026-05-14)**.
- **Damage formula — reference engine** [`Stephen-Choi/pokemon-unite-damage-calculator`](https://github.com/Stephen-Choi/pokemon-unite-damage-calculator):
  mitigation `floor(atk × 600/(600+Def))` + attack-speed buckets, taken **verbatim**.
- **Validated:** unite-db's Pikachu Thunder Shock `0.75×SpAtk + 21×(Lv−1) + 390` reproduces the
  reference engine *exactly*; unite-db stats match Game8 (current Lv6 Def 80). `tests/` reproduce
  the formula, Blastoise 35%, the attack-speed buckets, the Muscle Band cap, and the move formula —
  **20 tests green**.

## Run

```bash
pip install -r requirements.txt
python -m pytest tests/ -q               # verify engine + move formulas (20 tests)
python src/analysis.py                   # Phase 1: hits-to-kill chart (autos)
python src/abilities.py                  # roster-wide pre-evo burst (moves + autos)
python src/optimize.py                   # Phase 2: per-role optimizer + charts + data/phase2_offense.csv

# Refresh data from unite-db (re-cache + regenerate the derived files):
python src/fetch_unitedb.py              # -> data/unite_db_pokemon.json
python src/parse_unitedb_moves.py        # -> data/moves.json   (roster move ratios)
python src/build_pokemon_from_unitedb.py # -> data/pokemon.json (94 mons, per-level stats)
```

## Project layout

```
data/
  unite_db_pokemon.json / unite_db_stats.json   raw unite-db snapshot (source of truth)
  pokemon.json / moves.json                      generated: 94-mon stats + move ratios
  helditems.json / battleitems.json / emblems.json   Game8: items + emblems
src/
  stats.py       Stats algebra
  damage.py      verified engine (mitigation, attack-speed, basic, move, TTK/DPS, EHP)
  builds.py      build assembly (item pools + emblem templates + investment tiers)
  abilities.py   move / burst-combo modelling (roster-wide)
  analysis.py    Phase 1 charts
  optimize.py    Phase 2 per-role optimizer + charts
  fetch_unitedb.py · parse_unitedb_moves.py · build_pokemon_from_unitedb.py   data pipeline
tests/    engine + move-formula verification
figures/  exported charts
```

## Status & caveats

- ✅ **Phase 1** mechanism proof · ✅ **Phase 1b** abilities + X Attack (roster-wide) ·
  ✅ **Phase 2** per-role optimizer (item pools: 8 physical / 5 special / 7 bulk) ·
  ⬜ **Phase 3** personal match log (planned).
- unite-db's static endpoint lists the **pre-evo kit** (passive + basic + 2 base moves + Unite
  move); the **Lv5/7 upgrade moves aren't there**, so move metrics are exact pre-evo and a floor
  post-evo. Melee boosted (every-3rd) basics aren't modeled roster-wide.
- Crit base multiplier assumed 2.0 (+Scope Lens); X Attack move multiplier uses the 1.10 midpoint
  of the documented 1.05–1.15 range.
