"""Step 3: merge sites + AI results + briefings into docs/data.js for the web page.

Run:  python src/build_web.py   (analyze_pairs.py also calls this automatically)
"""
import json
from datetime import date

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))  # allow %run from any folder

from config import AI_JSON, BRIEFINGS_JSON, DOCS_DIR, SITES_JSON


def build():
    sites = json.loads(SITES_JSON.read_text())
    ai = json.loads(AI_JSON.read_text()) if AI_JSON.exists() else {}
    briefings = json.loads(BRIEFINGS_JSON.read_text()) if BRIEFINGS_JSON.exists() else {}
    for s in sites:
        s["before"].pop("path", None)
        s["after"].pop("path", None)
        s["ai"] = ai.get(s["id"])
    payload = {"generated": str(date.today()), "sites": sites, "briefings": briefings}
    out = DOCS_DIR / "data.js"
    out.write_text("window.FLOOD_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n")
    print(f"Wrote {out}: {len(sites)} sites, {len(ai)} with AI results, {len(briefings)} briefings")


if __name__ == "__main__":
    build()
