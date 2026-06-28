"""Defensive held-item breakdown: raw Lv40 stats + %-based passive effects + EHP gain.

For a chosen Pokemon, lists every held item that modifies HP / Defense / Sp.Def
(auto-detected from data/helditems.json), and for each shows:
  * its Lv40 flat stats (HP / Def / Sp.Def),
  * its percentage-based passive "text effect" (shields, reflect, lifesteal, heals),
  * the *marginal* effective HP it buys on that Pokemon, physical and special.

EHP recap (damage.effective_hp): EHP = HP * (1 + Defense/600) -- the pre-mitigation
damage needed to drop the target. Defense guards the physical EHP, Sp.Def the special
EHP; raw HP lifts both. An item that gives HP *and* a defense stat stacks
multiplicatively, so e.g. Rocky Helmet's marginal EHP beats the sum of its HP-only and
Def-only parts. Each item's gain is (EHP with the item) - (baseline EHP), so the synergy
with the baseline's defenses is captured.

Held items are Lv40 (account-wide), so this models a fully-maxed account at the chosen
in-game level (default Lv15, where a Defender is fully online).

Emblems are a separate lever, off by default. Pass --emblems (e.g. max_bulk) to fold an
emblem page into the baseline: items are then measured on top of the page (their realistic
marginal value in a full build), and an extra line reports what the page itself buys. The
page's flats AND its color-set percent bonuses are applied via builds.make_build.

Outputs a table to stdout, data/defensive_items_<mon>.csv, and a two-panel figure
figures/defensive_items_<mon>.png (per-item physical-vs-special EHP, and total defensive
value with shields).

Usage:
    python src/defensive_items.py                          # Crustle @ Lv15, no emblems
    python src/defensive_items.py snorlax --level 9
    python src/defensive_items.py --emblems max_bulk        # items on top of a bulk page
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

import damage
import emblems
from builds import emblem_page, load_data, make_build
from stats import from_mapping

DATA_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "data")
FIG_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "figures")

# Chart colors: physical/Def, special/Sp.Def, guaranteed EHP, situational shields.
PHYS_COLOR, SPEC_COLOR = "#1f77b4", "#9467bd"
EHP_COLOR, SHIELD_COLOR = "#2ca02c", "#e6a817"

# Stats that make an item "defensive" for this breakdown.
DEF_STATS = ("hp", "defense", "sp_def")
_PCT_LABEL = {"hp": "HP", "defense": "Def", "sp_def": "Sp.Def"}

# A balanced example loadout used to show how the items stack (HP + Def + Sp.Def + shields).
EXAMPLE_TRIO = ["buddy_barrier", "rocky_helmet", "assault_vest"]


# --------------------------------------------------------------------------- #
# Item selection + passive text
# --------------------------------------------------------------------------- #
def defensive_items(items: dict) -> list[str]:
    """Keys of every held item whose Lv40 stats touch HP, Defense, or Sp.Def."""
    return [k for k, it in items.items()
            if not k.startswith("_")
            and any(it.get("stats_lv40", {}).get(s, 0) for s in DEF_STATS)]


def shield_pct(passive: dict) -> float:
    """Self-shield as a fraction of max HP, or 0 if this passive isn't a %-HP shield.
    Mirrors optimize.shield_pct's list handling (Assault Vest scales 10/15/20% -> take max)."""
    if "shield" not in (passive.get("type") or ""):
        return 0.0
    v = passive.get("pct_max_hp")
    if isinstance(v, list):
        v = v[-1]
    return float(v or 0.0)


