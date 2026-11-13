"""Step 1: choose before/after pairs, export web images, attach FEMA/Census/OSM facts
and daily NOAA rainfall. Writes data/sites.json and docs/img/*.jpg.

Run:  python src/build_sites.py            (default 60 sites)
      python src/build_sites.py --n 120
"""
import argparse
import json
import math
from io import StringIO
from urllib.request import urlopen

import pandas as pd
from PIL import Image

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))  # allow %run from any folder

from config import DATA_DIR, FLOOD_DATA, IMG_DIR, SITES_JSON

# Share of sites per neighbourhood (roughly proportional, with a floor so small areas appear).
QUOTA = {
    "West Houston / Addicks and Barker": 0.22,
    "Richmond / Rosenberg / Brazos": 0.20,
    "Forest Cove / Kingwood": 0.16,
    "Bevil Oaks / Pine Island Bayou": 0.10,
    "Simonton / Brazos": 0.10,
    "Bear Creek / west Houston": 0.08,
    "Eldridge / northwest Houston": 0.07,
    "Kingwood / northeast Houston": 0.07,
}
RAIN_DAYS = 14
WEB_SIDE = 720


def num(value):
    try:
        f = float(value)
        return None if math.isnan(f) else round(f, 2)
    except (TypeError, ValueError):
        return None


def choose_pairs(meta, n):
    resp = meta[(meta.image_view_type == "response") & (meta.paired_image_id != "")]
    populated = pd.to_numeric(resp.osm_building_count, errors="coerce").fillna(0) >= 10
    picked = []
    for locality, share in QUOTA.items():
        full = resp[resp.locality == locality]
        k = min(len(full), max(3, round(n * share)))
        # Prefer places where people live; rural areas (no mapped buildings) still get included.
        pool = full[populated[full.index]]
        if len(pool) < k:
            pool = full
        # Balance FEMA high-risk (T) and not high-risk (F) so the comparison is meaningful.
        hi, lo = pool[pool.fema_sfha_tf == "T"], pool[pool.fema_sfha_tf != "T"]
        take_hi = min(len(hi), k // 2)
        part = pd.concat([hi.sample(take_hi, random_state=7),
                          lo.sample(min(len(lo), k - take_hi), random_state=7)])
        picked.append(part)
    return pd.concat(picked)


def export_image(src_rel, dest_name):
    dest = IMG_DIR / dest_name
    if not dest.exists():
        with Image.open(FLOOD_DATA / src_rel) as im:
            im = im.convert("RGB")
            im.thumbnail((WEB_SIDE, WEB_SIDE), Image.LANCZOS)
            im.save(dest, "JPEG", quality=78, optimize=True)
    return f"img/{dest_name}"


_rain_cache = {}


def fetch_rain(station, end_date):
    """Daily precipitation (mm) for RAIN_DAYS days strictly before end_date, from NOAA GHCN-Daily."""
    if not station:
        return []
    end = pd.Timestamp(end_date)
    days = pd.date_range(end=end - pd.Timedelta(days=1), periods=RAIN_DAYS)
    key = (station, str(end.date()))
    if key not in _rain_cache:
        url = ("https://www.ncei.noaa.gov/access/services/data/v1?dataset=daily-summaries"
               f"&stations={station}&startDate={days.min().date()}&endDate={days.max().date()}"
               "&dataTypes=PRCP&format=csv&units=metric&includeAttributes=true")
        try:
            text = urlopen(url, timeout=60).read().decode()
            df = pd.read_csv(StringIO(text), dtype=str, keep_default_na=False)
        except Exception as exc:  # network hiccup: keep going without rain for this station
            print(f"  rainfall fetch failed for {station}: {exc}")
            df = pd.DataFrame()
        values = {}
        if "PRCP" in df.columns:
            for _, r in df.iterrows():
                flags = (r.get("PRCP_ATTRIBUTES", "") + ",,").split(",")
                if flags[1] == "" and flags[0] not in ("P", "I"):  # drop failed-QC / presumed zeros
                    values[r["DATE"][:10]] = num(r["PRCP"])
        _rain_cache[key] = [{"date": str(d.date()), "mm": values.get(str(d.date()))} for d in days]
    return _rain_cache[key]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    args = ap.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    meta = pd.read_csv(FLOOD_DATA / "image_metadata.csv", keep_default_na=False)
    by_id = meta.set_index("image_id")
    chosen = choose_pairs(meta, args.n)
    print(f"Selected {len(chosen)} pairs")

    sites = []
    for i, (_, after) in enumerate(chosen.iterrows(), 1):
        before = by_id.loc[after.paired_image_id]
        print(f"[{i}/{len(chosen)}] {after.pair_id} {after.locality}")
        zones = json.loads(after.fema_flood_zones) if after.fema_flood_zones.startswith("[") else []
        sites.append({
            "id": after.pair_id,
            "locality": after.locality,
            "lat": num(after.latitude),
            "lon": num(after.longitude) if num(after.longitude) is None else float(after.longitude),
            "event": after.event_name,
            "before": {"id": before.name, "date": before.acquisition_date, "source": before.source_agency,
                       "img": export_image(before.image_path, f"{after.pair_id}_before.jpg"),
                       "path": before.image_path},
            "after": {"id": after.image_id, "date": after.acquisition_date, "source": after.source_agency,
                      "img": export_image(after.image_path, f"{after.pair_id}_after.jpg"),
                      "path": after.image_path},
            "fema": {"high_risk": {"T": True, "F": False}.get(after.fema_sfha_tf),
                     "zones": zones},
            "osm": {"buildings": num(after.osm_building_count), "roads": num(after.osm_road_or_path_count)},
            "county": {"name": after.county_name,
                       "poverty_pct": num(after.county_poverty_percent),
                       "no_vehicle_pct": num(after.county_no_vehicle_households_percent),
                       "disability_pct": num(after.county_disability_percent),
                       "age65_pct": num(after.county_age65plus_percent),
                       "population": num(after.county_population)},
            "rain": {"station": after.precipitation_station_name,
                     "station_km": num(after.precipitation_station_distance_km),
                     "total_7d_mm": num(after.preceding_7d_precipitation_mm),
                     "daily": fetch_rain(after.precipitation_station_id, after.acquisition_date)},
        })
    # lat/lon: keep full precision for the map
    for s, (_, after) in zip(sites, chosen.iterrows()):
        s["lat"], s["lon"] = float(after.latitude), float(after.longitude)
    SITES_JSON.write_text(json.dumps(sites, indent=1))
    print(f"Wrote {SITES_JSON} and {len(sites) * 2} images to {IMG_DIR}")


if __name__ == "__main__":
    main()
