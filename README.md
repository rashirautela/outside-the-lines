# Outside the Lines: Hurricane Harvey Flood Explorer

**An interactive map that shows what Hurricane Harvey did to Houston-area neighbourhoods and where it flooded places FEMA rated as lower risk. A vision-language model running locally on a Dell Pro Max GB10 explains each before/after photo.**

Built for the UTSA Social Impact AI Datathon.

<!-- Add a screenshot: docs/screenshot.png -->

## The problem

During Harvey (August 2017), rain gauges near our sites recorded up to **979 mm (38.5 in) in the 14 days before the photos**, and up to 390 mm (15.4 in) in a single day (NOAA GHCN-Daily). Many flooded homes sat **outside FEMA's high-risk flood zones**. People there are not required to buy flood insurance, so many had none. Aerial photos of the flooding exist, but residents, volunteers and local officials can't easily read them.

## What it does

- **Swipe before/after:** the same spot in 2016 (USDA) and on Aug 30, 2017 during the flood (NOAA).
- **The AI explains what changed:** a plain-language summary, the visible evidence, and an honest note on what can't be told from the photo.
- **"Outside the Lines" flag:** marks sites where the AI sees flooding even though FEMA maps them as lower risk.
- **Who was affected:** county poverty, no-vehicle and disability rates (U.S. Census ACS).
- **Rainfall context:** daily rain for the 14 days before each photo from the nearest NOAA gauge.
- **English / Español:** the whole interface and every AI summary.
- **Neighbourhood briefings:** the model writes a short public summary for each area from all its site assessments.

## How the GB10 model is used (Qwen3-VL-8B-Instruct, served locally)

The model does three different jobs, all on the GB10, with no cloud API:

1. **Vision comparison:** reads both photos of a pair and returns a structured JSON verdict: flooding visible, severity, roads flooded, buildings surrounded, confidence, evidence, a summary for residents, and an uncertainty note. The prompt tells it to ignore season and camera differences and normal rivers and ponds.
2. **Translation:** turns each summary into Spanish for Houston's large Spanish-speaking population.
3. **Synthesis:** combines every verdict in a neighbourhood with local facts into a briefing in English and Spanish.

## Data (5 sources combined)

| Source | Used for |
|---|---|
| [UTSA flood images](https://huggingface.co/datasets/jennifer-fowler/UTSA-flood-images) (USDA NAIP 2016 / NOAA 2017) | before/after aerial pairs |
| FEMA National Flood Hazard Layer (in dataset metadata) | high-risk vs lower-risk flood zone |
| U.S. Census ACS (in dataset metadata) | county poverty, no-vehicle, disability |
| OpenStreetMap (in dataset metadata) | building and road counts |
| [NOAA GHCN-Daily](https://www.ncei.noaa.gov/products/land-based-station/global-historical-climatology-network-daily) (fetched live) | daily rainfall before each photo |

56 sites are sampled across 8 neighbourhoods, balanced between FEMA high-risk and lower-risk zones.

## Run it

```bash
conda activate gb10
pip install -r requirements.txt
cp .env.example .env            # add your GB10 URL, model and key
```

Download the dataset into `../Texas_Flood_Student_Data`, or set `FLOOD_DATA_DIR`.

1. `python src/build_sites.py` picks the pairs, exports web images and fetches NOAA rain (already done; outputs are committed).
2. Run **`run_analysis.ipynb`** in JupyterLab, or `python src/analyze_pairs.py`. This calls the GB10. It is resumable, so you can stop and rerun.
3. Open **`docs/index.html`** in a browser. No server is needed. It also works on GitHub Pages: set the source to `/docs`.

```
src/build_sites.py     choose pairs, resize images, attach FEMA/Census/OSM facts, fetch NOAA rainfall
src/analyze_pairs.py   GB10: vision verdicts, Spanish translation, neighbourhood briefings
src/build_web.py       merges everything into docs/data.js
docs/index.html        the explorer (Leaflet + Chart.js, single file)
```

## Results and spot-check

- The AI found visible flooding at **51 of 56 sites**. **21 of those 51 are outside FEMA high-risk zones**, and 6 have no FEMA zone on record.
- The sites come from Harvey flood-response imagery, so a high flood rate is expected.
- We compared 16 sites by eye against the AI's flooded / not-flooded verdict:
  - All 5 "not flooded" sites look dry.
  - All 5 high-risk flooded sites look clearly flooded.
  - 4 of 6 "Outside the Lines" sites look clearly flooded. The other 2 are borderline: one shows a flooded field next to homes that look dry.
- The model's **severity** ratings run high (45 of 56 rated "severe"), and its self-reported confidence was always "high". The interface therefore shows severity as a colour cue only and does not display confidence.

## Limitations

- AI assessments can be wrong. Treat them as a first pass for human review, not an official damage survey.
- Before and after photos differ in season and camera, and the model can confuse shadows, wet fields or turbid ponds with floodwater.
- FEMA zones and OSM counts are current snapshots, not 2017 values. County statistics are county-wide averages.
- 56 sampled sites are not a full census of the flood.
