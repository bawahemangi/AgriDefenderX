"""
This module is the seam between the Django app and the ml/ package.
Given a freshly-created DiseaseReport (image + farm already saved), it:

    1. Runs the image classifier (ml/disease_classifier)
    2. Fetches/reuses today's weather for the farm (reports/weather.py)
    3. Counts nearby recent confirmed cases (reports/geo.py) and pest
       trap activity (reports/models.PestReport) for this farm
    4. Runs the risk model (ml/risk_model) on the combined feature set
    5. Generates a grounded advisory via RAG (ml/advisory_rag)
    6. Sets the report's status: auto-advisory, or flagged for expert
       review if confidence is low or risk is high

This keeps all the "combine weather + crop stage + pest history + image
confidence into one actionable alert" logic the problem statement asks
for in one auditable place.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from django.db.models import Sum
from django.utils import timezone

from .geo import count_nearby_confirmed_cases
from .models import DiseaseReport, PestReport
from .weather import get_or_fetch_weather

# ml/ lives as a sibling of the Django project root, not inside any app --
# make its subpackages importable.
BASE_DIR = Path(__file__).resolve().parent.parent
for sub in ("disease_classifier", "risk_model", "advisory_rag"):
    path = str(BASE_DIR / "ml" / sub)
    if path not in sys.path:
        sys.path.insert(0, path)


def _recent_pest_count(farm, days: int = 7) -> int:
    since = timezone.now() - dt.timedelta(days=days)
    total = PestReport.objects.filter(farm=farm, reported_at__gte=since).aggregate(total=Sum("trap_count"))["total"]
    return total or 0


def process_disease_report(report: DiseaseReport) -> DiseaseReport:
    # -- 1. Image classification --
    import infer as classifier_infer  # ml/disease_classifier/infer.py

    result = classifier_infer.classify_image(report.image.path)
    report.predicted_class = result["predicted_class"]
    report.crop_detected = result["crop"]
    report.disease_detected = result["disease"]
    report.confidence = result["confidence"]
    report.classifier_mode = result["mode"]

    # -- 2. Weather --
    weather = get_or_fetch_weather(report.farm)
    report.weather_snapshot = weather

    # -- 3. Contextual features --
    crop_cycle = report.crop_cycle
    growth_stage_code = crop_cycle.growth_stage_code if crop_cycle else 0
    days_since_sowing = crop_cycle.days_since_sowing if crop_cycle else 30
    nearby_cases = count_nearby_confirmed_cases(report.latitude, report.longitude)
    pest_count = _recent_pest_count(report.farm)
    is_healthy_prediction = "healthy" in result["predicted_class"].lower()

    # -- 4. Risk scoring --
    import predict as risk_predict  # ml/risk_model/predict.py

    risk = risk_predict.predict_risk({
        "temperature_c": weather.temperature_c,
        "humidity_pct": weather.humidity_pct,
        "rainfall_mm_7d": weather.rainfall_mm_7d,
        "wind_kmh": weather.wind_kmh,
        "days_since_sowing": days_since_sowing,
        "growth_stage_code": growth_stage_code,
        "pest_trap_count_7d": pest_count,
        "nearby_confirmed_cases_14d": nearby_cases,
        "image_model_confidence": result["confidence"],
        "image_model_flagged_disease": 0 if is_healthy_prediction else 1,
    })
    report.risk_score = risk["risk_score"]
    report.risk_band = risk["risk_band"]

    # -- 5. Advisory (RAG) --
    import generate as advisory_generate  # ml/advisory_rag/generate.py

    language = report.farmer.profile.preferred_language if hasattr(report.farmer, "profile") else "en"
    advisory = advisory_generate.generate_advisory(
        crop=result["crop"],
        disease=result["disease"],
        growth_stage=crop_cycle.growth_stage if crop_cycle else "",
        risk_band=risk["risk_band"],
        language=language,
        low_confidence=report.is_low_confidence,
    )
    report.advisory_text = advisory.text
    report.advisory_language = advisory.language
    report.advisory_sources = advisory.sources
    report.advisory_mode = advisory.generation_mode

    # -- 6. Routing --
    if report.is_low_confidence or report.risk_band == "HIGH":
        report.status = DiseaseReport.Status.FLAGGED_FOR_REVIEW
    else:
        report.status = DiseaseReport.Status.ADVISORY_SENT

    report.save()
    return report
