# Crop Health System — SIH Problem Statement 26131

Early detection and management of crop diseases and pest infestations, for
the Government of Maharashtra / Maharashtra State Innovation Society.

A farmer uploads a photo of a symptomatic leaf → an image classifier
identifies the likely disease/pest → that's combined with live weather,
crop growth stage, pest-trap history, and nearby confirmed cases into a
risk score → a retrieval-grounded advisory (never an LLM improvising
treatment advice) is generated and shown to the farmer, translated to
their language → low-confidence or high-risk cases are auto-flagged for
an expert/extension officer to confirm or correct → those corrections
become training data for the next model iteration → officials see
everything on a live hotspot map and dashboard.

**This ships pre-seeded with 55 demo reports already run through the real
pipeline, so the dashboard and map are populated the moment you start it.**

---

## Quick start (5 minutes)

```bash
python3 -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt

python manage.py runserver
```

Then open:

| URL | What it is | Login |
|---|---|---|
| `http://localhost:8000/farmer/upload/` | Farmer "scan crop" flow | `farmer1` / `demo1234` |
| `http://localhost:8000/dashboard/` | Officer dashboard + hotspot map | `officer1` / `demo1234` |
| `http://localhost:8000/admin/` | Expert review workflow | `expert1` / `demo1234` (or officer1) |
| `http://localhost:8000/api/` | REST API (for a future mobile app) | any of the above |

The repo ships with `db.sqlite3` and `media/` already populated by
`seed_demo_data` (see below), so these all work immediately with zero
setup. To start fresh:

```bash
rm db.sqlite3 && rm -rf media
python manage.py migrate
python manage.py seed_demo_data --reports 60
python manage.py createsuperuser   # optional, for your own admin login
```

---

## Architecture

```
Farmer photo ─┐
              ▼
   ml/disease_classifier  (CNN → disease + confidence)
              │
              ▼
   reports/weather.py  (OpenWeatherMap, or seasonal-synthetic fallback)
              │
              ▼
   reports/geo.py  (nearby confirmed cases, pest-trap history)
              │
              ▼
   ml/risk_model  (XGBoost → risk score: LOW / MEDIUM / HIGH)
              │
              ▼
   ml/advisory_rag  (retrieval-grounded IPM advisory, translated)
              │
              ▼
   reports/services.py process_disease_report()  ── orchestrates all of the above
              │
      ┌───────┴────────┐
      ▼                ▼
 Farmer sees        Flagged for
 advisory            expert review
 (low risk)          (low confidence
                      or high risk)
                          │
                          ▼
                 Django admin: confirm / correct / reject
                 (reports.ExpertReview)
                          │
                          ▼
          manage.py export_training_data
                          │
                          ▼
          ml/disease_classifier/train.py  (retrain on real confirmed labels)
                          │
                          └──────────► loop closes, model improves over time
```

Meanwhile every processed report also feeds the **hotspot map** and
**officer dashboard** (`dashboard/`), filterable by district, crop,
disease, and risk level.

---

## Project layout

```
config/                Django settings, root urls
accounts/               User roles: farmer / expert / officer
farms/                  Farm and CropCycle models
reports/                 The core app: DiseaseReport, PestReport, WeatherSnapshot,
                          ExpertReview, the orchestration service, admin (= expert
                          review UI), REST API, farmer-facing views
dashboard/               Officer dashboard: stats, hotspot map, charts
templates/               Farmer-facing HTML (base layout, upload, report detail)
ml/
  disease_classifier/    CNN architecture + training script (model.py, train.py),
                          38-class PlantVillage label set (labels.json), and a
                          feature-based DEMO fallback classifier so the app runs
                          without a trained checkpoint (features.py,
                          train_demo_model.py, infer.py)
  risk_model/             XGBoost risk model: train_risk_model.py (trains on
                          synthetic-but-realistic data), predict.py
  advisory_rag/           Knowledge base (13 markdown docs on real IPM practice),
                          TF-IDF retriever, grounded generator (generate.py)
```

---

## What's real vs. what's a placeholder (read this before a demo or a judge Q&A)

Being upfront about this is more credible than pretending everything is
production-grade — and it tells you exactly what to build next if you
keep going after the hackathon.

### Fully real and tested
- **Django backend, models, admin, API, and orchestration** — this is
  production-shape code, not a mockup.