def passive_text(passive: dict) -> str:
    """Human, percentage-bearing description of an item's passive (the in-game 'text effect')."""
    t = passive.get("type")
    if t == "shield_on_unite":
        return f"Shield {passive['pct_max_hp']:.0%} of max HP to self + nearest ally on Unite Move"
    if t == "shield_on_score":
        return f"Shield {passive['pct_max_hp']:.0%} of max HP while scoring a goal"
    if t == "shield_on_damage":  # Resonant Guard: % not pinned in Game8 archive / repo data
        return f"Shield to self + nearby ally when dealing damage ({passive.get('cooldown_s', 0):.0f}s CD; % not pinned)"
    if t == "special_shield":
        tiers = "/".join(f"{v:.0%}" for v in passive["pct_max_hp"])
        return (f"Special-damage shield {tiers} of max HP "
                f"after {passive.get('no_spatk_damage_s', 0):.0f}s without taking special damage")
    if t == "reflect":  # value is a % of the ATTACKER's max HP, not the holder's (Game8)
        return f"Reflect {passive['pct_target_max_hp']:g}% of the ATTACKER's max HP back when hit"
    if t == "lifesteal":
        return f"{passive['pct']:.0%} lifesteal of damage dealt"
    if t == "heal_low_hp":
        return f"Recover {passive['pct_lost_per_sec']:g}% of lost HP per second for 3s when low"
    if t == "attack_on_hit_taken":
        tot = passive["pct_per_stack"] * passive["max_stacks"]
        return (f"+{passive['pct_per_stack']:g}% Attack per hit taken, "
                f"up to {passive['max_stacks']} stacks (+{tot:g}%)")
    if t == "hp_on_score":
        return f"+{passive['per_goal']:g} max HP per goal, up to {passive['max_stacks']} stacks (flat, not %)"
    return t or "-"


# --------------------------------------------------------------------------- #
# EHP breakdown
# --------------------------------------------------------------------------- #
def _ehp(build) -> tuple[float, float]:
    """(physical EHP, special EHP) of a build — damage.effective_hp vs Def and Sp.Def."""
    return (damage.effective_hp(build.total.hp, build.total.defense),
            damage.effective_hp(build.total.hp, build.total.sp_def))


def item_rows(data: dict, pokemon: str, level: int,
              emb: str = "none", rarity: str = "gold") -> tuple[dict, list[dict]]:
    """Baseline survivability + one row per defensive item (marginal EHP on top of the
    baseline, which is base stats plus the emblem page when `emb` != 'none')."""
    items = data["items"]
    baseline = make_build(data, pokemon, level, [], emb, rarity)
    base_phys, base_spec = _ehp(baseline)

    rows = []
    for key in defensive_items(items):
        it = items[key]
        fl = from_mapping(it.get("stats_lv40", {}))
        b = make_build(data, pokemon, level, [key], emb, rarity)
        phys, spec = _ehp(b)
        d_phys, d_spec = phys - base_phys, spec - base_spec
        passive = it.get("passive", {})
        rows.append({
            "pokemon": pokemon, "level": level,
            "emblems": emb, "rarity": rarity if emb != "none" else "-",
            "key": key, "item": it["display_name"],
            "hp": fl.hp, "defense": fl.defense, "sp_def": fl.sp_def,
            "d_ehp_phys": round(d_phys), "d_ehp_spec": round(d_spec),
            "d_ehp_avg": round((d_phys + d_spec) / 2),
            "shield_hp": round(shield_pct(passive) * b.total.hp),
            "passive": passive_text(passive),
        })
    rows.sort(key=lambda r: -r["d_ehp_avg"])
    base_info = {
        "hp": baseline.total.hp, "defense": baseline.total.defense, "sp_def": baseline.total.sp_def,
        "ehp_phys": round(base_phys), "ehp_spec": round(base_spec),
    }
    return base_info, rows


