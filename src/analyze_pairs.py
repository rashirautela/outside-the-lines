"""Step 2 (runs on the GB10 model): three LLM jobs.

  1. VISION   - compare each before/after pair -> structured flood verdict + resident summary
  2. TRANSLATE - Spanish version of every summary
  3. BRIEF    - neighbourhood-level briefing written from all verdicts (EN + ES)

Resumable: results are saved after every pair, so a rerun skips finished pairs.
Run from JupyterLab (it must reach the GB10):  %run src/analyze_pairs.py
Options: --limit 5 (quick test)   --redo (ignore saved results)   --skip-briefings
"""
import argparse
import base64
import io
import json
import re
import sys
import time
from collections import defaultdict

from openai import OpenAI
from PIL import Image

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))  # allow %run from any folder

from config import AI_JSON, BRIEFINGS_JSON, FLOOD_DATA, SITES_JSON, load_env

ALLOWED = {
    "flood_visible": {"yes", "no", "uncertain"},
    "severity": {"none", "minor", "moderate", "severe"},
    "roads_flooded": {"yes", "no", "uncertain"},
    "buildings_surrounded": {"yes", "no", "uncertain"},
    "confidence": {"low", "medium", "high"},
}

VISION_PROMPT = """You are helping residents understand Hurricane Harvey flood imagery.
IMAGE 1 is a normal-conditions aerial photo from {before_date} ({before_source}).
IMAGE 2 is the SAME location photographed on {after_date} ({after_source}) during the Harvey flood response.
The two photos come from different cameras and seasons, so colour and vegetation differences alone are NOT flooding.
Rivers, ponds and channels that appear in BOTH images are normal water, NOT flooding.
Flooding means water (often brown/muddy) in image 2 covering land, roads, yards, fields or parking lots that are dry in image 1.

Return ONLY a JSON object with exactly these keys:
{{
  "flood_visible": "yes" | "no" | "uncertain",
  "severity": "none" | "minor" | "moderate" | "severe",
  "roads_flooded": "yes" | "no" | "uncertain",
  "buildings_surrounded": "yes" | "no" | "uncertain",
  "confidence": "low" | "medium" | "high",
  "evidence": "one sentence naming the specific visible evidence",
  "summary_en": "two short sentences for a resident, plain everyday language, no jargon",
  "uncertainty_en": "one sentence on what cannot be determined from these images"
}}"""

TRANSLATE_PROMPT = """Translate these two texts into clear, friendly Spanish for Houston residents.
Keep the meaning exact; do not add information. Return ONLY JSON:
{{"summary_es": "...", "uncertainty_es": "..."}}

summary_en: {summary}
uncertainty_en: {uncertainty}"""

BRIEF_PROMPT = """You are writing a short public briefing about one Houston-area neighbourhood after Hurricane Harvey.
Below are AI image assessments of {n} aerial before/after sites there, plus local facts.
Write 3 sentences in plain language: what the imagery suggests happened, who may have been most affected
(use the county facts), and one honest caveat that these are AI assessments of sampled images, not a full survey.
Do not invent numbers beyond those given. Then translate the briefing to Spanish.
Return ONLY JSON: {{"briefing_en": "...", "briefing_es": "..."}}

Neighbourhood: {locality}
Sites assessed: {n}; flooding visible at {flooded} ({pct}%); flooded roads at {roads}; buildings surrounded at {bldg};
flooded sites outside FEMA high-risk zones: {outside}.
County: {county}; poverty {poverty}%; households without a vehicle {novehicle}%; residents with a disability {disability}%.
Site notes:
{notes}"""


def encode(path, side=768):
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((side, side), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def parse_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError(f"No JSON in model reply: {text[:200]!r}")
    return json.loads(match.group(0))


class GB10:
    def __init__(self):
        base_url, self.model, api_key = load_env()
        self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=180, max_retries=2)

    def ask(self, content, max_tokens=500):
        for attempt in range(3):
            resp = self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                max_tokens=max_tokens,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                messages=[{"role": "user", "content": content}],
            )
            try:
                return parse_json(resp.choices[0].message.content)
            except (ValueError, json.JSONDecodeError) as exc:
                if attempt == 2:
                    raise
                print(f"    retrying (bad JSON: {exc})")