- **The RAG advisory pipeline** — the 13 knowledge base docs are genuine
  agronomic IPM guidance (deliberately without inventing precise pesticide
  dosages — that's a real safety line, not laziness); TF-IDF retrieval is
  fully offline and actually retrieves the right document; generation
  stays strictly grounded in retrieved text.
- **The risk model** — XGBoost trained on synthetic data with realistic,
  documented agronomic relationships (humidity/temperature/pest
  counts/nearby cases raising risk). It's a real, working ML model with a
  real held-out AUC (~0.69) — the *pipeline* is production-ready, only the
  *training data* is synthetic.
- **The expert-review feedback loop** — `ExpertReview` records really do
  export into a labeled training set via `export_training_data`, ready to
  retrain the classifier.

### Placeholder, clearly labeled as such in the code and UI
- **The image classifier defaults to a "demo heuristic" mode**
  (`ml/disease_classifier/features.py` + `demo_feature_model.pkl`): a
  small RandomForest over color/texture statistics, trained on synthetic
  proxy data, not real leaf photos. It's structurally sound (it will
  correctly call a green uniform photo "healthy" and a browning spotty
  photo some blight variant) but **cannot** reliably distinguish between
  diseases that look visually similar — that requires the real CNN.
  Every prediction is tagged `mode: "demo_heuristic"` in the API and shown
  with a warning badge in the farmer UI, so this is never silently passed
  off as more accurate than it is.
- **The real CNN** (`model.py`, `train.py`) is fully written and will run
  as soon as you point it at a real dataset — this sandbox had no network
  access to download the PlantVillage dataset or pretrained ImageNet
  weights, so it couldn't be trained or shipped here. See "Next steps"
  below.
- **Weather** falls back to season-representative synthetic data for
  Maharashtra if `OPENWEATHER_API_KEY` isn't set (get a free key at
  openweathermap.org).
- **Translation** (Marathi/Hindi) requires `ANTHROPIC_API_KEY` to be set;
  without it, advisories stay in English with a note explaining why.

---

## Next steps to take this from hackathon demo to real deployment

1. **Train the real classifier.** Get the PlantVillage dataset (search it
   on Kaggle), arrange it as described in `ml/disease_classifier/train.py`,
   and run:
   ```bash
   python ml/disease_classifier/train.py --data-dir ./data --arch efficientnet --epochs 15
   ```
   This produces `checkpoints/disease_classifier.pt`, which `infer.py`
   picks up automatically — no other code changes needed. For diseases/pests
   specific to Maharashtra that PlantVillage doesn't cover (e.g. local
   cotton, sugarcane, soybean pests), add your own labeled photos in the
   same folder structure and update `labels.json`.

2. **Retrain the risk model on real data.** Once you have real confirmed
   cases (via `ExpertReview`), replace `generate_synthetic_dataset()` in
   `train_risk_model.py` with a query joining confirmed reports, their
   weather snapshots, and pest history at the time.

3. **Get an OpenWeatherMap key** and set `OPENWEATHER_API_KEY` for real
   weather instead of the seasonal fallback.

4. **Set `ANTHROPIC_API_KEY`** for live Marathi/Hindi translation of
   advisories.

5. **Move to PostgreSQL** (set `POSTGRES_DB` etc. env vars — already wired
   up in `config/settings.py`) once you have real farmer/report volume
   beyond what SQLite comfortably handles.

6. **Expand the knowledge base** (`ml/advisory_rag/knowledge_base/`) with
   more crops/diseases and, ideally, get each entry reviewed by an actual
   agricultural extension expert before relying on it operationally.

---

## How this maps to the problem statement

| Problem statement ask | Where it is |
|---|---|
| Image-based symptom identification | `ml/disease_classifier/` |
| Pest-trap / sensor inputs | `reports.PestReport` (manual entry now; `pest_trap_count_7d` feeds the risk model — swap in real IoT sensor ingestion later without touching the risk model interface) |
| Weather-based risk forecasting | `reports/weather.py` + `ml/risk_model/` |
| Geospatial hotspot mapping | `dashboard/` (Leaflet map, `reports/geo.py` clustering) |
| Expert validation | Django admin `ExpertReview` inline on every report |
| Multilingual advisories | `ml/advisory_rag/generate.py` (English/Marathi/Hindi) |
| Integrated pest & disease management actions | Every knowledge base doc's "Integrated pest & disease management actions" section |
| Safe input usage | Every knowledge base doc's "Safe input use" section — deliberately generic on dosage, always defers to product label + extension officer |
| Referral to extension/lab | Auto-flagging on low confidence or high risk (`DiseaseReport.Status.FLAGGED_FOR_REVIEW`) |
| Follow-up monitoring | Every knowledge base doc's "Follow-up monitoring" section |
| Learn from field confirmations | `ExpertReview` → `export_training_data` → retrain loop |
| Dashboards for officials | `dashboard/` |

---

## A note on demo strategy

If you're presenting this at the hackathon: **lead with the real thing.**
Show the farmer upload flow end-to-end, show the dashboard and hotspot
map (both are genuinely fully functional), and show the expert-review →
retrain loop in the admin. When you get to the image classifier, be
upfront that it's running in demo/heuristic mode for this environment and
show `train.py`/`model.py` as evidence the real model is fully built and
one dataset download away from being live — judges respond far better to
"here's exactly what's real and what's next" than to a system that pretends
everything is finished.