def emblem_info(data: dict, pokemon: str, level: int, emb: str, rarity: str) -> dict | None:
    """What the emblem page itself buys (vs the bare Pokemon): net flats, color-set %, and
    the EHP gain. None when `emb` == 'none'."""
    if emb == "none":
        return None
    bare = make_build(data, pokemon, level, [], "none")
    paged = make_build(data, pokemon, level, [], emb, rarity)
    bare_phys, bare_spec = _ehp(bare)
    paged_phys, paged_spec = _ehp(paged)
    flat, pct = emblem_page(emb, rarity)
    return {
        "summary": emblems.page_summary(emb, rarity),
        "bare_hp": bare.total.hp, "bare_def": bare.total.defense, "bare_spdef": bare.total.sp_def,
        "bare_phys": round(bare_phys), "bare_spec": round(bare_spec),
        "flat_hp": flat.hp, "flat_def": flat.defense, "flat_spdef": flat.sp_def,
        "pct": {k: getattr(pct, k) for k in ("hp", "defense", "sp_def") if getattr(pct, k)},
        "d_phys": round(paged_phys - bare_phys), "d_spec": round(paged_spec - bare_spec),
    }


def example_stack(data: dict, pokemon: str, level: int, items: list[str],
                  emb: str = "none", rarity: str = "gold") -> dict:
    """Combined EHP + shields-up of a fixed bulk trio (plus the emblem page if set)."""
    b = make_build(data, pokemon, level, items, emb, rarity)
    phys, spec = _ehp(b)
    shield = sum(shield_pct(data["items"][k].get("passive", {})) for k in items) * b.total.hp
    return {"hp": b.total.hp, "defense": b.total.defense, "sp_def": b.total.sp_def,
            "ehp_phys": round(phys), "ehp_spec": round(spec), "shield_hp": round(shield)}


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def _s(v: float) -> str:
    """Format a flat stat: integer-ish without trailing .0, blank-dot for zero."""
    return "·" if not v else f"{v:g}"


def _c(v: float) -> str:
    """Comma int, blank-dot for zero."""
    return "·" if not v else f"{round(v):,}"


def _print_baseline(emb: str, rarity: str, base: dict, einfo: dict | None) -> None:
    if einfo is None:
        print(f"Base: HP {base['hp']:,.0f} · Def {base['defense']:,.0f} · Sp.Def {base['sp_def']:,.0f}"
              f"   →  physical EHP {base['ehp_phys']:,} · special EHP {base['ehp_spec']:,}")
        print("      (EHP = HP × (1 + Def/600); Def → physical EHP, Sp.Def → special EHP)\n")
        return
    print(f"Base (bare): HP {einfo['bare_hp']:,.0f} · Def {einfo['bare_def']:,.0f} · Sp.Def {einfo['bare_spdef']:,.0f}"
          f"   →  phys EHP {einfo['bare_phys']:,} · spec EHP {einfo['bare_spec']:,}")
    pctstr = ""
    if einfo["pct"]:
        pctstr = " + color-set " + ", ".join(f"{v:g}% {_PCT_LABEL[k]}" for k, v in einfo["pct"].items())
    print(f"+ Emblems [{emb}, {rarity}] ({einfo['summary']}): net flats "
          f"HP {einfo['flat_hp']:+,.0f} · Def {einfo['flat_def']:+g} · Sp.Def {einfo['flat_spdef']:+g}{pctstr}")
    print(f"  →  baseline HP {base['hp']:,.0f} · Def {base['defense']:,.0f} · Sp.Def {base['sp_def']:,.0f}"
          f"   →  phys EHP {base['ehp_phys']:,} (+{einfo['d_phys']:,}) · spec EHP {base['ehp_spec']:,} (+{einfo['d_spec']:,})")
    print("  (item ΔEHP below are measured on top of this emblem baseline)\n")


