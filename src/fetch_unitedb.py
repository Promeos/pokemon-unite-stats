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
    """Download unite-db's raw /<name>.json (e.g. 'pokemon', 'stats', 'emblems'), cache it to
    data/unite_db_<name>.json, and return the parsed object."""
    url = f"{BASE}/{name}.json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research; pokemon-unite-stats)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
    out = os.path.join(DATA_DIR, f"unite_db_{name}.json")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(raw)
    return json.loads(raw)


if __name__ == "__main__":
    # Cache the three raw unite-db datasets the rest of the pipeline derives from.
    for name in ("pokemon", "stats", "emblems"):
        d = fetch_json(name)
        print(f"cached data/unite_db_{name}.json  ({len(d)} entries)")
