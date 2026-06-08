"""Parse unite-db's cached pokemon.json into a clean per-Pokemon move dataset.

unite-db stores each move's damage as {ratio, base, slider, dmg_type} (+ add1..add4
for multi-component hits). VALIDATED against the reference engine: Pikachu Thunder
Shock ratio=75/slider=21/base=390 == 0.75*SpAtk + 21*(Lv-1) + 390 exactly.

Output schema (data/moves.json):
  "<key>": {
    "display_name": "Cinderace",
    "basic": {"dmg_type": "Atk", "ratio": 1.0},
    "moves": {
      "<move_key>": {"display_name","level","cooldown","is_unite",
                     "components":[{"ratio":frac,"base":x,"slider":per_level,"dmg_type":"Atk|SpAtk"}]}
    }
  }
Note: unite-db lists passive + basic + the 2 BASE moves + the Unite move (the pre-evo
kit). The Lv5/7 upgrade moves are not in this static endpoint.
"""
import json
import os
import re

DATA = os.path.join(os.path.dirname(__file__), os.pardir, "data")


def key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def damage_components(rsb: dict) -> list:
    out = []

    def add(ratio, base, slider, dt, label):
        if (ratio not in ("", None) or base not in ("", None)) and dt in ("Atk", "SpAtk"):
            c = {"ratio": _num(ratio) / 100.0, "base": _num(base), "slider": _num(slider), "dmg_type": dt}
            if c["ratio"] or c["base"]:
                c["label"] = label or "Damage"
                out.append(c)

    add(rsb.get("ratio"), rsb.get("base"), rsb.get("slider"), rsb.get("dmg_type"), rsb.get("label"))
    for n in ("add1", "add2", "add3", "add4"):
        add(rsb.get(f"{n}_ratio"), rsb.get(f"{n}_base"), rsb.get(f"{n}_slider"),
            rsb.get(f"{n}_dmg_type"), rsb.get(f"{n}_label"))
    return out


def build() -> dict:
    src = json.load(open(os.path.join(DATA, "unite_db_pokemon.json"), encoding="utf-8"))
    out = {
        "_meta": {
            "source": "unite-db.com/pokemon.json (Mathcord-sourced; the data its site uses)",
            "validated": "Pikachu Thunder Shock 0.75*SpAtk + 21*(Lv-1) + 390 matches reference engine exactly",
            "formula": "component damage = base + slider*(level-1) + ratio*stat[dmg_type], then *600/(600+def)",
            "coverage": "passive + basic + 2 base moves + Unite move per mon (the pre-evo kit); not Lv5/7 upgrades",
        }
    }
    for p in src:
        pk = key(p.get("name", ""))
        if not pk:
            continue
        tags = p.get("tags")
        role = tags[0] if isinstance(tags, list) and tags else None
        entry = {"display_name": p.get("name"), "role": role,
                 "damage_type": p.get("damage_type"), "basic": None, "moves": {}}
        for s in p.get("skills", []):
            comps = damage_components(s.get("rsb", {}) or {})
            if not comps:
                continue
            nm = s.get("name", "")
            if nm.lower() == "attack":
                entry["basic"] = {"dmg_type": comps[0]["dmg_type"], "ratio": comps[0]["ratio"]}
            else:
                entry["moves"][key(nm)] = {
                    "display_name": nm,
                    "level": s.get("level", ""),
                    "cooldown": s.get("cooldown", ""),
                    "is_unite": str(s.get("level", "")) == "9" or s.get("ability") == "Unite Move",
                    "components": comps,
                }
        out[pk] = entry
    return out


if __name__ == "__main__":
    data = build()
    path = os.path.join(DATA, "moves.json")
    json.dump(data, open(path, "w", encoding="utf-8"), indent=1)
    mons = [k for k in data if not k.startswith("_")]
    print(f"wrote {path}: {len(mons)} pokemon")
    for k in ("cinderace", "zeraora", "pikachu", "buzzwole"):
        e = data.get(k)
        if e:
            print(f"\n{e['display_name']}  basic={e['basic']}")
            for mk, mv in e["moves"].items():
                comp = ", ".join(f"{c['ratio']:.2f}*{c['dmg_type']}+{c['base']:.0f}+{c['slider']:.0f}/lv" for c in mv["components"])
                print(f"  {mv['display_name']:24} [{comp}]")