def print_report(pokemon: str, level: int, emb: str, rarity: str,
                 base: dict, einfo: dict | None, rows: list[dict], stack: dict) -> None:
    disp = pokemon.replace("_", " ").title()
    extra = f" + {rarity} {emb} emblems" if emb != "none" else ""
    print(f"Defensive held-item breakdown — {disp} @ Lv{level}  (Lv40 maxed items{extra})")
    _print_baseline(emb, rarity, base, einfo)

    print(f"  {'Item':<16}{'HP':>5}{'Def':>6}{'SpD':>6}{'ΔEHP_ph':>10}{'ΔEHP_sp':>10}"
          f"{'Shield':>8}  Passive (%-based text effect)")
    print("  " + "-" * 116)
    for r in rows:
        print(f"  {r['item']:<16}{_s(r['hp']):>5}{_s(r['defense']):>6}{_s(r['sp_def']):>6}"
              f"{_c(r['d_ehp_phys']):>10}{_c(r['d_ehp_spec']):>10}{_c(r['shield_hp']):>8}  {r['passive']}")

    ref_phys = einfo["bare_phys"] if einfo else base["ehp_phys"]
    ref_spec = einfo["bare_spec"] if einfo else base["ehp_spec"]
    pretty = " + ".join(r["item"] for r in rows if r["key"] in EXAMPLE_TRIO)
    emb_lab = f" + {emb} emblems" if emb != "none" else ""
    dp = (stack["ehp_phys"] / ref_phys - 1) * 100
    ds = (stack["ehp_spec"] / ref_spec - 1) * 100
    print(f"\nExample bulk build — {pretty}{emb_lab}:")
    print(f"  HP {stack['hp']:,.0f} · Def {stack['defense']:,.0f} · Sp.Def {stack['sp_def']:,.0f}")
    print(f"  Physical EHP {stack['ehp_phys']:,} (+{dp:.0f}% vs bare) · "
          f"Special EHP {stack['ehp_spec']:,} (+{ds:.0f}% vs bare)")
    print(f"  + shields up: ~{stack['shield_hp']:,} HP absorbed (situational, 'counted up')")


def write_csv(pokemon: str, rows: list[dict]) -> str:
    out = os.path.join(DATA_DIR, f"defensive_items_{pokemon}.csv")
    cols = ["pokemon", "level", "emblems", "rarity", "key", "item", "hp", "defense", "sp_def",
            "d_ehp_phys", "d_ehp_spec", "d_ehp_avg", "shield_hp", "passive"]
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return out


