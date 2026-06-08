"""Fetch unite-db's raw gamemaster JSON — the Mathcord-sourced data the site uses.

unite-db.com serves raw JSON at /<name>.json (the same data its JS frontend loads).
pokemon.json carries per-move damage scaling as:
    {"label":"Damage","ratio":"89","dmg_type":"Atk","slider":"6","base":"200"}
where ratio is a PERCENT of the stat (89 => 0.89x), base is flat, slider is per-level.
This is the missing piece Game8/PvPoke lacked. We cache it to data/ for reproducibility.
"""
import json
import os
import urllib.request

BASE = "https://unite-db.com"
DATA_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "data")


def fetch_json(name: str) -> object:
    url = f"{BASE}/{name}.json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research; pokemon-unite-stats)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
    out = os.path.join(DATA_DIR, f"unite_db_{name}.json")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(raw)
    return json.loads(raw)


if __name__ == "__main__":
    data = fetch_json("pokemon")
    items = list(data.values()) if isinstance(data, dict) else list(data)
    print("top-level:", type(data).__name__, "count:", len(items))
    sample = items[0]
    print("sample keys:", list(sample.keys()))

    def name_of(p):
        for k in ("name", "display_name", "pokemon", "id", "pokemonId"):
            if k in p:
                return str(p[k]).lower()
        return ""

    for p in items:
        if "pikachu" in name_of(p):
            print("\n=== PIKACHU keys:", list(p.keys()))
            for k in ("moves", "skills", "move", "skill"):
                if k in p:
                    print(f"\n--- '{k}' (truncated) ---")
                    print(json.dumps(p[k], indent=1)[:2000])
            break