def assess_pair(gb10, site):
    prompt = VISION_PROMPT.format(before_date=site["before"]["date"], before_source=site["before"]["source"],
                                  after_date=site["after"]["date"], after_source=site["after"]["source"])
    verdict = gb10.ask([
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": encode(FLOOD_DATA / site["before"]["path"])}},
        {"type": "image_url", "image_url": {"url": encode(FLOOD_DATA / site["after"]["path"])}},
    ])
    for key, allowed in ALLOWED.items():
        value = str(verdict.get(key, "")).strip().lower()
        verdict[key] = value if value in allowed else "uncertain" if "uncertain" in allowed else "low"
    if verdict["flood_visible"] == "no":
        verdict["severity"] = "none"
    spanish = gb10.ask(TRANSLATE_PROMPT.format(summary=verdict.get("summary_en", ""),
                                               uncertainty=verdict.get("uncertainty_en", "")), max_tokens=400)
    verdict["summary_es"] = spanish.get("summary_es", "")
    verdict["uncertainty_es"] = spanish.get("uncertainty_es", "")
    return verdict


def write_briefings(gb10, sites, results):
    groups = defaultdict(list)
    for s in sites:
        if s["id"] in results:
            groups[s["locality"]].append(s)
    briefings = {}
    for locality, group in groups.items():
        rs = [results[s["id"]] for s in group]
        flooded = sum(r["flood_visible"] == "yes" for r in rs)
        outside = sum(r["flood_visible"] == "yes" and s["fema"]["high_risk"] is False for s, r in zip(group, rs))
        c = group[0]["county"]
        notes = "\n".join(f"- {r['flood_visible']}/{r['severity']}: {r.get('evidence', '')}" for r in rs)
        print(f"  briefing: {locality}")
        briefings[locality] = gb10.ask(BRIEF_PROMPT.format(
            locality=locality, n=len(rs), flooded=flooded, pct=round(100 * flooded / len(rs)),
            roads=sum(r["roads_flooded"] == "yes" for r in rs),
            bldg=sum(r["buildings_surrounded"] == "yes" for r in rs), outside=outside,
            county=c["name"], poverty=c["poverty_pct"], novehicle=c["no_vehicle_pct"],
            disability=c["disability_pct"], notes=notes), max_tokens=700)
    BRIEFINGS_JSON.write_text(json.dumps(briefings, indent=1, ensure_ascii=False))
    print(f"Wrote {BRIEFINGS_JSON}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--skip-briefings", action="store_true")
    args = ap.parse_args(argv)

    sites = json.loads(SITES_JSON.read_text())
    results = {} if args.redo or not AI_JSON.exists() else json.loads(AI_JSON.read_text())
    todo = [s for s in sites if s["id"] not in results][: args.limit]
    gb10 = GB10()
    print(f"{len(results)} done already, {len(todo)} to assess with {gb10.model}")

    for i, site in enumerate(todo, 1):
        t0 = time.time()
        try:
            results[site["id"]] = assess_pair(gb10, site)
        except Exception as exc:
            print(f"[{i}/{len(todo)}] {site['id']} FAILED: {exc}")
            continue
        AI_JSON.write_text(json.dumps(results, indent=1, ensure_ascii=False))
        r = results[site["id"]]
        print(f"[{i}/{len(todo)}] {site['id']:<18} flood={r['flood_visible']:<9} severity={r['severity']:<8} "
              f"({time.time() - t0:.0f}s)")

    if not args.skip_briefings and results:
        write_briefings(gb10, sites, results)

    from build_web import build
    build()


if __name__ == "__main__":
    main(sys.argv[1:])