def make_chart(pokemon: str, level: int, emb: str, rarity: str, rows: list[dict]) -> str:
    """Two-panel figure: per-item physical-vs-special EHP (diverging) and total defensive
    value with shields (stacked). matplotlib is imported lazily so the module stays light."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    os.makedirs(FIG_DIR, exist_ok=True)
    disp = pokemon.replace("_", " ").title()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.6))

    # ---- Left: diverging — physical EHP extends left, special EHP extends right ----
    rr = sorted(rows, key=lambda r: r["d_ehp_avg"])  # ascending -> biggest ends on top in barh
    ys = list(range(len(rr)))
    max_ph = max((r["d_ehp_phys"] for r in rr), default=1) or 1
    max_sp = max((r["d_ehp_spec"] for r in rr), default=1) or 1
    ax1.barh(ys, [-r["d_ehp_phys"] for r in rr], color=PHYS_COLOR, height=0.72, label="physical EHP (vs Def)")
    ax1.barh(ys, [r["d_ehp_spec"] for r in rr], color=SPEC_COLOR, height=0.72, label="special EHP (vs Sp.Def)")
    ax1.axvline(0, color="#333333", lw=0.9)
    ax1.set_yticks(ys)
    ax1.set_yticklabels([r["item"] for r in rr], fontsize=9)
    for i, r in enumerate(rr):
        ax1.text(-r["d_ehp_phys"] - max_ph * 0.02, i, f"{r['d_ehp_phys']:,}", va="center", ha="right", fontsize=7)
        ax1.text(r["d_ehp_spec"] + max_sp * 0.02, i, f"{r['d_ehp_spec']:,}", va="center", ha="left", fontsize=7)
    ax1.set_xlim(-max_ph * 1.2, max_sp * 1.2)
    ax1.xaxis.set_major_formatter(FuncFormatter(lambda x, *_: f"{abs(int(x)):,}"))
    ax1.tick_params(axis="x", labelsize=7)
    ax1.set_xlabel("←  physical EHP added           special EHP added  →", fontsize=9)
    ax1.set_title("Effective HP each item adds — physical vs special", fontsize=10)
    ax1.legend(fontsize=8, loc="lower right", framealpha=0.9)

    # ---- Right: total defensive value — guaranteed avg EHP + situational shield ----
    rr2 = sorted(rows, key=lambda r: r["d_ehp_avg"] + r["shield_hp"])
    ys2 = list(range(len(rr2)))
    avg = [r["d_ehp_avg"] for r in rr2]
    shd = [r["shield_hp"] for r in rr2]
    ax2.barh(ys2, avg, color=EHP_COLOR, height=0.72, label="avg stat EHP (guaranteed)")
    ax2.barh(ys2, shd, left=avg, color=SHIELD_COLOR, height=0.72, hatch="//",
             edgecolor="white", label="shield HP (situational)")
    ax2.set_yticks(ys2)
    ax2.set_yticklabels([r["item"] for r in rr2], fontsize=9)
    tmax = max((a + s for a, s in zip(avg, shd)), default=1) or 1
    for i, (a, s) in enumerate(zip(avg, shd)):
        label = f"{a + s:,}" + (f"  (+{s:,} shield)" if s else "")
        ax2.text(a + s + tmax * 0.01, i, label, va="center", ha="left", fontsize=7)
    ax2.set_xlim(0, tmax * 1.26)
    ax2.tick_params(axis="x", labelsize=7)
    ax2.xaxis.set_major_formatter(FuncFormatter(lambda x, *_: f"{int(x):,}"))
    ax2.set_xlabel("effective HP (avg of physical & special) + shields up", fontsize=9)
    ax2.set_title("Total defensive value — stat EHP + shields", fontsize=10)
    ax2.legend(fontsize=8, loc="lower right", framealpha=0.9)

    tag = f"{disp} @ Lv{level}" + (f"  ·  + {rarity} {emb} emblems" if emb != "none" else "")
    fig.suptitle(f"Defensive held items — what each buys for {tag}", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    path = os.path.join(FIG_DIR, f"defensive_items_{pokemon}.png")
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


def main() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure:  # the report uses ×, →, Δ, · — keep them legible on Windows cp1252 consoles
        reconfigure(encoding="utf-8")

    data = load_data()
    ap = argparse.ArgumentParser(description="Defensive held-item EHP breakdown for a Pokemon.")
    ap.add_argument("pokemon", nargs="?", default="crustle",
                    help="Pokemon key (default: crustle). e.g. snorlax, blastoise, slowbro")
    ap.add_argument("--level", type=int, default=15, help="In-game level 1-15 (default: 15)")
    ap.add_argument("--emblems", default="none", choices=["none", *emblems.TEMPLATE_TARGET],
                    help="Emblem page to fold into the baseline (default: none; max_bulk for defense)")
    ap.add_argument("--rarity", default="gold", choices=["gold", "silver", "bronze"],
                    help="Emblem grade when --emblems is set (default: gold)")
    args = ap.parse_args()

    key = args.pokemon.lower()
    if key not in data["pokemon"]:
        avail = ", ".join(sorted(k for k in data["pokemon"] if not k.startswith("_")))
        raise SystemExit(f"Unknown Pokemon {key!r}. Available:\n{avail}")
    if str(args.level) not in data["pokemon"][key]["stats_by_level"]:
        raise SystemExit(f"Level {args.level} out of range for {key} (have 1-15).")

    base, rows = item_rows(data, key, args.level, args.emblems, args.rarity)
    einfo = emblem_info(data, key, args.level, args.emblems, args.rarity)
    stack = example_stack(data, key, args.level, EXAMPLE_TRIO, args.emblems, args.rarity)
    print_report(key, args.level, args.emblems, args.rarity, base, einfo, rows, stack)
    out = write_csv(key, rows)
    chart = make_chart(key, args.level, args.emblems, args.rarity, rows)
    print(f"\nSaved: {out}\n       {chart}")


if __name__ == "__main__":
    main()
