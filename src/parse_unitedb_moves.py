"""Parse unite-db's cached pokemon.json into a clean per-Pokemon move dataset.

unite-db stores each move's damage as {ratio, base, slider, dmg_type} (+ add1..add5 for
multi-component hits). Each base move also carries `upgrades` (the Lv5/7 options), and each
upgrade an `enhanced_*` (Lv11/13) form. Labels encode hit counts as "(Nx)"; true-damage
execute components appear as add-fields with exception=True and a "% of enemy missing/
remaining HP" description.

Damage model (per component): base + slider*(level-1) + ratio*stat[dmg_type], times `hits`,
then mitigated by the target's Def/Sp.Def. VALIDATED: Pikachu Thunder Shock 0.75*SpAtk +
21*(Lv-1) + 390 reproduces the reference engine exactly. (Note: the reference engine is STALE
on some rebalanced moves, e.g. Electro Ball; we trust unite-db, validated vs Game8 totals.)

Output schema (data/moves.json):
  "<key>": {display_name, role, damage_type,
            basic: {dmg_type, ratio},
            moves: { "<slot>": {display_name, is_unite,
                                base: FORM,                       # Lv1-3
                                upgrades: [ {name, min_level, enh_level, FORM,
                                             enhanced: FORM|null} ]}}}
  FORM = {cooldown, components: [{ratio, base, slider, dmg_type, hits}],
          execute: [{pct, of: missing|remaining|current|max}]}
"""
import json
import os
import re

DATA = os.path.join(os.path.dirname(__file__), os.pardir, "data")


def key(name):
    """Slugify a Pokemon/move name into a snake_case dict key (e.g. 'Mr. Mime' -> 'mr_mime')."""
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def _num(x):
    """Parse unite-db's string-typed numeric fields to float, defaulting blanks/junk to 0.0."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _hits(label):
    """Hit count encoded in a component label as '(Nx)' (e.g. 'Damage (3x)' -> 3); default 1."""
    m = re.search(r"\((\d+)\s*x\)", str(label or ""), re.I)
    return int(m.group(1)) if m else 1


def _execute(true_desc):
    """Parse a true-damage execute description ('8% of enemy missing HP') into
    {pct, of: missing|remaining|current|max}, or None if it isn't an execute component."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*of\s*(?:enemy\s*|target'?s?\s*)?"
                  r"(missing|remaining|current|max)\s*HP", str(true_desc or ""), re.I)
    return {"pct": float(m.group(1)) / 100.0, "of": m.group(2).lower()} if m else None


def extract_form(rsb, prefix, cooldown):
    """Pull damage + execute components from a rsb dict using the given field prefix."""
    g = lambda f: rsb.get(prefix + f, "")
    dmg, execs = [], []

    def one(lbl, ratio, base, slider, dt, exc, td):
        if dt in ("Atk", "SpAtk") and (ratio not in ("", None) or base not in ("", None)):
            c = {"ratio": _num(ratio) / 100.0, "base": _num(base),
                 "slider": _num(slider), "dmg_type": dt, "hits": _hits(lbl)}
            if c["ratio"] or c["base"]:
                dmg.append(c)
        elif str(exc).lower() == "true":
            ex = _execute(td)
            if ex:
                execs.append(ex)

    one(g("label"), g("ratio"), g("base"), g("slider"), g("dmg_type"), g("exception"), g("true_desc"))
    for n in range(1, 6):
        p = f"add{n}_"
        one(g(p + "label"), g(p + "ratio"), g(p + "base"), g(p + "slider"),
            g(p + "dmg_type"), g(p + "exception"), g(p + "true_desc"))
    return {"cooldown": cooldown, "components": dmg, "execute": execs}


