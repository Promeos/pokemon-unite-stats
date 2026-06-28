"""Phase 1 analysis: does a maxed build (Lv40 items + gold emblems) knock you out
faster pre-evolution, and by how much, regardless of Pokemon?

Scenario: a MAXED attacker vs. an UN-INVESTED squishy target (models "a fed/maxed
opponent knocking out un-invested me"). Metric: basic-attack hits-to-KO and
seconds-to-KO. Basic-attacks only (ability/boosted-attack burst is additive and
not modelled here) -- so absolute counts are an upper bound; the RELATIVE effect of
investment is the result.
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from builds import hits_between, load_data, tier_build, ttko_between

OFFENSIVE = ["cinderace", "zeraora", "pikachu"]
PRE_EVO_LEVELS = [1, 2, 3, 4, 5, 6]
FIG_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "figures")
DATA_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "data")

# Un-invested squishy reference target (attacker-tier bulk = Cinderace base line).
TARGET = "cinderace"


def investment_table(data: dict) -> pd.DataFrame:
    """Hits- and seconds-to-KO (un-invested vs maxed attacker) for each reference Pokemon
    across the pre-evo levels, with the reductions investment buys."""
    rows = []
    for mon in OFFENSIVE:
        for lvl in PRE_EVO_LEVELS:
            target = tier_build(data, TARGET, lvl, "uninvested")
            bare = tier_build(data, mon, lvl, "uninvested")
            maxed = tier_build(data, mon, lvl, "maxed_attacker")
            h0, h1 = hits_between(bare, target), hits_between(maxed, target)
            t0, t1 = ttko_between(bare, target), ttko_between(maxed, target)
            rows.append(dict(
                pokemon=mon, level=lvl,
                hits_uninvested=h0, hits_maxed=h1, hits_saved=h0 - h1,
                hits_reduction_pct=round(100 * (h0 - h1) / h0, 1),
                ttko_uninvested=round(t0, 2), ttko_maxed=round(t1, 2),
                ttko_reduction_pct=round(100 * (t0 - t1) / t0, 1) if t0 else 0.0,
            ))
    return pd.DataFrame(rows)


def plot_hits(df: pd.DataFrame) -> str:
    """Chart hits-to-KO vs level, maxed against un-invested, per reference Pokemon; returns
    the saved figure path."""
    fig, axes = plt.subplots(1, len(OFFENSIVE), figsize=(13, 4), sharey=True)
    for ax, mon in zip(axes, OFFENSIVE):
        d = df[df.pokemon == mon]
        ax.plot(d.level, d.hits_uninvested, "o-", color="#888", label="un-invested")
        ax.plot(d.level, d.hits_maxed, "o-", color="#d62728", label="MAXED (Lv40 items + gold emblems)")
        ax.set_title(mon.capitalize())
        ax.set_xlabel("Level")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("Basic attacks to knock out a squishy")
    axes[0].legend(fontsize=8)
    fig.suptitle("Pre-evolution: maxed vs un-invested — basic-attack hits to knock out an un-invested target", fontsize=11)
    fig.tight_layout()
    os.makedirs(FIG_DIR, exist_ok=True)
    path = os.path.join(FIG_DIR, "auto_attack_hits_to_ko.png")
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def main():
    data = load_data()
    df = investment_table(data)
    out_csv = os.path.join(DATA_DIR, "auto_attack_results.csv")
    df.to_csv(out_csv, index=False)
    fig_path = plot_hits(df)

    pd.set_option("display.width", 120)
    print(df.to_string(index=False))
    print()
    lvl3 = df[df.level == 3]
    print("=== Headline @ Lv3 (pre-evo) - hits to knock out an un-invested squishy ===")
    for _, r in lvl3.iterrows():
        print(f"  {r.pokemon.capitalize():10s}: {int(r.hits_uninvested):2d} -> {int(r.hits_maxed):2d} hits "
              f"({r.hits_reduction_pct:.0f}% fewer),  {r.ttko_uninvested:.1f}s -> {r.ttko_maxed:.1f}s")
    print(f"\nMean hits-reduction across Lv1-6, all mons: {df.hits_reduction_pct.mean():.1f}%")
    print(f"Mean TTKO-reduction across Lv1-6, all mons: {df.ttko_reduction_pct.mean():.1f}%")
    print(f"\nSaved: {out_csv}\n       {fig_path}")


if __name__ == "__main__":
    main()