def move_slot(skill):
    """Parse one skill into (base form, [upgrade forms]); returns (None, None) for utility moves
    that deal no damage at any form. Each upgrade carries its Lv5/7 form and Lv11/13 enhanced."""
    rsb = skill.get("rsb", {}) or {}
    base = extract_form(rsb, "", _num(skill.get("cd")))
    upgrades = []
    for up in skill.get("upgrades", []) or []:
        ursb = up.get("rsb", {}) or {}
        cd = _num(up.get("cd1") or up.get("cd"))
        form = extract_form(ursb, "", cd)
        enh = extract_form(ursb, "enhanced_", _num(up.get("cd2") or cd))
        upgrades.append({
            "name": up.get("name"),
            "min_level": int(_num(up.get("level1")) or 4),
            "enh_level": int(_num(up.get("level2")) or 11),
            "cooldown": cd,
            "components": form["components"], "execute": form["execute"],
            "enhanced": enh if (enh["components"] or enh["execute"]) else None,
        })
    has_dmg = base["components"] or any(u["components"] for u in upgrades)
    return (base, upgrades) if has_dmg else (None, None)


def is_unite(skill):
    """Whether a skill is the Pokemon's Unite move (flagged so it can be excluded by default)."""
    blob = (str(skill.get("ability", "")) + str(skill.get("type", ""))).lower()
    return "unite" in blob


def build():
    """Parse the cached unite-db pokemon.json into our moves.json schema for all Pokemon
    (basic + every damaging move slot with base/upgrade/enhanced forms). Returns the dict."""
    src = json.load(open(os.path.join(DATA, "unite_db_pokemon.json"), encoding="utf-8"))
    out = {"_meta": {
        "source": "unite-db.com/pokemon.json (Mathcord-sourced; the data its site uses)",
        "validated": "Pikachu Thunder Shock matches the reference engine; move totals cross-checked vs Game8",
        "formula": "component dmg = (base + slider*(level-1) + ratio*stat) * hits, then *600/(600+def[-pen])",
        "coverage": "passive + basic + base moves + Lv5/7 upgrades (+ enhanced Lv11/13 forms) + Unite move",
    }}
    for p in src:
        pk = key(p.get("name", ""))
        if not pk:
            continue
        tags = p.get("tags") if isinstance(p.get("tags"), dict) else {}
        entry = {"display_name": p.get("name"), "role": tags.get("role"),
                 "damage_type": p.get("damage_type"), "basic": None, "moves": {}}
        for s in p.get("skills", []):
            name = s.get("name", "")
            if name.lower() == "attack":
                base, _ = move_slot(s)
                if base and base["components"]:
                    c = base["components"][0]
                    entry["basic"] = {"dmg_type": c["dmg_type"], "ratio": c["ratio"]}
                continue
            base, upgrades = move_slot(s)
            if base is None:
                continue
            entry["moves"][key(name)] = {
                "display_name": name, "is_unite": is_unite(s),
                "base": base, "upgrades": upgrades,
            }
        out[pk] = entry
    return out


if __name__ == "__main__":
    data = build()
    json.dump(data, open(os.path.join(DATA, "moves.json"), "w", encoding="utf-8"), indent=1)
    mons = [k for k in data if not k.startswith("_")]
    print(f"wrote moves.json: {len(mons)} pokemon")

    def fmt(form):
        cs = ", ".join(f"{c['ratio']:.2f}*{c['dmg_type']}+{c['base']:.0f}+{c['slider']:.0f}/lv"
                       + (f" x{c['hits']}" if c['hits'] > 1 else "") for c in form["components"])
        ex = "".join(f" +exec {e['pct']*100:.0f}%{e['of'][:4]}" for e in form["execute"])
        return f"[{cs}]{ex}"

    for k in ("pikachu", "cinderace", "buzzwole"):
        e = data[k]
        print(f"\n{e['display_name']} ({e['role']}/{e['damage_type']}) basic={e['basic']}")
        for mk, mv in e["moves"].items():
            tag = " (UNITE)" if mv["is_unite"] else ""
            print(f"  {mv['display_name']}{tag}  base={fmt(mv['base'])}")
            for u in mv["upgrades"]:
                enh = f"  enh@{u['enh_level']}={fmt(u['enhanced'])}" if u["enhanced"] else ""
                print(f"     +Lv{u['min_level']} {u['name']}: {fmt(u)}{enh}")
